"""Scene-cut detection pipeline (``clips_detect_scenes``).

Two engines return the same ``[(time, score)]`` shape:

* ``ffmpeg`` -- the single ffmpeg scene scorer,
  :func:`workshop_video_brain.edit_mcp.adapters.ffmpeg.scene.scan_scene_cuts`.
  Its ``scene`` value is on the familiar 0..1 scale (0 = identical to previous
  frame, 1 = completely different), which matches the ``threshold`` contract.
* ``pyscenedetect`` -- the optional ``scene-detect`` extra
  (``adapters/scenedetect``). Its score is relative to that engine and is not
  comparable to ffmpeg's.

An agent (or ``media_segment_at_silence``) can then split the recording, and
each shot lands in the b-roll index as its own entry.
"""
from __future__ import annotations

import logging
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegNotFound
from workshop_video_brain.edit_mcp.adapters.ffmpeg.scene import (
    SceneScanError,
    build_scan_command,
    build_select_filter,
    parse_scene_scores as _parse_hits,
    scan_scene_cuts,
)
from workshop_video_brain.edit_mcp.adapters.scenedetect import engine as pyscenedetect_engine
from workshop_video_brain.edit_mcp.adapters.scenedetect.engine import (
    DETECTORS,
    SceneDetectError,
    SceneDetectUnavailable,
)
from workshop_video_brain.edit_mcp.pipelines.ai_mask import EngineUnavailable

logger = logging.getLogger(__name__)

__all__ = [
    "DETECTORS",
    "ENGINES",
    "EngineUnavailable",
    "SceneDetectError",
    "build_scan_command",
    "build_select_filter",
    "detect_scenes",
    "engine_available",
    "parse_scene_scores",
    "resolve_engine",
    "scan_cuts",
    "scene_change_scan",
]

# ffmpeg is always "available" here: its binary is checked at run time and a
# missing one raises FFmpegNotFound, the same as before engines existed.
ENGINES: dict[str, dict[str, str]] = {
    "ffmpeg": {"module": "", "pip": "install ffmpeg on PATH"},
    "pyscenedetect": {"module": "scenedetect", "pip": "uv pip install -e '.[scene-detect]'"},
}

# Preference order for ``engine="auto"``. Always ends at an available engine.
_AUTO_ORDER: tuple[str, ...] = ("pyscenedetect", "ffmpeg")


def engine_available(name: str) -> bool:
    """Return True if engine *name* can be attempted on this host."""
    if name == "ffmpeg":
        return True
    if name == "pyscenedetect":
        return pyscenedetect_engine.is_available()
    return False


def resolve_engine(requested: str = "auto") -> str:
    """Resolve an engine name.

    ``"auto"`` prefers PySceneDetect and falls back to ffmpeg. Raises
    ``ValueError`` for an unknown name and :class:`EngineUnavailable` (with an
    install hint) for a known engine whose package is missing.
    """
    name = (requested or "auto").strip().lower()
    if name == "auto":
        return next(candidate for candidate in _AUTO_ORDER if engine_available(candidate))
    if name not in ENGINES:
        raise ValueError(f"Unknown engine '{requested}'. Known: {', '.join(sorted(ENGINES))}, auto.")
    if not engine_available(name):
        raise EngineUnavailable(
            f"Engine '{name}' is selected but not installed. Install it: {ENGINES[name]['pip']}"
        )
    return name


def scan_cuts(
    source: Path,
    *,
    engine: str = "ffmpeg",
    threshold: float = 0.4,
    detector: str = "content",
    detector_threshold: float | None = None,
    min_scene_seconds: float = 0.5,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> tuple[str, list[tuple[float, float]]]:
    """Return ``(engine_used, [(cut_seconds, score)])``.

    ``threshold`` is ffmpeg's 0..1 knob (ignored by pyscenedetect);
    ``detector``, ``detector_threshold`` and ``min_scene_seconds`` belong to
    pyscenedetect (ignored by ffmpeg). Unknown engine or detector names raise
    ``ValueError``.
    """
    if detector not in pyscenedetect_engine.DETECTORS:
        raise ValueError(
            f"Unknown detector '{detector}'. Known: {', '.join(pyscenedetect_engine.DETECTORS)}."
        )
    engine_used = resolve_engine(engine)
    if engine_used == "ffmpeg":
        return engine_used, scan_scene_cuts(Path(source), threshold, start_seconds, end_seconds)
    try:
        hits = pyscenedetect_engine.scan_cuts(
            Path(source),
            detector=detector,
            detector_threshold=detector_threshold,
            min_scene_seconds=min_scene_seconds,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        )
    except SceneDetectUnavailable as exc:
        raise EngineUnavailable(str(exc)) from exc
    return engine_used, hits


def scene_change_scan(
    engine: str = "ffmpeg",
    detector: str = "content",
    detector_threshold: float | None = None,
):
    """Return a ``detect_scene_changes(scan=...)`` hook, or None for plain ffmpeg.

    Resolves the engine now, so a bad name or a missing package surfaces before
    any decoding. The adapter takes the hook because it may not import this layer.
    """
    engine_used = resolve_engine(engine)
    if engine_used == "ffmpeg":
        return None

    def scan(path, threshold, start, end):
        return scan_cuts(path, engine=engine_used, threshold=threshold, detector=detector,
                         detector_threshold=detector_threshold,
                         start_seconds=start, end_seconds=end)[1]

    return scan


def parse_scene_scores(stats_text: str) -> list[dict]:
    """Parse ``metadata=print`` output into ``[{time, score}]`` (score 0..1)."""
    return [_cut(t, score) for t, score in _parse_hits(stats_text)]


def _cut(time: float, score: float) -> dict:
    return {"time": round(time, 3), "score": round(score, 4)}


def detect_scenes(
    source: Path,
    threshold: float = 0.4,
    dry_run: bool = False,
    *,
    engine: str = "ffmpeg",
    detector: str = "content",
    detector_threshold: float | None = None,
) -> dict:
    """Detect scene cuts in *source*; return cut points and metadata."""
    source = Path(source)

    def failure(message: str, error_type: str, engine_name: str = engine) -> dict:
        return {
            "success": False,
            "source": str(source),
            "threshold": threshold,
            "engine": engine_name,
            "error": message,
            "error_type": error_type,
        }

    if dry_run:
        try:
            engine_used = resolve_engine(engine)
        except EngineUnavailable as exc:
            return failure(str(exc), "missing_dependency")
        command = build_scan_command(source, threshold) if engine_used == "ffmpeg" else None
        return {"success": True, "source": str(source), "threshold": threshold,
                "engine": engine_used, "command": command, "cuts": []}

    try:
        engine_used, hits = scan_cuts(
            source,
            engine=engine,
            threshold=threshold,
            detector=detector,
            detector_threshold=detector_threshold,
        )
    except EngineUnavailable as exc:
        return failure(str(exc), "missing_dependency")
    except FFmpegNotFound:
        # ffmpeg binary itself missing -- an environment error, not "no cuts".
        return failure("ffmpeg binary not found on PATH.", "missing_binary")
    except (SceneScanError, SceneDetectError) as exc:
        # Do NOT report a false success with zero cuts for an undecodable source.
        return failure(str(exc), "media_unreadable")

    cuts = [_cut(t, score) for t, score in hits]
    return {
        "success": True,
        "source": str(source),
        "threshold": threshold,
        "engine": engine_used,
        "cut_count": len(cuts),
        "cuts": cuts,
    }
