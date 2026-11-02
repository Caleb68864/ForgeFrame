"""PySceneDetect scene scanner: the optional second engine beside ffmpeg's.

:func:`scan_cuts` returns the same ``[(cut_time_seconds, score)]`` shape as
``adapters/ffmpeg/scene.scan_scene_cuts``, but the score is **relative to this
engine and not comparable to ffmpeg's**: it is the detector's own metric at the
cut frame, normalised to 0..1 (0.0 when the detector recorded no metric).

PySceneDetect decodes in-process, so no subprocess and no ``timeout=`` is
involved. A wedged decode cannot be bounded from here.
"""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

DETECTORS = ("content", "adaptive", "threshold")

_INSTALL_HINT = "uv pip install -e '.[scene-detect]'"


class SceneDetectUnavailable(RuntimeError):
    """The scenedetect package (or its opencv) is not importable."""


class SceneDetectError(RuntimeError):
    """PySceneDetect could not open or decode the source; never a silent ``[]``."""


def is_available() -> bool:
    """True when both ``scenedetect`` and a ``cv2`` build are importable."""
    return (
        importlib.util.find_spec("scenedetect") is not None
        and importlib.util.find_spec("cv2") is not None
    )


def _load_library():
    try:
        return importlib.import_module("scenedetect")
    except ImportError as exc:
        raise SceneDetectUnavailable(
            f"PySceneDetect is not installed. Install it: {_INSTALL_HINT}"
        ) from exc


def _build_detector(library, detector: str, threshold: float | None, min_scene_len: int):
    kwargs: dict = {"min_scene_len": min_scene_len}
    if detector == "content":
        if threshold is not None:
            kwargs["threshold"] = threshold
        return library.ContentDetector(**kwargs)
    if detector == "adaptive":
        if threshold is not None:
            kwargs["adaptive_threshold"] = threshold
        return library.AdaptiveDetector(**kwargs)
    if threshold is not None:
        kwargs["threshold"] = threshold
    return library.ThresholdDetector(**kwargs)


def _normalise_score(detector_name: str, detector, stats, frame: int) -> float:
    # AdaptiveDetector lists content_val first; its deciding metric is the
    # rolling ratio, which comes last. The other two decide on the first.
    keys = detector.get_metrics()
    key = keys[-1] if detector_name == "adaptive" else keys[0]
    if not stats.metrics_exist(frame, [key]):
        return 0.0
    value = float(stats.get_metrics(frame, [key])[0])
    if detector_name == "adaptive":
        return min(1.0, value / (4 * detector.adaptive_threshold))
    return min(1.0, value / 255.0)


def scan_cuts(
    video_path: Path,
    *,
    detector: str = "content",
    detector_threshold: float | None = None,
    min_scene_seconds: float = 0.5,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> list[tuple[float, float]]:
    """Return sorted, de-duplicated ``[(cut_seconds, score)]``; times are absolute.

    ``detector_threshold`` is the detector's native knob (library defaults:
    content 27.0, adaptive 3.0, threshold 12). Raises ``ValueError`` for an
    unknown detector, :class:`SceneDetectUnavailable` when the package is
    missing, and :class:`SceneDetectError` for an unreadable source.
    """
    if detector not in DETECTORS:
        raise ValueError(f"Unknown detector '{detector}'. Known: {', '.join(DETECTORS)}.")
    library = _load_library()
    failures = (importlib.import_module("scenedetect.video_stream").VideoOpenFailure, OSError)
    try:
        video = library.open_video(str(video_path))
        min_scene_len = max(1, round(min_scene_seconds * video.frame_rate))
        active = _build_detector(library, detector, detector_threshold, min_scene_len)
        stats = library.StatsManager()
        manager = library.SceneManager(stats_manager=stats)
        manager.add_detector(active)
        if start_seconds:
            video.seek(float(start_seconds))
        # A float is seconds; an int would be read as a frame number.
        end_time = float(end_seconds) if end_seconds is not None else None
        frames_read = manager.detect_scenes(video, end_time=end_time, show_progress=False)
        scenes = manager.get_scene_list()
    except failures as exc:
        raise SceneDetectError(
            f"PySceneDetect could not read {Path(video_path).name}: {str(exc).strip()}"
        ) from exc
    if frames_read == 0 and not start_seconds:
        raise SceneDetectError(f"PySceneDetect decoded no frames from {Path(video_path).name}.")

    hits: dict[float, float] = {}
    for start, _end in scenes[1:]:
        hits.setdefault(
            start.get_seconds(),
            _normalise_score(detector, active, stats, start.get_frames()),
        )
    return sorted(hits.items())
