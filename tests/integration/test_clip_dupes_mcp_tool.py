"""Integration tests for the ``clips_find_duplicates`` MCP bundle tool.

Builds synthetic fixtures with FFmpeg -- two near-identical ``testsrc`` clips
(one trimmed + re-encoded) and one visually different clip -- and proves the
phash method groups the pair and excludes the third.  Also exercises the
MPEG-7 ``signature`` method on a re-encoded pair when the filter is available.
FFmpeg-gated (skipped when ffmpeg / ffprobe are unavailable).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("fastmcp", reason="fastmcp not installed")
pytest.importorskip("PIL", reason="Pillow not installed")

ffmpeg_available = (
    shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
)
pytestmark = pytest.mark.skipif(
    not ffmpeg_available, reason="ffmpeg/ffprobe not available on PATH"
)

from workshop_video_brain.edit_mcp.server.bundles import clip_dupes as bundle


def _callable(obj):
    return getattr(obj, "fn", obj)


clips_find_duplicates = _callable(bundle.clips_find_duplicates)


def _ffmpeg(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", *args], capture_output=True, check=True)


def _make_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "reports").mkdir(parents=True)
    (ws / "media" / "raw").mkdir(parents=True)
    return ws


def _testsrc(path: Path, duration: float, rate: int = 15, size: str = "320x240") -> None:
    _ffmpeg([
        "-f", "lavfi",
        "-i", f"testsrc=size={size}:rate={rate}:duration={duration}",
        "-pix_fmt", "yuv420p", str(path),
    ])


def _mandelbrot(path: Path, duration: float, rate: int = 15, size: str = "320x240") -> None:
    _ffmpeg([
        "-f", "lavfi",
        "-i", f"mandelbrot=size={size}:rate={rate}",
        "-t", str(duration), "-pix_fmt", "yuv420p", str(path),
    ])


class TestPhashMethod:
    def _build(self, tmp_path: Path) -> tuple[Path, Path]:
        ws = _make_workspace(tmp_path)
        src = tmp_path / "clips"
        src.mkdir()
        _testsrc(src / "a.mp4", 3.0)
        # b: near-duplicate of a -- trimmed and re-encoded at a different CRF
        _ffmpeg(["-i", str(src / "a.mp4"), "-t", "2.5", "-c:v", "libx264",
                 "-crf", "30", str(src / "b.mp4")])
        # c: visually different
        _mandelbrot(src / "c.mp4", 3.0)
        return ws, src

    def test_groups_near_duplicates_excludes_different(self, tmp_path):
        ws, src = self._build(tmp_path)
        res = clips_find_duplicates(
            workspace_path=str(ws), source_dir=str(src),
            method="phash", frames_per_clip=5, threshold=10,
        )
        assert res["status"] == "success", res
        data = res["data"]
        assert data["clips_scanned"] == 3
        assert data["duplicate_group_count"] == 1

        group = data["duplicate_groups"][0]
        members = {m["clip"] for m in group["members"]}
        assert members == {"a.mp4", "b.mp4"}
        assert "c.mp4" not in members
        # near-dup similarity should be high
        for m in group["members"]:
            assert m["similarity_pct"] >= 80.0

    def test_writes_json_report_under_reports(self, tmp_path):
        ws, src = self._build(tmp_path)
        res = clips_find_duplicates(
            workspace_path=str(ws), source_dir=str(src), method="phash",
        )
        report = Path(res["data"]["report"])
        assert report.exists()
        assert report.parent.name == "reports"
        payload = json.loads(report.read_text())
        assert payload["method"] == "phash"
        assert payload["clips_scanned"] == 3
        assert len(payload["duplicate_groups"]) == 1
        # nothing was written into media/raw
        assert list((ws / "media" / "raw").iterdir()) == []

    def test_strict_threshold_splits_pair(self, tmp_path):
        ws, src = self._build(tmp_path)
        res = clips_find_duplicates(
            workspace_path=str(ws), source_dir=str(src),
            method="phash", threshold=0,
        )
        assert res["status"] == "success", res
        # at threshold 0 even the near-dup (distance ~0.7) is not grouped
        assert res["data"]["duplicate_group_count"] == 0


class TestSignatureMethod:
    """The MPEG-7 ``signature`` filter's verdict emission is nondeterministic
    across runs, so these tests assert the *contract* (gating + a valid report)
    rather than an exact grouping. The parser and command construction are
    proven deterministically in ``tests/unit/test_clip_dupes.py``."""

    def test_gating_error_when_filter_absent(self, tmp_path, monkeypatch):
        # Force the "no signature filter" path deterministically.
        monkeypatch.setattr(bundle._cd, "has_signature_filter", lambda: False)
        ws = _make_workspace(tmp_path)
        src = tmp_path / "clips"
        src.mkdir()
        _testsrc(src / "a.mp4", 1.0)
        _testsrc(src / "b.mp4", 1.0)
        res = clips_find_duplicates(
            workspace_path=str(ws), source_dir=str(src), method="signature",
        )
        assert res["status"] == "error"
        assert "signature" in res["message"].lower()
        # actionable alternative now lives in the suggestion field
        assert "phash" in res.get("suggestion", "").lower()

    def test_signature_method_runs_and_reports(self, tmp_path):
        if not bundle._cd.has_signature_filter():
            pytest.skip("ffmpeg build lacks the signature filter")
        ws = _make_workspace(tmp_path)
        src = tmp_path / "clips"
        src.mkdir()
        _testsrc(src / "a.mp4", 6.0, rate=25)
        shutil.copyfile(src / "a.mp4", src / "b.mp4")  # a genuine duplicate
        _mandelbrot(src / "c.mp4", 6.0, rate=25)

        res = clips_find_duplicates(
            workspace_path=str(ws), source_dir=str(src), method="signature",
        )
        assert res["status"] == "success", res
        data = res["data"]
        assert data["method"] == "signature"
        assert data["clips_scanned"] == 3
        report = Path(data["report"])
        assert report.exists() and report.parent.name == "reports"
        # the different clip must never be grouped with the duplicate pair
        for group in data["duplicate_groups"]:
            assert "c.mp4" not in {m["clip"] for m in group["members"]}


class TestErrors:
    def test_unknown_method(self, tmp_path):
        ws = _make_workspace(tmp_path)
        src = tmp_path / "clips"
        src.mkdir()
        _testsrc(src / "a.mp4", 1.0)
        _testsrc(src / "b.mp4", 1.0)
        res = clips_find_duplicates(
            workspace_path=str(ws), source_dir=str(src), method="bogus",
        )
        assert res["status"] == "error"
        assert "method" in res["message"].lower()

    def test_too_few_clips(self, tmp_path):
        ws = _make_workspace(tmp_path)
        src = tmp_path / "clips"
        src.mkdir()
        _testsrc(src / "only.mp4", 1.0)
        res = clips_find_duplicates(
            workspace_path=str(ws), source_dir=str(src),
        )
        assert res["status"] == "error"
        assert "at least 2" in res["message"]

    def test_missing_source_dir(self, tmp_path):
        ws = _make_workspace(tmp_path)
        res = clips_find_duplicates(
            workspace_path=str(ws), source_dir=str(tmp_path / "nope"),
        )
        assert res["status"] == "error"


class TestRegistration:
    def test_registered_via_list_tools(self):
        import asyncio
        import inspect
        from workshop_video_brain import server

        getter = getattr(server.mcp, "list_tools", None) or server.mcp.get_tools
        result = getter()
        if inspect.iscoroutine(result):
            result = asyncio.run(result)
        names = (
            list(result.keys()) if isinstance(result, dict)
            else [t.name for t in result]
        )
        assert "clips_find_duplicates" in names
