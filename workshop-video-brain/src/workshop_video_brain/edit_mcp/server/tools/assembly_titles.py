"""Assembly, title-card, replay, pacing, and pattern tools.

Carved from the former monolithic ``server/tools.py``. Each function
registers with the shared FastMCP singleton via ``@mcp.tool()``.
"""
from __future__ import annotations

import json
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _err,
)





# ---------------------------------------------------------------------------
# Replay tools
# ---------------------------------------------------------------------------
@mcp.tool()
def replay_generate(workspace_path: str, target_duration: float = 60.0) -> dict:
    """Generate a highlight-reel replay .kdenlive project from workspace markers.

    Ranks markers by score, greedily selects non-overlapping segments until
    target_duration is reached, pads each segment by 2 s, merges adjacent
    segments (gap < 3 s), and writes a versioned .kdenlive file.

    Args:
        workspace_path: Path to the workspace root directory.
        target_duration: Target replay duration in seconds (default 60).

    Returns:
        Path to the generated .kdenlive file and replay report data.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        # Coerce target_duration from string if needed
        try:
            target_duration = float(target_duration)
        except (TypeError, ValueError):
            return _err(f"target_duration must be a number, got: {target_duration!r}")
        if target_duration <= 0:
            return _err(f"target_duration must be positive, got: {target_duration}")
        from workshop_video_brain.edit_mcp.pipelines.replay_generator import generate_replay

        output_path = generate_replay(
            workspace_root=ws_path,
            target_duration=target_duration,
        )
        return _ok({
            "kdenlive_path": str(output_path),
            "target_duration": target_duration,
        })
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc))




# ---------------------------------------------------------------------------
# Title card tools
# ---------------------------------------------------------------------------
@mcp.tool()
def title_cards_generate(workspace_path: str) -> dict:
    """Generate title cards from chapter markers in the workspace.

    Reads chapter_candidate markers from the markers/ directory and produces
    a list of TitleCard objects, inserting an "Intro" card at the beginning
    if needed.  The cards are saved to reports/title_cards.json.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        List of title cards and the path to the saved JSON file.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        from workshop_video_brain.edit_mcp.pipelines.title_cards import (
            generate_title_cards,
            save_title_cards,
        )

        workspace_root = ws_path
        cards = generate_title_cards(workspace_root)
        out_path = save_title_cards(cards, workspace_root)
        return _ok({
            "title_cards": [json.loads(c.to_json()) for c in cards],
            "count": len(cards),
            "saved_to": str(out_path),
        })
    except Exception as exc:
        return _err(str(exc))




# ---------------------------------------------------------------------------
# Pacing tools
# ---------------------------------------------------------------------------
@mcp.tool()
def pacing_analyze(workspace_path: str) -> dict:
    """Analyse pacing and energy for all transcripts in the workspace.

    Divides each transcript into 30-second segments and computes WPM,
    speech density, word variety, and pace classification. Detects weak
    intros and energy drops (3+ consecutive slow segments).

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Per-file pacing reports with overall stats, segment breakdown,
        energy drops, and a formatted Markdown summary.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        from workshop_video_brain.core.models.transcript import Transcript
        from workshop_video_brain.edit_mcp.pipelines.pacing_analyzer import (
            analyze_pacing,
            format_pacing_report,
        )

        transcripts_dir = ws_path / "transcripts"
        if not transcripts_dir.exists():
            return _ok({
                "reports": [],
                "count": 0,
                "message": "No transcripts/ directory found. Run transcript_generate first.",
            })

        reports = []
        errors = []
        for json_path in sorted(transcripts_dir.glob("*_transcript.json")):
            try:
                transcript = Transcript.from_json(json_path.read_text(encoding="utf-8"))
                report = analyze_pacing(transcript)
                markdown = format_pacing_report(report)
                reports.append({
                    "file": json_path.name,
                    "overall_wpm": report.overall_wpm,
                    "overall_pace": report.overall_pace,
                    "weak_intro": report.weak_intro,
                    "energy_drop_count": len(report.energy_drops),
                    "energy_drops": report.energy_drops,
                    "segment_count": len(report.segments),
                    "summary": report.summary,
                    "markdown": markdown,
                })
            except Exception as exc:
                errors.append(f"{json_path.name}: {exc}")

        return _ok({
            "reports": reports,
            "count": len(reports),
            "errors": errors,
        })
    except Exception as exc:
        return _err(str(exc))




# ---------------------------------------------------------------------------
# Pattern Brain tools
# ---------------------------------------------------------------------------
@mcp.tool()
def pattern_extract(workspace_path: str) -> dict:
    """Extract MYOG build data (materials, measurements, steps, tips) from workspace transcripts.

    Reads the first available transcript in the workspace, runs the pattern
    brain pipeline, and returns extracted build data along with overlay text
    and a printable build notes markdown document.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Dict with build_data fields, overlay_text list, build_notes_md string,
        and notes_path where build_notes.md was saved.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        from workshop_video_brain.production_brain.skills.pattern import (
            extract_and_format,
            save_build_notes,
        )

        result = extract_and_format(ws_path)
        build_data = result["build_data"]
        overlay_text = result["overlay_text"]
        build_notes_md = result["build_notes_md"]

        # Auto-save build notes
        notes_path = save_build_notes(ws_path, build_notes_md)

        return _ok({
            "project_title": build_data.project_title,
            "materials": [m.model_dump() for m in build_data.materials],
            "measurements": [m.model_dump() for m in build_data.measurements],
            "steps": [s.model_dump() for s in build_data.steps],
            "tips": [t.model_dump() for t in build_data.tips],
            "overlay_text": overlay_text,
            "build_notes_md": build_notes_md,
            "notes_path": str(notes_path),
        })
    except FileNotFoundError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc))




# ---------------------------------------------------------------------------
# Assembly tools
# ---------------------------------------------------------------------------
@mcp.tool()
def assembly_plan(workspace_path: str) -> dict:
    """Generate an assembly plan matching clips to script steps.

    Reads script data, clip labels, and transcripts from the workspace.
    Returns a plan showing which clips match which script steps.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Assembly plan with step-to-clip assignments and unmatched clips.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")

        from workshop_video_brain.edit_mcp.pipelines.assembly import build_assembly_plan

        plan = build_assembly_plan(ws_path)
        steps_data = []
        for step in plan.steps:
            steps_data.append({
                "step_number": step.step_number,
                "step_description": step.step_description,
                "chapter_title": step.chapter_title,
                "clips": [
                    {
                        "clip_ref": c.clip_ref,
                        "role": c.role,
                        "score": c.score,
                        "reason": c.reason,
                    }
                    for c in step.clips
                ],
            })
        return _ok({
            "project_title": plan.project_title,
            "steps": steps_data,
            "unmatched_clips": plan.unmatched_clips,
            "total_estimated_duration": plan.total_estimated_duration,
            "assembly_report": plan.assembly_report,
        })
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def assembly_build(
    workspace_path: str,
    add_transitions: bool = True,
    add_chapters: bool = True,
) -> dict:
    """Build a first-cut Kdenlive project from the assembly plan.

    Generates a timeline with clips ordered to match script structure.
    Primary clips on V2, inserts on V1, chapter markers at step boundaries.

    Args:
        workspace_path: Path to the workspace root directory.
        add_transitions: Whether to add crossfade transitions between steps.
        add_chapters: Whether to add chapter marker guides at step starts.

    Returns:
        Path to the generated .kdenlive file and assembly summary.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")

        from workshop_video_brain.edit_mcp.pipelines.assembly import (
            assemble_timeline,
            build_assembly_plan,
        )

        plan = build_assembly_plan(ws_path)
        kdenlive_path = assemble_timeline(
            workspace_root=ws_path,
            plan=plan,
            add_transitions=add_transitions,
            add_chapter_markers=add_chapters,
        )
        return _ok({
            "kdenlive_path": str(kdenlive_path),
            "project_title": plan.project_title,
            "steps_count": len(plan.steps),
            "unmatched_clips": plan.unmatched_clips,
            "total_estimated_duration": plan.total_estimated_duration,
            "assembly_report_path": str(ws_path / "reports" / "assembly_report.md"),
            "assembly_plan_path": str(ws_path / "reports" / "assembly_plan.json"),
        })
    except Exception as exc:
        return _err(str(exc))
