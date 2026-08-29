"""Safety rule: never write into ``media/raw/`` or ``projects/source/``.

CLAUDE.md states the rule; before this test it was enforced only by one
pipeline's private substring check. The guard now lives in
``core.utils.paths`` and is called at the two write choke points every tool
goes through -- ``serialize_project`` (all .kdenlive writes) and
``run_ffmpeg`` (media outputs) -- so a tool handed ``project_file=
"projects/source/original.kdenlive"`` or an output path inside the user's raw
footage is refused with an ``invalid_input`` error instead of clobbering the
user's only copy.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.unit.test_serializer_bin import _make_project
from workshop_video_brain.core.utils.paths import (
    ProtectedPathError,
    assert_not_protected,
    is_protected_path,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import run_ffmpeg
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.server.errors import INVALID_INPUT, from_exception, tool_guard


# ---------------------------------------------------------------- predicate
@pytest.mark.parametrize(
    "rel",
    [
        "media/raw/clip.mp4",
        "media/raw/video/deep/clip.mp4",
        "projects/source/original.kdenlive",
        "projects/working_copies/../source/original.kdenlive",  # `..` resolved
    ],
)
def test_protected_paths_are_detected(tmp_path, rel):
    assert is_protected_path(tmp_path / rel)


@pytest.mark.parametrize(
    "rel",
    [
        "media/processed/clip.mp4",
        "media/proxies/clip_proxy.mp4",
        "projects/working_copies/edit_v2.kdenlive",
        "reports/previews/clip.gif",
        "media/raw_footage/clip.mp4",   # segment match, not substring
        "my_media/raw",                 # 'raw' is the leaf, no child written
        "source/projects/x.kdenlive",   # wrong order
    ],
)
def test_ordinary_workspace_paths_are_not_protected(tmp_path, rel):
    assert not is_protected_path(tmp_path / rel)


def test_assert_not_protected_returns_path_or_raises(tmp_path):
    ok = tmp_path / "media" / "processed" / "x.mp4"
    assert assert_not_protected(ok) == ok
    with pytest.raises(ProtectedPathError, match="protected tree"):
        assert_not_protected(tmp_path / "media" / "raw" / "x.mp4", "test output")


# ------------------------------------------------------- write choke points
def test_serializer_refuses_to_write_into_projects_source(tmp_path):
    target = tmp_path / "projects" / "source" / "original.kdenlive"
    target.parent.mkdir(parents=True)
    with pytest.raises(ProtectedPathError):
        serialize_project(_make_project(), target)
    assert not target.exists()


def test_serializer_still_writes_working_copies(tmp_path):
    target = tmp_path / "projects" / "working_copies" / "edit.kdenlive"
    serialize_project(_make_project(), target)
    assert target.exists()


def test_run_ffmpeg_refuses_to_overwrite_raw_footage(tmp_path):
    raw = tmp_path / "media" / "raw" / "clip.mp4"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"the user's only copy")
    # Guard fires before ffmpeg is even looked up, so this needs no binary.
    with pytest.raises(ProtectedPathError):
        run_ffmpeg(["-c", "copy"], tmp_path / "in.mp4", raw)
    assert raw.read_bytes() == b"the user's only copy"


def test_run_ffmpeg_dry_run_allows_new_file_beside_raw(tmp_path):
    # Creating a *new* file next to raw footage (an explicit single-frame
    # extract) is not an overwrite and stays the caller's decision.
    new = tmp_path / "media" / "raw" / "clip_frame_1_000.png"
    new.parent.mkdir(parents=True)
    result = run_ffmpeg(["-frames:v", "1"], tmp_path / "in.mp4", new, dry_run=True)
    assert result.success


# --------------------------------------------------------- error contract
def test_protected_path_error_is_actionable_invalid_input():
    exc = ProtectedPathError("Refusing to write project file inside a protected tree: x")
    out = from_exception(exc)
    assert out["error_type"] == INVALID_INPUT
    assert "working_copies" in out["suggestion"]

    @tool_guard
    def tool(workspace_path: str):
        raise exc

    guarded = tool("ws")
    assert guarded["error_type"] == INVALID_INPUT
    assert "please report" not in guarded["suggestion"].lower()
