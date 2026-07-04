"""Import-graph boundary enforcement for the ``production_brain`` <-> ``edit_mcp``
seam (ADR 005).

ADR 004 originally claimed both top-level modules "depend on ``core/`` models
only". ADR 005 supersedes that claim: it *blesses* a one-directional layering
with a single sanctioned escape hatch, and this test is its enforcement
mechanism. The layering (bottom -> top) is::

    core  <  edit_mcp.adapters  <  edit_mcp.pipelines
          <  production_brain.{skills,notes}  <  edit_mcp.server  <  app

Two rules follow (see docs/adr/005-production-brain-boundary.md):

Rule 1 -- ``edit_mcp`` may import ``production_brain`` **only** via a
function-local (lazy) import. A module-level ``edit_mcp -> production_brain``
import would create an import-time cycle (because ``production_brain`` imports
``edit_mcp.pipelines`` at module load). The lazy imports in
``pipelines/new_project.py``, ``pipelines/publishing.py`` and the
``server/tools/*`` shells are the sanctioned orchestration escape hatch.

Rule 2 -- ``production_brain`` may import ``edit_mcp.pipelines`` / ``.adapters``
/ ``core`` (the blessed downward "planning consumes analysis" direction) but
must **never** import ``edit_mcp.server`` (the shell layer that itself imports
``production_brain``) -- at any nesting level. That would reintroduce the cycle
at the top.

The test walks module ASTs (it does not import the tree) so it is fast and has
no side effects.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

# tests/unit/<this> -> parents[2] == repo root; source lives under
# workshop-video-brain/src/workshop_video_brain (see pyproject `pythonpath`).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PKG_ROOT = _REPO_ROOT / "workshop-video-brain" / "src" / "workshop_video_brain"

_PRODUCTION_BRAIN = _PKG_ROOT / "production_brain"
_EDIT_MCP = _PKG_ROOT / "edit_mcp"

_ROOT_PKG = "workshop_video_brain"


def _iter_py_files(root: Path):
    yield from sorted(root.rglob("*.py"))


def _module_name(path: Path) -> str:
    rel = path.relative_to(_PKG_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join([_ROOT_PKG, *parts])


def _resolve_from_import(node: ast.ImportFrom, module_name: str) -> str | None:
    """Return the absolute dotted target of an ``ImportFrom`` node.

    Handles relative imports (``level`` > 0) by resolving against the importing
    module's package path.
    """
    if node.level == 0:
        return node.module
    # Relative import: climb ``level`` packages from the current module.
    pkg_parts = module_name.split(".")
    # A module's own package is its name minus the final component.
    base = pkg_parts[: len(pkg_parts) - node.level]
    if node.module:
        base = base + node.module.split(".")
    return ".".join(base) if base else None


def _collect_import_edges(root: Path):
    """Yield ``(module_name, file_path, lineno, target, is_module_level)`` for
    every ``import``/``from ... import`` statement under ``root``.

    ``is_module_level`` is False when the import is nested inside a function
    (i.e. a lazy / function-local import).
    """
    for path in _iter_py_files(root):
        module_name = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        # Map every import node to whether it is enclosed by a function def.
        lazy_nodes: set[int] = set()

        def _mark(node: ast.AST, inside_func: bool) -> None:
            for child in ast.iter_child_nodes(node):
                child_inside = inside_func or isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
                )
                if isinstance(child, (ast.Import, ast.ImportFrom)) and inside_func:
                    lazy_nodes.add(id(child))
                _mark(child, child_inside)

        _mark(tree, False)

        for node in ast.walk(tree):
            is_module_level = id(node) not in lazy_nodes
            if isinstance(node, ast.ImportFrom):
                target = _resolve_from_import(node, module_name)
                if target:
                    yield module_name, path, node.lineno, target, is_module_level
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    yield module_name, path, node.lineno, alias.name, is_module_level


def _targets(prefix: str, target: str) -> bool:
    """True if ``target`` is ``prefix`` or a submodule of it."""
    return target == prefix or target.startswith(prefix + ".")


PB = f"{_ROOT_PKG}.production_brain"
EDIT_SERVER = f"{_ROOT_PKG}.edit_mcp.server"


def test_source_roots_exist():
    assert _PRODUCTION_BRAIN.is_dir(), _PRODUCTION_BRAIN
    assert _EDIT_MCP.is_dir(), _EDIT_MCP


def test_edit_mcp_never_imports_production_brain_at_module_level():
    """Rule 1: reverse edges (edit_mcp -> production_brain) must be lazy only."""
    violations = []
    for module_name, path, lineno, target, is_module_level in _collect_import_edges(
        _EDIT_MCP
    ):
        if _targets(PB, target) and is_module_level:
            violations.append(
                f"{path.relative_to(_REPO_ROOT)}:{lineno} module-level "
                f"import of {target} (must be function-local -- ADR 005 Rule 1)"
            )
    assert not violations, (
        "edit_mcp modules must only import production_brain via function-local "
        "(lazy) imports to avoid an import-time cycle:\n  " + "\n  ".join(violations)
    )


def test_production_brain_never_imports_edit_mcp_server():
    """Rule 2: production_brain must never reach up into the server/shell layer."""
    violations = []
    for module_name, path, lineno, target, is_module_level in _collect_import_edges(
        _PRODUCTION_BRAIN
    ):
        if _targets(EDIT_SERVER, target):
            level = "module-level" if is_module_level else "lazy"
            violations.append(
                f"{path.relative_to(_REPO_ROOT)}:{lineno} {level} import of "
                f"{target} (production_brain may consume edit_mcp.pipelines/"
                f"adapters/core only -- ADR 005 Rule 2)"
            )
    assert not violations, (
        "production_brain must not import the edit_mcp.server shell layer:\n  "
        + "\n  ".join(violations)
    )


def test_production_brain_edit_mcp_edges_are_only_pipelines_or_adapters():
    """Positive characterization: every production_brain -> edit_mcp edge points
    at the pipelines/adapters/core layers (the blessed downward direction).

    Guards against a future edge sneaking into some other edit_mcp subpackage
    (e.g. ``edit_mcp.server``) that Rule 2's server-specific check would miss.
    """
    allowed_prefixes = (
        f"{_ROOT_PKG}.edit_mcp.pipelines",
        f"{_ROOT_PKG}.edit_mcp.adapters",
        f"{_ROOT_PKG}.core",
    )
    unexpected = []
    for module_name, path, lineno, target, is_module_level in _collect_import_edges(
        _PRODUCTION_BRAIN
    ):
        if _targets(f"{_ROOT_PKG}.edit_mcp", target):
            if not any(_targets(p, target) for p in allowed_prefixes):
                unexpected.append(
                    f"{path.relative_to(_REPO_ROOT)}:{lineno} imports {target}"
                )
    assert not unexpected, (
        "production_brain -> edit_mcp edges must target pipelines/adapters "
        "only:\n  " + "\n  ".join(unexpected)
    )
