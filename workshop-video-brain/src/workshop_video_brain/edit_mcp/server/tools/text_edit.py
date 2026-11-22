"""Edit a recording by its transcript: list the words, delete some, get a cut list / file / .kdenlive.

Logic in ``pipelines/text_edit.py``. Rendering reuses prompt 12's
``silence_cut.render_keep_ranges``; the project reuses prompt 13's
``selects_timeline.build_ranges_project`` with the source's own profile.
"""
from __future__ import annotations

import json
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import source_path
from workshop_video_brain.edit_mcp.server.errors import (
    bad_json_param,
    invalid_input,
    media_unreadable,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok

_DELETE_EXAMPLE = '[{"words": [10, 14]}, {"segment": 3}, {"text": "um"}, {"time": [12.0, 15.5]}]'


@mcp.tool()
@tool_guard
def transcript_words(transcript_path: str, start_index: int = 0, limit: int = 400) -> dict:
    """The transcript as numbered words (``S3 [41] the [42] zipper ...``) to pick deletions from.

    Uses word timings when the transcript has them (``transcribe_file``'s
    JSON); otherwise every segment is one numbered unit. Page with
    ``start_index`` / ``next_start``.
    """
    from workshop_video_brain.edit_mcp.pipelines.text_edit import load_units, numbered_view

    path = source_path(transcript_path, "transcript_path")
    if isinstance(path, dict):
        return path
    try:
        units, granularity = load_units(path)
    except ValueError as exc:
        return invalid_input(str(exc), "Pass a transcript .json (from transcribe_file), .srt or .vtt.")
    text, next_start = numbered_view(units, max(0, start_index), max(1, limit))
    return _ok({"numbered_view": text, "granularity": granularity, "unit_count": len(units),
                "next_start": next_start})


@mcp.tool()
@tool_guard
def media_text_edit(source: str, transcript_path: str, delete: str = "[]", remove_fillers: bool = False,
                    padding_seconds: float = 0.05, output: str = "file", output_path: str = "", output_dir: str = "",
                    overwrite: bool = False) -> dict:
    """Cut words out of a recording by deleting them from its transcript.

    ``delete`` is a JSON list of ``{"words": [first, last]}`` (indices from
    ``transcript_words``), ``{"segment": n}``, ``{"text": "you know"}`` (every
    occurrence) and ``{"time": [start, end]}``; ``remove_fillers`` also cuts
    um/uh/erm/er/ah/hmm/mm. The silence around each deleted run goes too;
    kept words keep ``padding_seconds`` of air. ``output``: ``cutlist`` (keep
    ranges JSON), ``file`` (the edited media) or ``kdenlive`` (one clip per
    kept range, editable). Every mode also writes the cut list, a retimed
    ``<name>_edited_transcript.json`` and ``<name>_edited.srt``.
    """
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
    from workshop_video_brain.edit_mcp.pipelines import text_edit
    from workshop_video_brain.edit_mcp.pipelines.media_files import resolve_output
    from workshop_video_brain.edit_mcp.pipelines.subtitle_files import transcript_to_cues, write_cues
    from workshop_video_brain.workspace.safe_write import atomic_write_text

    src = source_path(source)
    if isinstance(src, dict):
        return src
    tpath = source_path(transcript_path, "transcript_path")
    if isinstance(tpath, dict):
        return tpath
    if output not in ("cutlist", "file", "kdenlive"):
        return invalid_input(f"output must be cutlist, file or kdenlive, got {output!r}", "Pick one of the three.")
    try:
        spec = json.loads(delete)
    except (TypeError, json.JSONDecodeError):
        return bad_json_param("delete", _DELETE_EXAMPLE, str(delete))
    if not isinstance(spec, list):
        return bad_json_param("delete", _DELETE_EXAMPLE, str(delete))
    asset = probe_media(src)
    duration = asset.duration_seconds or 0.0
    if not duration:
        return media_unreadable(str(src), "no duration")
    try:
        transcript = text_edit.load_transcript(tpath)
        units, granularity = text_edit.units_of(transcript)
        if units and units[-1].end > duration + 1.0:
            return invalid_input(f"The transcript runs to {units[-1].end:.2f}s but the media is {duration:.2f}s long",
                                 "Use the transcript made from this file (transcribe_file).")
        deleted = text_edit.select_deletions(units, spec, remove_fillers)
        ranges = text_edit.keep_ranges(units, deleted, duration, pad=padding_seconds)
        if not ranges:
            return invalid_input("Nothing would be left after these deletions", "Delete less.")
        folder = Path(output_dir) if output_dir else None

        def out(suffix: str, ext: str, explicit: str = "") -> Path:
            return resolve_output(src, explicit, str(folder) if folder else "", suffix=suffix, ext=ext,
                                  overwrite=overwrite)

        cutlist_path = out("_cutlist", ".json")
        transcript_out = out("_edited_transcript", ".json")
        srt_out = out("_edited", ".srt")
        media_out = out("_edited", src.suffix, output_path if output == "file" else "") if output == "file" else None
        project_out = out("_edited", ".kdenlive", output_path if output == "kdenlive" else "") if output == "kdenlive" else None
    except ValueError as exc:
        return invalid_input(str(exc), f"delete items look like {_DELETE_EXAMPLE}")

    summary = text_edit.edit_summary(ranges, duration)
    atomic_write_text(cutlist_path, json.dumps({"source": str(src), "ranges": [list(r) for r in ranges],
                                                "deleted_indices": sorted(deleted), "granularity": granularity,
                                                **summary}, indent=2))
    edited = text_edit.retime_transcript(transcript, ranges, deleted)
    atomic_write_text(transcript_out, edited.to_json())
    write_cues(transcript_to_cues(edited), srt_out, "srt")
    paths = {"cutlist": str(cutlist_path), "transcript": str(transcript_out), "srt": str(srt_out)}

    if output == "file":
        from workshop_video_brain.edit_mcp.pipelines.silence_cut import render_keep_ranges
        from workshop_video_brain.edit_mcp.server.bundles._pipeline_errors import error_from_pipeline_result
        rendered = render_keep_ranges(src, ranges, media_out)
        if not rendered.get("success"):
            return error_from_pipeline_result(rendered, "Rendering the edit failed", path=str(src))
        paths["file"] = str(media_out)
    elif output == "kdenlive":
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
        from workshop_video_brain.edit_mcp.pipelines.project_profile import profile_from_media
        from workshop_video_brain.edit_mcp.pipelines.selects_timeline import build_ranges_project
        profile = profile_from_media([src])
        project = build_ranges_project(src, ranges, profile=profile, has_audio=bool(asset.audio_codec or asset.channels),
                                       title=f"Text edit {src.stem}", source_frames=round(duration * profile.fps))
        serialize_project(project, project_out)
        paths["kdenlive"] = str(project_out)

    result = {"source": str(src), "granularity": granularity, "ranges": [list(r) for r in ranges],
              "deleted_count": len(deleted), "paths": paths, **summary}
    if granularity == "segment":
        result["warning"] = ("This transcript has no word timings, so deletions are whole sentences. "
                             "Transcribe with transcribe_file for word-level cuts.")
    return _ok(result)
