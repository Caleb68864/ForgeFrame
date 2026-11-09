"""render_final picks the edited working copy, never a stale snapshot.

Snapshots (projects/snapshots/<id>/) are pre-overwrite copies that keep the
working copy's ``_v<N>`` name. The old whole-workspace rglob plus a
tie-less version key could select the snapshot. Found 2026-11-09.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.pipelines.render_final import _find_latest_project


def _touch(path: Path, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<mlt/>")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_working_copy_beats_same_named_snapshot(tmp_path):
    # Snapshot names sort before working copies in most rglob orders
    # ("projects/snapshots" vs "projects/working_copies"), and both are _v3.
    _touch(tmp_path / "projects" / "snapshots" / "20261109-aaaa" / "demo_v3.kdenlive")
    _touch(tmp_path / "projects" / "snapshots" / "20261109-bbbb" / "demo_v9.kdenlive")
    wc = _touch(tmp_path / "projects" / "working_copies" / "demo_v3.kdenlive")

    assert _find_latest_project(tmp_path) == wc


def test_fallback_ignores_snapshots(tmp_path):
    _touch(tmp_path / "projects" / "snapshots" / "x" / "demo_v9.kdenlive")
    other = _touch(tmp_path / "edits" / "demo_v2.kdenlive")

    assert _find_latest_project(tmp_path) == other


def test_only_snapshots_is_not_found(tmp_path):
    _touch(tmp_path / "projects" / "snapshots" / "x" / "demo_v1.kdenlive")

    with pytest.raises(FileNotFoundError, match="snapshots are ignored"):
        _find_latest_project(tmp_path)
