"""``guide_add_scene_cuts`` MCP tool -- detected scene cuts as timeline guides.

Auto-imported by ``server/bundles/__init__.py``. Writes through
``serialize_project``, snapshotting before and after like ``guide_add``.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.core.models.timeline import AddGuide
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegNotFound
from workshop_video_brain.edit_mcp.adapters.ffmpeg.scene import SceneScanError
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import ProjectParseError, parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines import guides as guides_pipeline
from workshop_video_brain.edit_mcp.pipelines import scene_detect
from workshop_video_brain.edit_mcp.server.errors import (
    corrupt_project,
    invalid_input,
    media_unreadable,
    missing_binary,
    missing_dependency,
    missing_file,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _load_latest_project,
    _ok,
    _validate_workspace_path,
)
from workshop_video_brain.server import mcp
from workshop_video_brain.workspace import create_snapshot


@mcp.tool()
@tool_guard
def guide_add_scene_cuts(
    workspace_path: str,
    source: str,
    project_file: str = "",
    engine: str = "ffmpeg",
    threshold: float = 0.4,
    detector: str = "content",
    detector_threshold: float | None = None,
    label_prefix: str = "Scene",
    category: str | None = None,
) -> dict:
    """Add a guide on the timeline at every scene cut of a placed source.

    Positions are timeline frames: a cut in a source that is placed twice gets a
    guide per placement, and a cut outside every placement gets none.

    Args:
        workspace_path: Path to workspace root.
        source: Path to the video file to scan.
        project_file: Project to edit; defaults to the latest working copy.
        engine: "ffmpeg" (default), "pyscenedetect", or "auto", which prefers
            PySceneDetect when the scene-detect extra is installed.
        threshold: ffmpeg's scene-change sensitivity, 0..1.
        detector: PySceneDetect detector: "content", "adaptive" or "threshold".
        detector_threshold: PySceneDetect's native threshold (library default if omitted).
        label_prefix: Guides are labelled "<prefix> 1", "<prefix> 2", and so on.
        category: Optional Kdenlive guide category.
    """
    try:
        workspace = _validate_workspace_path(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory.")
    try:
        if project_file:
            project_path = Path(project_file)
            if not project_path.is_absolute():
                project_path = workspace / project_path
            if not project_path.is_file():
                return missing_file(project_file, "project_file")
            project = parse_project(project_path)
        else:
            _workspace, project, project_path = _load_latest_project(workspace_path)
    except ProjectParseError as exc:
        return corrupt_project(project_file or str(workspace), exc)
    except FileNotFoundError as exc:
        return missing_file(str(workspace), str(exc))

    source_path = Path(source)
    if not source or not source_path.is_file():
        return missing_file(source, "source")

    try:
        engine_used, hits = scene_detect.scan_cuts(
            source_path,
            engine=engine,
            threshold=threshold,
            detector=detector,
            detector_threshold=detector_threshold,
        )
    except scene_detect.EngineUnavailable:
        return missing_dependency("scenedetect", scene_detect.ENGINES["pyscenedetect"]["pip"])
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Pass engine as auto, ffmpeg or pyscenedetect, and detector as content, adaptive or threshold.")
    except FFmpegNotFound as exc:
        return missing_binary("ffmpeg", str(exc))
    except (SceneScanError, scene_detect.SceneDetectError) as exc:
        return media_unreadable(source, str(exc))

    positions = guides_pipeline.cut_positions_on_timeline(
        project, source_path, [time for time, _score in hits]
    )
    if not positions:
        return _ok({
            "guides_added": 0,
            "positions_frames": [],
            "engine": engine_used,
            "snapshot_id": None,
            "note": "No scene cut falls inside a placement of this source on the timeline.",
        })

    create_snapshot(workspace, project_path, description="before_guide_add_scene_cuts")
    updated = patch_project(project, [
        AddGuide(position_frames=frame, label=f"{label_prefix} {number}", category=category)
        for number, frame in enumerate(positions, start=1)
    ])
    serialize_project(updated, project_path)
    snapshot = create_snapshot(workspace, project_path, description="after_guide_add_scene_cuts")
    return _ok({
        "guides_added": len(positions),
        "positions_frames": positions,
        "engine": engine_used,
        "project_file": str(project_path),
        "snapshot_id": snapshot.snapshot_id,
    })
