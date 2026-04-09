"""CLI entry point for workshop-video-brain."""
from __future__ import annotations

import json
import sys

import click

from workshop_video_brain import __version__


# ---------------------------------------------------------------------------
# Main group
# ---------------------------------------------------------------------------


@click.group()
def main() -> None:
    """Workshop Video Brain -- local-first video production assistant."""


@main.command()
def version() -> None:
    """Print the current version."""
    click.echo(f"workshop-video-brain {__version__}")


# ---------------------------------------------------------------------------
# workspace group
# ---------------------------------------------------------------------------


@main.group()
def workspace() -> None:
    """Workspace management commands."""


@workspace.command("create")
@click.argument("title")
@click.option("--media-root", required=True, help="Absolute path to media source folder.")
@click.option("--vault-path", default="", help="Optional Obsidian vault root path.")
def workspace_create(title: str, media_root: str, vault_path: str) -> None:
    """Create a new workspace with TITLE and --media-root."""
    from workshop_video_brain.workspace.manager import WorkspaceManager

    config = {"vault_path": vault_path} if vault_path else {}
    try:
        ws = WorkspaceManager.create(title=title, media_root=media_root, config=config)
        click.echo(f"Workspace created: {ws.workspace_root}")
        click.echo(f"  ID:    {ws.id}")
        click.echo(f"  Slug:  {ws.project.slug}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@workspace.command("status")
@click.argument("path")
def workspace_status(path: str) -> None:
    """Show status of workspace at PATH."""
    from workshop_video_brain.workspace.manifest import read_manifest

    try:
        m = read_manifest(path)
        click.echo(f"Workspace: {m.project_title}")
        click.echo(f"  ID:     {m.workspace_id}")
        click.echo(f"  Slug:   {m.slug}")
        click.echo(f"  Status: {m.status}")
        click.echo(f"  Media:  {m.media_root}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# media group
# ---------------------------------------------------------------------------


@main.group()
def media() -> None:
    """Media management commands."""


@media.command("ingest")
@click.argument("workspace_path")
def media_ingest(workspace_path: str) -> None:
    """Run the full ingest pipeline for WORKSPACE_PATH."""
    from workshop_video_brain.workspace.manager import WorkspaceManager
    from workshop_video_brain.app.config import load_config
    from workshop_video_brain.edit_mcp.pipelines.ingest import run_ingest

    try:
        ws = WorkspaceManager.open(workspace_path)
        config = load_config()
        report = run_ingest(ws, config)
        click.echo(f"Ingest complete:")
        click.echo(f"  Scanned:     {report.scanned_count}")
        click.echo(f"  Proxied:     {report.proxied_count}")
        click.echo(f"  Transcribed: {report.transcribed_count}")
        click.echo(f"  Silence:     {report.silence_detected_count}")
        if report.errors:
            click.echo(f"  Errors ({len(report.errors)}):")
            for e in report.errors:
                click.echo(f"    - {e}", err=True)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@media.command("list")
@click.argument("workspace_path")
def media_list(workspace_path: str) -> None:
    """List media assets in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import scan_directory
    from pathlib import Path

    try:
        raw_dir = Path(workspace_path) / "media" / "raw"
        if not raw_dir.exists():
            click.echo("No media/raw directory found.")
            return
        assets = scan_directory(raw_dir)
        click.echo(f"Found {len(assets)} asset(s):")
        for a in assets:
            dur = f"{a.duration_seconds:.1f}s" if a.duration_seconds else "unknown"
            click.echo(f"  [{a.media_type}] {Path(a.path).name} ({dur})")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# transcript group
# ---------------------------------------------------------------------------


@main.group()
def transcript() -> None:
    """Transcript commands."""


@transcript.command("generate")
@click.argument("workspace_path")
def transcript_generate(workspace_path: str) -> None:
    """Generate transcripts for all media in WORKSPACE_PATH."""
    from workshop_video_brain.workspace.manager import WorkspaceManager
    from workshop_video_brain.app.config import load_config
    from workshop_video_brain.edit_mcp.pipelines.ingest import run_ingest

    try:
        ws = WorkspaceManager.open(workspace_path)
        config = load_config()
        report = run_ingest(ws, config)
        click.echo(f"Transcribed {report.transcribed_count} of {report.scanned_count} asset(s).")
        if report.errors:
            for e in report.errors:
                click.echo(f"  Warning: {e}", err=True)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@transcript.command("export")
@click.argument("workspace_path")
@click.option("--format", "fmt", default="srt", type=click.Choice(["srt", "json", "txt"]),
              help="Export format.")
def transcript_export(workspace_path: str, fmt: str) -> None:
    """Export transcripts from WORKSPACE_PATH."""
    from pathlib import Path

    transcripts_dir = Path(workspace_path) / "transcripts"
    if not transcripts_dir.exists():
        click.echo("No transcripts directory found.")
        return
    pattern = f"*_transcript.{fmt}"
    files = sorted(transcripts_dir.glob(pattern))
    click.echo(f"Found {len(files)} {fmt.upper()} file(s):")
    for f in files:
        click.echo(f"  {f}")


# ---------------------------------------------------------------------------
# markers group
# ---------------------------------------------------------------------------


@main.group()
def markers() -> None:
    """Marker generation and listing commands."""


@markers.command("auto")
@click.argument("workspace_path")
def markers_auto(workspace_path: str) -> None:
    """Auto-generate markers from transcripts in WORKSPACE_PATH."""
    import json as _json
    from pathlib import Path
    from workshop_video_brain.core.models.transcript import Transcript
    from workshop_video_brain.edit_mcp.pipelines.auto_mark import generate_markers
    from workshop_video_brain.core.models.markers import MarkerConfig

    try:
        transcripts_dir = Path(workspace_path) / "transcripts"
        markers_dir = Path(workspace_path) / "markers"
        markers_dir.mkdir(parents=True, exist_ok=True)

        if not transcripts_dir.exists():
            click.echo("No transcripts/ directory found. Run 'media ingest' first.")
            return

        config = MarkerConfig()
        total = 0
        files = 0
        for json_path in sorted(transcripts_dir.glob("*_transcript.json")):
            transcript = Transcript.from_json(json_path.read_text(encoding="utf-8"))
            stem = json_path.stem.replace("_transcript", "")
            silence_path = markers_dir / f"{stem}_silence.json"
            silence_gaps: list[tuple[float, float]] = []
            if silence_path.exists():
                raw = _json.loads(silence_path.read_text(encoding="utf-8"))
                silence_gaps = [(g["start"], g["end"]) for g in raw if "start" in g]
            mks = generate_markers(transcript, silence_gaps, config)
            out = markers_dir / f"{stem}_markers.json"
            out.write_text(_json.dumps([m.model_dump(mode="json") for m in mks], indent=2), encoding="utf-8")
            total += len(mks)
            files += 1
            click.echo(f"  {stem}: {len(mks)} markers")

        click.echo(f"Generated {total} markers across {files} file(s).")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@markers.command("list")
@click.argument("workspace_path")
def markers_list(workspace_path: str) -> None:
    """List marker files in WORKSPACE_PATH."""
    import json as _json
    from pathlib import Path

    markers_dir = Path(workspace_path) / "markers"
    if not markers_dir.exists():
        click.echo("No markers/ directory found.")
        return
    files = sorted(markers_dir.glob("*_markers.json"))
    if not files:
        click.echo("No marker files found.")
        return
    total = 0
    for mf in files:
        try:
            count = len(_json.loads(mf.read_text(encoding="utf-8")))
            total += count
            click.echo(f"  {mf.name}: {count} markers")
        except Exception:
            click.echo(f"  {mf.name}: (error reading)")
    click.echo(f"Total: {total} markers")


# ---------------------------------------------------------------------------
# timeline group
# ---------------------------------------------------------------------------


@main.group()
def timeline() -> None:
    """Timeline building commands."""


@timeline.command("review")
@click.argument("workspace_path")
@click.option("--mode", default="ranked", type=click.Choice(["ranked", "chronological"]),
              help="Ordering mode for markers.")
def timeline_review(workspace_path: str, mode: str) -> None:
    """Build a review timeline for WORKSPACE_PATH."""
    import json as _json
    from pathlib import Path
    from workshop_video_brain.core.models.markers import Marker
    from workshop_video_brain.edit_mcp.pipelines.review_timeline import build_review_timeline

    try:
        markers_dir = Path(workspace_path) / "markers"
        if not markers_dir.exists():
            click.echo("No markers/ directory. Run 'markers auto' first.", err=True)
            sys.exit(1)
        markers: list[Marker] = []
        for mf in markers_dir.glob("*_markers.json"):
            raw = _json.loads(mf.read_text(encoding="utf-8"))
            for item in raw:
                markers.append(Marker(**item))
        if not markers:
            click.echo("No markers found. Run 'markers auto' first.", err=True)
            sys.exit(1)
        out = build_review_timeline(markers, [], Path(workspace_path), mode=mode)
        click.echo(f"Review timeline written to: {out}")
        click.echo(f"  Markers included: {len(markers)}")
        click.echo(f"  Mode: {mode}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@timeline.command("selects")
@click.argument("workspace_path")
@click.option("--min-confidence", default=0.5, type=float,
              help="Minimum confidence score (0.0–1.0).")
def timeline_selects(workspace_path: str, min_confidence: float) -> None:
    """Build a selects timeline for WORKSPACE_PATH."""
    import json as _json
    from pathlib import Path
    from workshop_video_brain.core.models.markers import Marker, MarkerConfig
    from workshop_video_brain.edit_mcp.pipelines.selects_timeline import build_selects, build_selects_timeline

    try:
        markers_dir = Path(workspace_path) / "markers"
        if not markers_dir.exists():
            click.echo("No markers/ directory. Run 'markers auto' first.", err=True)
            sys.exit(1)
        markers: list[Marker] = []
        for mf in markers_dir.glob("*_markers.json"):
            raw = _json.loads(mf.read_text(encoding="utf-8"))
            for item in raw:
                markers.append(Marker(**item))
        config = MarkerConfig()
        selects = build_selects(markers, config, min_confidence=min_confidence)
        out = build_selects_timeline(selects, [], Path(workspace_path))
        click.echo(f"Selects timeline written to: {out}")
        click.echo(f"  Selects included: {len(selects)}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# project group
# ---------------------------------------------------------------------------


@main.group()
def project() -> None:
    """Project management commands."""


@project.command("validate")
@click.argument("workspace_path")
def project_validate(workspace_path: str) -> None:
    """Validate the latest .kdenlive project in WORKSPACE_PATH."""
    from pathlib import Path
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.validator import validate_project

    try:
        working_copies = Path(workspace_path) / "projects" / "working_copies"
        files = sorted(working_copies.glob("*.kdenlive")) if working_copies.exists() else []
        if not files:
            click.echo("No .kdenlive files found in projects/working_copies/", err=True)
            sys.exit(1)
        latest = files[-1]
        proj = parse_project(latest)
        report = validate_project(proj, workspace_root=Path(workspace_path))
        click.echo(f"Validating: {latest.name}")
        click.echo(f"Summary: {report.summary}")
        if report.items:
            for item in report.items:
                click.echo(f"  [{item.severity}] {item.category}: {item.message}")
        else:
            click.echo("  No issues found.")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@project.command("create-copy")
@click.argument("workspace_path")
def project_create_copy(workspace_path: str) -> None:
    """Create an initial .kdenlive working copy for WORKSPACE_PATH."""
    from pathlib import Path
    from workshop_video_brain.workspace.manifest import read_manifest
    from workshop_video_brain.core.models.kdenlive import KdenliveProject, ProjectProfile, Track, Playlist
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
    from workshop_video_brain.core.utils.naming import slugify

    try:
        manifest = read_manifest(workspace_path)
        proj = KdenliveProject(
            version="7",
            title=manifest.project_title,
            profile=ProjectProfile(width=1920, height=1080, fps=25.0, colorspace="709"),
        )
        proj.tracks = [
            Track(id="playlist_video", track_type="video"),
            Track(id="playlist_audio", track_type="audio"),
        ]
        proj.playlists = [Playlist(id="playlist_video"), Playlist(id="playlist_audio")]
        proj.tractor = {"id": "tractor0", "in": "0", "out": "99999"}
        slug = manifest.slug or slugify(manifest.project_title) or "project"
        out = serialize_versioned(proj, Path(workspace_path), slug)
        click.echo(f"Created: {out}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# render group
# ---------------------------------------------------------------------------


@main.group()
def render() -> None:
    """Render commands."""


@render.command("preview")
@click.argument("workspace_path")
def render_preview(workspace_path: str) -> None:
    """Render the latest .kdenlive project with the preview profile."""
    from pathlib import Path
    from workshop_video_brain.edit_mcp.pipelines.render_pipeline import run_render

    try:
        working_copies = Path(workspace_path) / "projects" / "working_copies"
        files = sorted(working_copies.glob("*.kdenlive")) if working_copies.exists() else []
        if not files:
            click.echo("No .kdenlive files found.", err=True)
            sys.exit(1)
        latest = files[-1]
        click.echo(f"Rendering: {latest.name}")
        job = run_render(Path(workspace_path), latest, "preview")
        click.echo(f"Status: {job.status}")
        click.echo(f"Output: {job.output_path}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@render.command("status")
@click.argument("workspace_path")
def render_status(workspace_path: str) -> None:
    """List render jobs for WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.pipelines.render_pipeline import list_renders

    try:
        jobs = list_renders(workspace_path)
        if not jobs:
            click.echo("No render jobs found.")
            return
        click.echo(f"Render jobs ({len(jobs)}):")
        for j in jobs:
            click.echo(f"  [{j.status}] {j.profile} -> {j.output_path}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# plan group
# ---------------------------------------------------------------------------


@main.group()
def plan() -> None:
    """Planning and scripting commands (production brain)."""


@plan.command("outline")
@click.argument("idea")
def plan_outline(idea: str) -> None:
    """Generate a video outline from IDEA."""
    from workshop_video_brain.production_brain.skills.outline import generate_outline

    try:
        md, _data = generate_outline(idea)
        click.echo(md)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@plan.command("script")
@click.option("--idea", default="", help="Idea text to use as input.")
def plan_script(idea: str) -> None:
    """Generate a script from a provided idea (or stdin)."""
    from workshop_video_brain.production_brain.skills.outline import generate_outline
    from workshop_video_brain.production_brain.skills.script import generate_script

    if not idea:
        idea = click.get_text_stream("stdin").read().strip()
    if not idea:
        click.echo("Provide an --idea or pipe text via stdin.", err=True)
        sys.exit(1)

    try:
        _md, outline_data = generate_outline(idea)
        script_md, _script_data = generate_script(outline_data)
        click.echo(script_md)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@plan.command("voiceover")
@click.argument("workspace_path")
def plan_voiceover(workspace_path: str) -> None:
    """Extract segments needing voiceover fixes from WORKSPACE_PATH."""
    from workshop_video_brain.production_brain.skills.voiceover import (
        extract_fixable_segments,
        format_for_review,
    )
    from pathlib import Path

    try:
        segments = extract_fixable_segments(Path(workspace_path))
        if not segments:
            click.echo("No fixable voiceover segments found.")
            return
        click.echo(format_for_review(segments))
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@plan.command("shots")
@click.option("--idea", default="", help="Idea text to base shots on.")
def plan_shots(idea: str) -> None:
    """Generate a shot plan from a provided idea (or stdin)."""
    from workshop_video_brain.production_brain.skills.outline import generate_outline
    from workshop_video_brain.production_brain.skills.shot_plan import generate_shot_plan

    if not idea:
        idea = click.get_text_stream("stdin").read().strip()
    if not idea:
        click.echo("Provide an --idea or pipe text via stdin.", err=True)
        sys.exit(1)

    try:
        _md, outline_data = generate_outline(idea)
        shot_md, _shot_data = generate_shot_plan(outline_data)
        click.echo(shot_md)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# prepare-tutorial-project guided workflow
# ---------------------------------------------------------------------------


@main.command("prepare-tutorial-project")
@click.argument("media_folder")
@click.option("--title", prompt=True, help="Project title.")
@click.option("--vault-path", default="", help="Optional Obsidian vault root path.")
def prepare_tutorial_project(media_folder: str, title: str, vault_path: str) -> None:
    """Guided workflow: create workspace, ingest, mark, build timeline, validate.

    MEDIA_FOLDER: Path to the folder containing raw media files.

    Steps:
    1. Create workspace
    2. Ingest media (proxy, transcribe, silence)
    3. Auto-generate markers
    4. Build review timeline
    5. Create/update Obsidian note (if --vault-path given)
    6. Validate project
    7. Print summary
    """
    import json as _json
    from pathlib import Path
    from workshop_video_brain.workspace.manager import WorkspaceManager
    from workshop_video_brain.app.config import load_config
    from workshop_video_brain.edit_mcp.pipelines.ingest import run_ingest
    from workshop_video_brain.core.models.transcript import Transcript
    from workshop_video_brain.edit_mcp.pipelines.auto_mark import generate_markers
    from workshop_video_brain.core.models.markers import Marker, MarkerConfig
    from workshop_video_brain.edit_mcp.pipelines.review_timeline import build_review_timeline
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.validator import validate_project

    click.echo(f"\n{'='*60}")
    click.echo(f"  prepare-tutorial-project: {title}")
    click.echo(f"{'='*60}\n")

    # Step 1: Create workspace
    click.echo("[1/6] Creating workspace...")
    try:
        config_data = {"vault_path": vault_path} if vault_path else {}
        ws = WorkspaceManager.create(title=title, media_root=media_folder, config=config_data)
        click.echo(f"      Created: {ws.workspace_root}")
    except Exception as exc:
        click.echo(f"      Error creating workspace: {exc}", err=True)
        sys.exit(1)

    # Step 2: Ingest
    click.echo("[2/6] Ingesting media...")
    try:
        config = load_config()
        report = run_ingest(ws, config)
        click.echo(f"      Scanned={report.scanned_count} Proxied={report.proxied_count} "
                   f"Transcribed={report.transcribed_count} Silence={report.silence_detected_count}")
        if report.errors:
            for e in report.errors:
                click.echo(f"      Warning: {e}", err=True)
    except Exception as exc:
        click.echo(f"      Error during ingest: {exc}", err=True)

    # Step 3: Auto-generate markers
    click.echo("[3/6] Generating markers...")
    try:
        transcripts_dir = Path(ws.workspace_root) / "transcripts"
        markers_dir = Path(ws.workspace_root) / "markers"
        markers_dir.mkdir(parents=True, exist_ok=True)
        marker_config = MarkerConfig()
        total_markers = 0
        for json_path in sorted(transcripts_dir.glob("*_transcript.json")):
            transcript = Transcript.from_json(json_path.read_text(encoding="utf-8"))
            stem = json_path.stem.replace("_transcript", "")
            silence_path = markers_dir / f"{stem}_silence.json"
            silence_gaps: list[tuple[float, float]] = []
            if silence_path.exists():
                raw = _json.loads(silence_path.read_text(encoding="utf-8"))
                silence_gaps = [(g["start"], g["end"]) for g in raw if "start" in g]
            mks = generate_markers(transcript, silence_gaps, marker_config)
            out = markers_dir / f"{stem}_markers.json"
            out.write_text(_json.dumps([m.model_dump(mode="json") for m in mks], indent=2), encoding="utf-8")
            total_markers += len(mks)
        click.echo(f"      Generated {total_markers} markers.")
    except Exception as exc:
        click.echo(f"      Error generating markers: {exc}", err=True)

    # Step 4: Build review timeline
    click.echo("[4/6] Building review timeline...")
    try:
        all_markers: list[Marker] = []
        markers_dir = Path(ws.workspace_root) / "markers"
        if markers_dir.exists():
            for mf in markers_dir.glob("*_markers.json"):
                raw = _json.loads(mf.read_text(encoding="utf-8"))
                for item in raw:
                    all_markers.append(Marker(**item))
        if all_markers:
            kdenlive_path = build_review_timeline(all_markers, [], Path(ws.workspace_root))
            click.echo(f"      Timeline: {kdenlive_path}")
        else:
            click.echo("      No markers to build timeline from.")
            kdenlive_path = None
    except Exception as exc:
        click.echo(f"      Error building timeline: {exc}", err=True)
        kdenlive_path = None

    # Step 5: Create/update Obsidian note
    click.echo("[5/6] Updating Obsidian note...")
    if vault_path:
        try:
            from workshop_video_brain.production_brain.notes.writer import NoteWriter
            from workshop_video_brain.production_brain.notes.updater import update_frontmatter
            writer = NoteWriter()
            note_filename = f"{ws.project.slug}.md"
            note_path = writer.create(
                vault_path=vault_path,
                folder="videos",
                filename=note_filename,
                template_name="video-idea.md",
                frontmatter={
                    "title": title,
                    "status": "ingesting",
                    "workspace_root": ws.workspace_root,
                },
            )
            click.echo(f"      Note created: {note_path}")
        except FileExistsError:
            click.echo("      Note already exists; updating frontmatter.")
            try:
                from workshop_video_brain.production_brain.notes.updater import update_frontmatter
                from pathlib import Path as _Path
                note_path = _Path(vault_path) / "videos" / f"{ws.project.slug}.md"
                if note_path.exists():
                    update_frontmatter(note_path, {"status": "ingesting"})
            except Exception as exc:
                click.echo(f"      Warning: {exc}", err=True)
        except Exception as exc:
            click.echo(f"      Warning: {exc}", err=True)
    else:
        click.echo("      Skipped (no --vault-path provided).")

    # Step 6: Validate
    click.echo("[6/6] Validating project...")
    try:
        working_copies = Path(ws.workspace_root) / "projects" / "working_copies"
        kfiles = sorted(working_copies.glob("*.kdenlive")) if working_copies.exists() else []
        if kfiles:
            proj = parse_project(kfiles[-1])
            val_report = validate_project(proj, workspace_root=Path(ws.workspace_root))
            click.echo(f"      {val_report.summary}")
        else:
            click.echo("      No .kdenlive file found to validate.")
    except Exception as exc:
        click.echo(f"      Validation error: {exc}", err=True)

    # Summary
    click.echo(f"\n{'='*60}")
    click.echo(f"  Done! Workspace: {ws.workspace_root}")
    click.echo(f"{'='*60}\n")
    click.echo("Next steps:")
    click.echo(f"  wvb workspace status {ws.workspace_root}")
    click.echo(f"  wvb timeline review {ws.workspace_root}")
    if kdenlive_path:
        click.echo(f"  Open in Kdenlive: {kdenlive_path}")


# ---------------------------------------------------------------------------
# transitions group
# ---------------------------------------------------------------------------


@main.group()
def transitions() -> None:
    """Transition commands for timeline editing."""


@transitions.command("apply")
@click.argument("workspace_path")
@click.option("--type", "transition_type", default="crossfade",
              help="Transition type (crossfade, dissolve, fade_in, fade_out).")
@click.option("--preset", default="medium",
              help="Duration preset (short, medium, long).")
def transitions_apply_cmd(workspace_path: str, transition_type: str, preset: str) -> None:
    """Apply transitions between all clips in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import transitions_apply

    result = transitions_apply(workspace_path, transition_type, preset)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Transitions applied: {d['transitions_applied']}")
    click.echo(f"  Output: {d['kdenlive_path']}")


@transitions.command("at")
@click.argument("workspace_path")
@click.argument("timestamp", type=float)
@click.option("--type", "transition_type", default="crossfade",
              help="Transition type (crossfade, dissolve, fade_in, fade_out).")
@click.option("--preset", default="medium",
              help="Duration preset (short, medium, long).")
def apply_at(workspace_path: str, timestamp: float, transition_type: str, preset: str) -> None:
    """Apply a transition at TIMESTAMP seconds in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import transitions_apply_at

    result = transitions_apply_at(workspace_path, timestamp, transition_type, preset)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Transition applied at {timestamp}s")
    click.echo(f"  Output: {d['kdenlive_path']}")


@transitions.command("between")
@click.argument("workspace_path")
@click.argument("clip_index", type=int)
@click.option("--type", "transition_type", default="crossfade",
              help="Transition type (crossfade, dissolve, fade_in, fade_out).")
@click.option("--preset", default="medium",
              help="Duration preset (short, medium, long).")
def apply_between(workspace_path: str, clip_index: int, transition_type: str, preset: str) -> None:
    """Apply a transition between clip CLIP_INDEX and clip_index+1 in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import transitions_apply_between

    result = transitions_apply_between(workspace_path, clip_index, transition_type, preset)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Transition applied between clips {clip_index} and {clip_index + 1}")
    click.echo(f"  Output: {d['kdenlive_path']}")


# ---------------------------------------------------------------------------
# clip group
# ---------------------------------------------------------------------------


@main.group()
def clip() -> None:
    """Clip insertion and management commands."""


@clip.command("insert")
@click.argument("workspace_path")
@click.argument("media_path")
@click.option("--in", "in_seconds", default=0.0, type=float,
              help="In-point in seconds (default: 0.0).")
@click.option("--out", "out_seconds", default=-1.0, type=float,
              help="Out-point in seconds (default: -1 = full duration).")
@click.option("--position", default=-1, type=int,
              help="Position index in playlist (default: -1 = append at end).")
def clip_insert_cmd(
    workspace_path: str,
    media_path: str,
    in_seconds: float,
    out_seconds: float,
    position: int,
) -> None:
    """Insert MEDIA_PATH into the timeline of WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import clip_insert

    result = clip_insert(workspace_path, media_path, in_seconds, out_seconds, position)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Clip inserted: {d['producer_id']}")
    click.echo(f"  Frames: {d['in_frame']} -> {d['out_frame']}")
    click.echo(f"  Output: {d['kdenlive_path']}")


# ---------------------------------------------------------------------------
# clips group
# ---------------------------------------------------------------------------


@main.group()
def clips() -> None:
    """Clip organization and search."""


@clips.command("label")
@click.argument("workspace_path")
def clips_label(workspace_path: str) -> None:
    """Auto-label clips from transcript data in WORKSPACE_PATH."""
    from pathlib import Path
    from workshop_video_brain.edit_mcp.pipelines.clip_labeler import generate_labels

    try:
        labels = generate_labels(Path(workspace_path))
        if not labels:
            click.echo("No clips labeled. Run media ingest and markers auto first.")
            return
        click.echo(f"Labeled {len(labels)} clip(s):")
        for label in labels:
            click.echo(
                f"  {label.clip_ref}: {label.content_type}"
                f" [shot={label.shot_type}, speech={label.speech_density:.2f}]"
            )
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@clips.command("search")
@click.argument("workspace_path")
@click.argument("query")
def clips_search(workspace_path: str, query: str) -> None:
    """Search clips by content in WORKSPACE_PATH."""
    from pathlib import Path
    from workshop_video_brain.edit_mcp.pipelines.clip_search import search_clips

    try:
        results = search_clips(Path(workspace_path), query)
        if not results:
            click.echo(f"No clips found matching '{query}'.")
            return
        click.echo(f"Found {len(results)} result(s) for '{query}':")
        for r in results:
            click.echo(
                f"  [{r['score']:.2f}] {r['clip_ref']}"
                f" ({r['content_type']}) -- {r['summary'][:60]}"
            )
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# broll group
# ---------------------------------------------------------------------------


@main.group()
def broll() -> None:
    """B-Roll suggestion commands."""


@broll.command("suggest")
@click.argument("workspace_path")
def broll_suggest(workspace_path: str) -> None:
    """Analyse transcripts in WORKSPACE_PATH and print B-roll suggestions."""
    from pathlib import Path
    from workshop_video_brain.production_brain.skills.broll import extract_and_format

    try:
        markdown, suggestions = extract_and_format(Path(workspace_path))
        if not suggestions:
            click.echo("No B-roll opportunities detected.")
            return
        click.echo(markdown)
        click.echo(f"Total suggestions: {len(suggestions)}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# replay group
# ---------------------------------------------------------------------------


@main.group()
def replay() -> None:
    """Replay / highlight-reel generation commands."""


@replay.command("generate")
@click.argument("workspace_path")
@click.option("--duration", default=60.0, type=float,
              help="Target replay duration in seconds (default 60).")
def generate(workspace_path: str, duration: float) -> None:
    """Generate a highlight-reel replay for WORKSPACE_PATH."""
    from pathlib import Path
    from workshop_video_brain.edit_mcp.pipelines.replay_generator import generate_replay

    try:
        out = generate_replay(workspace_root=Path(workspace_path), target_duration=duration)
        click.echo(f"Replay generated: {out}")
        click.echo(f"  Target duration: {duration}s")
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# title-cards group
# ---------------------------------------------------------------------------


@main.group("title-cards")
def title_cards_group() -> None:
    """Title card generation commands."""


@title_cards_group.command("generate")
@click.argument("workspace_path")
def title_cards_generate(workspace_path: str) -> None:
    """Generate title cards from chapter markers in WORKSPACE_PATH."""
    from pathlib import Path
    from workshop_video_brain.edit_mcp.pipelines.title_cards import (
        generate_title_cards,
        save_title_cards,
    )

    try:
        workspace_root = Path(workspace_path)
        cards = generate_title_cards(workspace_root)
        out_path = save_title_cards(cards, workspace_root)
        click.echo(f"Generated {len(cards)} title card(s):")
        for card in cards:
            click.echo(
                f"  [{card.timestamp_seconds:.1f}s] {card.chapter_title}"
                + (f" -- {card.subtitle}" if card.subtitle else "")
            )
        click.echo(f"Saved to: {out_path}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# pacing group
# ---------------------------------------------------------------------------


@main.group()
def pacing() -> None:
    """Pacing and energy analysis commands."""


@pacing.command("analyze")
@click.argument("workspace_path")
def pacing_analyze(workspace_path: str) -> None:
    """Analyse pacing and energy for all transcripts in WORKSPACE_PATH."""
    from pathlib import Path
    from workshop_video_brain.core.models.transcript import Transcript
    from workshop_video_brain.edit_mcp.pipelines.pacing_analyzer import (
        analyze_pacing,
        format_pacing_report,
    )

    try:
        transcripts_dir = Path(workspace_path) / "transcripts"
        if not transcripts_dir.exists():
            click.echo("No transcripts/ directory found. Run 'media ingest' first.")
            return

        json_files = sorted(transcripts_dir.glob("*_transcript.json"))
        if not json_files:
            click.echo("No transcript JSON files found.")
            return

        for json_path in json_files:
            try:
                transcript = Transcript.from_json(json_path.read_text(encoding="utf-8"))
                report = analyze_pacing(transcript)
                markdown = format_pacing_report(report)
                stem = json_path.stem.replace("_transcript", "")
                click.echo(f"\n{'='*60}")
                click.echo(f"  {stem}")
                click.echo(f"{'='*60}")
                click.echo(markdown)
            except Exception as exc:
                click.echo(f"  Warning: {json_path.name}: {exc}", err=True)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# wvb group
# ---------------------------------------------------------------------------


@main.group()
def wvb() -> None:
    """Workshop Video Brain pattern extraction commands."""


@wvb.group("pattern")
def wvb_pattern() -> None:
    """MYOG Pattern Brain commands."""


@wvb_pattern.command("extract")
@click.argument("workspace_path")
def wvb_pattern_extract(workspace_path: str) -> None:
    """Extract MYOG build data from transcripts in WORKSPACE_PATH.

    Reads the first available transcript, extracts materials, measurements,
    build steps, and tips/warnings, saves build_notes.md to reports/, and
    prints a summary.
    """
    from pathlib import Path
    from workshop_video_brain.production_brain.skills.pattern import (
        extract_and_format,
        save_build_notes,
    )

    try:
        ws_path = Path(workspace_path)
        result = extract_and_format(ws_path)
        build_data = result["build_data"]
        build_notes_md = result["build_notes_md"]

        notes_path = save_build_notes(ws_path, build_notes_md)

        click.echo(f"Pattern Brain extraction complete:")
        click.echo(f"  Materials:    {len(build_data.materials)}")
        click.echo(f"  Measurements: {len(build_data.measurements)}")
        click.echo(f"  Steps:        {len(build_data.steps)}")
        click.echo(f"  Tips:         {len([t for t in build_data.tips if t.tip_type == 'tip'])}")
        click.echo(f"  Warnings:     {len([t for t in build_data.tips if t.tip_type == 'warning'])}")
        click.echo(f"  Saved to:     {notes_path}")
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# NLE clip operations (extend existing `clip` group)
# ---------------------------------------------------------------------------


@clip.command("remove")
@click.argument("workspace_path")
@click.argument("clip_index", type=int)
@click.option("--track", default=0, type=int, help="Video track index (default: 0).")
def clip_remove_cmd(workspace_path: str, clip_index: int, track: int) -> None:
    """Remove clip at CLIP_INDEX from WORKSPACE_PATH timeline."""
    from workshop_video_brain.edit_mcp.server.tools import clip_remove

    result = clip_remove(workspace_path, clip_index, track)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Removed clip {d['removed_clip_index']} from {d['playlist_id']}")
    click.echo(f"  Output: {d['kdenlive_path']}")


@clip.command("move")
@click.argument("workspace_path")
@click.argument("from_index", type=int)
@click.argument("to_index", type=int)
@click.option("--track", default=0, type=int, help="Video track index (default: 0).")
def clip_move_cmd(workspace_path: str, from_index: int, to_index: int, track: int) -> None:
    """Move clip FROM_INDEX to TO_INDEX in WORKSPACE_PATH timeline."""
    from workshop_video_brain.edit_mcp.server.tools import clip_move

    result = clip_move(workspace_path, from_index, to_index, track)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Moved clip {d['from_index']} -> {d['to_index']} in {d['playlist_id']}")
    click.echo(f"  Output: {d['kdenlive_path']}")


@clip.command("split")
@click.argument("workspace_path")
@click.argument("clip_index", type=int)
@click.argument("timestamp", type=float)
@click.option("--track", default=0, type=int, help="Video track index (default: 0).")
def clip_split_cmd(workspace_path: str, clip_index: int, timestamp: float, track: int) -> None:
    """Split clip CLIP_INDEX at TIMESTAMP (seconds) in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import clip_split

    result = clip_split(workspace_path, clip_index, timestamp)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Split clip {d['clip_index']} at {d['split_at_seconds']}s ({d['split_at_frame']}f)")
    click.echo(f"  Output: {d['kdenlive_path']}")


@clip.command("trim")
@click.argument("workspace_path")
@click.argument("clip_index", type=int)
@click.option("--in", "in_seconds", default=-1.0, type=float,
              help="New in-point in seconds (-1 = unchanged).")
@click.option("--out", "out_seconds", default=-1.0, type=float,
              help="New out-point in seconds (-1 = unchanged).")
def clip_trim_cmd(
    workspace_path: str,
    clip_index: int,
    in_seconds: float,
    out_seconds: float,
) -> None:
    """Trim clip CLIP_INDEX in/out points in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import clip_trim

    result = clip_trim(workspace_path, clip_index, in_seconds, out_seconds)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Trimmed clip {d['clip_index']}: in={d['new_in_frame']} out={d['new_out_frame']}")
    click.echo(f"  Output: {d['kdenlive_path']}")


@clip.command("ripple-delete")
@click.argument("workspace_path")
@click.argument("clip_index", type=int)
@click.option("--track", default=0, type=int, help="Video track index (default: 0).")
def clip_ripple_delete_cmd(workspace_path: str, clip_index: int, track: int) -> None:
    """Ripple-delete clip CLIP_INDEX in WORKSPACE_PATH (close gap)."""
    from workshop_video_brain.edit_mcp.server.tools import clip_ripple_delete

    result = clip_ripple_delete(workspace_path, clip_index, track)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Ripple-deleted clip {d['deleted_clip_index']} from {d['playlist_id']}")
    click.echo(f"  Output: {d['kdenlive_path']}")


@clip.command("speed")
@click.argument("workspace_path")
@click.argument("clip_index", type=int)
@click.argument("speed_value", type=float)
@click.option("--track", default=0, type=int, help="Video track index (default: 0).")
def clip_speed_cmd(workspace_path: str, clip_index: int, speed_value: float, track: int) -> None:
    """Set playback speed for clip CLIP_INDEX in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import clip_speed

    result = clip_speed(workspace_path, clip_index, speed_value, track)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Set speed={d['speed']}x for clip {d['clip_index']} in {d['playlist_id']}")
    click.echo(f"  Output: {d['kdenlive_path']}")


@clip.command("gap")
@click.argument("workspace_path")
@click.argument("position", type=int)
@click.argument("duration", type=float)
@click.option("--track", default=0, type=int, help="Video track index (default: 0).")
def clip_gap_cmd(workspace_path: str, position: int, duration: float, track: int) -> None:
    """Insert a gap of DURATION seconds at POSITION in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import gap_insert

    result = gap_insert(workspace_path, position, duration, track)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Inserted {d['duration_seconds']}s gap at position {d['position']} in {d['playlist_id']}")
    click.echo(f"  Output: {d['kdenlive_path']}")


# ---------------------------------------------------------------------------
# audio group
# ---------------------------------------------------------------------------


@main.group()
def audio() -> None:
    """Audio editing commands."""


@audio.command("fade")
@click.argument("workspace_path")
@click.argument("clip_index", type=int)
@click.option("--type", "fade_type", default="in",
              type=click.Choice(["in", "out"]), help="Fade direction (default: in).")
@click.option("--duration", default=1.0, type=float, help="Fade duration in seconds (default: 1.0).")
@click.option("--track", default=0, type=int, help="Video track index (default: 0).")
def audio_fade_cmd(
    workspace_path: str,
    clip_index: int,
    fade_type: str,
    duration: float,
    track: int,
) -> None:
    """Apply an audio fade to clip CLIP_INDEX in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import audio_fade

    result = audio_fade(workspace_path, clip_index, fade_type, duration, track)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Applied audio fade-{d['fade_type']} ({d['duration_seconds']}s) to clip {d['clip_index']}")
    click.echo(f"  Output: {d['kdenlive_path']}")


# ---------------------------------------------------------------------------
# track group
# ---------------------------------------------------------------------------


@main.group()
def track() -> None:
    """Track management commands."""


@track.command("add")
@click.argument("workspace_path")
@click.option("--type", "track_type", default="video",
              type=click.Choice(["video", "audio"]), help="Track type (default: video).")
@click.option("--name", default="", help="Track name.")
def track_add_cmd(workspace_path: str, track_type: str, name: str) -> None:
    """Add a new track to the project in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import track_add

    result = track_add(workspace_path, track_type, name)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Added {d['track_type']} track: {d['new_playlist_id']}")
    click.echo(f"  Output: {d['kdenlive_path']}")


@track.command("mute")
@click.argument("workspace_path")
@click.argument("track_index", type=int)
@click.option("--unmute", is_flag=True, default=False, help="Unmute instead of muting.")
def track_mute_cmd(workspace_path: str, track_index: int, unmute: bool) -> None:
    """Mute (or unmute) track TRACK_INDEX in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import track_mute

    muted = not unmute
    result = track_mute(workspace_path, track_index, muted)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    action = "Muted" if d["muted"] else "Unmuted"
    click.echo(f"{action} track {d['track_index']} ({d['track_id']})")
    click.echo(f"  Output: {d['kdenlive_path']}")


@track.command("visibility")
@click.argument("workspace_path")
@click.argument("track_index", type=int)
@click.option("--hide", is_flag=True, default=False, help="Hide instead of showing.")
def track_visibility_cmd(workspace_path: str, track_index: int, hide: bool) -> None:
    """Show (or hide) track TRACK_INDEX in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import track_visibility

    visible = not hide
    result = track_visibility(workspace_path, track_index, visible)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    action = "Shown" if d["visible"] else "Hidden"
    click.echo(f"{action} track {d['track_index']} ({d['track_id']})")
    click.echo(f"  Output: {d['kdenlive_path']}")


# ---------------------------------------------------------------------------
# assembly group
# ---------------------------------------------------------------------------


@main.group()
def assembly() -> None:
    """Auto-assemble timeline from script and clips."""


@assembly.command("plan")
@click.argument("workspace_path")
def assembly_plan_cmd(workspace_path: str) -> None:
    """Generate assembly plan (clip-to-step matching) for WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import assembly_plan

    result = assembly_plan(workspace_path)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Assembly Plan: {d.get('project_title') or '(untitled)'}")
    click.echo(f"  Steps: {len(d['steps'])}")
    click.echo(f"  Unmatched clips: {len(d['unmatched_clips'])}")
    click.echo(f"  Estimated duration: {d['total_estimated_duration']:.1f}s")
    click.echo("")
    for step in d["steps"]:
        primaries = [c for c in step["clips"] if c["role"] == "primary"]
        inserts = [c for c in step["clips"] if c["role"] == "insert"]
        primary_str = (
            f"{primaries[0]['clip_ref']} (score: {primaries[0]['score']:.2f})"
            if primaries
            else "(no primary)"
        )
        insert_str = ""
        if inserts:
            insert_str = " + " + ", ".join(
                f"{c['clip_ref']} (insert)" for c in inserts
            )
        click.echo(
            f"  Step {step['step_number']}: '{step['step_description']}'"
            f" → {primary_str}{insert_str}"
        )
    if d["unmatched_clips"]:
        click.echo("")
        click.echo("  Unmatched clips:")
        for clip in d["unmatched_clips"]:
            click.echo(f"    - {clip}")


@assembly.command("build")
@click.argument("workspace_path")
@click.option("--no-transitions", is_flag=True, default=False,
              help="Disable transitions between steps.")
@click.option("--no-chapters", is_flag=True, default=False,
              help="Disable chapter markers.")
def assembly_build_cmd(
    workspace_path: str,
    no_transitions: bool,
    no_chapters: bool,
) -> None:
    """Build first-cut Kdenlive project from assembly plan for WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import assembly_build

    result = assembly_build(
        workspace_path,
        add_transitions=not no_transitions,
        add_chapters=not no_chapters,
    )
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Assembly complete.")
    click.echo(f"  Project: {d['kdenlive_path']}")
    click.echo(f"  Steps:   {d['steps_count']}")
    click.echo(f"  Duration: {d['total_estimated_duration']:.1f}s estimated")
    if d["unmatched_clips"]:
        click.echo(f"  Unmatched clips ({len(d['unmatched_clips'])}): {', '.join(d['unmatched_clips'])}")
    click.echo(f"  Report:  {d['assembly_report_path']}")


# ---------------------------------------------------------------------------
# audio group -- processing commands (extends existing audio group above)
# ---------------------------------------------------------------------------


@audio.command("enhance")
@click.argument("workspace_path")
@click.option("--file", "file_path", default="", help="Path to audio file (default: latest in media/raw/).")
@click.option("--preset", default="youtube_voice",
              type=click.Choice(["youtube_voice", "podcast", "raw_cleanup"]),
              help="Enhancement preset (default: youtube_voice).")
def audio_enhance_cmd(workspace_path: str, file_path: str, preset: str) -> None:
    """Apply full voice enhancement pipeline to an audio file in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import audio_enhance

    result = audio_enhance(workspace_path, file_path, preset)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Enhancement complete ({d['preset']} preset, {d['steps_count']} steps).")
    click.echo(f"  Input:  {d['input']}")
    click.echo(f"  Output: {d['output']}")


@audio.command("normalize")
@click.argument("workspace_path")
@click.option("--file", "file_path", default="", help="Path to audio file (default: latest in media/raw/).")
@click.option("--lufs", "target_lufs", default=-16.0, type=float, help="Target LUFS (default: -16.0).")
def audio_normalize_cmd(workspace_path: str, file_path: str, target_lufs: float) -> None:
    """Normalize audio loudness in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import audio_normalize

    result = audio_normalize(workspace_path, file_path, target_lufs)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Normalized to {d['target_lufs']} LUFS ({d['duration_ms']:.0f}ms).")
    click.echo(f"  Input:  {d['input']}")
    click.echo(f"  Output: {d['output']}")


@audio.command("denoise")
@click.argument("workspace_path")
@click.option("--file", "file_path", default="", help="Path to audio file (default: latest in media/raw/).")
@click.option("--strength", "strength_db", default=-25.0, type=float,
              help="Noise floor in dB (default: -25.0).")
def audio_denoise_cmd(workspace_path: str, file_path: str, strength_db: float) -> None:
    """Remove background noise from audio in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import audio_denoise

    result = audio_denoise(workspace_path, file_path, strength_db)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Denoised (floor {d['strength_db']} dB, {d['duration_ms']:.0f}ms).")
    click.echo(f"  Input:  {d['input']}")
    click.echo(f"  Output: {d['output']}")


@audio.command("analyze")
@click.argument("workspace_path")
@click.option("--file", "file_path", default="", help="Path to audio file (default: latest in media/raw/).")
def audio_analyze_cmd(workspace_path: str, file_path: str) -> None:
    """Analyze audio levels (LUFS, peak) in WORKSPACE_PATH."""
    from workshop_video_brain.edit_mcp.server.tools import audio_analyze

    result = audio_analyze(workspace_path, file_path)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Audio analysis: {d['input']}")
    click.echo(f"  Integrated LUFS: {d['integrated_lufs']:.1f}")
    click.echo(f"  True peak:       {d['true_peak_db']:.1f} dBTP")
    click.echo(f"  Loudness range:  {d['loudness_range']:.1f} LU")


@audio.command("enhance-all")
@click.argument("workspace_path")
@click.option("--preset", default="youtube_voice",
              type=click.Choice(["youtube_voice", "podcast", "raw_cleanup"]),
              help="Enhancement preset (default: youtube_voice).")
def audio_enhance_all_cmd(workspace_path: str, preset: str) -> None:
    """Enhance all audio files in WORKSPACE_PATH media/raw/ folder."""
    from workshop_video_brain.edit_mcp.server.tools import audio_enhance_all

    result = audio_enhance_all(workspace_path, preset)
    if result["status"] == "error":
        click.echo(f"Error: {result['message']}", err=True)
        sys.exit(1)
    d = result["data"]
    click.echo(f"Batch enhancement complete ({preset} preset).")
    click.echo(f"  Processed: {d['processed']}")
    click.echo(f"  Failed:    {d['failed']}")
    click.echo(f"  Output:    {d['output_dir']}")


# ---------------------------------------------------------------------------
# init / init-quick commands
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--vault-path",
    prompt="Where should your video vault live?",
    default="~/Videos",
    help="Path to master Obsidian vault",
)
@click.option(
    "--projects-root",
    prompt="Where do your project workspaces live?",
    default="~/Projects",
    help="Root folder for project workspaces",
)
@click.option(
    "--media-library",
    default="",
    help="Separate media library path (default: inside projects root)",
)
def init(vault_path: str, projects_root: str, media_library: str) -> None:
    """Initialize ForgeFrame: create vault structure, media folders, and config."""
    from pathlib import Path as _Path
    from workshop_video_brain.app.init_system import initialize_forgeframe

    media_lib = _Path(media_library) if media_library else None

    click.echo("ForgeFrame Init")
    click.echo("===============")
    click.echo("")

    try:
        result = initialize_forgeframe(
            vault_path=vault_path,
            projects_root=projects_root,
            media_library_root=media_lib,
        )
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    # Vault
    click.echo(f"Creating vault at {result.vault_path}...")
    _shown_vault: set[str] = set()
    for folder in result.vault_folders_created:
        top = folder.split("/")[0]
        if top not in _shown_vault:
            click.echo(f"  + {top}/")
            _shown_vault.add(top)
    click.echo(f"  Created {len(result.vault_folders_created)} vault folders")
    click.echo("")

    # Media
    click.echo(f"Creating media library at {result.projects_root}/Media Library/...")
    _shown_media: set[str] = set()
    for folder in result.media_folders_created:
        top = folder.split("/")[0]
        if top not in _shown_media:
            click.echo(f"  + {top}/")
            _shown_media.add(top)
    click.echo(f"  Created {len(result.media_folders_created)} media folders")
    click.echo("")

    # Config
    click.echo("Writing config...")
    click.echo(f"  + .env")
    click.echo(f"  + {result.config_file_written}")
    click.echo("")

    # Templates
    click.echo("Templates created:")
    for tmpl in [
        "Templates/YouTube/Video Idea.md",
        "Templates/YouTube/In Progress.md",
        "Templates/YouTube/Published.md",
        "Templates/YouTube/B-Roll Entry.md",
    ]:
        click.echo(f"  + {tmpl}")
    click.echo("")

    click.echo(f"Done! Open {result.vault_path}/ in Obsidian to see your vault.")

    if result.notes:
        for note in result.notes:
            click.echo(f"  Note: {note}")


@main.command("init-quick")
@click.argument("vault_path")
@click.argument("projects_root")
def init_quick(vault_path: str, projects_root: str) -> None:
    """Quick init with paths as arguments (no prompts)."""
    from workshop_video_brain.app.init_system import initialize_forgeframe

    try:
        result = initialize_forgeframe(
            vault_path=vault_path,
            projects_root=projects_root,
        )
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(f"ForgeFrame initialized.")
    click.echo(f"  Vault:         {result.vault_path}")
    click.echo(f"  Projects root: {result.projects_root}")
    click.echo(f"  Config:        {result.config_file_written}")
    click.echo(f"  .env:          {result.env_file_written}")
    click.echo(f"  Vault folders: {len(result.vault_folders_created)} created")
    click.echo(f"  Media folders: {len(result.media_folders_created)} created")


# ---------------------------------------------------------------------------
# new-project and list-projects top-level commands
# ---------------------------------------------------------------------------


@main.command("new-project")
@click.argument("title")
@click.option("--brain-dump", "-b", default="", help="Rough idea to start planning from")
@click.option("--type", "project_type", default="tutorial",
              type=click.Choice(["tutorial", "review", "vlog", "build"]))
def new_project(title: str, brain_dump: str, project_type: str) -> None:
    """Create a new video project and start the planning process.

    Examples:

        wvb new-project "Zippered Pouch Tutorial"

        wvb new-project "Stove Bag Build" -b "Make a lightweight alcohol stove bag from X-Pac"
    """
    from workshop_video_brain.edit_mcp.pipelines.new_project import create_new_project
    from pathlib import Path

    click.echo(f"\nCreating project: {title}")
    click.echo("=" * (len("Creating project: ") + len(title)))
    click.echo()

    try:
        result = create_new_project(
            title=title,
            brain_dump=brain_dump,
            project_type=project_type,
        )
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    # Workspace section
    workspace_display = result.workspace_path
    try:
        workspace_display = str(Path(result.workspace_path).relative_to(Path.home().parent.parent))
    except ValueError:
        pass
    try:
        workspace_display = "~/" + str(Path(result.workspace_path).relative_to(Path.home()))
    except ValueError:
        pass

    click.echo(f"Workspace: {workspace_display}/")
    click.echo("  \u2713 Folder structure created")
    click.echo("  \u2713 Intake folder ready (drop raw files here)")
    click.echo()

    # Vault note section
    if result.vault_note_path:
        note_display = result.vault_note_path
        try:
            note_display = "~/" + str(Path(result.vault_note_path).relative_to(Path.home()))
        except ValueError:
            pass
        click.echo(f"Vault note: {note_display}")
        if brain_dump:
            click.echo("  \u2713 Note created with brain dump")
        else:
            click.echo("  \u2713 Note created")
        click.echo()
    else:
        click.echo("Vault note: (skipped — no vault path configured)")
        click.echo()

    # Planning section
    if brain_dump:
        click.echo("Planning from brain dump...")
        if result.outline_generated:
            click.echo("  \u2713 Outline generated")
        if result.script_generated:
            click.echo("  \u2713 Script drafted")
        if result.shot_plan_generated:
            click.echo("  \u2713 Shot plan created")
        click.echo()

    # Next steps
    click.echo("Next steps:")
    step = 1
    if result.vault_note_path:
        note_disp = result.vault_note_path
        try:
            note_disp = "~/" + str(Path(result.vault_note_path).relative_to(Path.home()))
        except ValueError:
            pass
        click.echo(f"  {step}. Review the outline: open {note_disp}")
        step += 1
    ws_disp = result.workspace_path
    try:
        ws_disp = "~/" + str(Path(result.workspace_path).relative_to(Path.home()))
    except ValueError:
        pass
    click.echo(f"  {step}. Drop raw footage into {ws_disp}/intake/")
    step += 1
    click.echo(f"  {step}. Run: wvb media ingest {ws_disp}/")
    click.echo()


@main.command("list-projects")
def list_projects() -> None:
    """List all ForgeFrame video projects."""
    from workshop_video_brain.edit_mcp.pipelines.new_project import list_projects as _list_projects

    try:
        projects = _list_projects()
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if not projects:
        click.echo("No projects found.")
        click.echo("Run 'wvb new-project \"My Title\"' to create your first project.")
        return

    click.echo(f"Projects ({len(projects)}):")
    click.echo()
    for p in projects:
        click.echo(f"  {p['name']}")
        click.echo(f"    Status: {p['status']}")
        click.echo(f"    Path:   {p['workspace_path']}")
        if p.get("vault_note_path"):
            click.echo(f"    Note:   {p['vault_note_path']}")
        click.echo()


# ---------------------------------------------------------------------------
# broll-library group
# ---------------------------------------------------------------------------


@main.group("broll-library")
def broll_library_group() -> None:
    """Cross-project B-roll library management."""


def _get_vault_path() -> "Path | None":
    """Resolve vault path from env var or config."""
    import os
    from pathlib import Path as _Path
    vault = os.environ.get("WVB_VAULT_PATH")
    if vault:
        return _Path(vault).expanduser()
    config_path = _Path.home() / ".forgeframe" / "config.json"
    if config_path.exists():
        try:
            import json as _json
            cfg = _json.loads(config_path.read_text(encoding="utf-8"))
            if "vault_path" in cfg:
                return _Path(cfg["vault_path"]).expanduser()
        except Exception:
            pass
    return None


@broll_library_group.command("index")
@click.argument("workspace_path", default="")
def broll_library_index(workspace_path: str) -> None:
    """Index a project's clips into the B-roll library.

    If WORKSPACE_PATH is omitted, indexes all configured projects.
    """
    from pathlib import Path as _Path
    from workshop_video_brain.edit_mcp.pipelines.broll_library import (
        index_project,
        index_all_projects,
    )

    vault = _get_vault_path()
    if vault is None:
        click.echo(
            "Error: Vault path not configured. Set WVB_VAULT_PATH or run 'wvb init'.",
            err=True,
        )
        sys.exit(1)

    try:
        if workspace_path:
            ws = _Path(workspace_path)
            if not ws.exists():
                click.echo(f"Error: Workspace path does not exist: {workspace_path}", err=True)
                sys.exit(1)
            result = index_project(vault, ws)
            click.echo(f"Indexed {workspace_path}:")
            click.echo(f"  Added:   {result['added']}")
            click.echo(f"  Skipped: {result['skipped']}")
            click.echo(f"  Total:   {result['total']}")
        else:
            import json as _json
            config_path = _Path.home() / ".forgeframe" / "config.json"
            if not config_path.exists():
                click.echo(
                    "Error: No workspace_path provided and no ~/.forgeframe/config.json found.",
                    err=True,
                )
                sys.exit(1)
            cfg = _json.loads(config_path.read_text(encoding="utf-8"))
            projects_root = cfg.get("projects_root", "")
            if not projects_root:
                click.echo("Error: projects_root not set in config.", err=True)
                sys.exit(1)
            result = index_all_projects(vault, _Path(projects_root))
            click.echo("Indexed all projects:")
            click.echo(f"  Projects scanned: {result['projects_scanned']}")
            click.echo(f"  Total added:      {result['total_added']}")
            click.echo(f"  Total clips:      {result['total_clips']}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@broll_library_group.command("search")
@click.argument("query")
@click.option("--type", "content_type", default="", help="Filter by content type.")
@click.option("--shot", "shot_type", default="", help="Filter by shot type.")
@click.option("--min-rating", default=0, type=int, help="Minimum rating (0-5).")
def broll_library_search(query: str, content_type: str, shot_type: str, min_rating: int) -> None:
    """Search B-roll library across all projects."""
    from workshop_video_brain.edit_mcp.pipelines.broll_library import search_library

    vault = _get_vault_path()
    if vault is None:
        click.echo(
            "Error: Vault path not configured. Set WVB_VAULT_PATH or run 'wvb init'.",
            err=True,
        )
        sys.exit(1)

    try:
        filters: dict = {}
        if content_type:
            filters["content_type"] = content_type
        if shot_type:
            filters["shot_type"] = shot_type
        if min_rating > 0:
            filters["min_rating"] = min_rating

        results = search_library(vault, query, filters)
        if not results:
            click.echo("No matching clips found.")
            return

        click.echo(f"Found {len(results)} clip(s):\n")
        for entry in results:
            dur = f"{entry.duration_seconds:.1f}s" if entry.duration_seconds else "-"
            click.echo(f"  {entry.clip_ref}")
            click.echo(f"    Project:  {entry.source_project}")
            click.echo(f"    Duration: {dur}")
            click.echo(f"    Type:     {entry.content_type} / {entry.shot_type}")
            click.echo(f"    Tags:     {', '.join(entry.tags[:6])}")
            click.echo(f"    Path:     {entry.source_path}")
            if entry.rating:
                click.echo(f"    Rating:   {'*' * entry.rating}")
            click.echo()
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@broll_library_group.command("tag")
@click.argument("source_path")
@click.option("--tags", default="", help="Comma-separated tags to add.")
@click.option("--rating", default=-1, type=int, help="Rating 0-5 (-1 = no change).")
@click.option("--description", default="", help="Description to set.")
def broll_library_tag(source_path: str, tags: str, rating: int, description: str) -> None:
    """Tag a clip in the B-roll library."""
    from workshop_video_brain.edit_mcp.pipelines.broll_library import tag_clip

    vault = _get_vault_path()
    if vault is None:
        click.echo(
            "Error: Vault path not configured. Set WVB_VAULT_PATH or run 'wvb init'.",
            err=True,
        )
        sys.exit(1)

    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        entry = tag_clip(vault, source_path, tags=tag_list, rating=rating, description=description)
        click.echo(f"Updated: {entry.clip_ref}")
        click.echo(f"  Tags:   {', '.join(entry.tags)}")
        if entry.rating:
            click.echo(f"  Rating: {'*' * entry.rating}")
        if entry.description:
            click.echo(f"  Desc:   {entry.description}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@broll_library_group.command("stats")
def broll_library_stats() -> None:
    """Show B-roll library statistics."""
    from workshop_video_brain.edit_mcp.pipelines.broll_library import get_library_stats

    vault = _get_vault_path()
    if vault is None:
        click.echo(
            "Error: Vault path not configured. Set WVB_VAULT_PATH or run 'wvb init'.",
            err=True,
        )
        sys.exit(1)

    try:
        stats = get_library_stats(vault)
        click.echo(f"B-Roll Library Statistics:")
        click.echo(f"  Total clips:      {stats['total_clips']}")
        click.echo(f"  Projects indexed: {len(stats['projects_indexed'])}")
        if stats["projects_indexed"]:
            for proj in stats["projects_indexed"]:
                click.echo(f"    - {proj}")
        if stats["content_type_breakdown"]:
            click.echo("\n  Content types:")
            for ct, count in sorted(stats["content_type_breakdown"].items()):
                click.echo(f"    {ct}: {count}")
        if stats["top_tags"]:
            click.echo("\n  Top tags:")
            for tag, count in list(stats["top_tags"].items())[:10]:
                click.echo(f"    {tag}: {count}")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
