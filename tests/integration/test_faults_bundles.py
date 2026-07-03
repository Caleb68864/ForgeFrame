"""Hardening pass 2 -- adversarial fault injection across the bundle tools.

Goal (same contract as pass 1): every bundle MCP tool fails GRACEFULLY but
LOUDLY -- a structured error dict (``status == "error"``) with a machine-readable
``error_type`` and an actionable ``suggestion``, never a raw traceback, never a
silent fake success. Additionally, on failure:

* project files are byte-unchanged,
* ``media/raw`` is NEVER written,
* no half-written output is left in ``media/processed`` (failed runs clean up).

Pass 1 exercised deterministic pre-subprocess faults (missing workspace/project,
corrupt project, bad JSON). Pass 2 injects the *media* and *environment*
dimension: unreadable/zero-byte/wrong-format media, corrupt images, empty dirs,
TOCTOU deletion, read-only output dirs, ffmpeg/melt-absent, subprocess timeout,
and garbage keyframe/rect/source JSON -- and verifies the carry-over pipeline
error_type pass-through and cleanup behaviour.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server import errors as err_mod
from workshop_video_brain.edit_mcp.server import tools as tools_mod
from workshop_video_brain.edit_mcp.server.bundles import (
    ai_mask,
    audio_normalize_two_pass,
    audio_sync,
    beat_grid,
    clip_dupes,
    clip_preview,
    loudness_scan,
    media_denoise_video,
    motion_track,
    multicam,
    qc_scan,
    review_loop,
    scene_detect,
    silence_segment,
    slideshow,
    speed_ramp,
    stabilize,
    thumbnail_sheet,
    timeline_audio,
)

FIXTURES = Path(__file__).parent / "fixtures"
KEYFRAME_FIXTURE = FIXTURES / "keyframe_project.kdenlive"

_FFMPEG = shutil.which("ffmpeg")
_FFPROBE = shutil.which("ffprobe")
_MELT = shutil.which("melt")

_GENERIC = {"", "an error occurred", "try again", "unknown error", "error"}


def _fn(obj):
    """Unwrap a FastMCP tool object to its callable (identity for plain fns)."""
    return getattr(obj, "fn", obj)


def _assert_structured_error(result: dict, *, expected_type=None, allowed=None) -> None:
    assert isinstance(result, dict), result
    assert result.get("status") == "error", result
    dumped = json.dumps(result, default=str)
    assert "Traceback" not in dumped, dumped
    assert 'File "' not in dumped, dumped
    et = result.get("error_type")
    assert et is not None, f"missing error_type: {result}"
    assert et in err_mod.VALID_ERROR_TYPES, f"unknown error_type {et!r}: {result}"
    if expected_type is not None:
        assert et == expected_type, result
    if allowed is not None:
        assert et in allowed, result
    sug = result.get("suggestion", "")
    assert isinstance(sug, str) and len(sug.strip()) > 12, f"weak suggestion: {result}"
    assert sug.strip().lower() not in _GENERIC, result
    assert result.get("message"), result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    media_root = tmp_path / "media_src"
    media_root.mkdir(parents=True, exist_ok=True)
    res = _fn(tools_mod.workspace_create)(
        title="Fault Test", media_root=str(media_root)
    )
    assert res["status"] == "success", res
    return Path(res["data"]["workspace_root"])


@pytest.fixture()
def processed(ws: Path) -> Path:
    d = ws / "media" / "processed"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture()
def raw(ws: Path) -> Path:
    d = ws / "media" / "raw"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture()
def text_mp4(tmp_path: Path) -> Path:
    """A text file wearing a .mp4 extension (wrong-format media)."""
    p = tmp_path / "not_really_video.mp4"
    p.write_text("this is plainly not a video container\n" * 20, encoding="utf-8")
    return p


@pytest.fixture()
def zero_mp4(tmp_path: Path) -> Path:
    """A zero-byte .mp4 (truncated/empty media)."""
    p = tmp_path / "empty.mp4"
    p.touch()
    return p


@pytest.fixture()
def corrupt_png(tmp_path: Path) -> Path:
    """A file with a valid PNG magic header but a truncated/garbage body."""
    p = tmp_path / "broken.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\xff\x13\x37garbage-not-a-real-png")
    return p


@pytest.fixture(scope="session")
def real_mp4(tmp_path_factory) -> Path:
    """A short, valid H.264 test clip generated with ffmpeg lavfi."""
    if not _FFMPEG:
        pytest.skip("ffmpeg not available")
    out = tmp_path_factory.mktemp("realmedia") / "real.mp4"
    subprocess.run(
        [_FFMPEG, "-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=15:duration=1",
         "-pix_fmt", "yuv420p", "-g", "5", str(out)],
        capture_output=True, check=True,
    )
    return out


@pytest.fixture(scope="session")
def real_wav(tmp_path_factory) -> Path:
    """A short, valid audio-only WAV generated with ffmpeg lavfi."""
    if not _FFMPEG:
        pytest.skip("ffmpeg not available")
    out = tmp_path_factory.mktemp("realaudio") / "real.wav"
    subprocess.run(
        [_FFMPEG, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         str(out)],
        capture_output=True, check=True,
    )
    return out


def _corrupt_project(ws: Path, name: str = "corrupt.kdenlive") -> Path:
    p = ws / name
    p.write_text("<mlt><this is not <<< valid xml & unterminated", encoding="utf-8")
    return p


def _valid_project(ws: Path, name: str = "proj.kdenlive") -> Path:
    p = ws / name
    shutil.copy(KEYFRAME_FIXTURE, p)
    return p


def _project_with_media(ws: Path, media: Path, name: str = "media_proj.kdenlive") -> Path:
    """A valid project whose only clip resolves to a real, existing media file."""
    p = ws / name
    text = KEYFRAME_FIXTURE.read_text(encoding="utf-8")
    text = text.replace("/media/clip1.mp4", str(media))
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. Single-source media tools: wrong-format + zero-byte media
# ---------------------------------------------------------------------------
# Each callable takes (ws, source_path) and must return a structured error for
# an unreadable source -- no traceback, no fake success.
_SINGLE_SOURCE_TOOLS = [
    ("stabilize.media_stabilize",
     lambda ws, s: _fn(stabilize.media_stabilize)(str(ws), source=str(s))),
    ("media_denoise_video",
     lambda ws, s: _fn(media_denoise_video.media_denoise_video)(str(ws), source=str(s))),
    ("audio_normalize_two_pass",
     lambda ws, s: _fn(audio_normalize_two_pass.audio_normalize_two_pass)(str(ws), source=str(s))),
    ("silence_segment.media_segment_at_silence",
     lambda ws, s: _fn(silence_segment.media_segment_at_silence)(str(ws), source=str(s))),
    ("thumbnail_sheet.media_thumbnail_sheet",
     lambda ws, s: _fn(thumbnail_sheet.media_thumbnail_sheet)(str(ws), source=str(s))),
    ("scene_detect.clips_detect_scenes",
     lambda ws, s: _fn(scene_detect.clips_detect_scenes)(str(ws), source=str(s))),
    ("clip_preview.clips_preview_gif",
     lambda ws, s: _fn(clip_preview.clips_preview_gif)(str(ws), source=str(s))),
    ("beat_grid.music_beat_grid",
     lambda ws, s: _fn(beat_grid.music_beat_grid)(str(ws), source=str(s))),
    ("review_loop.thumbnail_generate",
     lambda ws, s: _fn(review_loop.thumbnail_generate)(str(ws), str(s), 0.0)),
    ("ai_mask.mask_generate",
     lambda ws, s: _fn(ai_mask.mask_generate)(str(ws), source=str(s))),
]


@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required to exercise decode failure")
@pytest.mark.parametrize("name,call", _SINGLE_SOURCE_TOOLS, ids=[n for n, _ in _SINGLE_SOURCE_TOOLS])
def test_wrong_format_media_is_structured_error(name, call, ws, text_mp4, raw):
    result = call(ws, text_mp4)
    _assert_structured_error(result)
    # media/raw never written by a processing tool.
    assert list(raw.iterdir()) == []


@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required to exercise decode failure")
@pytest.mark.parametrize("name,call", _SINGLE_SOURCE_TOOLS, ids=[n for n, _ in _SINGLE_SOURCE_TOOLS])
def test_zero_byte_media_is_structured_error(name, call, ws, zero_mp4, raw):
    result = call(ws, zero_mp4)
    _assert_structured_error(result)
    assert list(raw.iterdir()) == []


@pytest.mark.parametrize("name,call", _SINGLE_SOURCE_TOOLS, ids=[n for n, _ in _SINGLE_SOURCE_TOOLS])
def test_missing_source_is_structured_error(name, call, ws):
    result = call(ws, ws / "definitely_missing_source.mp4")
    _assert_structured_error(result)


# ---------------------------------------------------------------------------
# 1b. Batch analysis scanners (qc / loudness): a corrupt clip must be reported
#     loudly -- flagged / not-measured -- NEVER a false all-clear rating.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
def test_qc_scan_flags_unreadable_clip(ws, text_mp4):
    result = _fn(qc_scan.clips_qc_scan)(str(ws), source_or_dir=str(text_mp4))
    # QC is a diagnostic tool: scanning a corrupt clip succeeds but must FLAG it
    # (no silent perfect 5/5). Assert no false all-clear.
    assert result["status"] == "success", result
    clips = result["data"].get("clips") or result["data"].get("results") or []
    assert clips, result
    clip0 = clips[0]
    assert clip0.get("verdict") == "flagged" or "unreadable" in clip0.get("reasons", []), clip0
    assert clip0.get("rating", 5) < 5, clip0


@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
def test_loudness_scan_corrupt_no_false_measure(ws, text_mp4):
    result = _fn(loudness_scan.audio_loudness_scan)(str(ws), source_or_dir=str(text_mp4))
    # Honest: it may succeed but must report 0 measured, never fabricate a LUFS.
    assert result["status"] == "success", result
    summary = result["data"].get("summary", {})
    assert summary.get("measured", 0) == 0, result


@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
def test_qc_scan_missing_source(ws):
    result = _fn(qc_scan.clips_qc_scan)(str(ws), source_or_dir=str(ws / "nope.mp4"))
    _assert_structured_error(result)


@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
def test_loudness_scan_missing_source(ws):
    result = _fn(loudness_scan.audio_loudness_scan)(str(ws), source_or_dir=str(ws / "nope.mp4"))
    _assert_structured_error(result)


# ---------------------------------------------------------------------------
# 2. No half-written output left in media/processed after a failed render
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
@pytest.mark.parametrize("name,call", [
    ("media_stabilize",
     lambda ws, s: _fn(stabilize.media_stabilize)(str(ws), source=str(s))),
    ("media_denoise_video",
     lambda ws, s: _fn(media_denoise_video.media_denoise_video)(str(ws), source=str(s))),
    ("audio_normalize_two_pass",
     lambda ws, s: _fn(audio_normalize_two_pass.audio_normalize_two_pass)(str(ws), source=str(s))),
], ids=["stabilize", "denoise", "loudnorm"])
def test_failed_render_leaves_no_partial_output(name, call, ws, text_mp4, processed):
    result = call(ws, text_mp4)
    _assert_structured_error(result)
    leftovers = [p for p in processed.iterdir() if p.is_file() and p.stat().st_size >= 0]
    assert leftovers == [], f"{name} left partial output: {leftovers}"


# ---------------------------------------------------------------------------
# 3. Audio-only file to a video tool / video-only file to an audio tool
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
def test_audio_only_to_video_tool(ws, real_wav, processed):
    # stabilize needs a video stream; a pure-audio WAV must fail loudly, not
    # silently produce an empty/garbage output.
    result = _fn(stabilize.media_stabilize)(str(ws), source=str(real_wav))
    _assert_structured_error(result)
    assert [p for p in processed.iterdir() if p.is_file()] == []


@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
def test_video_only_to_audio_sync(ws, real_mp4):
    # testsrc has no audio stream; audio-sync must report a structured failure.
    result = _fn(audio_sync.media_sync_by_audio)(str(ws), str(real_mp4), str(real_mp4))
    _assert_structured_error(result)


# ---------------------------------------------------------------------------
# 4. audio_sync: two-source faults
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
def test_audio_sync_wrong_format(ws, text_mp4):
    result = _fn(audio_sync.media_sync_by_audio)(str(ws), str(text_mp4), str(text_mp4))
    _assert_structured_error(result)


def test_audio_sync_missing_second_source(ws, tmp_path):
    a = ws / "missing_a.wav"
    b = ws / "missing_b.wav"
    result = _fn(audio_sync.media_sync_by_audio)(str(ws), str(a), str(b))
    _assert_structured_error(result)


# ---------------------------------------------------------------------------
# 5. Directory-oriented tools: empty dir + corrupt-image dir
# ---------------------------------------------------------------------------
def test_slideshow_empty_folder(ws, tmp_path):
    empty = tmp_path / "empty_images"
    empty.mkdir()
    result = _fn(slideshow.media_slideshow)(str(ws), str(empty))
    _assert_structured_error(result)


@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
def test_slideshow_corrupt_images(ws, tmp_path, corrupt_png, monkeypatch):
    folder = tmp_path / "bad_images"
    folder.mkdir()
    shutil.copy(corrupt_png, folder / "a.png")
    (folder / "b.png").write_text("still not a png", encoding="utf-8")
    # A corrupt PNG on an -loop 1 input makes ffmpeg spin forever; the tool must
    # bound it with a timeout. Shrink the ceiling so the guard fires fast here.
    monkeypatch.setattr(slideshow, "SLIDESHOW_RENDER_TIMEOUT", 5.0)
    result = _fn(slideshow.media_slideshow)(str(ws), str(folder))
    # Must fail loudly (structured error) -- never crash, never fake success.
    assert isinstance(result, dict)
    dumped = json.dumps(result, default=str)
    assert "Traceback" not in dumped and 'File "' not in dumped
    _assert_structured_error(result)
    # No half-written slideshow left behind after the timeout/failure.
    leftovers = list((ws / "media" / "processed").glob("slideshow_*.mp4"))
    assert leftovers == [], leftovers


def test_clip_dupes_empty_dir(ws, tmp_path):
    empty = tmp_path / "no_clips"
    empty.mkdir()
    result = _fn(clip_dupes.clips_find_duplicates)(str(ws), str(empty))
    _assert_structured_error(result)


def test_clip_dupes_missing_dir(ws):
    result = _fn(clip_dupes.clips_find_duplicates)(str(ws), str(ws / "nope_dir"))
    _assert_structured_error(result)


# ---------------------------------------------------------------------------
# 6. Garbage JSON params on project tools -> bad_json_param / structured error
# ---------------------------------------------------------------------------
def test_speed_ramp_garbage_keyframes(ws):
    proj = _valid_project(ws)
    before = proj.read_bytes()
    result = _fn(speed_ramp.speed_ramp)(str(ws), proj.name, 2, 0, keyframes="{not json[[")
    _assert_structured_error(result)
    assert proj.read_bytes() == before  # project byte-unchanged on failure


def test_multicam_garbage_sources(ws):
    proj = _valid_project(ws)
    before = proj.read_bytes()
    result = _fn(multicam.multicam_assemble)(str(ws), proj.name, sources="[[[not json")
    _assert_structured_error(result)
    assert proj.read_bytes() == before


def test_multicam_garbage_cuts(ws):
    proj = _valid_project(ws)
    result = _fn(multicam.multicam_switch)(str(ws), proj.name, cuts="{bad json")
    _assert_structured_error(result)


def test_timeline_audio_garbage_keyframes(ws):
    proj = _valid_project(ws)
    before = proj.read_bytes()
    result = _fn(timeline_audio.track_volume)(str(ws), proj.name, 2, keyframes="}{not-json")
    _assert_structured_error(result)
    assert proj.read_bytes() == before


def test_timeline_audio_garbage_bands(ws):
    proj = _valid_project(ws)
    result = _fn(timeline_audio.track_eq)(str(ws), proj.name, 2, bands="not-json-bands[[")
    _assert_structured_error(result)


def test_motion_track_garbage_track_data(ws):
    proj = _valid_project(ws)
    result = _fn(motion_track.subject_zoom)(
        str(ws), proj.name, 2, 0, track_data="{{{not json", rect="10 10 20 20"
    )
    _assert_structured_error(result)


# ---------------------------------------------------------------------------
# 7. Corrupt project across the project-parsing tools
# ---------------------------------------------------------------------------
_CORRUPT_PROJECT_TOOLS = [
    ("speed_ramp",
     lambda ws, p: _fn(speed_ramp.speed_ramp)(str(ws), p, 2, 0, keyframes='[[0,1.0],[10,2.0]]')),
    ("timeline_audio.track_volume",
     lambda ws, p: _fn(timeline_audio.track_volume)(str(ws), p, 2, gain_db=-3.0)),
    ("timeline_audio.track_pan",
     lambda ws, p: _fn(timeline_audio.track_pan)(str(ws), p, 2, pan=0.5)),
    ("motion_track.subject_zoom",
     lambda ws, p: _fn(motion_track.subject_zoom)(str(ws), p, 2, 0, rect="10 10 20 20")),
    ("multicam.multicam_switch",
     lambda ws, p: _fn(multicam.multicam_switch)(str(ws), p, cuts='[[0,0]]')),
]


@pytest.mark.parametrize("name,call", _CORRUPT_PROJECT_TOOLS, ids=[n for n, _ in _CORRUPT_PROJECT_TOOLS])
def test_corrupt_project_is_structured_error(name, call, ws):
    proj = _corrupt_project(ws)
    before = proj.read_bytes()
    result = call(ws, proj.name)
    _assert_structured_error(result)
    assert proj.read_bytes() == before  # never rewrites a project on failure


# ---------------------------------------------------------------------------
# 8. Invalid index across project tools (real project, out-of-range track/clip)
# ---------------------------------------------------------------------------
_INVALID_INDEX_TOOLS = [
    ("timeline_audio.track_volume",
     lambda ws, p: _fn(timeline_audio.track_volume)(str(ws), p, 99, gain_db=-3.0)),
    ("motion_track.subject_zoom",
     lambda ws, p: _fn(motion_track.subject_zoom)(str(ws), p, 99, 0, rect="1 1 2 2")),
    ("speed_ramp",
     lambda ws, p: _fn(speed_ramp.speed_ramp)(str(ws), p, 99, 0, keyframes='[[0,1.0],[5,2.0]]')),
]


@pytest.mark.parametrize("name,call", _INVALID_INDEX_TOOLS, ids=[n for n, _ in _INVALID_INDEX_TOOLS])
def test_invalid_index_is_structured_error(name, call, ws):
    proj = _valid_project(ws)
    before = proj.read_bytes()
    result = call(ws, proj.name)
    _assert_structured_error(result)
    assert proj.read_bytes() == before


# ---------------------------------------------------------------------------
# 9. TOCTOU -- media deleted between resolve and execute
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
def test_toctou_source_deleted(ws, real_mp4, monkeypatch):
    """Delete the source right after the tool's exists() check, before ffmpeg."""
    victim = ws / "media" / "raw" / "victim.mp4"
    victim.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_mp4, victim)

    import workshop_video_brain.edit_mcp.pipelines.stabilize as st

    real_available = st.vidstab_available

    def _delete_then_probe():
        # Fires during stabilize_file, after the bundle's exists() gate.
        if victim.exists():
            victim.unlink()
        return real_available()

    monkeypatch.setattr(st, "vidstab_available", _delete_then_probe)
    result = _fn(stabilize.media_stabilize)(str(ws), source=str(victim))
    _assert_structured_error(result)


# ---------------------------------------------------------------------------
# 10. Read-only output directory
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _FFMPEG or os.geteuid() == 0,
                    reason="ffmpeg required; chmod ineffective as root")
def test_readonly_processed_dir(ws, real_mp4):
    processed = ws / "media" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    os.chmod(processed, 0o500)
    try:
        result = _fn(media_denoise_video.media_denoise_video)(str(ws), source=str(real_mp4))
        # Must fail loudly (cannot write) rather than crash with a traceback.
        _assert_structured_error(result)
    finally:
        os.chmod(processed, 0o755)


# ---------------------------------------------------------------------------
# 11. melt-absent: PATH manipulation hitting the missing_binary path
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _MELT or not _FFMPEG, reason="melt+ffmpeg required")
def test_melt_absent_subject_track(ws, real_mp4, monkeypatch, tmp_path):
    """With melt removed from PATH, subject_track(engine='melt') -> missing_dependency."""
    empty = tmp_path / "empty_bin"
    empty.mkdir()
    # A PATH with neither melt nor anything else -> shutil.which('melt') is None.
    monkeypatch.setenv("PATH", str(empty))
    proj = _project_with_media(ws, real_mp4)  # clip source really exists
    result = _fn(motion_track.subject_track)(
        str(ws), proj.name, 2, 0, rect="10 10 20 20", engine="melt"
    )
    _assert_structured_error(result, allowed={"missing_dependency", "missing_binary"})


def test_melt_absent_resolve_engine_raises(monkeypatch, tmp_path):
    """Unit-level: motion_track.resolve_engine('melt') is loud when melt is gone."""
    import workshop_video_brain.edit_mcp.pipelines.motion_track as mt
    empty = tmp_path / "empty_bin2"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    with pytest.raises(mt.TrackerUnavailable):
        mt.resolve_engine("melt")


# ---------------------------------------------------------------------------
# 12. Carry-over: pipeline error_type actually propagates through the bundle
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
def test_carryover_denoise_error_type_passthrough(ws, text_mp4):
    result = _fn(media_denoise_video.media_denoise_video)(str(ws), source=str(text_mp4))
    _assert_structured_error(result)
    # The pipeline now tags operation_failed; the bundle passes it through
    # instead of an untyped _err.
    assert result["error_type"] in {"operation_failed", "media_unreadable"}


@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
def test_carryover_audio_sync_missing_file_type(ws):
    result = _fn(audio_sync.media_sync_by_audio)(
        str(ws), str(ws / "a_missing.wav"), str(ws / "b_missing.wav")
    )
    _assert_structured_error(result, expected_type="missing_file")


def test_carryover_motion_track_typed_exceptions_exist():
    import workshop_video_brain.edit_mcp.pipelines.motion_track as mt
    assert issubclass(mt.FfmpegUnavailable, RuntimeError)
    assert issubclass(mt.FrameExtractionError, RuntimeError)
    # They are distinct so the bundle can map missing_binary vs media_unreadable.
    assert mt.FfmpegUnavailable is not mt.FrameExtractionError


# ---------------------------------------------------------------------------
# 13. Subprocess timeout path actually fires (tiny override)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
def test_ffmpeg_timeout_fires(real_mp4, tmp_path):
    """The pass-1 timeout plumbing must actually raise FFmpegTimeout."""
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
        FFmpegTimeout, run_ffmpeg,
    )
    out = tmp_path / "slow.mp4"
    # A CPU-heavy filter + a 1ms ceiling guarantees the timeout branch fires.
    with pytest.raises(FFmpegTimeout):
        run_ffmpeg(
            ["-vf", "scale=1920:1080,gblur=sigma=40", "-c:v", "libx264",
             "-preset", "veryslow"],
            input_path=real_mp4, output_path=out, timeout=0.001,
        )


# ---------------------------------------------------------------------------
# 14. probe-duration helpers log + distinguish missing vs unparseable
# ---------------------------------------------------------------------------
def test_probe_duration_missing_file_logs(caplog):
    from workshop_video_brain.edit_mcp.server.bundles.slideshow import _probe_duration
    import logging
    with caplog.at_level(logging.WARNING):
        assert _probe_duration(Path("/no/such/file.mp4")) is None
    assert any("missing" in r.message.lower() for r in caplog.records)


@pytest.mark.skipif(not _FFPROBE, reason="ffprobe required")
def test_probe_duration_unparseable_logs(caplog, tmp_path):
    from workshop_video_brain.edit_mcp.server.bundles.clip_dupes import _probe_duration
    import logging
    bad = tmp_path / "bad.mp4"
    bad.write_text("not a media file", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert _probe_duration(bad) is None
    # ffprobe exits nonzero on garbage; we log that, never silently swallow.
    assert any("probe" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# 15. Corrupt-image faults to image-consuming tools
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
def test_clip_dupes_corrupt_video(ws, tmp_path, text_mp4):
    folder = tmp_path / "clips"
    folder.mkdir()
    shutil.copy(text_mp4, folder / "a.mp4")
    shutil.copy(text_mp4, folder / "b.mp4")
    result = _fn(clip_dupes.clips_find_duplicates)(str(ws), str(folder))
    # Either a structured error, or a graceful success reporting zero comparable
    # clips -- but NEVER a crash / traceback.
    assert isinstance(result, dict)
    dumped = json.dumps(result, default=str)
    assert "Traceback" not in dumped and 'File "' not in dumped
    if result.get("status") == "error":
        _assert_structured_error(result)
