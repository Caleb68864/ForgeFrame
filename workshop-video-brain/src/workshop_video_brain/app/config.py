"""Configuration loader for workshop-video-brain.

Reads environment variables with sensible defaults.
Reports missing optional tools via warnings; never crashes.
"""
from __future__ import annotations

import os
import shutil
import warnings
from dataclasses import dataclass, field


@dataclass
class Config:
    vault_path: str | None
    workspace_root: str | None
    ffmpeg_path: str
    whisper_model: str
    whisper_available: bool
    ffmpeg_available: bool


def _detect_ffmpeg(ffmpeg_path: str) -> bool:
    return shutil.which(ffmpeg_path) is not None


def _detect_whisper() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def load_config() -> Config:
    """Load configuration from environment variables."""
    vault_path = os.environ.get("WVB_VAULT_PATH") or None
    workspace_root = os.environ.get("WVB_WORKSPACE_ROOT") or None
    ffmpeg_path = os.environ.get("WVB_FFMPEG_PATH", "ffmpeg")
    whisper_model = os.environ.get("WVB_WHISPER_MODEL", "small")

    ffmpeg_available = _detect_ffmpeg(ffmpeg_path)
    whisper_available = _detect_whisper()

    if not ffmpeg_available:
        warnings.warn(
            f"FFmpeg not found at '{ffmpeg_path}'. "
            "Video processing features will be unavailable. "
            "Install FFmpeg or set WVB_FFMPEG_PATH to the correct path.",
            stacklevel=2,
        )

    if not whisper_available:
        warnings.warn(
            "faster-whisper is not installed. "
            "Transcription features will be unavailable. "
            "Install with: pip install faster-whisper",
            stacklevel=2,
        )

    if vault_path is None:
        warnings.warn(
            "WVB_VAULT_PATH is not set. "
            "Obsidian note features will be unavailable.",
            stacklevel=2,
        )

    return Config(
        vault_path=vault_path,
        workspace_root=workspace_root,
        ffmpeg_path=ffmpeg_path,
        whisper_model=whisper_model,
        ffmpeg_available=ffmpeg_available,
        whisper_available=whisper_available,
    )
