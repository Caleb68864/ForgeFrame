"""Turn a :class:`ResearchQuery` into bounded :class:`ResearchRegion` objects.

Selection methods, in the order they're evaluated:

1. Explicit ``start_seconds``/``end_seconds`` range on the query (no text) --
   ``source_method="query"``.
2. Explicit ``segment_ids`` -- resolved against the transcript repository,
   ``source_method="query"``.
3. Keyword ``text`` search against the transcript repository --
   ``source_method="transcript"``.
4. Explicit ``timestamps`` -- windowed around each timestamp. If a transcript
   repository is available and yields overlapping segments the region is
   tagged ``source_method="transcript"``; otherwise ``source_method="manual_timestamp"``.

Every raw region is expanded by ``pre_roll_seconds``/``post_roll_seconds``,
clamped to ``maximum_region_seconds``, then near-adjacent regions (gap <=
``merge_gap_seconds``) are merged, unioning their transcript segment ids.

AI-suggested regions (future extraction methods) are expected to be passed
through :func:`_expand_and_clamp` the same as every other candidate window --
they are never trusted as final spans.
"""
from __future__ import annotations

from workshop_video_brain.core.models.transcript import TranscriptSegment
from workshop_video_brain.core.models.visual_research import (
    ResearchConfig,
    ResearchQuery,
    ResearchRegion,
)
from workshop_video_brain.edit_mcp.pipelines.transcript_repository import (
    TranscriptRepository,
)


class _RawRegion:
    __slots__ = (
        "start_seconds",
        "end_seconds",
        "source_method",
        "reason",
        "transcript_segment_ids",
        "transcript_excerpt",
        "anchor_seconds",
    )

    def __init__(
        self,
        start_seconds: float,
        end_seconds: float,
        source_method: str,
        reason: str,
        transcript_segment_ids: list[str],
        transcript_excerpt: str,
        anchor_seconds: float,
    ):
        self.start_seconds = start_seconds
        self.end_seconds = end_seconds
        self.source_method = source_method
        self.reason = reason
        self.transcript_segment_ids = transcript_segment_ids
        self.transcript_excerpt = transcript_excerpt
        self.anchor_seconds = anchor_seconds


def _segment_id(segment: TranscriptSegment, fallback_index: int) -> str:
    return segment.segment_id if segment.segment_id else f"seg-{fallback_index}"


def _expand_and_clamp(
    anchor_start: float,
    anchor_end: float,
    config: ResearchConfig,
) -> tuple[float, float]:
    """Expand ``[anchor_start, anchor_end]`` by pre/post roll, then clamp length."""
    windowing = config.windowing
    start = max(0.0, anchor_start - windowing.pre_roll_seconds)
    end = anchor_end + windowing.post_roll_seconds
    if end - start > windowing.maximum_region_seconds:
        end = start + windowing.maximum_region_seconds
    return start, end


def _region_from_range(
    query: ResearchQuery, config: ResearchConfig
) -> _RawRegion | None:
    if query.start_seconds is None or query.end_seconds is None or query.text:
        return None
    start, end = _expand_and_clamp(query.start_seconds, query.end_seconds, config)
    return _RawRegion(
        start_seconds=start,
        end_seconds=end,
        source_method="query",
        reason=f"explicit range [{query.start_seconds}, {query.end_seconds}]",
        transcript_segment_ids=[],
        transcript_excerpt="",
        anchor_seconds=query.start_seconds,
    )


def _regions_from_segment_ids(
    repo: TranscriptRepository | None,
    query: ResearchQuery,
    config: ResearchConfig,
) -> list[_RawRegion]:
    if not query.segment_ids or repo is None:
        return []
    regions: list[_RawRegion] = []
    for sid in query.segment_ids:
        for index, segment in enumerate(repo.segments):
            if _segment_id(segment, index) != sid:
                continue
            start, end = _expand_and_clamp(
                segment.start_seconds, segment.end_seconds, config
            )
            regions.append(
                _RawRegion(
                    start_seconds=start,
                    end_seconds=end,
                    source_method="query",
                    reason=f"explicit segment id {sid}",
                    transcript_segment_ids=[sid],
                    transcript_excerpt=segment.text,
                    anchor_seconds=segment.start_seconds,
                )
            )
            break
    return regions


def _regions_from_keyword_search(
    repo: TranscriptRepository | None,
    query: ResearchQuery,
    config: ResearchConfig,
) -> list[_RawRegion]:
    if not query.text or repo is None:
        return []
    regions: list[_RawRegion] = []
    matches = repo.search(query.text)
    for match in matches:
        index = repo.segments.index(match)
        start, end = _expand_and_clamp(match.start_seconds, match.end_seconds, config)
        regions.append(
            _RawRegion(
                start_seconds=start,
                end_seconds=end,
                source_method="transcript",
                reason=f"keyword match: '{query.text}'",
                transcript_segment_ids=[_segment_id(match, index)],
                transcript_excerpt=match.text,
                anchor_seconds=match.start_seconds,
            )
        )
    return regions


def _regions_from_timestamps(
    repo: TranscriptRepository | None,
    query: ResearchQuery,
    config: ResearchConfig,
) -> list[_RawRegion]:
    if not query.timestamps:
        return []
    regions: list[_RawRegion] = []
    for timestamp in query.timestamps:
        overlapping: list[TranscriptSegment] = []
        if repo is not None:
            overlapping = repo.context_around(
                timestamp, config.windowing.pre_roll_seconds
            )
        if overlapping:
            start, end = _expand_and_clamp(
                min(seg.start_seconds for seg in overlapping),
                max(seg.end_seconds for seg in overlapping),
                config,
            )
            ids = [
                _segment_id(seg, repo.segments.index(seg)) for seg in overlapping
            ]
            excerpt = " ".join(seg.text for seg in overlapping)
            regions.append(
                _RawRegion(
                    start_seconds=start,
                    end_seconds=end,
                    source_method="transcript",
                    reason=f"manual timestamp {timestamp} with transcript context",
                    transcript_segment_ids=ids,
                    transcript_excerpt=excerpt,
                    anchor_seconds=timestamp,
                )
            )
        else:
            start, end = _expand_and_clamp(timestamp, timestamp, config)
            regions.append(
                _RawRegion(
                    start_seconds=start,
                    end_seconds=end,
                    source_method="manual_timestamp",
                    reason=f"explicit timestamp {timestamp}",
                    transcript_segment_ids=[],
                    transcript_excerpt="",
                    anchor_seconds=timestamp,
                )
            )
    return regions


def _merge_adjacent(
    regions: list[_RawRegion], merge_gap_seconds: float
) -> list[_RawRegion]:
    if not regions:
        return []
    ordered = sorted(regions, key=lambda r: r.start_seconds)
    merged: list[_RawRegion] = [ordered[0]]
    for region in ordered[1:]:
        last = merged[-1]
        if region.start_seconds - last.end_seconds <= merge_gap_seconds:
            last.end_seconds = max(last.end_seconds, region.end_seconds)
            last.start_seconds = min(last.start_seconds, region.start_seconds)
            merged_ids = list(last.transcript_segment_ids)
            for seg_id in region.transcript_segment_ids:
                if seg_id not in merged_ids:
                    merged_ids.append(seg_id)
            last.transcript_segment_ids = merged_ids
            if region.transcript_excerpt and region.transcript_excerpt not in last.transcript_excerpt:
                last.transcript_excerpt = " ".join(
                    part for part in [last.transcript_excerpt, region.transcript_excerpt] if part
                )
            if region.reason not in last.reason:
                last.reason = f"{last.reason}; {region.reason}"
            if last.source_method != region.source_method:
                last.source_method = "transcript"
        else:
            merged.append(region)
    return merged


def select_regions(
    repo: TranscriptRepository | None,
    query: ResearchQuery,
    config: ResearchConfig,
) -> list[ResearchRegion]:
    """Resolve ``query`` into bounded, merged :class:`ResearchRegion` objects.

    Evaluates, in order: an explicit start/end range, explicit segment ids,
    a keyword search, then an explicit timestamp list. Every candidate window
    is expanded by pre/post roll and clamped to ``maximum_region_seconds``
    before near-adjacent candidates are merged (gap <= ``merge_gap_seconds``).
    """
    raw: list[_RawRegion] = []

    range_region = _region_from_range(query, config)
    if range_region is not None:
        raw.append(range_region)

    raw.extend(_regions_from_segment_ids(repo, query, config))
    raw.extend(_regions_from_keyword_search(repo, query, config))
    raw.extend(_regions_from_timestamps(repo, query, config))

    merged = _merge_adjacent(raw, config.windowing.merge_gap_seconds)

    return [
        ResearchRegion(
            source_id=query.source_id,
            start_seconds=region.start_seconds,
            end_seconds=region.end_seconds,
            source_method=region.source_method,
            reason=region.reason,
            transcript_segment_ids=region.transcript_segment_ids,
            transcript_excerpt=region.transcript_excerpt,
            anchor_seconds=region.anchor_seconds,
        )
        for region in merged
    ]
