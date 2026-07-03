"""Voiceover-loop MCP tools: ``vo_plan`` / ``vo_attach`` / ``vo_status``.

A script-first voiceover workflow (gap-analysis item 5, "Voiceover loop") that
needs no TTS:

* ``vo_plan`` splits a markdown script into numbered VO cues, estimates each
  cue's spoken length from its word count at ``wpm``, writes
  ``reports/vo_plan.json`` + a human-readable recording checklist, and lays a
  guide (with a project) or a workspace marker (without one) at each cue's
  cumulative timestamp.
* ``vo_attach`` records a real take against a cue: it probes the take's true
  duration, inserts it onto an audio track at the cue's planned position (a
  model-level insert following the ``overlay_looks`` blank-padding pattern -- it
  does NOT wait for ``clip_place``), updates the plan with actual-vs-estimated
  duration, and reports downstream drift.
* ``vo_status`` prints the cue table: planned / recorded / missing, est vs
  actual, cumulative drift.

Pure logic lives in ``pipelines/vo_loop.py``; this module owns snapshotting,
project XML I/O, and plan/marker/guide writing.  Registered by the ``bundles``
package auto-importer.
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
    _ok,
    _err,
    _require_workspace,
)
from workshop_video_brain.edit_mcp.pipelines import vo_loop as _vo


def _plan_path(ws_path: Path) -> Path:
    return ws_path / "reports" / "vo_plan.json"


def _read_plan(ws_path: Path) -> dict | None:
    p = _plan_path(ws_path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _write_plan(ws_path: Path, plan: dict) -> Path:
    p = _plan_path(ws_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return p


@mcp.tool()
@tool_guard
def vo_plan(
    workspace_path: str,
    script_file: str,
    wpm: float = 150.0,
    project_file: str = "",
) -> dict:
    """Split a markdown script into numbered VO cues and lay them on the timeline.

    Args:
        workspace_path: Workspace root directory.
        script_file: Markdown narration script (absolute or workspace-relative).
        wpm: Narration pace in words per minute (default 150).
        project_file: Optional .kdenlive project (workspace-relative). When given,
            a guide is added per cue at its cumulative timestamp; otherwise a
            workspace marker per cue is written to ``markers/vo_cues_markers.json``.

    Writes ``reports/vo_plan.json`` and ``reports/vo_recording_checklist.md`` and
    returns the plan, the checklist path, and the placement (guides|markers).
    """
    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    if wpm <= 0:
        return _err("wpm must be > 0")

    script_path = Path(script_file)
    if not script_path.is_absolute():
        script_path = ws_path / script_file
    if not script_path.exists():
        return _err(f"Script file not found: {script_file}")

    try:
        text = script_path.read_text(encoding="utf-8")
    except OSError as exc:
        return _err(f"Could not read script: {exc}")

    plan = _vo.build_plan(text, wpm)
    if plan["cue_count"] == 0:
        return invalid_input("Script produced no cues (empty or unparseable)", suggestion="Provide a markdown script with headings and paragraphs; a blank or heading-less file yields no cues.")

    plan["script_file"] = str(script_path)
    plan["project_file"] = project_file or None

    # --- Placement: guides (with project) or workspace markers (without) ---
    placement = "markers"
    guide_info: list[dict] = []
    marker_path: str | None = None
    snapshot_id = None

    if project_file:
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
            serialize_project,
        )
        from workshop_video_brain.edit_mcp.pipelines import guides as _guides
        from workshop_video_brain.workspace import create_snapshot

        project_path = ws_path / project_file
        if not project_path.exists():
            return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)
        try:
            record = create_snapshot(
                ws_path, project_path, description="before_vo_plan"
            )
            snapshot_id = record.snapshot_id
        except Exception as exc:  # noqa: BLE001
            return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

        project = parse_project(project_path)
        for cue in plan["cues"]:
            project = _guides.add_guide(
                project,
                cue["start_seconds"],
                f"{cue['cue_id']}: {cue['heading']}",
                category=None,
            )
            guide_info.append(
                {"cue_id": cue["cue_id"], "at_seconds": cue["start_seconds"]}
            )
        serialize_project(project, project_path)
        placement = "guides"
    else:
        markers = []
        for cue in plan["cues"]:
            markers.append(
                {
                    "category": "step_explanation",
                    "confidence_score": 1.0,
                    "source_method": "vo_plan",
                    "reason": cue["text"][:120],
                    "clip_ref": "",
                    "start_seconds": cue["start_seconds"],
                    "end_seconds": cue["end_seconds"],
                    "suggested_label": f"{cue['cue_id']}: {cue['heading']}",
                }
            )
        markers_dir = ws_path / "markers"
        markers_dir.mkdir(parents=True, exist_ok=True)
        mp = markers_dir / "vo_cues_markers.json"
        mp.write_text(json.dumps(markers, indent=2), encoding="utf-8")
        marker_path = str(mp)

    plan["placement"] = placement
    plan_path = _write_plan(ws_path, plan)

    checklist = _vo.format_checklist(plan, script_name=script_path.name)
    checklist_path = ws_path / "reports" / "vo_recording_checklist.md"
    checklist_path.write_text(checklist, encoding="utf-8")

    return _ok(
        {
            "plan_path": str(plan_path),
            "checklist_path": str(checklist_path),
            "placement": placement,
            "cue_count": plan["cue_count"],
            "total_est_seconds": plan["total_est_seconds"],
            "cues": plan["cues"],
            "guides": guide_info,
            "marker_path": marker_path,
            "snapshot_id": snapshot_id,
        }
    )


@mcp.tool()
@tool_guard
def vo_attach(
    workspace_path: str,
    project_file: str,
    cue_id: str,
    audio_file: str,
    ripple: bool = False,
    audio_track: int = 0,
) -> dict:
    """Attach a recorded take for *cue_id*: probe, place on an audio track, report drift.

    Args:
        workspace_path: Workspace root directory.
        project_file: .kdenlive project (workspace-relative).
        cue_id: Cue identifier from the plan (e.g. ``cue_02``).
        audio_file: The recorded take (absolute or workspace-relative).
        ripple: When true, the reported drift is framed as *applied* downstream
            shift. The actual video ripple is out of scope (composes with
            ``clip_place`` in Wave 3b); either way only the report changes.
        audio_track: Which audio track to place the take on (default 0).

    Probes the take's real duration, inserts it at the cue's planned position on
    an audio track (model-level insert; no ``clip_place`` dependency), updates
    ``reports/vo_plan.json`` with actual-vs-estimated, and returns per-cue drift.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
        serialize_project,
    )
    from workshop_video_brain.workspace import create_snapshot

    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    plan = _read_plan(ws_path)
    if plan is None:
        return _err("No vo_plan.json found; run vo_plan first")

    cue = next((c for c in plan["cues"] if c["cue_id"] == cue_id), None)
    if cue is None:
        return _err(f"Unknown cue_id: {cue_id}")

    audio_path = Path(audio_file)
    if not audio_path.is_absolute():
        audio_path = ws_path / audio_file
    if not audio_path.exists():
        return _err(f"Audio take not found: {audio_file}")

    project_path = ws_path / project_file
    if not project_path.exists():
        return err(f"Project file not found: {project_file}", error_type=MISSING_FILE, suggestion="Check the project path is correct and resolved under the workspace root; run project_list to see available projects.", path=project_file)

    try:
        actual_seconds = _vo.audio_duration_seconds(audio_path)
    except RuntimeError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    try:
        record = create_snapshot(
            ws_path, project_path, description="before_vo_attach"
        )
        snapshot_id = record.snapshot_id
    except Exception as exc:  # noqa: BLE001
        return operation_failed(f"Snapshot failed: {exc}", cause=exc, suggestion="Ensure the workspace is writable and has free disk space so a pre-edit snapshot can be created.")

    project = parse_project(project_path)
    fps = project.profile.fps or _vo.DEFAULT_FPS
    at_frame = _vo.seconds_to_frames(cue["start_seconds"], fps)
    dur_frames = max(1, _vo.seconds_to_frames(actual_seconds, fps))

    try:
        clip_index = _vo.insert_take_clip(
            project, audio_track, str(audio_path), at_frame, dur_frames
        )
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    serialize_project(project, project_path)

    # Update the plan with the recorded take.
    cue["actual_seconds"] = round(actual_seconds, 3)
    cue["audio_file"] = str(audio_path)
    cue["delta_seconds"] = round(actual_seconds - cue["est_seconds"], 3)
    _write_plan(ws_path, plan)

    drift = _vo.compute_drift(plan)
    downstream = [d for d in drift if d["cue_id"] > cue_id]

    return _ok(
        {
            "cue_id": cue_id,
            "audio_file": str(audio_path),
            "est_seconds": cue["est_seconds"],
            "actual_seconds": cue["actual_seconds"],
            "delta_seconds": cue["delta_seconds"],
            "audio_track": audio_track,
            "clip_index": clip_index,
            "at_frame": at_frame,
            "duration_frames": dur_frames,
            "ripple": bool(ripple),
            "ripple_note": (
                "Video ripple is report-only; composes with clip_place (Wave 3b)."
            ),
            "downstream_drift": downstream,
            "snapshot_id": snapshot_id,
        }
    )


@mcp.tool()
@tool_guard
def vo_status(workspace_path: str) -> dict:
    """Return the VO cue table: planned / recorded / missing, est vs actual, drift.

    Reads ``reports/vo_plan.json`` and joins it with the drift report so an agent
    can see, per cue, whether a take has been recorded and how far downstream
    cues would shift.
    """
    try:
        ws_path, _ws = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory, and that any project_file resolves under it.")

    plan = _read_plan(ws_path)
    if plan is None:
        return _err("No vo_plan.json found; run vo_plan first")

    drift_by_cue = {d["cue_id"]: d for d in _vo.compute_drift(plan)}
    rows = []
    recorded = 0
    for cue in plan["cues"]:
        has_take = cue.get("actual_seconds") is not None
        if has_take:
            recorded += 1
        d = drift_by_cue.get(cue["cue_id"], {})
        rows.append(
            {
                "cue_id": cue["cue_id"],
                "heading": cue["heading"],
                "status": "recorded" if has_take else "missing",
                "est_seconds": cue["est_seconds"],
                "actual_seconds": cue.get("actual_seconds"),
                "delta_seconds": cue.get("delta_seconds"),
                "planned_start_seconds": cue["start_seconds"],
                "drift_seconds": d.get("drift_seconds"),
                "rippled_start_seconds": d.get("rippled_start_seconds"),
            }
        )

    return _ok(
        {
            "cue_count": plan["cue_count"],
            "recorded": recorded,
            "missing": plan["cue_count"] - recorded,
            "total_est_seconds": plan["total_est_seconds"],
            "placement": plan.get("placement"),
            "rows": rows,
        }
    )
