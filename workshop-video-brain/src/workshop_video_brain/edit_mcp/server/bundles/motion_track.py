"""Bundle tools: AI subject focus & auto-zoom (plan §5).

Three composable tools automate Kdenlive's "track a subject, copy tracked data
to Transform" workflow **headlessly**:

* ``subject_locate_frames`` -- extract frame(s) from a clip so the calling agent
  can look at them and supply a subject bounding box (agent-vision mode; zero
  new deps).
* ``subject_track`` -- run the tracker (MLT ``opencv.tracker`` by default,
  OpenCV fallback) over the clip's source and save tracked keyframes to
  ``reports/tracks/<name>.json`` (normalised + pixel rects per frame).
* ``subject_zoom`` -- turn tracked rects (or a single static ``rect``) into a
  smoothed, padded, clamped, boundary-eased ``affine``/``transform`` rect
  animation applied to the clip via the shared keyframe machinery -- exactly
  like ``effect_pan_zoom``, but *following* the subject.

Geometry + tracker engines live in the pure module
``pipelines/motion_track.py``. ``subject_locate_frames`` / ``subject_track``
never modify the project; ``subject_zoom`` snapshots before writing. All
failures return ``{"status": "error", ...}`` -- tools never crash. Missing
tracker engines return an actionable install hint.

Auto-imported by ``server/bundles/__init__.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    invalid_input,
    bad_json_param,
    corrupt_project,
    operation_failed,
    media_unreadable,
    MISSING_FILE,
    MISSING_BINARY,
    INVALID_INDEX,
    INVALID_INPUT,
    CORRUPT_PROJECT,
    MISSING_DEPENDENCY,
    BAD_JSON_PARAM,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _err,
    _ok,
    _validate_workspace_path,
)

_MLT_SERVICE = "affine"
_KDENLIVE_ID = "transform"
# The MLT ``affine`` filter reads the keyframed rect from ``transition.rect``
# (a *destination* placement rect, emitted by motion_track.region_to_transform_rect).
# Verified against a real melt render in the §5 render-proof test.
_RECT_PROPERTY = "transition.rect"


# ---------------------------------------------------------------------------
# Shared clip resolution
# ---------------------------------------------------------------------------

def _resolve_project(ws_path: Path, project_file: str):
    """Return ``(project, project_path)`` or raise ``FileNotFoundError``."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

    project_path = ws_path / project_file
    if not project_path.exists():
        raise FileNotFoundError(f"Project file not found: {project_file}")
    return parse_project(project_path), project_path


def _resolve_clip(project, track: int, clip_index: int):
    """Resolve a clip -> ``(entry, real_index, producer)``.

    ``clip_index`` counts only real (non-gap) entries, matching effect tools.
    Raises ``IndexError`` / ``ValueError`` with a clear message.
    """
    if track < 0 or track >= len(project.playlists):
        raise IndexError(
            f"track index {track} out of range "
            f"(project has {len(project.playlists)} track(s))"
        )
    entries = project.playlists[track].entries
    real = [(i, e) for i, e in enumerate(entries) if e.producer_id]
    if clip_index < 0 or clip_index >= len(real):
        raise IndexError(
            f"clip_index {clip_index} out of range "
            f"(track has {len(real)} clip(s))"
        )
    real_index, entry = real[clip_index]
    producer = next(
        (p for p in project.producers if p.id == entry.producer_id), None
    )
    if producer is None:
        raise ValueError(
            f"no producer '{entry.producer_id}' for clip {clip_index}"
        )
    return entry, real_index, producer


def _producer_resource(ws_path: Path, producer) -> Path | None:
    """Resolve a producer's media resource to an existing filesystem path."""
    resource = producer.resource or producer.properties.get("resource", "")
    if not resource:
        return None
    p = Path(resource)
    if not p.is_absolute():
        p = ws_path / resource
    return p


def _find_workspace_root(project_path: Path) -> Path:
    """Nearest ancestor holding ``workspace.yaml`` (else the project dir)."""
    for parent in (project_path.parent, *project_path.parents):
        if (parent / "workspace.yaml").exists():
            return parent
    return project_path.parent


# ---------------------------------------------------------------------------
# subject_locate_frames
# ---------------------------------------------------------------------------

@mcp.tool()
@tool_guard
def subject_locate_frames(
    workspace_path: str,
    project_file: str,
    track: int,
    clip_index: int,
    at_seconds: float = 0.0,
) -> dict:
    """Extract a frame from a clip so an agent can supply a subject bbox.

    Agent-vision mode (plan §5, default, zero new deps): the tool decodes one
    frame at ``at_seconds`` **into the clip** and returns its path plus clip
    metadata (source, fps, resolution, clip length). The calling agent looks at
    the image, picks a subject rectangle ``"x y w h"`` in source pixels, and
    passes it to :func:`subject_track` (or :func:`subject_zoom` for a static
    punch-in). Reads only -- the project is never modified.

    Args:
        workspace_path: Workspace root.
        project_file: Project path relative to the workspace.
        track: Playlist/track index of the clip.
        clip_index: 0-based index among real (non-gap) clips on the track.
        at_seconds: Offset **into the clip** to grab the frame (default 0 =
            first frame).
    """
    from workshop_video_brain.edit_mcp.pipelines import motion_track as mt

    try:
        ws_path = _validate_workspace_path(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")
    try:
        project, project_path = _resolve_project(ws_path, project_file)
        entry, _real_index, producer = _resolve_clip(project, track, clip_index)
    except (FileNotFoundError, IndexError, ValueError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    source = _producer_resource(ws_path, producer)
    if source is None or not source.exists():
        return _err(f"Clip source media not found: {source}")

    fps = project.profile.fps or 25.0
    # Convert the clip-relative offset to a source timestamp (clip in_point).
    source_seconds = (entry.in_point / fps) + max(0.0, float(at_seconds))
    out_dir = ws_path.joinpath(*mt.TRACKS_DIR) / "frames"
    try:
        frames = mt.extract_locator_frames(
            source, [source_seconds], out_dir,
            stem=f"{source.stem}_t{track}_c{clip_index}",
        )
    except RuntimeError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    clip_frames = entry.out_point - entry.in_point + 1
    return _ok({
        "frames": frames,
        "source": str(source),
        "track": track,
        "clip_index": clip_index,
        "at_seconds": float(at_seconds),
        "source_seconds": source_seconds,
        "fps": fps,
        "width": project.profile.width,
        "height": project.profile.height,
        "clip_in_point": entry.in_point,
        "clip_out_point": entry.out_point,
        "clip_length_frames": clip_frames,
    })


# ---------------------------------------------------------------------------
# subject_track
# ---------------------------------------------------------------------------

@mcp.tool()
@tool_guard
def subject_track(
    workspace_path: str,
    project_file: str,
    track: int,
    clip_index: int,
    rect: str,
    algorithm: str = "csrt",
    start_seconds: float = 0.0,
    end_seconds: float = 0.0,
    engine: str = "auto",
) -> dict:
    """Track a subject rectangle across a clip; save tracked keyframes to JSON.

    Runs the MLT ``opencv.tracker`` filter headless by default (the §5
    feasibility spike proved melt persists analysis results), or the OpenCV
    fallback (``engine="opencv"``; needs ``opencv-contrib-python-headless``).
    Writes ``reports/tracks/<name>.json`` with per-frame pixel + normalised
    rects. Reads only -- the project is never modified. Feed the JSON path into
    :func:`subject_zoom` (``track_data=...``).

    Args:
        workspace_path: Workspace root.
        project_file: Project path relative to the workspace.
        track: Playlist/track index of the clip.
        clip_index: 0-based index among real clips on the track.
        rect: Seed subject rectangle ``"x y w h"`` in source pixels (from a
            frame returned by :func:`subject_locate_frames`).
        algorithm: Tracker algorithm -- ``csrt`` (accurate, default), ``kcf``,
            ``mosse``, ``mil``, ``boosting``, ``tld``, ``medianflow``.
        start_seconds: Start of the tracking window, clip-relative (0 = start).
        end_seconds: End of the tracking window, clip-relative (0 = clip end).
        engine: ``auto`` (melt then opencv), ``melt``, or ``opencv``.
    """
    from workshop_video_brain.edit_mcp.pipelines import motion_track as mt

    try:
        ws_path = _validate_workspace_path(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")
    try:
        project, project_path = _resolve_project(ws_path, project_file)
        entry, _real_index, producer = _resolve_clip(project, track, clip_index)
    except (FileNotFoundError, IndexError, ValueError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    source = _producer_resource(ws_path, producer)
    if source is None or not source.exists():
        return _err(f"Clip source media not found: {source}")

    try:
        seed = tuple(float(v) for v in rect.split())
        if len(seed) != 4:
            raise ValueError
    except ValueError:
        return _err(f"rect must be four space-separated numbers 'x y w h'; got {rect!r}")

    fps = project.profile.fps or 25.0
    width = project.profile.width
    height = project.profile.height
    # Clip-relative window -> source-absolute frame indices.
    start_frame = entry.in_point + int(round(max(0.0, start_seconds) * fps))
    if end_seconds and end_seconds > 0:
        end_frame = entry.in_point + int(round(end_seconds * fps))
    else:
        end_frame = entry.out_point

    try:
        result = mt.track_subject(
            source, seed, width, height, fps,
            algorithm=algorithm, engine=engine,
            start_frame=start_frame, end_frame=end_frame,
        )
    except mt.TrackerUnavailable as exc:
        return err(str(exc), error_type=MISSING_DEPENDENCY, suggestion="Install the tracker backend as shown, or pass engine='opencv' after: pip install opencv-contrib-python-headless.")
    except (ValueError, RuntimeError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    out_dir = ws_path.joinpath(*mt.TRACKS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{source.stem}_t{track}_c{clip_index}.json"
    out_path = out_dir / name
    payload = result.to_dict()
    payload["track"] = track
    payload["clip_index"] = clip_index
    payload["clip_in_point"] = entry.in_point
    out_path.write_text(json.dumps(payload, indent=2))

    return _ok({
        "track_data": str(out_path),
        "engine": result.engine,
        "algorithm": result.algorithm,
        "keyframe_count": len(result.keyframes),
        "start_frame": result.start_frame,
        "end_frame": result.end_frame,
        "width": width,
        "height": height,
        "fps": fps,
        "first_rect": list(result.keyframes[0][1]),
        "last_rect": list(result.keyframes[-1][1]),
    })


# ---------------------------------------------------------------------------
# subject_zoom
# ---------------------------------------------------------------------------

def _build_transform_xml(track: int, clip_index: int, rect_kf: str) -> str:
    import xml.etree.ElementTree as ET

    root = ET.Element(
        "filter",
        {
            "mlt_service": _MLT_SERVICE,
            "track": str(track),
            "clip_index": str(clip_index),
        },
    )
    svc = ET.SubElement(root, "property", {"name": "mlt_service"})
    svc.text = _MLT_SERVICE
    kid = ET.SubElement(root, "property", {"name": "kdenlive_id"})
    kid.text = _KDENLIVE_ID
    rect = ET.SubElement(root, "property", {"name": _RECT_PROPERTY})
    rect.text = rect_kf
    return ET.tostring(root, encoding="unicode")


def _load_tracked_keyframes(track_data: str, ws_path: Path):
    """Load ``[(frame, rect)]`` from a subject_track JSON path."""
    p = Path(track_data)
    if not p.is_absolute():
        p = ws_path / track_data
    if not p.exists():
        raise FileNotFoundError(f"track_data file not found: {track_data}")
    data = json.loads(p.read_text())
    kfs = [
        (int(k["frame"]), tuple(float(v) for v in k["rect"]))
        for k in data.get("keyframes", [])
    ]
    if not kfs:
        raise ValueError(f"track_data has no keyframes: {track_data}")
    return kfs, data


@mcp.tool()
@tool_guard
def subject_zoom(
    workspace_path: str,
    project_file: str,
    track: int,
    clip_index: int,
    track_data: str = "",
    rect: str = "",
    fill: float = 0.6,
    smoothing: int = 5,
    ease: str = "cubic",
) -> dict:
    """Apply a tracked follow-zoom (or a static punch-in) to a clip.

    Converts tracked subject rects (``track_data`` = a :func:`subject_track`
    JSON) -- or a single static ``rect`` -- into padded, frame-clamped,
    moving-average-smoothed, boundary-eased ``affine``/``transform`` rect
    keyframes and inserts the filter on the clip via the shared keyframe
    machinery (same path as ``effect_pan_zoom``). Snapshots before writing.

    Composable: pass ``rect="x y w h"`` alone for a static punch-in that works
    before any tracking exists; pass ``track_data`` for a moving follow-zoom.

    Args:
        workspace_path: Workspace root.
        project_file: Project path relative to the workspace.
        track: Playlist/track index of the clip.
        clip_index: 0-based index among real clips on the track.
        track_data: Path to a ``subject_track`` JSON (follow-zoom). Absolute or
            workspace-relative.
        rect: Static subject rect ``"x y w h"`` in source pixels (static
            punch-in). Ignored when ``track_data`` is given.
        fill: Fraction of the frame the subject should occupy (0<fill<=1;
            default 0.6).
        smoothing: Moving-average window over tracked rects (frames; <=1 = off).
        ease: Ease family for the punch-in boundaries (``cubic``, ``sine``,
            ``quad``, ...).
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
        serialize_project,
    )
    from workshop_video_brain.edit_mcp.pipelines import motion_track as mt
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path = _validate_workspace_path(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")
    try:
        project, project_path = _resolve_project(ws_path, project_file)
        _entry, _real_index, _producer = _resolve_clip(project, track, clip_index)
    except (FileNotFoundError, IndexError, ValueError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    fps = project.profile.fps or 25.0
    width = project.profile.width
    height = project.profile.height

    mode: str
    try:
        if track_data and track_data.strip():
            kfs, _meta = _load_tracked_keyframes(track_data, ws_path)
            rect_kf = mt.build_zoom_keyframes(
                kfs, width, height, fps,
                fill=fill, smoothing=smoothing, ease=ease,
            )
            mode = "tracked"
            keyframe_count = len(kfs)
        elif rect and rect.strip():
            seed = tuple(float(v) for v in rect.split())
            if len(seed) != 4:
                return _err(
                    f"rect must be four numbers 'x y w h'; got {rect!r}"
                )
            rect_kf = mt.build_static_zoom_keyframes(
                seed, width, height, fps, fill=fill,
            )
            mode = "static"
            keyframe_count = 1
        else:
            return _err("provide either track_data (follow-zoom) or rect (static punch-in)")
    except (FileNotFoundError, ValueError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    clip_ref = (track, clip_index)
    try:
        effect_index = len(patcher.list_effects(project, clip_ref))
    except IndexError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    ws_root = _find_workspace_root(project_path)
    try:
        record = create_snapshot(
            ws_root, project_path, description="before_subject_zoom"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001 - surface snapshot failure as error
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    xml = _build_transform_xml(track, clip_index, rect_kf)
    try:
        patcher.insert_effect_xml(project, clip_ref, xml, position=effect_index)
    except (IndexError, ValueError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    serialize_project(project, project_path)

    return _ok({
        "project_file": str(project_path),
        "track": track,
        "clip_index": clip_index,
        "effect_index": effect_index,
        "mode": mode,
        "mlt_service": _MLT_SERVICE,
        "kdenlive_id": _KDENLIVE_ID,
        "property": _RECT_PROPERTY,
        "fill": fill,
        "smoothing": smoothing,
        "ease": ease,
        "keyframe_count": keyframe_count,
        "width": width,
        "height": height,
        "fps": fps,
        "keyframes_written": rect_kf,
        "snapshot_id": snapshot_id,
    })
