"""``media_split_scenes`` MCP tool -- one file per detected shot.

Auto-imported by ``server/bundles/__init__.py``. A bare-file tool: it leads with
``source``, takes no workspace and touches no project, so there is no snapshot.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.pipelines.scene_detect import (
    DETECTORS,
    ENGINES,
    EngineUnavailable,
    resolve_engine,
)
from workshop_video_brain.edit_mcp.pipelines.scene_split import split_scenes
from workshop_video_brain.edit_mcp.server.bundles._pipeline_errors import (
    error_from_pipeline_result,
)
from workshop_video_brain.edit_mcp.server.errors import (
    MISSING_DEPENDENCY,
    invalid_input,
    missing_dependency,
    missing_file,
    nonfinite_guard,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok
from workshop_video_brain.server import mcp


@mcp.tool()
@tool_guard
def media_split_scenes(
    source: str,
    output_dir: str,
    engine: str = "auto",
    threshold: float = 0.4,
    detector: str = "content",
    detector_threshold: float | None = None,
    min_shot_seconds: float = 0.5,
    reencode: bool = True,
) -> dict:
    """Split a video into one file per detected shot.

    Args:
        source: Path to the video file.
        output_dir: Folder for the shot files. Required, and refused inside
            media/raw or projects/source.
        engine: "auto" (default) prefers PySceneDetect when the scene-detect extra
            is installed and otherwise uses ffmpeg; or "ffmpeg", "pyscenedetect".
        threshold: ffmpeg's scene-change sensitivity, 0..1.
        detector: PySceneDetect detector: "content", "adaptive" or "threshold".
        detector_threshold: PySceneDetect's native threshold (library default if omitted).
        min_shot_seconds: A shorter shot merges into its neighbour.
        reencode: True cuts exactly and writes .mp4. False stream-copies, which
            starts each shot on a keyframe rather than exactly on the cut.
    """
    if not output_dir or not output_dir.strip():
        return invalid_input("output_dir is required.", suggestion="pass a folder outside media/raw")
    path = Path(source)
    if not source or not path.is_file():
        return missing_file(source, "source")
    try:
        resolve_engine(engine)
    except EngineUnavailable:
        return missing_dependency("scenedetect", ENGINES["pyscenedetect"]["pip"])
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Pass engine as auto, ffmpeg or pyscenedetect.")
    if detector not in DETECTORS:
        return invalid_input(
            f"Unknown detector '{detector}'.",
            suggestion=f"Pass detector as one of: {', '.join(DETECTORS)}.",
        )
    bad_number = nonfinite_guard(threshold=threshold, min_shot_seconds=min_shot_seconds)
    if bad_number:
        return bad_number
    if min_shot_seconds <= 0:
        return invalid_input("min_shot_seconds must be > 0.", suggestion="Pass a positive number of seconds, such as 0.5.")

    result = split_scenes(
        path,
        Path(output_dir),
        engine=engine,
        threshold=threshold,
        detector=detector,
        detector_threshold=detector_threshold,
        min_shot_seconds=min_shot_seconds,
        reencode=reencode,
    )
    if not result.get("success"):
        if result.get("error_type") == MISSING_DEPENDENCY:
            return missing_dependency("scenedetect", ENGINES["pyscenedetect"]["pip"])
        return error_from_pipeline_result(result, "Scene split failed", path=source)
    return _ok(result)
