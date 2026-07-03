"""FFmpeg-gated integration tests for the five analysis/sorting tools.

Generates synthetic fixtures with FFmpeg (a mid-clip scene change via concat, a
clip with black + frozen sections, sine audio with a silence gap) and proves
each tool's detection actually fires. Lives in ``tests/integration/`` (not
``external/``) because it only uses the local FFmpeg install -- no network.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ffmpeg_available = shutil.which("ffmpeg") is not None
ffprobe_available = shutil.which("ffprobe") is not None
pytestmark = pytest.mark.skipif(
    not (ffmpeg_available and ffprobe_available),
    reason="ffmpeg/ffprobe not available on PATH",
)


def _invoke(tool, *args, **kwargs):
    fn = getattr(tool, "fn", tool)
    return fn(*args, **kwargs)


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _png_dims(path: Path) -> tuple[int, int]:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    w, h = proc.stdout.strip().split(",")
    return int(w), int(h)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "media" / "raw").mkdir(parents=True)
    (tmp_path / "media" / "processed").mkdir(parents=True)
    (tmp_path / "reports").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def scene_clip(workspace: Path) -> Path:
    """testsrc (2s) hard-cut to mandelbrot (2s) -> scene change at t=2."""
    a = workspace / "a.mp4"
    b = workspace / "b.mp4"
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=2",
          "-pix_fmt", "yuv420p", str(a)])
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "mandelbrot=size=320x240:rate=10:end_pts=2",
          "-t", "2", "-pix_fmt", "yuv420p", str(b)])
    lst = workspace / "list.txt"
    lst.write_text(f"file '{a}'\nfile '{b}'\n")
    out = workspace / "media" / "raw" / "scene.mp4"
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    return out


@pytest.fixture()
def junk_clip(workspace: Path) -> Path:
    """1s black + 2s static red (frozen) + 1s testsrc -> black + freeze."""
    blk = workspace / "blk.mp4"
    frz = workspace / "frz.mp4"
    mov = workspace / "mov.mp4"
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:size=320x240:rate=10:duration=1",
          "-pix_fmt", "yuv420p", str(blk)])
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:size=320x240:rate=10:duration=2",
          "-pix_fmt", "yuv420p", str(frz)])
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=1",
          "-pix_fmt", "yuv420p", str(mov)])
    lst = workspace / "junk_list.txt"
    lst.write_text(f"file '{blk}'\nfile '{frz}'\nfile '{mov}'\n")
    out = workspace / "media" / "raw" / "junk.mp4"
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    return out


@pytest.fixture()
def silence_video(workspace: Path) -> Path:
    """6s testsrc w/ forced keyframes + audio: tone / 1s silence / tone / 1s silence / tone."""
    out = workspace / "media" / "raw" / "takes.mp4"
    audio = (
        "sine=frequency=440:duration=1.5[t1];"
        "anullsrc=r=44100:cl=stereo:d=1[s1];"
        "sine=frequency=440:duration=1.5[t2];"
        "anullsrc=r=44100:cl=stereo:d=1[s2];"
        "sine=frequency=440:duration=1[t3];"
        "[t1][s1][t2][s2][t3]concat=n=5:v=0:a=1[a]"
    )
    _run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=6",
        "-filter_complex", audio,
        "-map", "0:v", "-map", "[a]",
        "-c:v", "libx264", "-g", "10",
        "-force_key_frames", "expr:gte(t,n_forced*1)",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        str(out),
    ])
    return out


@pytest.fixture()
def loud_clip(workspace: Path) -> Path:
    out = workspace / "media" / "raw" / "tone.wav"
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
          "-c:a", "pcm_s16le", str(out)])
    return out


# ---------------------------------------------------------------------------
# 1. media_thumbnail_sheet
# ---------------------------------------------------------------------------

class TestThumbnailSheet:
    def test_frames_and_sheet_exist_with_dims(self, workspace, scene_clip):
        from workshop_video_brain.edit_mcp.server.bundles.thumbnail_sheet import (
            media_thumbnail_sheet,
        )
        res = _invoke(media_thumbnail_sheet, str(workspace),
                      source="media/raw/scene.mp4", frames=6, width=320)
        assert res["status"] == "success", res
        data = res["data"]
        # Frame files exist at requested width.
        assert data["frame_count"] >= 1
        for fp in data["frame_paths"]:
            assert Path(fp).exists()
            assert _png_dims(Path(fp))[0] == 320
        # Contact sheet exists; 3x2 grid at 320 wide tiles -> 960px wide.
        assert data["sheet_path"] and Path(data["sheet_path"]).exists()
        assert _png_dims(Path(data["sheet_path"]))[0] == 960


# ---------------------------------------------------------------------------
# 2. clips_qc_scan
# ---------------------------------------------------------------------------

class TestQCScan:
    def test_black_and_freeze_flagged(self, workspace, junk_clip):
        from workshop_video_brain.edit_mcp.server.bundles.qc_scan import clips_qc_scan
        res = _invoke(clips_qc_scan, str(workspace), "media/raw/junk.mp4")
        assert res["status"] == "success", res
        result = res["data"]["results"][0]
        assert result["verdict"] == "flagged"
        assert "black_frames" in result["reasons"]
        assert "frozen" in result["reasons"]
        assert result["metrics"]["black_regions"] >= 1
        assert Path(res["data"]["report_path"]).exists()


# ---------------------------------------------------------------------------
# 3. clips_detect_scenes
# ---------------------------------------------------------------------------

class TestDetectScenes:
    def test_scene_cut_found_near_t2(self, workspace, scene_clip):
        from workshop_video_brain.edit_mcp.server.bundles.scene_detect import (
            clips_detect_scenes,
        )
        res = _invoke(clips_detect_scenes, str(workspace),
                      source="media/raw/scene.mp4", threshold=0.3)
        assert res["status"] == "success", res
        cuts = res["data"]["cuts"]
        assert cuts, "expected at least one scene cut"
        # A cut within 0.5s of the 2.0s boundary.
        assert any(abs(c["time"] - 2.0) <= 0.5 for c in cuts), cuts
        assert Path(res["data"]["report_path"]).exists()


# ---------------------------------------------------------------------------
# 4. media_segment_at_silence
# ---------------------------------------------------------------------------

class TestSegmentAtSilence:
    def test_splits_at_silences(self, workspace, silence_video):
        from workshop_video_brain.edit_mcp.server.bundles.silence_segment import (
            media_segment_at_silence,
        )
        res = _invoke(media_segment_at_silence, str(workspace),
                      source="media/raw/takes.mp4",
                      noise_db=-30, min_silence=0.6, min_segment=1.0)
        assert res["status"] == "success", res
        data = res["data"]
        # Two silence gaps -> up to 3 takes; at least 2 segments produced.
        assert data["segment_count"] >= 2, data
        assert len(data["segment_paths"]) == data["segment_count"]
        for p in data["segment_paths"]:
            assert Path(p).exists()
            # Output lives under media/processed, never media/raw.
            assert "media/processed" in p
            assert "media/raw" not in p


# ---------------------------------------------------------------------------
# 5. audio_loudness_scan
# ---------------------------------------------------------------------------

class TestLoudnessScan:
    def test_lufs_measured_in_range(self, workspace, loud_clip):
        from workshop_video_brain.edit_mcp.server.bundles.loudness_scan import (
            audio_loudness_scan,
        )
        res = _invoke(audio_loudness_scan, str(workspace), "media/raw/tone.wav")
        assert res["status"] == "success", res
        row = res["data"]["results"][0]
        assert row["ok"] is True
        # A -3 dB full-scale 440 Hz sine sits well within a sane LUFS window.
        assert -30.0 < row["lufs"] < -5.0, row
        assert row["true_peak"] is not None
        assert Path(res["data"]["report_path"]).exists()
