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


if __name__ == "__main__":
    main()
