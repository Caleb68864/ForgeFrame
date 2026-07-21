"""Read-only visual-research transcript tools: search and time-window context.

Thin shells over ``edit_mcp/adapters/transcript/parsers.py`` (``parse_transcript``)
and ``edit_mcp/pipelines/transcript_repository.py`` (``TranscriptRepository``). No
mutation of project/workspace state -- these tools only read transcript files.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (
    tool_guard,
    missing_file,
    invalid_input,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok
from workshop_video_brain.edit_mcp.adapters.transcript.parsers import parse_transcript
from workshop_video_brain.edit_mcp.pipelines.transcript_repository import (
    TranscriptRepository,
)


def _load_repository(transcript_path: str) -> tuple[TranscriptRepository | None, dict | None]:
    """Parse *transcript_path* into a :class:`TranscriptRepository`.

    Returns ``(repository, None)`` on success or ``(None, error_envelope)`` on
    failure -- missing files are distinguished from unparseable content so
    callers can surface the right error type.
    """
    path = Path(transcript_path)
    if not path.exists():
        return None, missing_file(transcript_path, "transcript_path")

    try:
        segments = parse_transcript(path)
    except Exception as exc:
        return None, invalid_input(
            f"Could not parse transcript: {exc}",
            "Provide a well-formed .json, .srt, or .vtt transcript file.",
            transcript_path=transcript_path,
        )

    return TranscriptRepository(segments), None


def _segment_dict(index: int, seg) -> dict:
    return {
        "id": seg.segment_id if seg.segment_id is not None else index,
        "start_seconds": seg.start_seconds,
        "end_seconds": seg.end_seconds,
        "text": seg.text,
    }


@mcp.tool()
@tool_guard
def research_transcript_search(transcript_path: str, query: str, limit: int = 10) -> dict:
    """Search a transcript for segments containing *query*.

    Args:
        transcript_path: Path to a .json, .srt, or .vtt transcript file.
        query: Substring to search for (case-insensitive).
        limit: Maximum number of matching segments to return.

    Returns:
        Matching segments (id, start/end seconds, text) in transcript order.
        Unscored -- ``TranscriptRepository.search`` does not rank results.
    """
    repository, error = _load_repository(transcript_path)
    if error is not None:
        return error

    all_segments = repository.segments
    matches = repository.search(query)
    matched_ids = {id(m) for m in matches}
    ordered_matches = [
        _segment_dict(idx, seg)
        for idx, seg in enumerate(all_segments)
        if id(seg) in matched_ids
    ][:limit]

    return _ok({
        "segments": ordered_matches,
        "count": len(ordered_matches),
    })


@mcp.tool()
@tool_guard
def research_transcript_context(
    transcript_path: str,
    timestamp_seconds: float,
    window_seconds: float = 30.0,
) -> dict:
    """Return transcript segments overlapping a time window around *timestamp_seconds*.

    Args:
        transcript_path: Path to a .json, .srt, or .vtt transcript file.
        timestamp_seconds: Center timestamp, in seconds.
        window_seconds: Half-width of the window on each side of the timestamp.

    Returns:
        Segments overlapping ``[timestamp - window, timestamp + window]``,
        ordered by start time. If none overlap, an empty list with a message
        noting the transcript's end time.
    """
    repository, error = _load_repository(transcript_path)
    if error is not None:
        return error

    context_segments = sorted(
        repository.context_around(timestamp_seconds, window_seconds),
        key=lambda seg: seg.start_seconds,
    )

    all_segments = repository.segments
    result = {
        "segments": [_segment_dict(i, seg) for i, seg in enumerate(context_segments)],
        "count": len(context_segments),
    }

    if not context_segments:
        end_time = max((seg.end_seconds for seg in all_segments), default=0.0)
        result["message"] = (
            f"No segments overlap the requested window; transcript ends at "
            f"{end_time:.2f}s."
        )

    return _ok(result)
