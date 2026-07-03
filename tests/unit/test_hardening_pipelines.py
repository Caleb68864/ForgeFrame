"""Hardening Pass 1 -- pipeline/adapter plumbing.

Verifies that non-Kdenlive plumbing fails GRACEFULLY but LOUDLY:

* subprocess runners raise TYPED exceptions carrying path/context,
* a missing binary is distinguished from a command failure,
* command failures carry the stderr TAIL (not the full dump),
* long-running subprocess calls have timeouts that raise a clear error,
* the media/raw write-guard can never be bypassed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    DEFAULT_TIMEOUT_SECONDS,
    FFmpegCommandError,
    FFmpegNotFound,
    FFmpegResult,
    FFmpegTimeout,
    _stderr_tail,
    run_ffmpeg,
)


# ---------------------------------------------------------------------------
# _stderr_tail helper
# ---------------------------------------------------------------------------
class TestStderrTail:
    def test_returns_last_lines_only(self):
        text = "\n".join(f"line{i}" for i in range(50))
        tail = _stderr_tail(text, max_lines=10)
        assert "line49" in tail
        assert "line40" in tail
        assert "line39" not in tail  # older lines dropped
        assert tail.count("\n") == 9  # exactly 10 lines

    def test_skips_blank_lines(self):
        assert _stderr_tail("a\n\n\nb\n\n") == "a\nb"


# ---------------------------------------------------------------------------
# run_ffmpeg -- the linchpin runner
# ---------------------------------------------------------------------------
class TestRunFfmpeg:
    def test_default_timeout_is_generous(self):
        # Renders/minterpolate can be slow; ceiling exists but is large.
        assert DEFAULT_TIMEOUT_SECONDS >= 1800

    def test_missing_binary_raises_typed_with_install_hint(self, tmp_path, monkeypatch):
        def _boom(*a, **k):
            raise FileNotFoundError("ffmpeg")

        monkeypatch.setattr(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.runner.subprocess.run",
            _boom,
        )
        with pytest.raises(FFmpegNotFound) as exc:
            run_ffmpeg(["-vf", "scale=2:2"], tmp_path / "in.mp4", tmp_path / "out.mp4")
        msg = str(exc.value)
        assert "not found on PATH" in msg
        assert "install" in msg.lower()  # actionable hint
        assert "in.mp4" in msg  # path context

    def test_timeout_raises_typed_naming_elapsed(self, tmp_path, monkeypatch):
        def _slow(*a, **k):
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=5)

        monkeypatch.setattr(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.runner.subprocess.run",
            _slow,
        )
        with pytest.raises(FFmpegTimeout) as exc:
            run_ffmpeg([], tmp_path / "clip.mp4", tmp_path / "out.mp4", timeout=5)
        assert "timed out" in str(exc.value)
        assert "clip.mp4" in str(exc.value)

    def test_command_failure_is_result_not_raise(self, tmp_path, monkeypatch):
        # A nonzero exit is a *command* failure the caller inspects, NOT a raise.
        class _CP:
            returncode = 1
            stdout = ""
            stderr = "\n".join(f"err{i}" for i in range(30))

        monkeypatch.setattr(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.runner.subprocess.run",
            lambda *a, **k: _CP(),
        )
        result = run_ffmpeg([], tmp_path / "in.mp4", tmp_path / "out.mp4")
        assert isinstance(result, FFmpegResult)
        assert result.success is False
        # stderr tail exposes the diagnosable last lines
        assert "err29" in result.stderr_tail
        assert "err0" not in result.stderr_tail

    def test_dry_run_skips_subprocess(self, tmp_path):
        result = run_ffmpeg([], tmp_path / "in.mp4", tmp_path / "out.mp4", dry_run=True)
        assert result.success is True
        assert result.command[0] == "ffmpeg"


# ---------------------------------------------------------------------------
# probe.probe_media -- binary-missing vs command-failure distinction
# ---------------------------------------------------------------------------
class TestProbeHardening:
    def _existing_file(self, tmp_path) -> Path:
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"\x00" * 1024)
        return f

    def test_missing_media_file_raises_filenotfound(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg import probe

        with pytest.raises(FileNotFoundError) as exc:
            probe.probe_media(tmp_path / "nope.mp4")
        assert "does not exist" in str(exc.value)
        assert "nope.mp4" in str(exc.value)

    def test_missing_ffprobe_binary_raises_typed(self, tmp_path, monkeypatch):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg import probe

        f = self._existing_file(tmp_path)
        monkeypatch.setattr(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.subprocess.run",
            lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("ffprobe")),
        )
        with pytest.raises(FFmpegNotFound) as exc:
            probe.probe_media(f)
        assert "ffprobe" in str(exc.value)
        assert str(f) in str(exc.value)

    def test_command_failure_carries_stderr_tail(self, tmp_path, monkeypatch):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg import probe

        f = self._existing_file(tmp_path)
        long_stderr = "\n".join(f"probe_err{i}" for i in range(40))

        def _fail(*a, **k):
            raise subprocess.CalledProcessError(
                returncode=1, cmd="ffprobe", stderr=long_stderr
            )

        monkeypatch.setattr(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.subprocess.run",
            _fail,
        )
        with pytest.raises(FFmpegCommandError) as exc:
            probe.probe_media(f)
        msg = str(exc.value)
        assert "probe_err39" in msg  # tail present
        assert "probe_err0" not in msg  # head trimmed
        assert str(f) in msg

    def test_scan_directory_reraises_missing_binary(self, tmp_path, monkeypatch):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg import probe

        (tmp_path / "a.mp4").write_bytes(b"\x00" * 16)
        monkeypatch.setattr(
            probe,
            "probe_media",
            lambda p: (_ for _ in ()).throw(FFmpegNotFound("ffprobe missing")),
        )
        # A missing binary is an environment error -- must not be swallowed
        # per-file into an empty list.
        with pytest.raises(FFmpegNotFound):
            probe.scan_directory(tmp_path)


# ---------------------------------------------------------------------------
# proxy / whisper -- missing source + missing binary
# ---------------------------------------------------------------------------
class TestProxyHardening:
    def test_missing_source_raises_filenotfound(self, tmp_path):
        from workshop_video_brain.core.models import MediaAsset
        from workshop_video_brain.edit_mcp.adapters.ffmpeg import proxy

        asset = MediaAsset(path=str(tmp_path / "gone.mp4"), media_type="video")
        with pytest.raises(FileNotFoundError) as exc:
            proxy.generate_proxy(asset, tmp_path / "proxies")
        assert "gone.mp4" in str(exc.value)

    def test_missing_binary_raises_typed(self, tmp_path, monkeypatch):
        from workshop_video_brain.core.models import MediaAsset
        from workshop_video_brain.edit_mcp.adapters.ffmpeg import proxy

        src = tmp_path / "src.mp4"
        src.write_bytes(b"\x00" * 32)
        asset = MediaAsset(path=str(src), media_type="video")
        monkeypatch.setattr(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy.subprocess.run",
            lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("ffmpeg")),
        )
        with pytest.raises(FFmpegNotFound):
            proxy.generate_proxy(asset, tmp_path / "proxies")


class TestWhisperExtractHardening:
    def test_missing_source_raises_filenotfound(self, tmp_path):
        from workshop_video_brain.edit_mcp.adapters.stt import whisper_engine

        with pytest.raises(FileNotFoundError) as exc:
            whisper_engine.extract_audio(tmp_path / "no.mp4", tmp_path / "o.wav")
        assert "no.mp4" in str(exc.value)

    def test_command_failure_carries_tail(self, tmp_path, monkeypatch):
        from workshop_video_brain.edit_mcp.adapters.stt import whisper_engine

        src = tmp_path / "vid.mp4"
        src.write_bytes(b"\x00" * 32)
        long_stderr = "\n".join(f"x{i}" for i in range(40))

        def _fail(*a, **k):
            raise subprocess.CalledProcessError(
                returncode=2, cmd="ffmpeg", stderr=long_stderr
            )

        monkeypatch.setattr(
            "workshop_video_brain.edit_mcp.adapters.stt.whisper_engine.subprocess.run",
            _fail,
        )
        with pytest.raises(FFmpegCommandError) as exc:
            whisper_engine.extract_audio(src, tmp_path / "o.wav")
        assert "x39" in str(exc.value)
        assert "x0" not in str(exc.value)


class TestSilenceHardening:
    def test_missing_binary_raises_typed(self, tmp_path, monkeypatch):
        from workshop_video_brain.edit_mcp.adapters.ffmpeg import silence

        monkeypatch.setattr(
            "workshop_video_brain.edit_mcp.adapters.ffmpeg.silence.subprocess.run",
            lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("ffmpeg")),
        )
        with pytest.raises(FFmpegNotFound):
            silence.detect_silence(tmp_path / "a.wav")


# ---------------------------------------------------------------------------
# media/raw write-guard -- can never be bypassed
# ---------------------------------------------------------------------------
class TestMediaRawWriteGuard:
    def test_assert_not_protected_blocks_media_raw(self, tmp_path):
        from workshop_video_brain.workspace import snapshot

        with pytest.raises(ValueError) as exc:
            snapshot._assert_not_protected(tmp_path, tmp_path / "media" / "raw" / "x.mp4")
        assert "protected" in str(exc.value).lower()

    def test_assert_not_protected_blocks_projects_source(self, tmp_path):
        from workshop_video_brain.workspace import snapshot

        with pytest.raises(ValueError):
            snapshot._assert_not_protected(
                tmp_path, tmp_path / "projects" / "source" / "p.kdenlive"
            )

    def test_assert_not_protected_allows_processed(self, tmp_path):
        from workshop_video_brain.workspace import snapshot

        # Must NOT raise for a legitimate processed/output path.
        snapshot._assert_not_protected(
            tmp_path, tmp_path / "media" / "processed" / "x.mp4"
        )

    def test_restore_refuses_to_write_into_media_raw(self, tmp_path):
        """A snapshot whose recorded original is under media/raw must not restore."""
        from uuid import uuid4

        from workshop_video_brain.core.models.project import SnapshotRecord
        from workshop_video_brain.workspace import snapshot

        snap_dir = tmp_path / "projects" / "snapshots" / "snap1"
        snap_dir.mkdir(parents=True)
        raw_target = tmp_path / "media" / "raw" / "original.mp4"
        record = SnapshotRecord(
            workspace_id=uuid4(),
            project_file_path=str(raw_target),
            snapshot_id="snap1",
        )
        (snap_dir / "metadata.yaml").write_text(record.to_yaml(), encoding="utf-8")
        (snap_dir / "original.mp4").write_bytes(b"\x00")

        with pytest.raises(ValueError):
            snapshot.restore(tmp_path, "snap1")
        # The protected file was never created/overwritten.
        assert not raw_target.exists()
