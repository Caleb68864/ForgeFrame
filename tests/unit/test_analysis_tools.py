"""Unit tests for the five analysis/sorting pipelines + their MCP tools.

Pure command construction, threshold parsing, report shaping, and tool
registration. No FFmpeg execution -- subprocess-facing helpers are exercised
via dry-run paths or mocks.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from workshop_video_brain.edit_mcp.pipelines import (
    analysis_common,
    loudness_scan,
    qc_scan,
    scene_detect,
    silence_segment,
    thumbnail_sheet,
)


# ---------------------------------------------------------------------------
# Registration helpers (FastMCP interface variants + .fn unwrap)
# ---------------------------------------------------------------------------

from tests._testkit import call_tool as _invoke  # noqa: E402
from tests._testkit import registered_tool_names as _tool_names  # noqa: E402


# ---------------------------------------------------------------------------
# analysis_common
# ---------------------------------------------------------------------------

class TestAnalysisCommon:
    def test_resolve_relative(self, tmp_path):
        p = analysis_common.resolve_under_workspace(tmp_path, "media/raw/a.mp4")
        assert p == tmp_path / "media" / "raw" / "a.mp4"

    def test_resolve_absolute_kept(self, tmp_path):
        p = analysis_common.resolve_under_workspace(tmp_path, "/abs/a.mp4")
        assert p == Path("/abs/a.mp4")

    def test_iter_single_file(self, tmp_path):
        f = tmp_path / "a.mp4"
        f.write_bytes(b"\x00")
        assert analysis_common.iter_media_files(f) == [f]

    def test_iter_directory_sorted(self, tmp_path):
        (tmp_path / "b.mp4").write_bytes(b"\x00")
        (tmp_path / "a.mov").write_bytes(b"\x00")
        (tmp_path / "note.txt").write_text("x")
        got = analysis_common.iter_media_files(tmp_path)
        assert [p.name for p in got] == ["a.mov", "b.mp4"]

    def test_iter_missing(self, tmp_path):
        assert analysis_common.iter_media_files(tmp_path / "nope") == []

    def test_write_json_report(self, tmp_path):
        p = analysis_common.write_json_report(tmp_path, "r.json", {"a": 1})
        assert p == tmp_path / "reports" / "r.json"
        assert json.loads(p.read_text())["a"] == 1


# ---------------------------------------------------------------------------
# thumbnail_sheet
# ---------------------------------------------------------------------------

class TestThumbnailSheet:
    def test_grid_dimensions_square(self):
        assert thumbnail_sheet.grid_dimensions(9) == (3, 3)

    def test_grid_dimensions_six(self):
        cols, rows = thumbnail_sheet.grid_dimensions(6)
        assert cols * rows >= 6 and (cols, rows) == (3, 2)

    def test_compute_batch_size(self):
        assert thumbnail_sheet.compute_batch_size(60, 6) == 10
        assert thumbnail_sheet.compute_batch_size(0, 6) == 1
        assert thumbnail_sheet.compute_batch_size(3, 6) == 1

    def test_frames_filter(self):
        assert thumbnail_sheet.build_frames_filter(10, 320) == "thumbnail=n=10,scale=320:-1"

    def test_sheet_filter(self):
        f = thumbnail_sheet.build_sheet_filter(10, 320, 3, 2)
        assert f == "thumbnail=n=10,scale=320:-1,tile=3x2"

    def test_sheet_output_dir(self, tmp_path):
        d = thumbnail_sheet.sheet_output_dir(tmp_path, "media/raw/clip.mp4")
        assert d == tmp_path / "reports" / "thumbnails" / "clip"

    def test_generate_dry_run_builds_commands(self, tmp_path):
        with patch.object(thumbnail_sheet, "_total_frames", return_value=60):
            res = thumbnail_sheet.generate_thumbnail_sheet(
                tmp_path / "clip.mp4", tmp_path / "out", frames=6, dry_run=True
            )
        assert res["success"] is True
        assert res["batch"] == 10
        assert res["grid_dims"] == [3, 2]
        assert "thumbnail=n=10" in res["commands"]["frames"][res["commands"]["frames"].index("-vf") + 1]
        assert "tile=3x2" in res["commands"]["sheet"][res["commands"]["sheet"].index("-vf") + 1]


# ---------------------------------------------------------------------------
# qc_scan
# ---------------------------------------------------------------------------

class TestQCScan:
    def test_video_filter_has_all_stages(self, tmp_path):
        f = qc_scan.build_video_filter(tmp_path / "s.txt", 0.5, 0.10, -60.0, 0.5)
        for stage in ("blackdetect=d=0.5", "freezedetect=n=-60.0dB:d=0.5",
                      "signalstats", "blurdetect", "metadata=print:file="):
            assert stage in f

    def test_audio_filter(self):
        assert qc_scan.build_audio_filter(-30.0, 0.6) == "silencedetect=noise=-30.0dB:d=0.6"

    def test_scan_command_shape(self, tmp_path):
        cmd = qc_scan.build_scan_command(tmp_path / "c.mp4", tmp_path / "s.txt", qc_scan.DEFAULTS)
        assert cmd[0] == "ffmpeg"
        assert "-vf" in cmd and "-af" in cmd
        assert cmd[-3:] == ["-f", "null", "-"]

    def test_parse_black(self):
        s = "black_start:1.0 black_end:2.5 black_duration:1.5"
        assert qc_scan.parse_black_regions(s) == [(1.0, 2.5)]

    def test_parse_freeze(self):
        s = ("lavfi.freezedetect.freeze_start: 0\n"
             "lavfi.freezedetect.freeze_end: 1\n")
        assert qc_scan.parse_freeze_regions(s) == [(0.0, 1.0)]

    def test_parse_silence_ratio(self):
        s = "silence_start: 1.0\nsilence_end: 2.0\n"
        assert qc_scan.parse_silence_ratio(s, 4.0) == 0.25

    def test_parse_signalstats(self):
        text = ("lavfi.signalstats.YMIN=16\nlavfi.signalstats.YAVG=20\nlavfi.signalstats.YMAX=200\n"
                "lavfi.signalstats.YMIN=10\nlavfi.signalstats.YAVG=40\nlavfi.signalstats.YMAX=255\n")
        got = qc_scan.parse_signalstats(text)
        assert got["yavg_avg"] == 30.0
        assert got["ymin"] == 10.0
        assert got["ymax"] == 255.0

    def test_parse_blur_skips_nan(self):
        text = "lavfi.blur=-nan\nlavfi.blur=5.0\nlavfi.blur=15.0\n"
        assert qc_scan.parse_blur(text) == 10.0

    def test_classify_usable(self):
        metrics = {"black_regions": 0, "freeze_regions": 0, "blur_avg": 5.0,
                   "yavg_avg": 120.0, "silence_ratio": 0.1}
        verdict, reasons = qc_scan.classify(metrics, qc_scan.DEFAULTS)
        assert verdict == "usable" and reasons == []

    def test_classify_flags_each(self):
        metrics = {"black_regions": 1, "freeze_regions": 1, "blur_avg": 31.0,
                   "yavg_avg": 10.0, "silence_ratio": 0.9}
        verdict, reasons = qc_scan.classify(metrics, qc_scan.DEFAULTS)
        assert verdict == "flagged"
        assert set(reasons) == {"black_frames", "frozen", "blurry", "underexposed", "mostly_silent"}

    def test_classify_overexposed(self):
        metrics = {"black_regions": 0, "freeze_regions": 0, "blur_avg": 5.0,
                   "yavg_avg": 250.0, "silence_ratio": 0.0}
        _, reasons = qc_scan.classify(metrics, qc_scan.DEFAULTS)
        assert reasons == ["overexposed"]

    def test_verdict_to_rating(self):
        assert qc_scan.verdict_to_rating("usable") == 5
        assert qc_scan.verdict_to_rating("flagged") == 1

    def test_scan_clip_dry_run(self, tmp_path):
        res = qc_scan.scan_clip(tmp_path / "c.mp4", dry_run=True)
        assert res["success"] is True
        assert res["command"][0] == "ffmpeg"

    def test_scan_batch_tallies(self):
        with patch.object(qc_scan, "scan_clip") as mock:
            mock.side_effect = [
                {"verdict": "usable"}, {"verdict": "flagged"}, {"verdict": "usable"},
            ]
            rep = qc_scan.scan_batch([Path("a"), Path("b"), Path("c")])
        assert rep["clips_scanned"] == 3
        assert rep["usable"] == 2 and rep["flagged"] == 1


# ---------------------------------------------------------------------------
# scene_detect
# ---------------------------------------------------------------------------

class TestSceneDetect:
    def test_select_filter_uses_threshold(self, tmp_path):
        f = scene_detect.build_select_filter(0.4, tmp_path / "s.txt")
        assert "select='gt(scene\\,0.4)'" in f
        assert "metadata=print:file=" in f

    def test_select_filter_clamps(self, tmp_path):
        assert "gt(scene\\,1)" in scene_detect.build_select_filter(5.0, tmp_path / "s.txt")
        assert "gt(scene\\,0)" in scene_detect.build_select_filter(-1.0, tmp_path / "s.txt")

    def test_scan_command(self, tmp_path):
        cmd = scene_detect.build_scan_command(tmp_path / "s.mp4", 0.4, tmp_path / "s.txt")
        assert any("select=" in c for c in cmd)
        assert cmd[-3:] == ["-f", "null", "-"]

    def test_parse_scene_scores(self):
        s = ("frame:0    pts:20480   pts_time:2\n"
             "lavfi.scene_score=0.657581\n"
             "frame:1    pts:56320   pts_time:5.5\n"
             "lavfi.scene_score=0.5\n")
        cuts = scene_detect.parse_scene_scores(s)
        assert cuts == [{"time": 2.0, "score": 0.6576}, {"time": 5.5, "score": 0.5}]

    def test_detect_dry_run(self, tmp_path):
        res = scene_detect.detect_scenes(tmp_path / "s.mp4", dry_run=True)
        assert res["success"] is True and res["cuts"] == []


# ---------------------------------------------------------------------------
# silence_segment
# ---------------------------------------------------------------------------

class TestSilenceSegment:
    def test_cut_points_midpoints(self):
        cuts = silence_segment.compute_cut_points([(2.0, 3.0), (6.0, 7.0)], 10.0, 2.0)
        assert cuts == [2.5, 6.5]

    def test_cut_points_min_segment_spacing(self):
        # Second silence too close to first accepted cut -> dropped.
        cuts = silence_segment.compute_cut_points([(2.0, 3.0), (3.2, 3.6)], 10.0, 2.0)
        assert cuts == [2.5]

    def test_cut_points_end_guard(self):
        # Midpoint 9.5 leaves <2s to end -> dropped.
        cuts = silence_segment.compute_cut_points([(9.0, 10.0)], 10.0, 2.0)
        assert cuts == []

    def test_takes_dir(self, tmp_path):
        d = silence_segment.takes_dir(tmp_path, "media/raw/lecture.mov")
        assert d == tmp_path / "media" / "processed" / "lecture_takes"

    def test_segment_command(self, tmp_path):
        cmd = silence_segment.build_segment_command(
            tmp_path / "in.mp4", tmp_path / "out_%03d.mp4", [2.5, 6.5]
        )
        assert "-c" in cmd and "copy" in cmd
        assert "segment" in cmd
        assert cmd[cmd.index("-segment_times") + 1] == "2.5,6.5"

    def test_segment_dry_run(self, tmp_path):
        with patch.object(silence_segment, "detect_silence", return_value=[(2.0, 3.0)]), \
             patch.object(silence_segment, "probe_media") as mp:
            mp.return_value.duration = 10.0
            res = silence_segment.segment_at_silence(
                tmp_path / "in.mp4", tmp_path / "takes", dry_run=True
            )
        assert res["success"] is True
        assert res["cut_points"] == [2.5]
        assert res["segment_count"] == 2


# ---------------------------------------------------------------------------
# loudness_scan
# ---------------------------------------------------------------------------

class TestLoudnessScan:
    def test_measure_clip_ok(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import LoudnessResult
        with patch.object(loudness_scan, "measure_loudness",
                          return_value=LoudnessResult(-22.4, -18.1, 0.2)):
            row = loudness_scan.measure_clip(tmp_path / "a.wav")
        assert row["ok"] is True
        assert row["lufs"] == -22.4 and row["true_peak"] == -18.1 and row["lra"] == 0.2

    def test_measure_clip_failure(self, tmp_path):
        with patch.object(loudness_scan, "measure_loudness", return_value=None):
            row = loudness_scan.measure_clip(tmp_path / "a.wav")
        assert row["ok"] is False and row["lufs"] is None

    def test_summarize(self):
        rows = [
            {"ok": True, "lufs": -20.0}, {"ok": True, "lufs": -16.0},
            {"ok": False, "lufs": None},
        ]
        s = loudness_scan.summarize(rows)
        assert s["measured"] == 2
        assert s["avg_lufs"] == -18.0
        assert s["lufs_spread"] == 4.0

    def test_scan_loudness(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import LoudnessResult
        with patch.object(loudness_scan, "measure_loudness",
                          return_value=LoudnessResult(-20.0, -2.0, 5.0)):
            rep = loudness_scan.scan_loudness([tmp_path / "a.wav", tmp_path / "b.wav"])
        assert rep["clips_scanned"] == 2
        assert rep["summary"]["measured"] == 2


# ---------------------------------------------------------------------------
# MCP registration + error paths
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_all_five_registered(self):
        from workshop_video_brain.server import mcp
        import workshop_video_brain.edit_mcp.server.bundles  # noqa: F401
        names = _tool_names(mcp)
        for tool in ("media_thumbnail_sheet", "clips_qc_scan", "clips_detect_scenes",
                     "media_segment_at_silence", "audio_loudness_scan"):
            assert tool in names

    def test_thumbnail_requires_source(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles.thumbnail_sheet import (
            media_thumbnail_sheet,
        )
        res = _invoke(media_thumbnail_sheet, str(tmp_path))
        assert res["status"] == "error" and "source" in res["message"]

    def test_qc_scan_no_media(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles.qc_scan import clips_qc_scan
        res = _invoke(clips_qc_scan, str(tmp_path), "media/raw")
        assert res["status"] == "error" and "No media" in res["message"]

    def test_scene_requires_source(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles.scene_detect import (
            clips_detect_scenes,
        )
        res = _invoke(clips_detect_scenes, str(tmp_path))
        assert res["status"] == "error" and "source" in res["message"]

    def test_segment_missing_file(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles.silence_segment import (
            media_segment_at_silence,
        )
        res = _invoke(media_segment_at_silence, str(tmp_path), "media/raw/nope.mp4")
        assert res["status"] == "error" and "not found" in res["message"].lower()

    def test_loudness_no_media(self, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles.loudness_scan import (
            audio_loudness_scan,
        )
        res = _invoke(audio_loudness_scan, str(tmp_path), "media/raw")
        assert res["status"] == "error" and "No media" in res["message"]
