"""Split a recording into one file per detected shot (``media_split_scenes``).

Pure planning (:func:`shot_ranges`, :func:`build_shot_command_args`) plus one
ffmpeg call per shot. Files only ever go to the caller's ``output_dir``, which
may not sit inside a protected tree.

``reencode=False`` stream-copies, which can only cut on keyframes, so a shot
then starts at the keyframe at or before its range rather than exactly on it.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from workshop_video_brain.core.utils.paths import assert_not_protected
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    DEFAULT_TIMEOUT_SECONDS,
    FFmpegCommandError,
    FFmpegNotFound,
    FFmpegTimeout,
    _stderr_tail,
    run_ffmpeg,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.scene import SceneScanError
from workshop_video_brain.edit_mcp.pipelines import scene_detect
from workshop_video_brain.edit_mcp.pipelines.scene_detect import (
    EngineUnavailable,
    SceneDetectError,
)

logger = logging.getLogger(__name__)


def shot_ranges(
    cuts: list[float],
    duration: float,
    min_shot_seconds: float = 0.5,
) -> list[tuple[float, float]]:
    """Turn cut times into ``[start, end)`` shots covering ``[0, duration)``.

    Cuts at or outside the file's ends are dropped. A shot shorter than
    ``min_shot_seconds`` merges into its predecessor; the first shot has none,
    so it merges forward.
    """
    if duration <= 0:
        return []
    inner = sorted({cut for cut in cuts if 0 < cut < duration})
    ranges: list[tuple[float, float]] = []
    for start, end in zip([0.0, *inner], [*inner, duration]):
        if ranges and end - start < min_shot_seconds:
            ranges[-1] = (ranges[-1][0], end)
        else:
            ranges.append((start, end))
    if len(ranges) > 1 and ranges[0][1] - ranges[0][0] < min_shot_seconds:
        ranges[:2] = [(ranges[0][0], ranges[1][1])]
    return ranges


def build_shot_command_args(
    start: float,
    end: float,
    *,
    reencode: bool,
    has_video: bool,
    has_audio: bool,
) -> tuple[list[str], list[str]]:
    """Return ``(pre_input_args, args)`` for one shot's :func:`run_ffmpeg` call."""
    pre_input = ["-ss", f"{start:.3f}"]
    args = ["-t", f"{end - start:.3f}", "-map", "0:v:0?", "-map", "0:a:0?"]
    if not reencode:
        return pre_input, [*args, "-c", "copy"]
    if has_video:
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
    if has_audio:
        args += ["-c:a", "aac"]
    return pre_input, args


def _remove_files(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover - defensive
            logger.warning("could not remove partial shot %s: %s", path, exc)


def split_scenes(
    source: Path,
    output_dir: Path,
    *,
    engine: str = "auto",
    threshold: float = 0.4,
    detector: str = "content",
    detector_threshold: float | None = None,
    min_shot_seconds: float = 0.5,
    reencode: bool = True,
    dry_run: bool = False,
) -> dict:
    """Detect cuts in *source* and write one file per shot into *output_dir*."""
    source = Path(source)
    output_dir = assert_not_protected(Path(output_dir), "scene split output")

    def failure(message: str, error_type: str) -> dict:
        return {"success": False, "source": str(source), "output_dir": str(output_dir),
                "error": message, "error_type": error_type}

    try:
        asset = probe_media(source)
    except FFmpegNotFound as exc:
        return failure(str(exc), "missing_binary")
    except (FFmpegCommandError, subprocess.CalledProcessError, OSError, ValueError) as exc:
        return failure(f"Could not read {source.name}: {exc}", "media_unreadable")
    if not asset.video_codec or asset.duration <= 0:
        return failure(f"{source.name} has no video stream to split.", "media_unreadable")

    try:
        engine_used, hits = scene_detect.scan_cuts(
            source,
            engine=engine,
            threshold=threshold,
            detector=detector,
            detector_threshold=detector_threshold,
            min_scene_seconds=min_shot_seconds,
        )
    except EngineUnavailable as exc:
        return failure(str(exc), "missing_dependency")
    except FFmpegNotFound as exc:
        return failure(str(exc), "missing_binary")
    except (SceneScanError, SceneDetectError) as exc:
        return failure(str(exc), "media_unreadable")

    cuts = [round(time, 6) for time, _score in hits]
    ranges = shot_ranges(cuts, asset.duration, min_shot_seconds)
    suffix = ".mp4" if reencode else (source.suffix or ".mp4")
    shots = [
        {"index": index, "start": start, "end": end,
         "path": str(output_dir / f"{source.stem}_shot_{index:03d}{suffix}")}
        for index, (start, end) in enumerate(ranges)
    ]
    result = {"success": True, "source": str(source), "output_dir": str(output_dir),
              "engine": engine_used, "cuts": cuts, "shots": shots, "shot_count": len(shots)}
    if dry_run:
        return result

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for shot in shots:
        pre_input, args = build_shot_command_args(
            shot["start"], shot["end"], reencode=reencode,
            has_video=bool(asset.video_codec), has_audio=bool(asset.audio_codec),
        )
        path = Path(shot["path"])
        written.append(path)
        try:
            ran = run_ffmpeg(args, input_path=source, output_path=path,
                             pre_input_args=pre_input, timeout=DEFAULT_TIMEOUT_SECONDS)
        except (FFmpegNotFound, FFmpegTimeout):
            _remove_files(written)
            raise
        if not ran.success:
            _remove_files(written)
            return failure(
                f"ffmpeg failed on shot {shot['index']}: {_stderr_tail(ran.stderr, 6)}",
                "operation_failed",
            )
    return result
