"""Two-call agent handshake MCP tools: generate candidates, then select.

Thin shells over ``edit_mcp/pipelines/visual_research/handshake.py``
(``generate_handshake``, ``select_from_handshake``). No JSON-schema or
persistence logic lives here -- that belongs entirely to the pipeline module.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (
    tool_guard,
    missing_file,
    invalid_input,
    not_found,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok
from workshop_video_brain.edit_mcp.pipelines.visual_research.handshake import (
    CandidatesManifestNotFoundError,
    OutputDirNotEmptyError,
    SourceFingerprintMismatchError,
    UnknownCandidateIdsError,
    generate_handshake,
    select_from_handshake,
)


@mcp.tool()
@tool_guard
def research_generate_candidates(
    video_path: str,
    output_dir: str,
    transcript_path: str | None = None,
    query: str | None = None,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
    max_candidates: int | None = None,
    overwrite: bool = False,
) -> dict:
    """Generate candidate frames for *video_path* and persist a candidates manifest.

    Args:
        video_path: Path to the source video file.
        output_dir: Directory to write ``candidates/*.png`` and
            ``candidates.json`` into. Must not already exist with content
            unless ``overwrite`` is set (and only honored when the existing
            directory contains a prior ``candidates.json``).
        transcript_path: Optional transcript file (.json/.srt/.vtt) used to
            scope regions by keyword search.
        query: Optional keyword search text.
        start_seconds: Optional explicit region start.
        end_seconds: Optional explicit region end.
        max_candidates: Optional override for the per-region candidate cap.
        overwrite: When True, replace an existing candidates package.

    Returns:
        The schema-v1 candidates manifest dict.
    """
    path = Path(video_path)
    if not path.exists():
        return missing_file(video_path, "video_path")

    try:
        manifest = generate_handshake(
            path,
            transcript_path=transcript_path,
            query=query,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            output_dir=output_dir,
            max_candidates=max_candidates,
            overwrite=overwrite,
        )
    except OutputDirNotEmptyError as exc:
        return invalid_input(
            str(exc),
            "Pass overwrite=True to regenerate an existing candidates package, "
            "or choose a different output_dir.",
            output_dir=output_dir,
        )

    return _ok(manifest)


@mcp.tool()
@tool_guard
def research_select_candidate(
    candidates_dir: str,
    candidate_ids: list[str],
    output_dir: str | None = None,
    obsidian: bool = False,
    keep_candidates: bool = False,
    overwrite: bool = False,
) -> dict:
    """Select one or more candidates from a prior generate call and export a package.

    Args:
        candidates_dir: Directory previously written by
            ``research_generate_candidates`` (contains ``candidates.json``).
        candidate_ids: One or more candidate ids (e.g. ``["cand-001"]``) to export.
        output_dir: Optional explicit export destination; defaults to
            ``<candidates_dir>/export``.
        obsidian: When True, also write an Obsidian note.
        keep_candidates: When True, also copy non-selected candidate images.
        overwrite: When True, replace an existing non-empty ``output_dir``.

    Returns:
        The exported research manifest, export directory, and selected ids.
    """
    try:
        result = select_from_handshake(
            candidates_dir,
            candidate_ids,
            output_dir=output_dir,
            obsidian=obsidian,
            keep_candidates=keep_candidates,
            overwrite=overwrite,
        )
    except OutputDirNotEmptyError as exc:
        return invalid_input(
            str(exc),
            "Pass overwrite=True to replace a prior research package, or "
            "choose a different output_dir.",
            output_dir=str(output_dir) if output_dir else None,
        )
    except CandidatesManifestNotFoundError as exc:
        return not_found(
            "candidates.json",
            str(Path(candidates_dir) / "candidates.json"),
            hint=str(exc),
        )
    except UnknownCandidateIdsError as exc:
        return invalid_input(
            str(exc),
            "Pass one of the valid candidate ids listed below.",
            unknown_ids=exc.unknown_ids,
            valid_ids=exc.valid_ids,
        )
    except SourceFingerprintMismatchError as exc:
        return invalid_input(
            str(exc),
            "The source video changed since candidates were generated. "
            "Re-run research_generate_candidates and select again.",
            candidates_dir=candidates_dir,
        )

    return _ok(result)
