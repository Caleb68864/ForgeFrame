"""§1.3: a corrupt project must surface an error, not be silently overwritten.

Before the fix, ``parse_project`` returned an empty project on a parse failure,
so an intent-driven tool would "patch" nothing and serialize a fresh (empty)
version over the corrupt-but-recoverable file.  These tests prove the tools now
return their standard error dict instead of proceeding.
"""
from __future__ import annotations

from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

import workshop_video_brain.server as _server  # noqa: F401
import workshop_video_brain.edit_mcp.server.tools as _tools
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import (
    ProjectParseError,
    parse_project,
)


from tests._testkit import unwrap as _fn  # noqa: E402


workspace_create = _fn(_tools.workspace_create)
clip_remove = _fn(_tools.clip_remove)


def _corrupt_ws(tmp_path: Path) -> Path:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Corrupt Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws = Path(result["data"]["workspace_root"])
    wc = ws / "projects" / "working_copies"
    wc.mkdir(parents=True, exist_ok=True)
    corrupt = wc / "corrupt_v1.kdenlive"
    corrupt.write_text("<mlt><this is not valid xml", encoding="utf-8")
    return ws, corrupt


def test_parse_project_raises_on_corrupt(tmp_path):
    _ws, corrupt = _corrupt_ws(tmp_path)
    with pytest.raises(ProjectParseError):
        parse_project(corrupt)


def test_clip_remove_returns_error_on_corrupt(tmp_path):
    ws, corrupt = _corrupt_ws(tmp_path)
    before = corrupt.read_text(encoding="utf-8")
    result = clip_remove(str(ws), clip_index=0)
    assert result["status"] == "error", result
    # The corrupt file must be left untouched (not overwritten with an empty project).
    assert corrupt.read_text(encoding="utf-8") == before
