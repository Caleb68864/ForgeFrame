"""Research service orchestrator: query in, :class:`ResearchManifest` package out.

Wires the whole visual-research pipeline behind one entry point,
:func:`research_video`:

``probe_media`` -> resolve transcript (explicit, transcribed, or
transcript-free) -> :func:`select_regions` -> :func:`generate_candidates` ->
:class:`FrameScorer` -> (OCR, skipped unless ``config.ocr.enabled``) ->
:func:`deduplicate` -> (vision, skipped unless ``config.vision.enabled``) ->
deterministic top-ranked selection -> :func:`export_package`.

Each region is processed independently: a region that raises during
extraction/scoring/dedup is recorded in ``manifest.errors`` and skipped, and
the run still returns a partial manifest built from the healthy regions
rather than aborting.
"""
from __future__ import annotations

import logging
from pathlib import Path

from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.core.models.visual_research import (
    FrameCandidate,
    ResearchCapture,
    ResearchConfig,
    ResearchManifest,
    ResearchQuery,
    ResearchRegion,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.pipelines.transcript_repository import (
    TranscriptRepository,
)
from workshop_video_brain.edit_mcp.pipelines.visual_research.candidates import (
    generate_candidates,
)
from workshop_video_brain.edit_mcp.pipelines.visual_research.dedup import deduplicate
from workshop_video_brain.edit_mcp.pipelines.visual_research.export import export_package
from workshop_video_brain.edit_mcp.pipelines.visual_research.regions import select_regions
from workshop_video_brain.edit_mcp.pipelines.visual_research.scoring import FrameScorer

logger = logging.getLogger(__name__)


def _build_transcript_repository(
    transcript: Transcript | list[TranscriptSegment] | None,
    video_path: Path,
    asset_id,
    auto_transcribe: bool,
) -> TranscriptRepository | None:
    """Resolve *transcript* into a :class:`TranscriptRepository`, or ``None``.

    ``transcript`` may already be a :class:`Transcript` or a raw list of
    :class:`TranscriptSegment`. If it's absent and ``auto_transcribe`` is set,
    a best-effort transcription is attempted; any failure there degrades to
    transcript-free processing rather than aborting the whole run.
    """
    if transcript is not None:
        if isinstance(transcript, Transcript):
            return TranscriptRepository(transcript.segments)
        return TranscriptRepository(list(transcript))

    if not auto_transcribe:
        return None

    try:
        from workshop_video_brain.edit_mcp.adapters.stt import whisper_engine

        result = whisper_engine.transcribe(video_path, asset_id=asset_id)
        return TranscriptRepository(result.segments)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Auto-transcription failed for %s; continuing transcript-free: %s",
            video_path,
            exc,
        )
        return None


def _build_queries(
    source_id,
    query: str | None,
    topics: list[str] | None,
    timestamp_ranges: list[tuple[float, float]] | None,
) -> list[ResearchQuery]:
    """Turn the caller-facing search parameters into one or more :class:`ResearchQuery`."""
    queries: list[ResearchQuery] = []

    if query:
        queries.append(ResearchQuery(source_id=source_id, text=query))

    for topic in topics or []:
        queries.append(ResearchQuery(source_id=source_id, text=topic))

    for start_seconds, end_seconds in timestamp_ranges or []:
        queries.append(
            ResearchQuery(
                source_id=source_id,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
            )
        )

    return queries


def _fallback_region(source_id, duration_seconds: float, config: ResearchConfig) -> ResearchRegion:
    """Bounded uniform-sampling region used when there is no transcript and no range.

    Spans from the start of the source up to
    ``config.windowing.maximum_region_seconds`` (or the source duration if
    shorter) -- the actual candidate-count ceiling is enforced downstream by
    :func:`generate_candidates`.
    """
    span = duration_seconds if duration_seconds > 0 else config.windowing.maximum_region_seconds
    end_seconds = min(span, config.windowing.maximum_region_seconds)
    return ResearchRegion(
        source_id=source_id,
        start_seconds=0.0,
        end_seconds=end_seconds,
        source_method="uniform_sampling",
        reason="no transcript and no explicit range: bounded uniform sampling",
    )


def _resolve_regions(
    repo: TranscriptRepository | None,
    source_id,
    query: str | None,
    topics: list[str] | None,
    timestamp_ranges: list[tuple[float, float]] | None,
    duration_seconds: float,
    config: ResearchConfig,
) -> list[ResearchRegion]:
    queries = _build_queries(source_id, query, topics, timestamp_ranges)

    if not queries:
        return [_fallback_region(source_id, duration_seconds, config)]

    regions: list[ResearchRegion] = []
    for research_query in queries:
        regions.extend(select_regions(repo, research_query, config))
    return regions


def _process_region(
    video_path: Path,
    region: ResearchRegion,
    source,
    config: ResearchConfig,
) -> ResearchCapture:
    """Run candidate generation/scoring/dedup/selection for one region.

    Raises on any stage failure; the caller is responsible for isolating
    that failure into the manifest's error list.
    """
    candidates: list[FrameCandidate] = generate_candidates(video_path, region, source, config)

    scorer = FrameScorer()
    ranked = scorer.rank(candidates, config)

    # OCR and vision are optional enrichment stages, skipped by default and
    # only invoked when explicitly enabled in config -- no adapters are
    # wired here since neither stage is enabled by default.

    if config.deduplication.enabled and ranked:
        kept, _duplicate_map = deduplicate(
            ranked, threshold=config.deduplication.max_hamming_distance
        )
    else:
        kept = ranked

    if not kept:
        raise RuntimeError(
            f"No candidates survived scoring/dedup for region {region.region_id}"
        )

    # Deterministic selection: the top-ranked surviving candidate.
    kept[0].metadata["selected"] = True

    return ResearchCapture(
        region_id=region.region_id,
        source_id=source.id,
        candidates=kept,
    )


def research_video(
    source: Path | str,
    transcript: Transcript | list[TranscriptSegment] | None = None,
    query: str | None = None,
    topics: list[str] | None = None,
    timestamp_ranges: list[tuple[float, float]] | None = None,
    config: ResearchConfig | None = None,
    *,
    output_dir: Path | str | None = None,
    auto_transcribe: bool = False,
    obsidian: bool = False,
    keep_candidates: bool = False,
) -> ResearchManifest:
    """Run the full visual-research pipeline over *source* and export a package.

    Pipeline: ``probe_media`` -> resolve transcript -> :func:`select_regions`
    -> :func:`generate_candidates` -> score -> (OCR, skipped by default) ->
    :func:`deduplicate` -> (vision, skipped by default) -> deterministic
    top-ranked selection -> :func:`export_package`.

    Each region is processed with error isolation: a region that raises is
    recorded in ``manifest.errors`` (with its ``region_id`` and the error
    message) and skipped, rather than aborting the whole run. With no
    transcript and no explicit query/topics/timestamp range, region
    selection falls back to a single bounded uniform-sampling region, and
    the hard candidate ceiling from ``config.candidate_generation`` still
    applies.

    Returns the (possibly partial) :class:`ResearchManifest`, after writing
    the exported ``research/`` package for any surviving captures.
    """
    video_path = Path(source)
    cfg = config or ResearchConfig()

    source_asset = probe_media(video_path)
    duration_seconds = source_asset.duration_seconds or source_asset.duration

    repo = _build_transcript_repository(
        transcript, video_path, source_asset.id, auto_transcribe
    )

    regions = _resolve_regions(
        repo, source_asset.id, query, topics, timestamp_ranges, duration_seconds, cfg
    )

    manifest = ResearchManifest(source=source_asset)

    for region in regions:
        try:
            capture = _process_region(video_path, region, source_asset, cfg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Region %s failed during research: %s", region.region_id, exc)
            manifest.errors.append(
                {
                    "region_id": str(region.region_id),
                    "start_seconds": region.start_seconds,
                    "end_seconds": region.end_seconds,
                    "error": str(exc),
                }
            )
            continue

        manifest.regions.append(region)
        manifest.captures.append(capture)

    if manifest.captures:
        resolved_output_dir = (
            Path(output_dir)
            if output_dir is not None
            else video_path.parent / cfg.export.output_dir / str(manifest.manifest_id)[:8]
        )
        export_package(
            manifest,
            resolved_output_dir,
            obsidian=obsidian,
            keep_candidates=keep_candidates,
            config=cfg,
        )

    return manifest
