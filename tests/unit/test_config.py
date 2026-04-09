"""Unit tests for app/config.py — load_config() and detection helpers."""
from __future__ import annotations

import os
import warnings
from unittest.mock import patch, MagicMock

import pytest

from workshop_video_brain.app.config import load_config, Config, _detect_ffmpeg, _detect_whisper


class TestLoadConfigDefaults:
    def test_returns_config_instance(self, monkeypatch):
        monkeypatch.delenv("WVB_VAULT_PATH", raising=False)
        monkeypatch.delenv("WVB_WORKSPACE_ROOT", raising=False)
        monkeypatch.delenv("WVB_FFMPEG_PATH", raising=False)
        monkeypatch.delenv("WVB_WHISPER_MODEL", raising=False)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cfg = load_config()
        assert isinstance(cfg, Config)

    def test_default_ffmpeg_path(self, monkeypatch):
        monkeypatch.delenv("WVB_FFMPEG_PATH", raising=False)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cfg = load_config()
        assert cfg.ffmpeg_path == "ffmpeg"

    def test_default_whisper_model(self, monkeypatch):
        monkeypatch.delenv("WVB_WHISPER_MODEL", raising=False)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cfg = load_config()
        assert cfg.whisper_model == "small"

    def test_default_vault_path_is_none(self, monkeypatch):
        monkeypatch.delenv("WVB_VAULT_PATH", raising=False)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cfg = load_config()
        assert cfg.vault_path is None

    def test_default_workspace_root_is_none(self, monkeypatch):
        monkeypatch.delenv("WVB_WORKSPACE_ROOT", raising=False)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cfg = load_config()
        assert cfg.workspace_root is None


class TestLoadConfigEnvVars:
    def test_reads_vault_path(self, monkeypatch):
        monkeypatch.setenv("WVB_VAULT_PATH", "/my/vault")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cfg = load_config()
        assert cfg.vault_path == "/my/vault"

    def test_reads_workspace_root(self, monkeypatch):
        monkeypatch.setenv("WVB_WORKSPACE_ROOT", "/my/workspace")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cfg = load_config()
        assert cfg.workspace_root == "/my/workspace"

    def test_reads_ffmpeg_path(self, monkeypatch):
        monkeypatch.setenv("WVB_FFMPEG_PATH", "/usr/local/bin/ffmpeg")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cfg = load_config()
        assert cfg.ffmpeg_path == "/usr/local/bin/ffmpeg"

    def test_reads_whisper_model(self, monkeypatch):
        monkeypatch.setenv("WVB_WHISPER_MODEL", "large-v2")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cfg = load_config()
        assert cfg.whisper_model == "large-v2"


class TestFfmpegDetection:
    def test_returns_true_when_ffmpeg_found(self):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            assert _detect_ffmpeg("ffmpeg") is True

    def test_returns_false_when_ffmpeg_not_found(self):
        with patch("shutil.which", return_value=None):
            assert _detect_ffmpeg("ffmpeg") is False

    def test_config_ffmpeg_available_true_when_which_finds_it(self, monkeypatch):
        monkeypatch.delenv("WVB_VAULT_PATH", raising=False)
        with patch("workshop_video_brain.app.config._detect_ffmpeg", return_value=True):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cfg = load_config()
        assert cfg.ffmpeg_available is True

    def test_config_ffmpeg_available_false_when_which_misses(self, monkeypatch):
        monkeypatch.delenv("WVB_VAULT_PATH", raising=False)
        with patch("workshop_video_brain.app.config._detect_ffmpeg", return_value=False):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cfg = load_config()
        assert cfg.ffmpeg_available is False


class TestWhisperDetection:
    def test_returns_true_when_faster_whisper_importable(self):
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"faster_whisper": mock_module}):
            result = _detect_whisper()
        assert result is True

    def test_returns_false_when_faster_whisper_missing(self):
        with patch.dict("sys.modules", {"faster_whisper": None}):
            # Simulate ImportError by patching the import
            with patch("builtins.__import__", side_effect=lambda name, *a, **kw: (
                __import__(name, *a, **kw) if name != "faster_whisper" else (_ for _ in ()).throw(ImportError())
            )):
                result = _detect_whisper()
        assert result is False

    def test_config_whisper_available_reflects_detection(self, monkeypatch):
        monkeypatch.delenv("WVB_VAULT_PATH", raising=False)
        with patch("workshop_video_brain.app.config._detect_whisper", return_value=True):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                cfg = load_config()
        assert cfg.whisper_available is True


class TestLoadConfigWarnings:
    def test_warns_when_ffmpeg_not_found(self, monkeypatch):
        monkeypatch.delenv("WVB_VAULT_PATH", raising=False)
        with patch("workshop_video_brain.app.config._detect_ffmpeg", return_value=False):
            with patch("workshop_video_brain.app.config._detect_whisper", return_value=True):
                with pytest.warns(UserWarning, match="FFmpeg"):
                    load_config()

    def test_warns_when_whisper_not_installed(self, monkeypatch):
        monkeypatch.delenv("WVB_VAULT_PATH", raising=False)
        with patch("workshop_video_brain.app.config._detect_ffmpeg", return_value=True):
            with patch("workshop_video_brain.app.config._detect_whisper", return_value=False):
                with pytest.warns(UserWarning, match="faster-whisper"):
                    load_config()

    def test_warns_when_vault_path_not_set(self, monkeypatch):
        monkeypatch.delenv("WVB_VAULT_PATH", raising=False)
        with patch("workshop_video_brain.app.config._detect_ffmpeg", return_value=True):
            with patch("workshop_video_brain.app.config._detect_whisper", return_value=True):
                with pytest.warns(UserWarning, match="WVB_VAULT_PATH"):
                    load_config()
