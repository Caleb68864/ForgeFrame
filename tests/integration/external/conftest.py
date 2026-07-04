"""Harness infrastructure for the external oracle suite.

Owns tool discovery and availability gating only -- nothing about *what* is
correct (that lives in the test modules) and nothing about project construction
(that lives in ``builders.py``). Tools are located with ``shutil.which`` and a
test requesting an absent tool is skipped, mirroring the existing
``shutil.which`` guards elsewhere in the codebase.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

# The whole package is the external tier.
pytestmark = pytest.mark.external


def pytest_collection_modifyitems(items):
    """Auto-mark real-melt render tests as ``render_retry`` (job 3 stabilizer).

    Any external test that requests the ``melt_bin`` fixture drives a real
    ``melt`` render and is therefore exposed to the CPU-load flake; the bounded
    2-attempt retry protocol lives in the root ``tests/conftest.py``.
    """
    for item in items:
        if "melt_bin" in getattr(item, "fixturenames", ()):  # real render test
            item.add_marker(pytest.mark.render_retry)


def _require(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        pytest.skip(f"{binary} not on PATH -- external oracle test skipped")
    return path


@pytest.fixture(scope="session")
def melt_bin() -> str:
    return _require("melt")


@pytest.fixture(scope="session")
def ffprobe_bin() -> str:
    return _require("ffprobe")


@pytest.fixture(scope="session")
def ffmpeg_bin() -> str:
    return _require("ffmpeg")


@pytest.fixture
def render_dir(tmp_path: Path) -> Path:
    """A per-test scratch directory for rendered frames / media."""
    d = tmp_path / "renders"
    d.mkdir(parents=True, exist_ok=True)
    return d


def melt_has_service(melt_bin: str, kind: str, name: str) -> bool:
    """Return True if melt reports *name* among ``-query {kind}``.

    *kind* is e.g. ``"filters"`` or ``"transitions"``. Lets tests skip when a
    specific optional MLT module (frei0r/opencv/Qt) is missing on this build,
    so the harness reflects "wired correctly" not "build fully featured".
    """
    import subprocess

    try:
        out = subprocess.run(
            [melt_bin, "-query", kind],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except Exception:
        return False
    return any(name in line for line in out.splitlines())
