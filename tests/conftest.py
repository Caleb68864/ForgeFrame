"""Root pytest configuration and shared gating fixtures.

Canonical home for the ffmpeg/ffprobe/melt availability gates that were spelled
half a dozen different ways across the integration suite. Two equivalent styles
are offered so migrations stay mechanical:

* Module-level marks -- assign one to ``pytestmark``::

      from tests.conftest import requires_ffmpeg
      pytestmark = requires_ffmpeg

* Fixtures -- request ``ffmpeg`` / ``ffprobe`` / ``melt`` and the test is
  skipped (not failed) when the tool is absent, returning its resolved path.

The ``external`` marker itself is declared in ``pyproject.toml``.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

# Re-export the canonical availability gates so ``from tests.conftest import
# requires_ffmpeg`` keeps working; the definitions live in tests/_testkit.py.
from tests._testkit import (  # noqa: F401
    HAVE_FFMPEG,
    HAVE_FFPROBE,
    HAVE_MELT,
    requires_ffmpeg,
    requires_ffmpeg_ffprobe,
    requires_ffprobe,
    requires_melt,
    requires_melt_ffmpeg,
)


def _require(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        pytest.skip(f"{binary} not on PATH -- test skipped")
    return path


@pytest.fixture(scope="session")
def ffmpeg() -> str:
    return _require("ffmpeg")


@pytest.fixture(scope="session")
def ffprobe() -> str:
    return _require("ffprobe")


@pytest.fixture(scope="session")
def melt() -> str:
    return _require("melt")


# ---------------------------------------------------------------------------
# Bounded retry for real-melt render tests (job 3 -- load-flake stabilizer)
# ---------------------------------------------------------------------------
#
# A single leftover unbounded `melt` render (a project whose tractor `out` is
# huge rendered with no `out=` cap) can eat a CPU core and starve subsequent
# melt renders, tipping timing-tight pixel/duration renders over their timeout
# roughly once per full-suite run. The real fix is not leaking such processes;
# as a belt-and-braces stabilizer we give tests marked ``render_retry`` (see
# ``tests/integration/external/conftest.py``, which auto-applies it to every
# external test that requests the ``melt_bin`` fixture) up to two attempts,
# with a loud terminal line whenever a retry fires. This is deliberately NOT a
# blanket rerun plugin: only real-melt render tests are eligible.

_RENDER_RETRY_ATTEMPTS = 2


def _loud(config, message: str) -> None:
    tr = config.pluginmanager.get_plugin("terminalreporter")
    if tr is not None:
        tr.write_line(message, yellow=True, bold=True)


def pytest_runtest_protocol(item, nextitem):
    if item.get_closest_marker("render_retry") is None:
        return None  # default protocol
    from _pytest.runner import runtestprotocol

    for attempt in range(1, _RENDER_RETRY_ATTEMPTS + 1):
        final = attempt == _RENDER_RETRY_ATTEMPTS
        reports = runtestprotocol(item, nextitem=nextitem, log=False)
        call = next((r for r in reports if r.when == "call"), None)
        passed = call is not None and call.passed
        if passed or final:
            if attempt > 1 and passed:
                _loud(
                    item.config,
                    f"RENDER-RETRY: {item.nodeid} PASSED on attempt {attempt}/"
                    f"{_RENDER_RETRY_ATTEMPTS} (melt load-flake absorbed)",
                )
            elif attempt > 1:
                _loud(
                    item.config,
                    f"RENDER-RETRY: {item.nodeid} still FAILING after "
                    f"{_RENDER_RETRY_ATTEMPTS} attempts (not a flake)",
                )
            for rep in reports:
                item.ihook.pytest_runtest_logreport(report=rep)
            return True
        _loud(
            item.config,
            f"RENDER-RETRY: {item.nodeid} failed attempt {attempt}/"
            f"{_RENDER_RETRY_ATTEMPTS} under load -- retrying",
        )
    return True


# ---------------------------------------------------------------------------
# Shared research candidates package (generate once per session, copy per test)
# ---------------------------------------------------------------------------
# A real ``generate_handshake`` over the 20 s fixture costs ~40 ffmpeg/ffprobe
# spawns (~10 s, far more under CPU contention). Tests that exercise *selection*
# / *export* / *manifest validation* only need *a* valid package, not a fresh
# one, so they share one generation and work on a private copy. Tests of
# generation itself (overwrite, stable ids, output-dir prep) keep calling
# ``generate_handshake`` directly.


@pytest.fixture(scope="session")
def _research_candidates_seed(tmp_path_factory):
    if not (HAVE_FFMPEG and HAVE_FFPROBE):
        pytest.skip("ffmpeg/ffprobe not available on PATH")
    from workshop_video_brain.edit_mcp.pipelines.visual_research.handshake import (
        generate_handshake,
    )

    fixture = Path("tests/fixtures/media_generated/greenscreen_reporter_720.mp4").resolve()
    seed = tmp_path_factory.mktemp("research-seed") / "run"
    manifest = generate_handshake(
        fixture, start_seconds=0.0, end_seconds=2.0, output_dir=seed
    )
    return manifest, seed


@pytest.fixture
def research_candidates_pkg(_research_candidates_seed, tmp_path):
    """``(manifest_dict, candidates_dir)`` -- a private copy of the shared
    package under this test's ``tmp_path`` with image paths repointed."""
    import json
    import shutil

    _manifest, seed = _research_candidates_seed
    dest = tmp_path / "run"
    shutil.copytree(seed, dest)
    manifest_path = dest / "candidates.json"
    text = manifest_path.read_text(encoding="utf-8")
    # Paths are JSON-encoded (backslashes escaped on Windows); swap the
    # encoded prefix so every image_path points into the copy.
    text = text.replace(json.dumps(str(seed))[1:-1], json.dumps(str(dest))[1:-1])
    manifest_path.write_text(text, encoding="utf-8")
    return json.loads(text), dest
