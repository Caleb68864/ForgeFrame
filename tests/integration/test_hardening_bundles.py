"""Hardening pass 1 -- representative failure cases across the bundle tools.

Every bundle MCP tool must fail GRACEFULLY but LOUDLY: a structured error dict
(``status == "error"``) carrying a machine-readable ``error_type`` and an
actionable, non-generic ``suggestion`` -- and NEVER a raw traceback in the
payload, NEVER a silent fake success.

These tests exercise deterministic error paths that need no external binaries
or media (they fail before any ffmpeg/melt subprocess), so they run anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server import errors as err_mod
from workshop_video_brain.edit_mcp.server.bundles import (
    ai_mask,
    beat_grid,
    clip_place,
    guides,
    image_overlay,
    loudness_scan,
    masked_wipes,
    media_denoise_video,
    motion_track,
    multicam,
    pan_zoom,
    proxy_wiring,
    qc_scan,
    scene_detect,
    shape_alpha_mask,
    silence_segment,
    slideshow,
    speed_ramp,
    stabilize,
    subtitle_track,
    thumbnail_sheet,
    timeline_audio,
    titles,
    transcript_index,
    vo_loop,
    zoom_whip,
)
from workshop_video_brain.edit_mcp.server import tools as tools_mod

FIXTURES = Path(__file__).parent / "fixtures"
KEYFRAME_FIXTURE = FIXTURES / "keyframe_project.kdenlive"
ZOOM_WHIP_FIXTURE = FIXTURES / "zoom_whip_project.kdenlive"

NONEXISTENT_WS = "/nonexistent/workspace/path/xyzzy-hardening"

# Generic filler suggestions we explicitly do NOT want to see.
_GENERIC = {"", "an error occurred", "try again", "unknown error", "error"}


def _fn(obj):
    """Unwrap a FastMCP ``FunctionTool`` to its (tool_guard-wrapped) callable."""
    return getattr(obj, "fn", obj)


def _assert_structured_error(result: dict, *, expected_type=None) -> None:
    """Assert the result is a loud-but-graceful structured error."""
    assert isinstance(result, dict), result
    assert result.get("status") == "error", result
    # No raw traceback anywhere in the payload.
    dumped = json.dumps(result, default=str)
    assert "Traceback" not in dumped, dumped
    assert 'File "' not in dumped, dumped
    # A machine-readable, in-taxonomy error_type.
    et = result.get("error_type")
    assert et is not None, f"missing error_type: {result}"
    assert et in err_mod.VALID_ERROR_TYPES, f"unknown error_type {et!r}: {result}"
    if expected_type is not None:
        assert et == expected_type, result
    # A non-generic, actionable suggestion.
    sug = result.get("suggestion", "")
    assert isinstance(sug, str) and len(sug.strip()) > 12, f"weak suggestion: {result}"
    assert sug.strip().lower() not in _GENERIC, result
    # message preserved (legacy contract).
    assert result.get("message"), result


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    """A real, empty workspace created via the canonical workspace_create tool."""
    media_root = tmp_path / "media_src"
    media_root.mkdir(parents=True, exist_ok=True)
    res = _fn(tools_mod.workspace_create)(
        title="Hardening Test", media_root=str(media_root)
    )
    assert res["status"] == "success", res
    return Path(res["data"]["workspace_root"])


# ---------------------------------------------------------------------------
# 1. Nonexistent workspace -> structured error (never a raw traceback)
# ---------------------------------------------------------------------------
# One representative tool per module; each validates the workspace early.
_WORKSPACE_TOOLS = [
    ("stabilize.media_stabilize", lambda: _fn(stabilize.media_stabilize)(NONEXISTENT_WS)),
    ("media_denoise_video", lambda: _fn(media_denoise_video.media_denoise_video)(NONEXISTENT_WS)),
    ("qc_scan.clips_qc_scan", lambda: _fn(qc_scan.clips_qc_scan)(NONEXISTENT_WS)),
    ("loudness_scan.audio_loudness_scan", lambda: _fn(loudness_scan.audio_loudness_scan)(NONEXISTENT_WS)),
    ("thumbnail_sheet.media_thumbnail_sheet", lambda: _fn(thumbnail_sheet.media_thumbnail_sheet)(NONEXISTENT_WS, source="x.mp4")),
    ("transcript_index.transcript_index_build", lambda: _fn(transcript_index.transcript_index_build)(NONEXISTENT_WS)),
    ("clip_place.clip_place", lambda: _fn(clip_place.clip_place)(NONEXISTENT_WS, "p.kdenlive", "s.mp4", 0, 0.0)),
    ("timeline_audio.track_volume", lambda: _fn(timeline_audio.track_volume)(NONEXISTENT_WS, "p.kdenlive", 0)),
    ("image_overlay.overlay_insert", lambda: _fn(image_overlay.overlay_insert)(NONEXISTENT_WS, "p.kdenlive", "i.png", 0.0)),
    ("vo_loop.vo_status", lambda: _fn(vo_loop.vo_status)(NONEXISTENT_WS)),
    ("ai_mask.mask_generate", lambda: _fn(ai_mask.mask_generate)(NONEXISTENT_WS)),
    ("motion_track.subject_locate_frames", lambda: _fn(motion_track.subject_locate_frames)(NONEXISTENT_WS, "p.kdenlive", 0, 0)),
    ("beat_grid.music_beat_grid", lambda: _fn(beat_grid.music_beat_grid)(NONEXISTENT_WS, "song.wav")),
    ("proxy_wiring.proxy_status", lambda: _fn(proxy_wiring.proxy_status)(NONEXISTENT_WS)),
]


@pytest.mark.parametrize("name,call", _WORKSPACE_TOOLS, ids=[n for n, _ in _WORKSPACE_TOOLS])
def test_nonexistent_workspace_is_structured_error(name, call):
    _assert_structured_error(call())


# ---------------------------------------------------------------------------
# 2. Nonexistent project file (real workspace) -> structured error
# ---------------------------------------------------------------------------
_PROJECT_TOOLS = [
    ("clip_place.clip_place", lambda ws: _fn(clip_place.clip_place)(str(ws), "missing.kdenlive", "s.mp4", 0, 0.0)),
    ("timeline_audio.track_volume", lambda ws: _fn(timeline_audio.track_volume)(str(ws), "missing.kdenlive", 0)),
    ("image_overlay.overlay_insert", lambda ws: _fn(image_overlay.overlay_insert)(str(ws), "missing.kdenlive", "i.png", 0.0)),
    ("masked_wipes.effect_luma_key", lambda ws: _fn(masked_wipes.effect_luma_key)(str(ws), "missing.kdenlive", 0, 0)),
    ("shape_alpha_mask.mask_set_from_file", lambda ws: _fn(shape_alpha_mask.mask_set_from_file)(str(ws), "missing.kdenlive", 0, 0, "m.png")),
    ("subtitle_track.subtitles_attach", lambda ws: _fn(subtitle_track.subtitles_attach)(str(ws), "missing.kdenlive")),
]


@pytest.mark.parametrize("name,call", _PROJECT_TOOLS, ids=[n for n, _ in _PROJECT_TOOLS])
def test_missing_project_file_is_structured_error(ws, name, call):
    res = call(ws)
    _assert_structured_error(res)
    # Missing files should classify as a path/lookup problem, not a generic crash.
    assert res["error_type"] in {
        err_mod.MISSING_FILE,
        err_mod.INVALID_INPUT,
        err_mod.NOT_FOUND,
    }, res


# ---------------------------------------------------------------------------
# 3. Corrupt / unparseable project -> corrupt_project
# ---------------------------------------------------------------------------
def test_pan_zoom_corrupt_project(ws):
    bad = ws / "corrupt.kdenlive"
    bad.write_text("<mlt> this is <<< not valid kdenlive xml", encoding="utf-8")
    res = _fn(pan_zoom.effect_pan_zoom)(str(bad), 0, 0, preset="zoom_in")
    _assert_structured_error(res, expected_type=err_mod.CORRUPT_PROJECT)


def test_zoom_whip_corrupt_project(ws):
    bad = ws / "corrupt.kdenlive"
    bad.write_text("not xml at all {{{", encoding="utf-8")
    res = _fn(zoom_whip.transition_zoom_whip)(str(ws), "corrupt.kdenlive", 0, 0, 1)
    _assert_structured_error(res, expected_type=err_mod.CORRUPT_PROJECT)


# ---------------------------------------------------------------------------
# 4. Invalid track/clip index -> invalid_index (with a valid project)
# ---------------------------------------------------------------------------
def test_pan_zoom_invalid_track_index(ws):
    dest = ws / "kf.kdenlive"
    dest.write_bytes(KEYFRAME_FIXTURE.read_bytes())
    res = _fn(pan_zoom.effect_pan_zoom)(str(dest), 99, 0, preset="zoom_in")
    _assert_structured_error(res, expected_type=err_mod.INVALID_INDEX)
    assert "valid_range" in res, res


def test_zoom_whip_invalid_track_index(ws):
    dest = ws / "zw.kdenlive"
    dest.write_bytes(ZOOM_WHIP_FIXTURE.read_bytes())
    res = _fn(zoom_whip.transition_zoom_whip)(str(ws), "zw.kdenlive", 99, 0, 1)
    _assert_structured_error(res, expected_type=err_mod.INVALID_INDEX)


# ---------------------------------------------------------------------------
# 5. Malformed JSON params -> bad_json_param (with a minimal valid example)
# ---------------------------------------------------------------------------
def test_multicam_switch_bad_cuts_json(ws):
    res = _fn(multicam.multicam_switch)(str(ws), "p.kdenlive", cuts="{not valid json")
    _assert_structured_error(res, expected_type=err_mod.BAD_JSON_PARAM)
    assert "at_seconds" in res["suggestion"], res  # shows a concrete example


def test_multicam_assemble_empty_sources(ws):
    # An empty sources argument cannot be parsed into angle paths.
    res = _fn(multicam.multicam_assemble)(str(ws), "p.kdenlive", sources="")
    _assert_structured_error(res, expected_type=err_mod.BAD_JSON_PARAM)


# ---------------------------------------------------------------------------
# 6. Empty / no-op inputs -> explicit error, not a fake success
# ---------------------------------------------------------------------------
def test_markers_from_beats_empty_beats(ws):
    beat_file = ws / "reports" / "beat_grid.json"
    beat_file.parent.mkdir(parents=True, exist_ok=True)
    beat_file.write_text(json.dumps({"beats": []}), encoding="utf-8")
    res = _fn(beat_grid.markers_from_beats)(str(ws), beat_file=str(beat_file))
    _assert_structured_error(res, expected_type=err_mod.NOT_FOUND)


def test_vo_plan_empty_script(ws):
    script = ws / "empty.md"
    script.write_text("", encoding="utf-8")
    res = _fn(vo_loop.vo_plan)(str(ws), str(script))
    _assert_structured_error(res, expected_type=err_mod.INVALID_INPUT)


# ---------------------------------------------------------------------------
# 7. Missing source (analysis tool) -> structured error, not a traceback
# ---------------------------------------------------------------------------
def test_scene_detect_missing_source(ws):
    res = _fn(scene_detect.clips_detect_scenes)(str(ws), source="does_not_exist.mp4")
    _assert_structured_error(res)


def test_silence_segment_missing_source(ws):
    res = _fn(silence_segment.media_segment_at_silence)(str(ws), source="nope.mp4")
    _assert_structured_error(res)


def test_title_card_missing_project():
    res = _fn(titles.title_card_add)("/no/such/project.kdenlive", "Hello")
    _assert_structured_error(res)


def test_guides_missing_project():
    res = _fn(guides.guide_add)("/no/such/project.kdenlive", 1.0, "Intro")
    _assert_structured_error(res)


def test_speed_ramp_missing_project(ws):
    res = _fn(speed_ramp.speed_ramp)(str(ws), "missing.kdenlive", 0, 0, keyframes="[]")
    _assert_structured_error(res)
