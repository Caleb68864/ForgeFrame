"""Transcript, subtitle, marker, and voiceover tools.

Carved from the former monolithic ``server/tools.py``. Each function
registers with the shared FastMCP singleton via ``@mcp.tool()``.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # noqa: F401
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    bad_json_param,
    corrupt_project,
    media_unreadable,
    not_found,
    invalid_input,
    from_exception,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _err,
    _require_workspace,
)





# ---------------------------------------------------------------------------
# Transcript tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
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
            return err(
                "ffmpeg is not available on PATH.",
                suggestion="Install FFmpeg and make sure it is on your PATH, then run transcript_generate again.",
            )
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return err(
                "faster-whisper is not installed.",
                suggestion="Install it: pip install faster-whisper (or `uv add faster-whisper`), then run transcript_generate again.",
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
        return from_exception(exc)


@mcp.tool()
@tool_guard
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
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
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
            return invalid_input(f"Unsupported export format: {format}", "Pass format='srt', 'json', or 'txt'.", param="format", given=format)
        return _ok({"exported": exported, "count": len(exported), "format": format})
    except Exception as exc:
        return from_exception(exc)




# ---------------------------------------------------------------------------
# Marker tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
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
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
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
        return from_exception(exc)


@mcp.tool()
@tool_guard
def markers_list(workspace_path: str) -> dict:
    """List all marker files and their marker counts in the workspace.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        List of marker file info with paths and marker counts.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
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
        return from_exception(exc)




# ---------------------------------------------------------------------------
# Subtitle tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
def subtitles_generate(workspace_path: str) -> dict:
    """Generate SRT subtitles from transcripts in the workspace.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        List of generated SRT file paths.
    """
    try:
        if not workspace_path or not workspace_path.strip():
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
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
        return from_exception(exc)


@mcp.tool()
@tool_guard
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
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        reports_dir = ws_path / "reports"
        if not reports_dir.exists():
            return _ok({"files": [], "count": 0})
        if format == "srt":
            files = [str(f) for f in sorted(reports_dir.glob("*.srt"))]
        else:
            return invalid_input(f"Unsupported subtitle export format: {format}", "Only format='srt' is supported for subtitle export.", param="format", given=format)
        return _ok({"files": files, "count": len(files), "format": format})
    except Exception as exc:
        return from_exception(exc)




# ---------------------------------------------------------------------------
# Voiceover tools
# ---------------------------------------------------------------------------
@mcp.tool()
@tool_guard
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
            return invalid_input("workspace_path must be a non-empty string", "Pass the absolute path to your workspace directory (the folder containing projects/, media/, etc.).", param="workspace_path")
        ws_path = Path(workspace_path)
        if not ws_path.exists():
            return missing_file(workspace_path, "Workspace path")
        if not ws_path.is_dir():
            return invalid_input(f"Workspace path is not a directory: {workspace_path}", "Point workspace_path at the workspace directory, not a file.", path=workspace_path)
        from workshop_video_brain.production_brain.skills.voiceover import (
            extract_fixable_segments,
        )

        segments = extract_fixable_segments(ws_path)
        return _ok({
            "segments": segments,
            "count": len(segments),
        })
    except Exception as exc:
        return from_exception(exc)
