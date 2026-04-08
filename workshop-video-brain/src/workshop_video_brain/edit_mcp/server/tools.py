"""MCP tool registrations for workshop-video-brain.

All tools validate inputs, call the appropriate pipeline/adapter, and return
a structured dict: {"status": "success", "data": {...}} or
{"status": "error", "message": "..."}.

This module must be imported by server.py so that the @mcp.tool() decorators
execute and register each tool with the FastMCP instance.
"""
from __future__ import annotations

import json
from pathlib import Path

from workshop_video_brain.server import mcp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(data: dict) -> dict:
    return {"status": "success", "data": data}


def _err(message: str) -> dict:
    return {"status": "error", "message": message}


def _require_workspace(workspace_path: str):
    """Return (Path, Workspace) or raise ValueError."""
    from workshop_video_brain.workspace.manager import WorkspaceManager
    p = Path(workspace_path)
    if not p.exists():
        raise FileNotFoundError(f"Workspace path does not exist: {workspace_path}")
    return p, WorkspaceManager.open(p)


# ---------------------------------------------------------------------------
# Workspace tools
# ---------------------------------------------------------------------------


@mcp.tool()
def workspace_create(title: str, media_root: str, vault_path: str = "") -> dict:
    """Create a new workspace with the given title and media root.

    Args:
        title: Human-readable project title.
        media_root: Absolute path to the folder containing raw media files.
        vault_path: Optional path to an Obsidian vault root.

    Returns:
        Workspace metadata including workspace_root and workspace_id.
    """
    try:
        from workshop_video_brain.workspace.manager import WorkspaceManager
        config = {"vault_path": vault_path} if vault_path else {}
        workspace = WorkspaceManager.create(
            title=title,
            media_root=media_root,
            config=config,
        )
        return _ok({
            "workspace_id": str(workspace.id),
            "workspace_root": workspace.workspace_root,
            "media_root": workspace.media_root,
            "title": workspace.project.title,
            "slug": workspace.project.slug,
            "status": workspace.project.status,
        })
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def workspace_status(workspace_path: str) -> dict:
    """Return manifest data for an existing workspace.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Manifest fields: workspace_id, title, slug, status, media_root, etc.
    """
    try:
        from workshop_video_brain.workspace.manifest import read_manifest
        manifest = read_manifest(workspace_path)
        return _ok({
            "workspace_id": str(manifest.workspace_id),
            "project_title": manifest.project_title,
            "slug": manifest.slug,
            "status": manifest.status,
            "media_root": manifest.media_root,
            "vault_note_path": manifest.vault_note_path,
            "content_type": manifest.content_type,
            "created_at": manifest.created_at.isoformat(),
            "updated_at": manifest.updated_at.isoformat(),
        })
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Media tools
# ---------------------------------------------------------------------------


@mcp.tool()
def media_ingest(workspace_path: str) -> dict:
    """Run the full ingest pipeline: scan, proxy, transcribe, detect silence.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        IngestReport summary with counts of scanned, proxied, transcribed assets.
    """
    try:
        p, workspace = _require_workspace(workspace_path)
        from workshop_video_brain.app.config import load_config
        from workshop_video_brain.edit_mcp.pipelines.ingest import run_ingest
        config = load_config()
        report = run_ingest(workspace, config)
        return _ok({
            "scanned_count": report.scanned_count,
            "proxied_count": report.proxied_count,
            "transcribed_count": report.transcribed_count,
            "silence_detected_count": report.silence_detected_count,
            "errors": report.errors,
        })
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def media_list_assets(workspace_path: str) -> dict:
    """List media assets found in the workspace media/raw directory.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        List of asset file paths found under media/raw/.
    """
    try:
        raw_dir = Path(workspace_path) / "media" / "raw"
        if not raw_dir.exists():
            return _ok({"assets": [], "count": 0})
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import scan_directory
        assets = scan_directory(raw_dir)
        return _ok({
            "assets": [
                {
                    "id": str(a.id),
                    "path": a.path,
                    "media_type": a.media_type,
                    "duration_seconds": a.duration_seconds,
                    "file_size_bytes": a.file_size_bytes,
                }
                for a in assets
            ],
            "count": len(assets),
        })
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Proxy tools
# ---------------------------------------------------------------------------


@mcp.tool()
def proxy_generate(workspace_path: str) -> dict:
    """Generate proxy files for all media assets that need them.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Count of proxies generated and any errors encountered.
    """
    try:
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import scan_directory
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import (
            ProxyPolicy,
            generate_proxy,
            needs_proxy,
            proxy_path_for,
        )
        raw_dir = Path(workspace_path) / "media" / "raw"
        proxy_dir = Path(workspace_path) / "media" / "proxies"
        proxy_dir.mkdir(parents=True, exist_ok=True)
        if not raw_dir.exists():
            return _ok({"proxied": 0, "skipped": 0, "errors": []})
        assets = scan_directory(raw_dir)
        policy = ProxyPolicy()
        proxied, skipped, errors = 0, 0, []
        for asset in assets:
            if needs_proxy(asset, policy):
                existing = proxy_path_for(asset, proxy_dir)
                if existing.exists():
                    skipped += 1
                    continue
                try:
                    generate_proxy(asset, proxy_dir, policy)
                    proxied += 1
                except Exception as exc:
                    errors.append(str(exc))
            else:
                skipped += 1
        return _ok({"proxied": proxied, "skipped": skipped, "errors": errors})
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Transcript tools
# ---------------------------------------------------------------------------


@mcp.tool()
def transcript_generate(workspace_path: str) -> dict:
    """Generate transcripts for all media assets in the workspace.

    Requires FFmpeg and faster-whisper to be available.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Count of transcripts generated and any errors.
    """
    try:
        p, workspace = _require_workspace(workspace_path)
        from workshop_video_brain.app.config import load_config
        from workshop_video_brain.edit_mcp.pipelines.ingest import run_ingest
        config = load_config()
        report = run_ingest(workspace, config)
        return _ok({
            "transcribed_count": report.transcribed_count,
            "scanned_count": report.scanned_count,
            "errors": report.errors,
        })
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def transcript_export(workspace_path: str, format: str = "srt") -> dict:
    """Export transcripts in the specified format.

    Args:
        workspace_path: Path to the workspace root directory.
        format: Export format, currently only "srt" is supported.

    Returns:
        List of exported file paths.
    """
    try:
        transcripts_dir = Path(workspace_path) / "transcripts"
        if not transcripts_dir.exists():
            return _ok({"exported": [], "count": 0})
        exported = []
        if format == "srt":
            srt_files = list(transcripts_dir.glob("*_transcript.srt"))
            exported = [str(f) for f in srt_files]
        elif format == "json":
            json_files = list(transcripts_dir.glob("*_transcript.json"))
            exported = [str(f) for f in json_files]
        elif format == "txt":
            txt_files = list(transcripts_dir.glob("*_transcript.txt"))
            exported = [str(f) for f in txt_files]
        else:
            return _err(f"Unsupported export format: {format}")
        return _ok({"exported": exported, "count": len(exported), "format": format})
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Marker tools
# ---------------------------------------------------------------------------


@mcp.tool()
def markers_auto_generate(workspace_path: str) -> dict:
    """Auto-generate markers for all transcripts in the workspace.

    Reads transcript JSON files and silence data, runs the auto-mark pipeline,
    and writes marker files to markers/.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Count of marker files written and total markers generated.
    """
    try:
        import json as _json
        from workshop_video_brain.core.models.transcript import Transcript
        from workshop_video_brain.edit_mcp.pipelines.auto_mark import generate_markers
        from workshop_video_brain.core.models.markers import MarkerConfig

        transcripts_dir = Path(workspace_path) / "transcripts"
        markers_dir = Path(workspace_path) / "markers"
        markers_dir.mkdir(parents=True, exist_ok=True)

        if not transcripts_dir.exists():
            return _ok({"marker_files": 0, "total_markers": 0, "errors": []})

        config = MarkerConfig()
        total_markers = 0
        marker_files = 0
        errors = []

        for json_path in transcripts_dir.glob("*_transcript.json"):
            try:
                transcript = Transcript.from_json(json_path.read_text(encoding="utf-8"))
                stem = json_path.stem.replace("_transcript", "")
                silence_path = markers_dir / f"{stem}_silence.json"
                silence_gaps: list[tuple[float, float]] = []
                if silence_path.exists():
                    raw = _json.loads(silence_path.read_text(encoding="utf-8"))
                    silence_gaps = [(g["start"], g["end"]) for g in raw if "start" in g and "end" in g]
                markers = generate_markers(transcript, silence_gaps, config)
                out_path = markers_dir / f"{stem}_markers.json"
                out_path.write_text(
                    _json.dumps(
                        [m.model_dump(mode="json") for m in markers],
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                total_markers += len(markers)
                marker_files += 1
            except Exception as exc:
                errors.append(f"{json_path.name}: {exc}")

        return _ok({
            "marker_files": marker_files,
            "total_markers": total_markers,
            "errors": errors,
        })
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def markers_list(workspace_path: str) -> dict:
    """List all marker files and their marker counts in the workspace.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        List of marker file info with paths and marker counts.
    """
    try:
        import json as _json
        markers_dir = Path(workspace_path) / "markers"
        if not markers_dir.exists():
            return _ok({"marker_files": [], "total_markers": 0})
        files = []
        total = 0
        for mf in sorted(markers_dir.glob("*_markers.json")):
            try:
                data = _json.loads(mf.read_text(encoding="utf-8"))
                count = len(data)
                total += count
                files.append({"path": str(mf), "count": count})
            except Exception:
                files.append({"path": str(mf), "count": 0})
        return _ok({"marker_files": files, "total_markers": total})
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Timeline tools
# ---------------------------------------------------------------------------


@mcp.tool()
def timeline_build_review(workspace_path: str, mode: str = "ranked") -> dict:
    """Build a Kdenlive review timeline from workspace markers.

    Args:
        workspace_path: Path to the workspace root directory.
        mode: Ordering mode -- "ranked" (by confidence) or "chronological".

    Returns:
        Path to the generated .kdenlive file and marker count.
    """
    try:
        import json as _json
        from workshop_video_brain.core.models.markers import Marker, MarkerConfig
        from workshop_video_brain.core.models.media import MediaAsset
        from workshop_video_brain.edit_mcp.pipelines.review_timeline import build_review_timeline

        markers_dir = Path(workspace_path) / "markers"
        if not markers_dir.exists():
            return _err("No markers/ directory found. Run markers_auto_generate first.")

        markers: list[Marker] = []
        for mf in markers_dir.glob("*_markers.json"):
            try:
                raw = _json.loads(mf.read_text(encoding="utf-8"))
                for item in raw:
                    markers.append(Marker(**item))
            except Exception:
                pass

        if not markers:
            return _err("No markers found. Run markers_auto_generate first.")

        kdenlive_path = build_review_timeline(
            markers=markers,
            assets=[],
            workspace_root=Path(workspace_path),
            mode=mode,
        )
        return _ok({
            "kdenlive_path": str(kdenlive_path),
            "marker_count": len(markers),
            "mode": mode,
        })
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def timeline_build_selects(workspace_path: str, min_confidence: float = 0.5) -> dict:
    """Build a Kdenlive selects timeline from high-confidence markers.

    Args:
        workspace_path: Path to the workspace root directory.
        min_confidence: Minimum confidence score for a marker to be included.

    Returns:
        Path to the generated .kdenlive file and selects count.
    """
    try:
        import json as _json
        from workshop_video_brain.core.models.markers import Marker, MarkerConfig
        from workshop_video_brain.edit_mcp.pipelines.selects_timeline import (
            build_selects,
            build_selects_timeline,
        )

        markers_dir = Path(workspace_path) / "markers"
        if not markers_dir.exists():
            return _err("No markers/ directory found. Run markers_auto_generate first.")

        markers: list[Marker] = []
        for mf in markers_dir.glob("*_markers.json"):
            try:
                raw = _json.loads(mf.read_text(encoding="utf-8"))
                for item in raw:
                    markers.append(Marker(**item))
            except Exception:
                pass

        if not markers:
            return _err("No markers found. Run markers_auto_generate first.")

        config = MarkerConfig()
        selects = build_selects(markers, config, min_confidence=min_confidence)
        kdenlive_path = build_selects_timeline(
            selects=selects,
            assets=[],
            workspace_root=Path(workspace_path),
        )
        return _ok({
            "kdenlive_path": str(kdenlive_path),
            "selects_count": len(selects),
            "min_confidence": min_confidence,
        })
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Project tools
# ---------------------------------------------------------------------------


@mcp.tool()
def project_create_working_copy(workspace_path: str) -> dict:
    """Create an initial .kdenlive working copy for the workspace.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Path to the created .kdenlive file.
    """
    try:
        from workshop_video_brain.workspace.manifest import read_manifest
        from workshop_video_brain.core.models.kdenlive import (
            KdenliveProject,
            ProjectProfile,
            Track,
            Playlist,
        )
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
        from workshop_video_brain.core.utils.naming import slugify

        manifest = read_manifest(workspace_path)
        project = KdenliveProject(
            version="7",
            title=manifest.project_title,
            profile=ProjectProfile(width=1920, height=1080, fps=25.0, colorspace="709"),
        )
        project.tracks = [
            Track(id="playlist_video", track_type="video", name="Video"),
            Track(id="playlist_audio", track_type="audio", name="Audio"),
        ]
        project.playlists = [
            Playlist(id="playlist_video"),
            Playlist(id="playlist_audio"),
        ]
        project.tractor = {"id": "tractor0", "in": "0", "out": "99999"}

        slug = manifest.slug or slugify(manifest.project_title) or "project"
        out_path = serialize_versioned(project, Path(workspace_path), slug)
        return _ok({"kdenlive_path": str(out_path), "title": manifest.project_title})
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def project_validate(workspace_path: str) -> dict:
    """Validate the latest .kdenlive working copy project file.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Validation report with summary and list of issues.
    """
    try:
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.validator import validate_project

        working_copies = Path(workspace_path) / "projects" / "working_copies"
        kdenlive_files = sorted(working_copies.glob("*.kdenlive"))
        if not kdenlive_files:
            return _err("No .kdenlive files found in projects/working_copies/")

        latest = kdenlive_files[-1]
        project = parse_project(latest)
        report = validate_project(project, workspace_root=Path(workspace_path))
        return _ok({
            "project_file": str(latest),
            "summary": report.summary,
            "issue_count": len(report.items),
            "issues": [
                {
                    "severity": str(item.severity),
                    "category": item.category,
                    "message": item.message,
                    "location": item.location,
                }
                for item in report.items
            ],
        })
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def project_summary(workspace_path: str) -> dict:
    """Return a summary of the workspace project including all artifacts.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Project metadata with counts of transcripts, markers, timelines, renders.
    """
    try:
        from workshop_video_brain.workspace.manifest import read_manifest

        ws = Path(workspace_path)
        manifest = read_manifest(ws)

        transcripts = list((ws / "transcripts").glob("*_transcript.json")) if (ws / "transcripts").exists() else []
        markers = list((ws / "markers").glob("*_markers.json")) if (ws / "markers").exists() else []
        timelines = list((ws / "projects" / "working_copies").glob("*.kdenlive")) if (ws / "projects" / "working_copies").exists() else []
        renders = list((ws / "renders").rglob("*.mp4")) if (ws / "renders").exists() else []

        return _ok({
            "workspace_id": str(manifest.workspace_id),
            "title": manifest.project_title,
            "slug": manifest.slug,
            "status": manifest.status,
            "media_root": manifest.media_root,
            "transcript_count": len(transcripts),
            "marker_file_count": len(markers),
            "timeline_count": len(timelines),
            "render_count": len(renders),
            "latest_timeline": str(timelines[-1]) if timelines else None,
        })
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Transitions tools
# ---------------------------------------------------------------------------


@mcp.tool()
def transitions_apply(
    workspace_path: str,
    transition_type: str = "crossfade",
    preset: str = "medium",
) -> dict:
    """Apply transitions to the latest working copy project.

    Args:
        workspace_path: Path to the workspace root directory.
        transition_type: Type of transition, e.g. "crossfade".
        preset: Duration preset: "short", "medium", or "long".

    Returns:
        Path to the updated .kdenlive file.
    """
    try:
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
        from workshop_video_brain.core.models.transitions import TransitionPreset, TransitionType
        from workshop_video_brain.core.models.timeline import AddTransition
        from workshop_video_brain.core.utils.naming import slugify
        from workshop_video_brain.workspace.manifest import read_manifest

        working_copies = Path(workspace_path) / "projects" / "working_copies"
        kdenlive_files = sorted(working_copies.glob("*.kdenlive"))
        if not kdenlive_files:
            return _err("No .kdenlive files found in projects/working_copies/")

        latest = kdenlive_files[-1]
        project = parse_project(latest)

        try:
            t_preset = TransitionPreset(preset)
        except ValueError:
            t_preset = TransitionPreset.medium

        # Identify audio playlist IDs from tracks
        audio_playlist_ids = {
            t.id for t in project.tracks if t.track_type == "audio"
        }

        intents = []
        # Apply a transition between each adjacent pair of video playlist entries
        for playlist in project.playlists:
            if playlist.id in audio_playlist_ids:
                continue
            entries = [e for e in playlist.entries if e.producer_id]
            for i in range(len(entries) - 1):
                left = entries[i]
                right = entries[i + 1]
                intents.append(
                    AddTransition(
                        type=transition_type,
                        track_ref=playlist.id,
                        left_clip_ref=left.producer_id,
                        right_clip_ref=right.producer_id,
                        duration_frames=t_preset.frames,
                    )
                )

        patched = patch_project(
            project,
            intents,
            workspace_root=Path(workspace_path),
            project_path=latest,
        )
        manifest = read_manifest(workspace_path)
        slug = manifest.slug or "project"
        out_path = serialize_versioned(patched, Path(workspace_path), slug)
        return _ok({
            "kdenlive_path": str(out_path),
            "transitions_applied": len(intents),
            "transition_type": transition_type,
            "preset": preset,
        })
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Subtitle tools
# ---------------------------------------------------------------------------


@mcp.tool()
def subtitles_generate(workspace_path: str) -> dict:
    """Generate SRT subtitles from transcripts in the workspace.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        List of generated SRT file paths.
    """
    try:
        from workshop_video_brain.core.models.transcript import Transcript
        from workshop_video_brain.edit_mcp.pipelines.subtitle_pipeline import generate_srt, save_srt

        transcripts_dir = Path(workspace_path) / "transcripts"
        if not transcripts_dir.exists():
            return _ok({"generated": [], "count": 0})

        generated = []
        errors = []
        for json_path in transcripts_dir.glob("*_transcript.json"):
            try:
                transcript = Transcript.from_json(json_path.read_text(encoding="utf-8"))
                srt_content = generate_srt(transcript)
                stem = json_path.stem.replace("_transcript", "")
                out_path = save_srt(srt_content, Path(workspace_path), f"{stem}.srt")
                generated.append(str(out_path))
            except Exception as exc:
                errors.append(f"{json_path.name}: {exc}")

        return _ok({"generated": generated, "count": len(generated), "errors": errors})
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def subtitles_export(workspace_path: str, format: str = "srt") -> dict:
    """Export subtitle files in the specified format.

    Args:
        workspace_path: Path to the workspace root directory.
        format: Export format. Currently only "srt" is supported.

    Returns:
        List of SRT file paths in the reports directory.
    """
    try:
        reports_dir = Path(workspace_path) / "reports"
        if not reports_dir.exists():
            return _ok({"files": [], "count": 0})
        if format == "srt":
            files = [str(f) for f in sorted(reports_dir.glob("*.srt"))]
        else:
            return _err(f"Unsupported subtitle export format: {format}")
        return _ok({"files": files, "count": len(files), "format": format})
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Render tools
# ---------------------------------------------------------------------------


@mcp.tool()
def render_preview(workspace_path: str) -> dict:
    """Render the latest working copy project with the preview profile.

    Requires melt (MLT) or ffmpeg to be available.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Render job status and output path.
    """
    try:
        from workshop_video_brain.edit_mcp.pipelines.render_pipeline import run_render

        working_copies = Path(workspace_path) / "projects" / "working_copies"
        kdenlive_files = sorted(working_copies.glob("*.kdenlive"))
        if not kdenlive_files:
            return _err("No .kdenlive files found in projects/working_copies/")

        latest = kdenlive_files[-1]
        job = run_render(
            workspace_root=Path(workspace_path),
            project_path=latest,
            profile_name="preview",
        )
        return _ok({
            "job_id": str(job.id),
            "status": job.status,
            "project_path": job.project_path,
            "output_path": job.output_path,
            "log_path": job.log_path,
        })
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def render_status(workspace_path: str) -> dict:
    """List all render jobs for the workspace.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        List of render jobs with status, profile, and output paths.
    """
    try:
        from workshop_video_brain.edit_mcp.pipelines.render_pipeline import list_renders

        jobs = list_renders(workspace_path)
        return _ok({
            "jobs": [
                {
                    "id": str(j.id),
                    "status": j.status,
                    "profile": j.profile,
                    "output_path": j.output_path,
                    "started_at": j.started_at.isoformat() if j.started_at else None,
                    "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                }
                for j in jobs
            ],
            "count": len(jobs),
        })
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Voiceover tools
# ---------------------------------------------------------------------------


@mcp.tool()
def voiceover_extract_segments(workspace_path: str) -> dict:
    """Extract transcript segments flagged for voiceover fixes.

    Reads transcript and marker files from the workspace, filters to
    mistake_problem, repetition, and dead_air markers with confidence > 0.5,
    and returns the matching transcript text with surrounding context.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        List of fixable segments with timestamps, original text, context,
        reason, category, and confidence score.
    """
    try:
        from workshop_video_brain.production_brain.skills.voiceover import (
            extract_fixable_segments,
        )

        segments = extract_fixable_segments(Path(workspace_path))
        return _ok({
            "segments": segments,
            "count": len(segments),
        })
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# Snapshot tools
# ---------------------------------------------------------------------------


@mcp.tool()
def snapshot_list(workspace_path: str) -> dict:
    """List all snapshots in the workspace.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        List of snapshot records with IDs, timestamps, and descriptions.
    """
    try:
        from workshop_video_brain.workspace.snapshot import list_snapshots

        records = list_snapshots(workspace_path)
        snaps_dir = Path(workspace_path) / "projects" / "snapshots"
        snap_dirs = sorted(snaps_dir.iterdir()) if snaps_dir.exists() else []
        dir_names = [d.name for d in snap_dirs if d.is_dir()]

        return _ok({
            "snapshots": [
                {
                    "id": str(r.id),
                    "timestamp": r.timestamp.isoformat(),
                    "project_file_path": r.project_file_path,
                    "description": r.description,
                }
                for r in records
            ],
            "snapshot_dirs": dir_names,
            "count": len(records),
        })
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def snapshot_restore(workspace_path: str, snapshot_id: str) -> dict:
    """Restore a snapshot by its directory name (timestamp-slug).

    Args:
        workspace_path: Path to the workspace root directory.
        snapshot_id: Snapshot directory name, e.g. "20240101_120000-project-v1".

    Returns:
        Confirmation of the restore with the original file path.
    """
    try:
        from workshop_video_brain.workspace.snapshot import restore, list_snapshots

        restore(workspace_path, snapshot_id)
        return _ok({
            "snapshot_id": snapshot_id,
            "restored": True,
            "workspace_path": workspace_path,
        })
    except FileNotFoundError as exc:
        return _err(f"Snapshot not found: {exc}")
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc))
