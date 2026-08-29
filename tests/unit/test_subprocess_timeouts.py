"""Every blocking ``subprocess`` call in the source tree must carry ``timeout=``.

The MCP server runs ffmpeg / ffprobe / melt as child processes on the request
path. A call with no wall-clock ceiling turns any wedged child (a Store-alias
``python`` shim, an AV-scanner stall on a fresh output file, a codec that never
terminates on a truncated container) into a server that hangs forever while
the client RPC times out with no diagnosable cause. CLAUDE.md states the rule
("all ffmpeg subprocess calls ... must pass ``timeout=``"); this test is the
mechanism that keeps it true after the next drop-in bundle is added.

The vocabulary of ceilings lives next to the runner::

    adapters/ffmpeg/runner.py
        CAPABILITY_TIMEOUT_SECONDS   -- ``ffmpeg -version`` style feature probes
        ANALYSIS_TIMEOUT_SECONDS     -- one-pass reads that scale with clip length
        DEFAULT_TIMEOUT_SECONDS      -- full transcodes and renders

The test walks module ASTs (it does not import the tree) so it is fast and has
no side effects. A ``**kwargs`` splat at the call site is accepted -- the
ceiling may legitimately be forwarded by a wrapper.
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PKG_ROOT = _REPO_ROOT / "workshop-video-brain" / "src" / "workshop_video_brain"

# The blocking entry points that accept ``timeout=``. ``Popen`` is excluded:
# its ceiling is on ``communicate()`` / ``wait()``, which is a different shape
# and is not used on the request path today.
_BLOCKING_CALLS = frozenset({"run", "check_output", "check_call", "call"})


def _iter_py_files(root: Path):
    yield from sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _subprocess_aliases(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Return ``(module_aliases, bare_function_aliases)`` bound in *tree*.

    ``import subprocess as sp`` -> module alias ``sp``;
    ``from subprocess import run as _run`` -> bare alias ``_run``.
    """
    modules: set[str] = set()
    funcs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    modules.add(alias.asname or "subprocess")
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                if alias.name in _BLOCKING_CALLS:
                    funcs.add(alias.asname or alias.name)
    return modules, funcs


def _is_blocking_subprocess_call(
    node: ast.Call, modules: set[str], funcs: set[str]
) -> bool:
    fn = node.func
    if isinstance(fn, ast.Attribute):
        return (
            isinstance(fn.value, ast.Name)
            and fn.value.id in modules
            and fn.attr in _BLOCKING_CALLS
        )
    if isinstance(fn, ast.Name):
        return fn.id in funcs
    return False


def _has_timeout(node: ast.Call) -> bool:
    for kw in node.keywords:
        if kw.arg == "timeout":
            return True
        if kw.arg is None:  # ``**kwargs`` splat -- ceiling forwarded by caller
            return True
    return False


def _find_violations(root: Path) -> list[str]:
    violations: list[str] = []
    for path in _iter_py_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        modules, funcs = _subprocess_aliases(tree)
        if not modules and not funcs:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not _is_blocking_subprocess_call(node, modules, funcs):
                continue
            if not _has_timeout(node):
                rel = path.relative_to(root).as_posix()
                violations.append(f"{rel}:{node.lineno}")
    return violations


def test_every_blocking_subprocess_call_has_a_timeout():
    violations = _find_violations(_PKG_ROOT)
    assert not violations, (
        "subprocess call(s) without `timeout=` -- a wedged child process would "
        "hang the MCP server forever. Pick a ceiling from "
        "adapters/ffmpeg/runner.py (CAPABILITY_/ANALYSIS_/DEFAULT_TIMEOUT_SECONDS) "
        "and catch subprocess.TimeoutExpired where the call is best-effort:\n  "
        + "\n  ".join(f"workshop_video_brain/{v}" for v in violations)
    )


def test_detector_catches_the_shapes_it_claims_to(tmp_path: Path):
    """Self-check: the scanner must flag module-attribute, aliased-module and
    bare-imported call shapes, and accept the ``timeout=`` / splat escapes."""
    src = tmp_path / "sample.py"
    src.write_text(
        "import subprocess\n"
        "import subprocess as sp\n"
        "from subprocess import run as _run, check_output\n"
        "subprocess.run(['x'])\n"                    # 4 -- flagged
        "sp.check_call(['x'])\n"                     # 5 -- flagged
        "_run(['x'])\n"                              # 6 -- flagged
        "check_output(['x'])\n"                      # 7 -- flagged
        "subprocess.run(['x'], timeout=5)\n"         # 8 -- ok
        "subprocess.run(['x'], **opts)\n"            # 9 -- ok (splat)
        "subprocess.Popen(['x'])\n"                  # 10 -- out of scope
        "other.run(['x'])\n",                        # 11 -- not subprocess
        encoding="utf-8",
    )
    found = _find_violations(tmp_path)
    lines = sorted(int(v.rsplit(":", 1)[1]) for v in found)
    assert lines == [4, 5, 6, 7], found
