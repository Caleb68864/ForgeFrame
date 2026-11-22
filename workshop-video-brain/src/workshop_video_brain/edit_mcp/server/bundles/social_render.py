"""``media_render_social_clips``: turn a social_generate_package manifest into reframed video files."""
from __future__ import annotations

import json
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import source_path
from workshop_video_brain.edit_mcp.server.errors import (
    bad_json_param,
    err,
    invalid_index,
    invalid_input,
    missing_file,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok


@mcp.tool()
@tool_guard
def media_render_social_clips(source: str, manifest_path: str, output_dir: str = "", aspect: str = "",
                              mode: str = "smart", clip_indices: str = "", height: int = 0,
                              overwrite: bool = False) -> dict:
    """Cut and reframe every clip in ``reports/social/clips_manifest.json`` from ``source``.

    ``source`` is the video the manifest's times refer to (the manifest's own
    ``source_video`` is a folder, so it is not used). ``aspect`` "" uses each
    clip's ``aspect_ratio``; ``mode`` as in ``media_reframe``; ``clip_indices``
    an optional JSON list. Clips starting past the end are ``skipped``; a clip
    that fails is listed under ``failed`` and the rest still render.
    """
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
    from workshop_video_brain.edit_mcp.pipelines.media_files import output_summary, resolve_output
    from workshop_video_brain.edit_mcp.pipelines.reframe import reframe_file
    from workshop_video_brain.edit_mcp.server.bundles._pipeline_errors import cleanup_partial_output

    src = source_path(source)
    if isinstance(src, dict):
        return src
    manifest = Path(manifest_path)
    if not manifest.is_file():
        return missing_file(str(manifest), "manifest")
    try:
        clips = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return bad_json_param("manifest_path", "a clips_manifest.json list", str(manifest))
    if not isinstance(clips, list):
        return invalid_input("The manifest must be a JSON list of clips", "Point at reports/social/clips_manifest.json.")
    indices = list(range(len(clips)))
    if clip_indices:
        try:
            indices = json.loads(clip_indices)
        except json.JSONDecodeError:
            return bad_json_param("clip_indices", "[0, 2]", clip_indices)
        bad = [i for i in indices if not isinstance(i, int) or not 0 <= i < len(clips)]
        if bad:
            return invalid_index("clip", bad[0], f"0-{len(clips) - 1}" if clips else "none")
    total = probe_media(src).duration_seconds or 0.0
    folder = output_dir or str(manifest.parent)
    rendered, skipped, failed = [], [], []
    for i in indices:
        clip = clips[i]
        start, end = float(clip.get("start_seconds", 0)), float(clip.get("end_seconds", 0))
        clip_id = str(clip.get("clip_id") or f"clip_{i + 1}")
        if total and start >= total:
            skipped.append({"index": i, "clip_id": clip_id, "reason": f"starts at {start:.2f}s, past the end ({total:.2f}s)"})
            continue
        if end <= start:
            skipped.append({"index": i, "clip_id": clip_id, "reason": "end is not after start"})
            continue
        out = None
        try:
            out = resolve_output(src, str(Path(folder) / f"{clip_id}_{src.stem}.mp4"), overwrite=overwrite)
            done = reframe_file(src, out, aspect or clip.get("aspect_ratio") or "9:16", mode,
                                height=height, start=start, duration=end - start)
            if not done["result"].success:
                raise RuntimeError(done["result"].stderr_tail or "ffmpeg failed")
            rendered.append({**output_summary(out), "index": i, "clip_id": clip_id, "title": clip.get("title", ""),
                             "focus_x": done["focus_x"]})
        except (ValueError, RuntimeError) as exc:
            cleanup_partial_output(out)
            failed.append({"index": i, "clip_id": clip_id, "error": str(exc)[:300]})
    if failed and not rendered and not skipped:
        return err(f"Every clip failed to render ({len(failed)})", suggestion="See 'failed' for each clip's reason.",
                   error_type="operation_failed", failed=failed)
    return _ok({"rendered": rendered, "skipped": skipped, "failed": failed})
