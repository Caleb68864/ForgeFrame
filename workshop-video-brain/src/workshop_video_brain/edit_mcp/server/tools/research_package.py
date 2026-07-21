"""One-shot run + package export MCP tools.

``research_run`` is a thin shell over
:func:`~workshop_video_brain.edit_mcp.pipelines.visual_research.service.research_video`
(the deterministic full pipeline; mirrors ``wvb research``).
``research_export_package`` exports from an existing handshake dir (see
``edit_mcp/pipelines/visual_research/handshake.py``) without requiring an
agent selection: it uses ``candidates.json``'s recorded ``selections`` when
present, otherwise the deterministic top-scored candidate per region.

Both tools own their own ``output_dir`` overwrite guard here (rather than
relying on ``export_package``'s bare "must not exist" contract) so an
``overwrite=True`` request is honored only against a directory that already
holds a prior research artifact, and never against ``media/raw/`` or
``projects/source/``.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.adapters.transcript.parsers import parse_transcript
from workshop_video_brain.edit_mcp.server.errors import (
    tool_guard,
    missing_file,
    invalid_input,
    not_found,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok
from workshop_video_brain.edit_mcp.pipelines.visual_research.handshake import (
    CandidatesManifestNotFoundError,
    SourceFingerprintMismatchError,
    UnknownCandidateIdsError,
    load_handshake,
    select_from_handshake,
    top_scored_candidate_ids,
)
from workshop_video_brain.edit_mcp.pipelines.visual_research.service import research_video

_PROTECTED_SUBSTRINGS = ("media/raw", "projects/source")

_OVERWRITE_SUGGESTION = (
    "Pass overwrite=True to replace an existing research output directory "
    "(only honored when it already contains a manifest.json or "
    "candidates.json from a prior research run), or choose a different "
    "output_dir."
)


def _is_protected_path(path: Path) -> bool:
    posix = path.resolve().as_posix()
    return any(marker in posix for marker in _PROTECTED_SUBSTRINGS)


def _prepare_output_dir(output_dir: Path, overwrite: bool) -> dict | None:
    """Enforce the shared output_dir overwrite contract.

    Returns an error envelope if the request should be refused, else ``None``
    after clearing *output_dir* (when it was non-empty and overwrite was
    honored) so the caller can write into a clean directory.
    """
    if not output_dir.exists() or not any(output_dir.iterdir()):
        return None

    has_prior_artifact = (output_dir / "manifest.json").exists() or (
        output_dir / "candidates.json"
    ).exists()

    if not overwrite or not has_prior_artifact or _is_protected_path(output_dir):
        return invalid_input(
            f"Output directory already exists and is not empty: {output_dir}.",
            _OVERWRITE_SUGGESTION,
            output_dir=str(output_dir),
        )

    shutil.rmtree(output_dir)
    return None


@mcp.tool()
@tool_guard
def research_run(
    video_path: str,
    output_dir: str,
    transcript_path: str | None = None,
    query: str | None = None,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
    obsidian: bool = False,
    keep_candidates: bool = False,
    overwrite: bool = False,
) -> dict:
    """Run the full deterministic visual-research pipeline and export a package.

    Args:
        video_path: Path to the source video file.
        output_dir: Directory to write ``index.md``, ``manifest.json``, and
            ``screenshots/`` into. Must not already exist with content
            unless ``overwrite`` is set (and only honored when the existing
            directory contains a prior research artifact).
        transcript_path: Optional transcript file (.json/.srt/.vtt) used to
            scope regions by keyword search.
        query: Optional keyword search text.
        start_seconds: Optional explicit region start; combined with
            ``end_seconds`` into a single ``timestamp_ranges`` entry.
        end_seconds: Optional explicit region end.
        obsidian: When True, also write an Obsidian note.
        keep_candidates: When True, also copy non-selected candidate images.
        overwrite: When True, replace an existing non-empty ``output_dir``.

    Returns:
        The manifest summary (source, regions, captures, errors, output_dir).
    """
    path = Path(video_path)
    if not path.exists():
        return missing_file(video_path, "video_path")

    resolved_output_dir = Path(output_dir)
    guard = _prepare_output_dir(resolved_output_dir, overwrite)
    if guard is not None:
        return guard

    segments = parse_transcript(Path(transcript_path)) if transcript_path else None

    timestamp_ranges = None
    if start_seconds is not None or end_seconds is not None:
        timestamp_ranges = [(start_seconds, end_seconds)]

    manifest = research_video(
        path,
        transcript=segments,
        query=query,
        timestamp_ranges=timestamp_ranges,
        output_dir=resolved_output_dir,
        obsidian=obsidian,
        keep_candidates=keep_candidates,
    )

    return _ok(
        {
            "source": {
                "path": manifest.source.path,
                "duration_seconds": manifest.source.duration_seconds
                or manifest.source.duration,
            },
            "regions": [region.model_dump(mode="json") for region in manifest.regions],
            "captures": [capture.model_dump(mode="json") for capture in manifest.captures],
            "errors": manifest.errors,
            "output_dir": str(resolved_output_dir),
        }
    )


@mcp.tool()
@tool_guard
def research_export_package(
    candidates_dir: str,
    output_dir: str,
    obsidian: bool = False,
    keep_candidates: bool = False,
    overwrite: bool = False,
) -> dict:
    """Export a research package from an existing handshake dir, no agent selection needed.

    Uses the ``selections`` already recorded in ``candidates_dir/candidates.json``
    when non-empty, else the deterministic top-scored candidate per region.

    Args:
        candidates_dir: Directory previously written by
            ``research_generate_candidates`` (contains ``candidates.json``).
        output_dir: Export destination. Must not already exist with content
            unless ``overwrite`` is set (and only honored when the existing
            directory contains a prior research artifact).
        obsidian: When True, also write an Obsidian note.
        keep_candidates: When True, also copy non-selected candidate images.
        overwrite: When True, replace an existing non-empty ``output_dir``.

    Returns:
        The exported research manifest, export directory, and selected ids.
    """
    try:
        manifest = load_handshake(candidates_dir)
    except CandidatesManifestNotFoundError as exc:
        return not_found(
            "candidates.json",
            str(Path(candidates_dir) / "candidates.json"),
            hint=str(exc),
        )
    except SourceFingerprintMismatchError as exc:
        return invalid_input(
            str(exc),
            "The source video changed since candidates were generated. "
            "Re-run research_generate_candidates and select again.",
            candidates_dir=candidates_dir,
        )

    resolved_output_dir = Path(output_dir)
    guard = _prepare_output_dir(resolved_output_dir, overwrite)
    if guard is not None:
        return guard

    selections = manifest.get("selections") or []
    candidate_ids = selections if selections else top_scored_candidate_ids(manifest)

    if not candidate_ids:
        return invalid_input(
            f"No candidates found in {candidates_dir}.",
            "Re-run research_generate_candidates first.",
            candidates_dir=candidates_dir,
        )

    try:
        result = select_from_handshake(
            candidates_dir,
            candidate_ids,
            output_dir=resolved_output_dir,
            obsidian=obsidian,
            keep_candidates=keep_candidates,
            overwrite=False,
        )
    except UnknownCandidateIdsError as exc:
        return invalid_input(
            str(exc),
            "Pass one of the valid candidate ids listed below.",
            unknown_ids=exc.unknown_ids,
            valid_ids=exc.valid_ids,
        )

    return _ok(result)
