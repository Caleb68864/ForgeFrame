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


def _validate_workspace_path(workspace_path: str) -> Path:
    """Validate workspace_path: must be non-empty, exist, and be a directory.

    Raises ValueError with a clear message if any check fails.
    """
    if not workspace_path or not workspace_path.strip():
        raise ValueError("workspace_path must be a non-empty string")
    p = Path(workspace_path)
    if not p.exists():
        raise FileNotFoundError(f"Workspace path does not exist: {workspace_path}")
    if not p.is_dir():
        raise ValueError(f"Workspace path is not a directory: {workspace_path}")
    return p


def _require_workspace(workspace_path: str):
    """Return (Path, Workspace) or raise ValueError."""
    from workshop_video_brain.workspace.manager import WorkspaceManager
    p = _validate_workspace_path(workspace_path)
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
        if not title or not title.strip():
            return _err("title must be a non-empty string")
        if not media_root or not media_root.strip():
            return _err("media_root must be a non-empty string")
        media_root_path = Path(media_root)
        if not media_root_path.exists():
            return _err(f"media_root does not exist: {media_root}")
        if not media_root_path.is_dir():
            return _err(f"media_root is not a directory: {media_root}")
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
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
        raw_dir = p / "media" / "raw"
        if not raw_dir.exists():
            return _err(
                f"media/raw directory not found at {workspace_path}. "
                "Create and populate media/raw/ before running ingest."
            )
        import shutil as _shutil
        if not _shutil.which("ffmpeg"):
            return _err(
                "ffmpeg is not available on PATH. "
                "Install FFmpeg before running media_ingest."
            )
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        raw_dir = ws_path / "media" / "raw"
        if not raw_dir.exists():
            return _ok({"assets": [], "count": 0, "message": "media/raw directory not found"})
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import scan_directory
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import (
            ProxyPolicy,
            generate_proxy,
            needs_proxy,
            proxy_path_for,
        )
        raw_dir = ws_path / "media" / "raw"
        proxy_dir = ws_path / "media" / "proxies"
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
        import shutil as _shutil
        if not _shutil.which("ffmpeg"):
            return _err(
                "ffmpeg is not available on PATH. "
                "Install FFmpeg before running transcript_generate."
            )
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return _err(
                "faster-whisper is not installed. "
                "Install with: pip install faster-whisper"
            )
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        transcripts_dir = ws_path / "transcripts"
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        import json as _json
        from workshop_video_brain.core.models.transcript import Transcript
        from workshop_video_brain.edit_mcp.pipelines.auto_mark import generate_markers
        from workshop_video_brain.core.models.markers import MarkerConfig

        transcripts_dir = ws_path / "transcripts"
        markers_dir = ws_path / "markers"
        markers_dir.mkdir(parents=True, exist_ok=True)

        if not transcripts_dir.exists():
            return _ok({
                "marker_files": 0,
                "total_markers": 0,
                "errors": [],
                "message": "No transcripts/ directory found. Run transcript_generate first.",
            })

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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        import json as _json
        markers_dir = ws_path / "markers"
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        import json as _json
        from workshop_video_brain.core.models.markers import Marker, MarkerConfig
        from workshop_video_brain.core.models.media import MediaAsset
        from workshop_video_brain.edit_mcp.pipelines.review_timeline import build_review_timeline

        markers_dir = ws_path / "markers"
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
            workspace_root=ws_path,
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        # Coerce min_confidence from string if needed
        try:
            min_confidence = float(min_confidence)
        except (TypeError, ValueError):
            return _err(f"min_confidence must be a number, got: {min_confidence!r}")
        import json as _json
        from workshop_video_brain.core.models.markers import Marker, MarkerConfig
        from workshop_video_brain.edit_mcp.pipelines.selects_timeline import (
            build_selects,
            build_selects_timeline,
        )

        markers_dir = ws_path / "markers"
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
            workspace_root=ws_path,
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
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
        out_path = serialize_versioned(project, ws_path, slug)
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.validator import validate_project

        working_copies = ws_path / "projects" / "working_copies"
        if not working_copies.exists():
            return _err(
                "No projects/working_copies/ directory found. "
                "Run project_create_working_copy first."
            )
        kdenlive_files = sorted(working_copies.glob("*.kdenlive"))
        if not kdenlive_files:
            return _err("No .kdenlive files found in projects/working_copies/")

        latest = kdenlive_files[-1]
        project = parse_project(latest)
        report = validate_project(project, workspace_root=ws_path)
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        from workshop_video_brain.workspace.manifest import read_manifest

        ws = Path(workspace_path)
        if not ws.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
        from workshop_video_brain.core.models.transitions import TransitionPreset, TransitionType
        from workshop_video_brain.core.models.timeline import AddTransition
        from workshop_video_brain.core.utils.naming import slugify
        from workshop_video_brain.workspace.manifest import read_manifest

        working_copies = ws_path / "projects" / "working_copies"
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
            workspace_root=ws_path,
            project_path=latest,
        )
        manifest = read_manifest(workspace_path)
        slug = manifest.slug or "project"
        out_path = serialize_versioned(patched, ws_path, slug)
        return _ok({
            "kdenlive_path": str(out_path),
            "transitions_applied": len(intents),
            "transition_type": transition_type,
            "preset": preset,
        })
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def transitions_apply_at(
    workspace_path: str,
    timestamp_seconds: float,
    transition_type: str = "crossfade",
    preset: str = "medium",
) -> dict:
    """Apply a transition at a specific timestamp in the timeline.

    Finds the cut point closest to the given timestamp and applies
    a transition between those two clips.

    Args:
        workspace_path: Path to workspace root.
        timestamp_seconds: Time in seconds where the transition should go.
        transition_type: Type (crossfade, dissolve, fade_in, fade_out).
        preset: Duration (short=12f, medium=24f, long=48f).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        if timestamp_seconds < 0:
            return _err("timestamp_seconds must be >= 0")

        _KNOWN_TRANSITION_TYPES = {"crossfade", "dissolve", "fade_in", "fade_out"}
        if transition_type not in _KNOWN_TRANSITION_TYPES:
            return _err(
                f"Unknown transition_type '{transition_type}'. "
                f"Must be one of: {', '.join(sorted(_KNOWN_TRANSITION_TYPES))}"
            )
        _KNOWN_PRESETS = {"short", "medium", "long"}
        if preset not in _KNOWN_PRESETS:
            return _err(
                f"Unknown preset '{preset}'. "
                f"Must be one of: {', '.join(sorted(_KNOWN_PRESETS))}"
            )

        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
        from workshop_video_brain.core.models.transitions import TransitionPreset
        from workshop_video_brain.core.models.timeline import AddTransition
        from workshop_video_brain.workspace.manifest import read_manifest

        working_copies = ws_path / "projects" / "working_copies"
        kdenlive_files = sorted(working_copies.glob("*.kdenlive"))
        if not kdenlive_files:
            return _err("No .kdenlive files found in projects/working_copies/")

        latest = kdenlive_files[-1]
        project = parse_project(latest)

        fps = project.profile.fps or 25.0
        target_frame = int(timestamp_seconds * fps)
        tolerance_frames = int(2.0 * fps)  # 2-second tolerance

        # Identify audio playlist IDs
        audio_playlist_ids = {t.id for t in project.tracks if t.track_type == "audio"}

        # Find the closest cut boundary across all video playlists
        best_distance = None
        best_playlist_id = None
        best_left = None
        best_right = None

        for playlist in project.playlists:
            if playlist.id in audio_playlist_ids:
                continue
            entries = [e for e in playlist.entries if e.producer_id]
            # Calculate cumulative frame positions for each entry boundary
            current_frame = 0
            for i, entry in enumerate(entries):
                duration = entry.out_point - entry.in_point + 1
                boundary_frame = current_frame + duration  # frame where this entry ends
                if i < len(entries) - 1:
                    # There's a next entry — this is a cut point
                    dist = abs(boundary_frame - target_frame)
                    if best_distance is None or dist < best_distance:
                        best_distance = dist
                        best_playlist_id = playlist.id
                        best_left = entries[i]
                        best_right = entries[i + 1]
                current_frame += duration

        if best_distance is None or best_distance > tolerance_frames:
            return _err(f"No cut point found near {timestamp_seconds}s")

        t_preset = TransitionPreset(preset)
        intents = [
            AddTransition(
                type=transition_type,
                track_ref=best_playlist_id,
                left_clip_ref=best_left.producer_id,
                right_clip_ref=best_right.producer_id,
                duration_frames=t_preset.frames,
            )
        ]

        patched = patch_project(project, intents, workspace_root=ws_path, project_path=latest)
        manifest = read_manifest(workspace_path)
        slug = manifest.slug or "project"
        out_path = serialize_versioned(patched, ws_path, slug)
        return _ok({
            "kdenlive_path": str(out_path),
            "transition_type": transition_type,
            "preset": preset,
            "timestamp_seconds": timestamp_seconds,
            "boundary_frame": int(target_frame + best_distance if best_left else target_frame),
            "playlist_id": best_playlist_id,
        })
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def transitions_apply_between(
    workspace_path: str,
    clip_index: int,
    transition_type: str = "crossfade",
    preset: str = "medium",
) -> dict:
    """Apply a transition between clip N and clip N+1 on the first video track.

    Args:
        workspace_path: Path to workspace root.
        clip_index: Zero-based index of the left clip. Transition goes between this and the next.
        transition_type: Type (crossfade, dissolve, fade_in, fade_out).
        preset: Duration (short, medium, long).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        if clip_index < 0:
            return _err("clip_index must be >= 0")

        _KNOWN_TRANSITION_TYPES = {"crossfade", "dissolve", "fade_in", "fade_out"}
        if transition_type not in _KNOWN_TRANSITION_TYPES:
            return _err(
                f"Unknown transition_type '{transition_type}'. "
                f"Must be one of: {', '.join(sorted(_KNOWN_TRANSITION_TYPES))}"
            )
        _KNOWN_PRESETS = {"short", "medium", "long"}
        if preset not in _KNOWN_PRESETS:
            return _err(
                f"Unknown preset '{preset}'. "
                f"Must be one of: {', '.join(sorted(_KNOWN_PRESETS))}"
            )

        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
        from workshop_video_brain.core.models.transitions import TransitionPreset
        from workshop_video_brain.core.models.timeline import AddTransition
        from workshop_video_brain.workspace.manifest import read_manifest

        working_copies = ws_path / "projects" / "working_copies"
        kdenlive_files = sorted(working_copies.glob("*.kdenlive"))
        if not kdenlive_files:
            return _err("No .kdenlive files found in projects/working_copies/")

        latest = kdenlive_files[-1]
        project = parse_project(latest)

        # Find first video playlist
        audio_playlist_ids = {t.id for t in project.tracks if t.track_type == "audio"}
        video_playlist = None
        for playlist in project.playlists:
            if playlist.id not in audio_playlist_ids:
                video_playlist = playlist
                break

        if video_playlist is None:
            return _err("No video playlist found in project")

        entries = [e for e in video_playlist.entries if e.producer_id]
        if len(entries) < 2:
            return _err("Video playlist has fewer than 2 clips; no transition possible")

        if clip_index >= len(entries) - 1:
            return _err(
                f"clip_index {clip_index} is out of range. "
                f"Valid range is 0 to {len(entries) - 2} (playlist has {len(entries)} clips)."
            )

        left = entries[clip_index]
        right = entries[clip_index + 1]

        t_preset = TransitionPreset(preset)
        intents = [
            AddTransition(
                type=transition_type,
                track_ref=video_playlist.id,
                left_clip_ref=left.producer_id,
                right_clip_ref=right.producer_id,
                duration_frames=t_preset.frames,
            )
        ]

        patched = patch_project(project, intents, workspace_root=ws_path, project_path=latest)
        manifest = read_manifest(workspace_path)
        slug = manifest.slug or "project"
        out_path = serialize_versioned(patched, ws_path, slug)
        return _ok({
            "kdenlive_path": str(out_path),
            "transition_type": transition_type,
            "preset": preset,
            "clip_index": clip_index,
            "left_clip": left.producer_id,
            "right_clip": right.producer_id,
            "playlist_id": video_playlist.id,
        })
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def clip_insert(
    workspace_path: str,
    media_path: str,
    in_seconds: float = 0.0,
    out_seconds: float = -1.0,
    position: int = -1,
) -> dict:
    """Insert a clip into the timeline of the latest working copy project.

    Args:
        workspace_path: Path to workspace root.
        media_path: Path to the media file to insert.
        in_seconds: In-point in seconds (default: start of clip).
        out_seconds: Out-point in seconds (default: end of clip, -1 means full duration).
        position: Position index in the playlist (default: -1 = append at end).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        if not media_path or not media_path.strip():
            return _err("media_path must be a non-empty string")
        media_file = Path(media_path)
        if not media_file.exists():
            return _err(f"media_path does not exist: {media_path}")

        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
        from workshop_video_brain.core.models.timeline import AddClip
        from workshop_video_brain.workspace.manifest import read_manifest

        working_copies = ws_path / "projects" / "working_copies"
        kdenlive_files = sorted(working_copies.glob("*.kdenlive"))
        if not kdenlive_files:
            return _err("No .kdenlive files found in projects/working_copies/")

        latest = kdenlive_files[-1]
        project = parse_project(latest)

        fps = project.profile.fps or 25.0

        # Probe media for duration using ffprobe if available
        duration_seconds: float | None = None
        try:
            import shutil
            if shutil.which("ffprobe"):
                import subprocess
                import json as _json
                probe_result = subprocess.run(
                    [
                        "ffprobe", "-v", "quiet",
                        "-print_format", "json",
                        "-show_streams",
                        str(media_file),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if probe_result.returncode == 0:
                    probe_data = _json.loads(probe_result.stdout)
                    for stream in probe_data.get("streams", []):
                        if stream.get("codec_type") == "video":
                            dur = stream.get("duration")
                            if dur:
                                duration_seconds = float(dur)
                                r_num = stream.get("r_frame_rate", "")
                                if "/" in r_num:
                                    num, den = r_num.split("/")
                                    if int(den) > 0:
                                        fps = int(num) / int(den)
                            break
                    if duration_seconds is None:
                        # fallback: check format
                        fmt = probe_data.get("format", {})
                        dur = fmt.get("duration")
                        if dur:
                            duration_seconds = float(dur)
        except Exception:
            pass  # ffprobe unavailable or failed; continue with defaults

        # Convert seconds to frames
        in_frame = int(in_seconds * fps)
        if out_seconds < 0:
            if duration_seconds is not None:
                out_frame = int(duration_seconds * fps) - 1
            else:
                out_frame = in_frame  # fallback: single frame
        else:
            out_frame = int(out_seconds * fps)

        # Find first video playlist to insert into
        audio_playlist_ids = {t.id for t in project.tracks if t.track_type == "audio"}
        video_playlist = None
        for playlist in project.playlists:
            if playlist.id not in audio_playlist_ids:
                video_playlist = playlist
                break

        if video_playlist is None:
            return _err("No video playlist found in project")

        # Build a unique producer ID from the media filename
        import hashlib
        stem = media_file.stem
        h = hashlib.md5(str(media_file).encode()).hexdigest()[:6]
        producer_id = f"{stem}_{h}"

        intent = AddClip(
            producer_id=producer_id,
            track_ref=video_playlist.id,
            track_id=video_playlist.id,
            in_point=in_frame,
            out_point=out_frame,
            position=position,
            source_path=str(media_file),
        )

        patched = patch_project(project, [intent])
        manifest = read_manifest(workspace_path)
        slug = manifest.slug or "project"
        out_path = serialize_versioned(patched, ws_path, slug)
        return _ok({
            "kdenlive_path": str(out_path),
            "media_path": str(media_file),
            "producer_id": producer_id,
            "in_frame": in_frame,
            "out_frame": out_frame,
            "playlist_id": video_playlist.id,
            "position": position,
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        from workshop_video_brain.core.models.transcript import Transcript
        from workshop_video_brain.edit_mcp.pipelines.subtitle_pipeline import generate_srt, save_srt

        transcripts_dir = ws_path / "transcripts"
        if not transcripts_dir.exists():
            return _ok({"generated": [], "count": 0})

        generated = []
        errors = []
        for json_path in transcripts_dir.glob("*_transcript.json"):
            try:
                transcript = Transcript.from_json(json_path.read_text(encoding="utf-8"))
                srt_content = generate_srt(transcript)
                stem = json_path.stem.replace("_transcript", "")
                out_path = save_srt(srt_content, ws_path, f"{stem}.srt")
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        reports_dir = ws_path / "reports"
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        from workshop_video_brain.edit_mcp.pipelines.render_pipeline import run_render

        working_copies = ws_path / "projects" / "working_copies"
        if not working_copies.exists():
            return _err(
                "No projects/working_copies/ directory found. "
                "Run project_create_working_copy first."
            )
        kdenlive_files = sorted(working_copies.glob("*.kdenlive"))
        if not kdenlive_files:
            return _err("No .kdenlive files found in projects/working_copies/")

        latest = kdenlive_files[-1]
        job = run_render(
            workspace_root=ws_path,
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        from workshop_video_brain.production_brain.skills.voiceover import (
            extract_fixable_segments,
        )

        segments = extract_fixable_segments(ws_path)
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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        from workshop_video_brain.workspace.snapshot import list_snapshots

        records = list_snapshots(workspace_path)
        snaps_dir = ws_path / "projects" / "snapshots"
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


# ---------------------------------------------------------------------------
# Clip tools
# ---------------------------------------------------------------------------


@mcp.tool()
def clips_label(workspace_path: str) -> dict:
    """Auto-label all clips in workspace from transcript and marker data.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Count of labels generated and a summary of content types found.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        from workshop_video_brain.edit_mcp.pipelines.clip_labeler import generate_labels

        labels = generate_labels(ws_path)
        content_type_counts: dict[str, int] = {}
        for label in labels:
            content_type_counts[label.content_type] = (
                content_type_counts.get(label.content_type, 0) + 1
            )
        return _ok({
            "label_count": len(labels),
            "content_types": content_type_counts,
            "clips": [
                {
                    "clip_ref": l.clip_ref,
                    "content_type": l.content_type,
                    "shot_type": l.shot_type,
                    "has_speech": l.has_speech,
                    "speech_density": l.speech_density,
                    "topic_count": len(l.topics),
                    "duration": l.duration,
                }
                for l in labels
            ],
        })
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def clips_search(workspace_path: str, query: str) -> dict:
    """Search clips by content. Returns ranked matches.

    Args:
        workspace_path: Path to the workspace root directory.
        query: Search query string (case-insensitive).

    Returns:
        Ranked list of matching clips with scores.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        if not query or not query.strip():
            return _err("query must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        from workshop_video_brain.edit_mcp.pipelines.clip_search import search_clips

        results = search_clips(ws_path, query)
        return _ok({
            "results": results,
            "count": len(results),
            "query": query,
        })
    except Exception as exc:
        return _err(str(exc))


# ---------------------------------------------------------------------------
# B-Roll tools
# ---------------------------------------------------------------------------


@mcp.tool()
def broll_suggest(workspace_path: str) -> dict:
    """Analyze transcript and suggest specific B-roll shots.

    Scans all transcript files in the workspace, detects visual description
    patterns, and returns categorised B-roll shot suggestions with timestamps,
    descriptions, and confidence scores.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        Suggestions grouped by category with total count and formatted markdown.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        from workshop_video_brain.production_brain.skills.broll import extract_and_format

        markdown, suggestions = extract_and_format(ws_path)
        by_category: dict[str, int] = {}
        for s in suggestions:
            by_category[s["category"]] = by_category.get(s["category"], 0) + 1
        return _ok({
            "suggestions": suggestions,
            "count": len(suggestions),
            "by_category": by_category,
            "markdown": markdown,
        })
    except Exception as exc:
        return _err(str(exc))


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
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        if not snapshot_id or not snapshot_id.strip():
            return _err("snapshot_id must be a non-empty string")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return _err(f"Workspace path does not exist: {workspace_path}")
        if not ws_path.is_dir():
            return _err(f"Workspace path is not a directory: {workspace_path}")
        # Validate that snapshot_id exists
        snap_dir = ws_path / "projects" / "snapshots" / snapshot_id
        if not snap_dir.exists():
            return _err(
                f"Snapshot '{snapshot_id}' not found in {workspace_path}/projects/snapshots/"
            )
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
# NLE operation helpers
# ---------------------------------------------------------------------------


def _get_video_playlists(project):
    """Return list of video playlist objects (non-audio tracks)."""
    audio_ids = {t.id for t in project.tracks if t.track_type == "audio"}
    return [p for p in project.playlists if p.id not in audio_ids]


def _load_latest_project(workspace_path: str):
    """Load the latest .kdenlive file from working_copies.  Returns (ws_path, project, latest_path)."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    ws_path = _validate_workspace_path(workspace_path)
    working_copies = ws_path / "projects" / "working_copies"
    kdenlive_files = sorted(working_copies.glob("*.kdenlive")) if working_copies.exists() else []
    if not kdenlive_files:
        raise FileNotFoundError("No .kdenlive files found in projects/working_copies/")
    latest = kdenlive_files[-1]
    project = parse_project(latest)
    return ws_path, project, latest


def _save_patched(ws_path, project, workspace_path: str) -> Path:
    """Serialize patched project and return output path."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
    from workshop_video_brain.workspace.manifest import read_manifest
    manifest = read_manifest(workspace_path)
    slug = manifest.slug or "project"
    return serialize_versioned(project, ws_path, slug)


def _resolve_playlist(project, track: int):
    """Resolve track index to a video playlist.  Returns playlist or raises ValueError."""
    video_playlists = _get_video_playlists(project)
    if not video_playlists:
        raise ValueError("No video playlists found in project")
    if track < 0 or track >= len(video_playlists):
        raise ValueError(
            f"track index {track} out of range (project has {len(video_playlists)} video track(s))"
        )
    return video_playlists[track]


def _validate_clip_index(playlist, clip_index: int) -> list:
    """Return list of real entries, raising ValueError if clip_index out of range."""
    real = [e for e in playlist.entries if e.producer_id]
    if not real:
        raise ValueError(f"Playlist '{playlist.id}' has no clips")
    if clip_index < 0 or clip_index >= len(real):
        raise ValueError(
            f"clip_index {clip_index} out of range (playlist has {len(real)} clip(s))"
        )
    return real


# ---------------------------------------------------------------------------
# NLE clip operations
# ---------------------------------------------------------------------------


@mcp.tool()
def clip_remove(workspace_path: str, clip_index: int, track: int = 0) -> dict:
    """Remove a clip from the timeline by index.

    Args:
        workspace_path: Path to workspace root.
        clip_index: Zero-based index of the clip to remove.
        track: Video track index (0 = first video track).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path, project, latest = _load_latest_project(workspace_path)
        playlist = _resolve_playlist(project, track)
        _validate_clip_index(playlist, clip_index)

        from workshop_video_brain.core.models.timeline import RemoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = RemoveClip(track_ref=playlist.id, clip_index=clip_index)
        patched = patch_project(project, [intent])
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "removed_clip_index": clip_index,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def clip_move(workspace_path: str, from_index: int, to_index: int, track: int = 0) -> dict:
    """Move a clip from one position to another on the timeline.

    Args:
        workspace_path: Path to workspace root.
        from_index: Source clip index.
        to_index: Destination clip index.
        track: Video track index (0 = first video track).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path, project, latest = _load_latest_project(workspace_path)
        playlist = _resolve_playlist(project, track)
        real = _validate_clip_index(playlist, from_index)
        if to_index < 0 or to_index >= len(real):
            return _err(
                f"to_index {to_index} out of range (playlist has {len(real)} clip(s))"
            )

        from workshop_video_brain.core.models.timeline import MoveClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = MoveClip(track_ref=playlist.id, from_index=from_index, to_index=to_index)
        patched = patch_project(project, [intent])
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "from_index": from_index,
            "to_index": to_index,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def clip_split(workspace_path: str, clip_index: int, split_at_seconds: float = 0.0) -> dict:
    """Split a clip at a timestamp (razor tool).

    Args:
        workspace_path: Path to workspace root.
        clip_index: Zero-based index of the clip to split.
        split_at_seconds: Time offset within the clip (in seconds) to split at.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path, project, latest = _load_latest_project(workspace_path)
        # clip_split operates on the first video playlist
        playlist = _resolve_playlist(project, 0)
        real = _validate_clip_index(playlist, clip_index)

        fps = project.profile.fps or 25.0
        split_at_frame = int(split_at_seconds * fps)

        from workshop_video_brain.core.models.timeline import SplitClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = SplitClip(
            track_ref=playlist.id,
            clip_index=clip_index,
            split_at_frame=split_at_frame,
        )
        patched = patch_project(project, [intent])
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "clip_index": clip_index,
            "split_at_seconds": split_at_seconds,
            "split_at_frame": split_at_frame,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def clip_trim(
    workspace_path: str,
    clip_index: int,
    in_seconds: float = -1,
    out_seconds: float = -1,
) -> dict:
    """Trim a clip's in and/or out points.

    Args:
        workspace_path: Path to workspace root.
        clip_index: Zero-based index of the clip to trim.
        in_seconds: New in-point in seconds (-1 = leave unchanged).
        out_seconds: New out-point in seconds (-1 = leave unchanged).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path, project, latest = _load_latest_project(workspace_path)
        playlist = _resolve_playlist(project, 0)
        _validate_clip_index(playlist, clip_index)

        fps = project.profile.fps or 25.0
        new_in = int(in_seconds * fps) if in_seconds >= 0 else -1
        new_out = int(out_seconds * fps) if out_seconds >= 0 else -1

        from workshop_video_brain.core.models.timeline import TrimClip
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        clip_ref = f"{playlist.id}:{clip_index}"
        intent = TrimClip(clip_ref=clip_ref, new_in=new_in, new_out=new_out)
        patched = patch_project(project, [intent])
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "clip_index": clip_index,
            "new_in_frame": new_in,
            "new_out_frame": new_out,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def clip_ripple_delete(workspace_path: str, clip_index: int, track: int = 0) -> dict:
    """Remove a clip and close the gap.

    Args:
        workspace_path: Path to workspace root.
        clip_index: Zero-based index of the clip to delete.
        track: Video track index (0 = first video track).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path, project, latest = _load_latest_project(workspace_path)
        playlist = _resolve_playlist(project, track)
        _validate_clip_index(playlist, clip_index)

        from workshop_video_brain.core.models.timeline import RippleDelete
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = RippleDelete(track_ref=playlist.id, clip_index=clip_index)
        patched = patch_project(project, [intent])
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "deleted_clip_index": clip_index,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def clip_speed(
    workspace_path: str,
    clip_index: int,
    speed: float = 1.0,
    track: int = 0,
) -> dict:
    """Change clip playback speed (0.5=slow, 2.0=fast).

    Args:
        workspace_path: Path to workspace root.
        clip_index: Zero-based index of the clip.
        speed: Playback speed multiplier (must be > 0).
        track: Video track index (0 = first video track).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        if speed <= 0:
            return _err(f"speed must be greater than 0, got: {speed}")
        ws_path, project, latest = _load_latest_project(workspace_path)
        playlist = _resolve_playlist(project, track)
        _validate_clip_index(playlist, clip_index)

        from workshop_video_brain.core.models.timeline import SetClipSpeed
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = SetClipSpeed(track_ref=playlist.id, clip_index=clip_index, speed=speed)
        patched = patch_project(project, [intent])
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "clip_index": clip_index,
            "speed": speed,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def audio_fade(
    workspace_path: str,
    clip_index: int,
    fade_type: str = "in",
    duration_seconds: float = 1.0,
    track: int = 0,
) -> dict:
    """Apply audio fade in or out to a clip.

    Args:
        workspace_path: Path to workspace root.
        clip_index: Zero-based index of the clip.
        fade_type: "in" or "out".
        duration_seconds: Duration of the fade in seconds.
        track: Video track index (0 = first video track).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        if fade_type not in ("in", "out"):
            return _err(f"fade_type must be 'in' or 'out', got: {fade_type!r}")
        ws_path, project, latest = _load_latest_project(workspace_path)
        playlist = _resolve_playlist(project, track)
        _validate_clip_index(playlist, clip_index)

        fps = project.profile.fps or 25.0
        duration_frames = max(1, int(duration_seconds * fps))

        from workshop_video_brain.core.models.timeline import AudioFade as AudioFadeIntent
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = AudioFadeIntent(
            track_ref=playlist.id,
            clip_index=clip_index,
            fade_type=fade_type,
            duration_frames=duration_frames,
        )
        patched = patch_project(project, [intent])
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "clip_index": clip_index,
            "fade_type": fade_type,
            "duration_seconds": duration_seconds,
            "duration_frames": duration_frames,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def track_add(workspace_path: str, track_type: str = "video", name: str = "") -> dict:
    """Add a new video or audio track to the project.

    Args:
        workspace_path: Path to workspace root.
        track_type: "video" or "audio".
        name: Optional name for the new track.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        if track_type not in ("video", "audio"):
            return _err(f"track_type must be 'video' or 'audio', got: {track_type!r}")
        ws_path, project, latest = _load_latest_project(workspace_path)

        from workshop_video_brain.core.models.timeline import CreateTrack
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = CreateTrack(track_type=track_type, name=name)
        patched = patch_project(project, [intent])
        # Find the newly added playlist (last one)
        new_playlist_id = patched.playlists[-1].id if patched.playlists else ""
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "track_type": track_type,
            "name": name,
            "new_playlist_id": new_playlist_id,
        })
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def track_mute(workspace_path: str, track_index: int, muted: bool = True) -> dict:
    """Mute or unmute a track.

    Args:
        workspace_path: Path to workspace root.
        track_index: Zero-based index into all project tracks.
        muted: True to mute, False to unmute.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path, project, latest = _load_latest_project(workspace_path)

        if track_index < 0 or track_index >= len(project.tracks):
            return _err(
                f"track_index {track_index} out of range "
                f"(project has {len(project.tracks)} track(s))"
            )

        track = project.tracks[track_index]

        from workshop_video_brain.core.models.timeline import SetTrackMute
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = SetTrackMute(track_ref=track.id, muted=muted)
        patched = patch_project(project, [intent])
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "track_index": track_index,
            "track_id": track.id,
            "muted": muted,
        })
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def track_visibility(workspace_path: str, track_index: int, visible: bool = True) -> dict:
    """Show or hide a video track.

    Args:
        workspace_path: Path to workspace root.
        track_index: Zero-based index into all project tracks.
        visible: True to show, False to hide.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        ws_path, project, latest = _load_latest_project(workspace_path)

        if track_index < 0 or track_index >= len(project.tracks):
            return _err(
                f"track_index {track_index} out of range "
                f"(project has {len(project.tracks)} track(s))"
            )

        track = project.tracks[track_index]

        from workshop_video_brain.core.models.timeline import SetTrackVisibility
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = SetTrackVisibility(track_ref=track.id, visible=visible)
        patched = patch_project(project, [intent])
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "track_index": track_index,
            "track_id": track.id,
            "visible": visible,
        })
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(str(exc))


@mcp.tool()
def gap_insert(
    workspace_path: str,
    position: int,
    duration_seconds: float,
    track: int = 0,
) -> dict:
    """Insert a gap/blank at a position on the timeline.

    Args:
        workspace_path: Path to workspace root.
        position: Playlist entry index at which to insert the gap.
        duration_seconds: Duration of the gap in seconds.
        track: Video track index (0 = first video track).
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return _err("workspace_path must be a non-empty string")
        if duration_seconds <= 0:
            return _err(f"duration_seconds must be positive, got: {duration_seconds}")
        ws_path, project, latest = _load_latest_project(workspace_path)
        playlist = _resolve_playlist(project, track)

        fps = project.profile.fps or 25.0
        duration_frames = max(1, int(duration_seconds * fps))

        from workshop_video_brain.core.models.timeline import InsertGap
        from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

        intent = InsertGap(
            track_id=playlist.id,
            position=position,
            duration_frames=duration_frames,
        )
        patched = patch_project(project, [intent])
        out_path = _save_patched(ws_path, patched, workspace_path)
        return _ok({
            "kdenlive_path": str(out_path),
            "position": position,
            "duration_seconds": duration_seconds,
            "duration_frames": duration_frames,
            "playlist_id": playlist.id,
        })
    except (ValueError, FileNotFoundError) as exc:
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
