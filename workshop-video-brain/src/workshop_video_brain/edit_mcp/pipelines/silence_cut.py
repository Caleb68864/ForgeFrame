"""Find what to keep when cutting silence, and render a tightened file.

Two engines produce the same keep-ranges (source seconds to keep):

* ``auto-editor`` -- the optional extra; ``min_silence`` has no counterpart there
  and is ignored. Its nearest knob is ``margin``.
* ``ffmpeg`` -- no dependency: ``silencedetect``, inverted and padded by ``margin``.

:func:`render_keep_ranges` knows nothing about silence, so any caller with its
own ranges can reuse it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from workshop_video_brain.core.utils.paths import assert_not_protected
from workshop_video_brain.edit_mcp.adapters.autoeditor import cli as autoeditor
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    FFmpegCommandError,
    _stderr_tail,
    run_ffmpeg,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.silence import detect_silence
from workshop_video_brain.edit_mcp.pipelines.ai_mask import EngineUnavailable
from workshop_video_brain.edit_mcp.pipelines.timeline_audio import invert_silence, merge_intervals

__all__ = [
    "ENGINES",
    "EngineUnavailable",
    "MAX_RANGES",
    "SourceUnreadable",
    "build_cut_filter",
    "engine_available",
    "keep_ranges",
    "remove_silence_file",
    "render_keep_ranges",
    "resolve_engine",
]

ENGINES: dict[str, dict[str, str]] = {
    "auto-editor": {
        "module": "auto_editor",
        "pip": "uv pip install -e '.[auto-editor]', then run `auto-editor --version` once to fetch its binary",
    },
    "ffmpeg": {"module": "", "pip": "install ffmpeg on PATH"},
}

_AUTO_ORDER: tuple[str, ...] = ("auto-editor", "ffmpeg")

MAX_RANGES = 500


class SourceUnreadable(RuntimeError):
    """The source cannot be probed, or reports no duration."""


def engine_available(name: str) -> bool:
    """Return True if engine *name* can run on this host."""
    if name == "ffmpeg":
        return True
    if name == "auto-editor":
        # A package with no fetched binary would otherwise download on first use.
        return autoeditor.resolve_binary() is not None
    return False


def resolve_engine(requested: str = "auto") -> str:
    """Resolve an engine name; ``"auto"`` prefers auto-editor, falling back to ffmpeg."""
    name = (requested or "auto").strip().lower()
    if name == "auto":
        return next(candidate for candidate in _AUTO_ORDER if engine_available(candidate))
    if name not in ENGINES:
        raise ValueError(f"Unknown engine '{requested}'. Known: {', '.join(sorted(ENGINES))}, auto.")
    if not engine_available(name):
        raise EngineUnavailable(
            f"Engine '{name}' is selected but its binary is not available. Install it: {ENGINES[name]['pip']}"
        )
    return name


def _duration(source: Path) -> float:
    try:
        duration = probe_media(source).duration
    except (FFmpegCommandError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        raise SourceUnreadable(f"Could not read {source.name}: {exc}") from exc
    if not duration or duration <= 0:
        raise SourceUnreadable(f"{source.name} reports no duration.")
    return duration


def keep_ranges(
    source: Path,
    *,
    engine: str = "auto",
    threshold_db: float = -30.0,
    min_silence: float = 0.5,
    margin: float = 0.2,
) -> tuple[str, list[tuple[float, float]], float]:
    """Return ``(engine_used, ranges, source_duration)``; ranges are source seconds."""
    source = Path(source)
    engine_used = resolve_engine(engine)
    duration = _duration(source)
    if engine_used == "auto-editor":
        v3 = autoeditor.run_v3(source, threshold_db=threshold_db, margin_seconds=margin)
        return engine_used, autoeditor.keep_ranges_from_v3(v3), duration

    silences = detect_silence(source, threshold_db, min_duration=min_silence)
    padded = [
        (max(0.0, start - margin), min(duration, end + margin))
        for start, end in invert_silence(silences, 0.0, duration)
    ]
    return engine_used, [(round(s, 6), round(e, 6)) for s, e in merge_intervals(padded)], duration


def build_cut_filter(
    ranges: list[tuple[float, float]],
    *,
    has_video: bool,
    has_audio: bool,
) -> str:
    """Build a ``trim``/``atrim`` + ``concat`` filtergraph keeping only *ranges*."""
    if len(ranges) > MAX_RANGES:
        raise ValueError(f"too many ranges to render at once: {len(ranges)} > {MAX_RANGES}")
    if not ranges:
        raise ValueError("no ranges to keep")
    if not (has_video or has_audio):
        raise ValueError("source has neither a video nor an audio stream")
    parts: list[str] = []
    inputs: list[str] = []
    for index, (start, end) in enumerate(ranges):
        if has_video:
            parts.append(f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{index}]")
            inputs.append(f"[v{index}]")
        if has_audio:
            parts.append(f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[a{index}]")
            inputs.append(f"[a{index}]")
    outputs = ("[outv]" if has_video else "") + ("[outa]" if has_audio else "")
    concat = f"concat=n={len(ranges)}:v={int(has_video)}:a={int(has_audio)}{outputs}"
    return ";".join([*parts, "".join(inputs) + concat])


def _failure(message: str, error_type: str, source: Path, output_path: Path | None = None) -> dict:
    return {"success": False, "source": str(source),
            "output_path": str(output_path) if output_path else None,
            "error": message, "error_type": error_type}


def render_keep_ranges(source: Path, ranges: list[tuple[float, float]], output_path: Path) -> dict:
    """Render only *ranges* of *source* to *output_path*, re-encoding."""
    source, output_path = Path(source), Path(output_path)
    assert_not_protected(output_path, "render output")
    if output_path.resolve() == source.resolve():
        return _failure("output_path must differ from source.", "invalid_input", source, output_path)
    if not ranges:
        return _failure("Nothing to keep: the whole file is silent at this threshold.",
                        "invalid_input", source, output_path)
    try:
        asset = probe_media(source)
    except (FFmpegCommandError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        return _failure(f"Could not read {source.name}: {exc}", "media_unreadable", source, output_path)
    has_video, has_audio = bool(asset.video_codec), bool(asset.audio_codec)
    if not (has_video or has_audio) or not asset.duration or asset.duration <= 0:
        return _failure(f"{source.name} has no readable streams.", "media_unreadable", source, output_path)
    try:
        graph = build_cut_filter(ranges, has_video=has_video, has_audio=has_audio)
    except ValueError as exc:
        return _failure(str(exc), "invalid_input", source, output_path)

    args = ["-filter_complex", graph]
    if has_video:
        args += ["-map", "[outv]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
    if has_audio:
        args += ["-map", "[outa]"]
        # Audio-only output: let the container pick, since aac cannot go in .mp3 or .wav.
        if has_video:
            args += ["-c:a", "aac"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ran = run_ffmpeg(args, input_path=source, output_path=output_path)
    if not ran.success:
        output_path.unlink(missing_ok=True)
        return _failure(f"ffmpeg failed: {_stderr_tail(ran.stderr, 6)}",
                        "operation_failed", source, output_path)
    kept = sum(end - start for start, end in ranges)
    return {
        "success": True,
        "source": str(source),
        "output_path": str(output_path),
        "keep_ranges": [list(item) for item in ranges],
        "kept_seconds": round(kept, 6),
        "removed_seconds": round(max(0.0, asset.duration - kept), 6),
        "source_duration": asset.duration,
    }


def remove_silence_file(
    source: Path,
    output_path: Path,
    *,
    engine: str = "auto",
    threshold_db: float = -30.0,
    min_silence: float = 0.5,
    margin: float = 0.2,
    dry_run: bool = False,
) -> dict:
    """Cut the silence out of *source*, writing a tightened copy to *output_path*."""
    source, output_path = Path(source), Path(output_path)
    assert_not_protected(output_path, "render output")
    try:
        engine_used, ranges, duration = keep_ranges(
            source, engine=engine, threshold_db=threshold_db, min_silence=min_silence, margin=margin,
        )
    except SourceUnreadable as exc:
        return _failure(str(exc), "media_unreadable", source, output_path)
    if dry_run:
        return {"success": True, "engine": engine_used, "source": str(source),
                "output_path": str(output_path), "keep_ranges": [list(item) for item in ranges],
                "source_duration": duration}
    result = render_keep_ranges(source, ranges, output_path)
    result["engine"] = engine_used
    return result
