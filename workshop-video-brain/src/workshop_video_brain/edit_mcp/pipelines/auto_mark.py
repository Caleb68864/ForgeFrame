"""Auto-marking pipeline: generate Marker objects from a Transcript."""
from __future__ import annotations

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.markers import Marker, MarkerConfig, MarkerRule
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment

_INTRO_WINDOW_SECONDS = 30.0
_ENDING_WINDOW_SECONDS = 60.0


def _match_strength(text_lower: str, keyword: str) -> float:
    """Return match strength for a keyword against lower-cased text.

    Exact phrase match → 1.0
    All words of keyword present but not as a continuous phrase → 0.7
    """
    if keyword in text_lower:
        return 1.0
    words = keyword.split()
    if len(words) > 1 and all(w in text_lower for w in words):
        return 0.7
    return 0.0


def _check_rules(
    text: str,
    rules: list[MarkerRule],
) -> list[tuple[MarkerRule, float]]:
    """Return (rule, confidence) pairs for all matching rules, sorted by confidence desc."""
    text_lower = text.lower()
    hits: list[tuple[MarkerRule, float]] = []
    for rule in rules:
        best: float = 0.0
        for kw in rule.keywords:
            strength = _match_strength(text_lower, kw.lower())
            if strength > best:
                best = strength
        if best > 0.0:
            hits.append((rule, rule.base_confidence * best))
    hits.sort(key=lambda x: x[1], reverse=True)
    return hits


def _merge_markers(markers: list[Marker], gap: float) -> list[Marker]:
    """Merge nearby markers of the same category within *gap* seconds.

    Groups are merged into a single marker whose time span covers all members.
    The highest confidence_score in the group is kept.
    """
    if not markers:
        return []

    # Sort by category then start_seconds for a deterministic merge pass.
    by_cat: dict[str, list[Marker]] = {}
    for m in markers:
        cat = str(m.category)
        by_cat.setdefault(cat, []).append(m)

    merged: list[Marker] = []
    for cat, group in by_cat.items():
        group_sorted = sorted(group, key=lambda m: m.start_seconds)
        current = group_sorted[0]
        current_start = current.start_seconds
        current_end = current.end_seconds
        current_conf = current.confidence_score
        current_reason = current.reason
        current_source = current.source_method
        current_clip = current.clip_ref

        for nxt in group_sorted[1:]:
            if nxt.start_seconds - current_end <= gap:
                # Extend the current span
                current_end = max(current_end, nxt.end_seconds)
                if nxt.confidence_score > current_conf:
                    current_conf = nxt.confidence_score
                    current_reason = nxt.reason
            else:
                merged.append(
                    Marker(
                        category=MarkerCategory(cat),
                        confidence_score=current_conf,
                        source_method=current_source,
                        reason=current_reason,
                        clip_ref=current_clip,
                        start_seconds=current_start,
                        end_seconds=current_end,
                    )
                )
                current_start = nxt.start_seconds
                current_end = nxt.end_seconds
                current_conf = nxt.confidence_score
                current_reason = nxt.reason
                current_source = nxt.source_method
                current_clip = nxt.clip_ref

        merged.append(
            Marker(
                category=MarkerCategory(cat),
                confidence_score=current_conf,
                source_method=current_source,
                reason=current_reason,
                clip_ref=current_clip,
                start_seconds=current_start,
                end_seconds=current_end,
            )
        )

    # Sort merged list by start_seconds for determinism
    merged.sort(key=lambda m: (str(m.category), m.start_seconds))
    return merged


def generate_markers(
    transcript: Transcript,
    silence_gaps: list[tuple[float, float]],
    config: MarkerConfig,
    extra_keywords: list[str] | None = None,
) -> list[Marker]:
    """Generate a list of Marker objects from a transcript and silence gaps.

    Algorithm (deterministic for same inputs):
    1. Iterate transcript segments and apply keyword rules.
    2. Map silence gaps to dead_air markers.
    3. First 30 seconds of speech → intro_candidate marker.
    4. Last 60 seconds → ending_reveal marker.
    5. Merge nearby markers of the same category.
    6. Apply extra_keywords as additional rules if provided.
    """
    all_rules = list(config.rules)

    # Build extra rules from extra_keywords (one rule per keyword, misc category)
    if extra_keywords:
        for kw in extra_keywords:
            all_rules.append(
                MarkerRule(
                    keywords=[kw],
                    category=MarkerCategory.chapter_candidate,
                    base_confidence=0.6,
                )
            )

    raw_markers: list[Marker] = []

    # Determine speech boundaries for intro/ending detection
    speech_start: float | None = None
    speech_end: float | None = None
    for seg in transcript.segments:
        text = seg.text.strip()
        if not text:
            continue
        if speech_start is None or seg.start_seconds < speech_start:
            speech_start = seg.start_seconds
        if speech_end is None or seg.end_seconds > speech_end:
            speech_end = seg.end_seconds

    # 1. Keyword rule matching per segment
    for seg in transcript.segments:
        text = seg.text.strip()
        if not text:
            continue

        hits = _check_rules(text, all_rules)
        for rule, confidence in hits:
            cat = MarkerCategory(str(rule.category))
            raw_markers.append(
                Marker(
                    category=cat,
                    confidence_score=round(confidence, 6),
                    source_method="keyword_rule",
                    reason=f"Keyword match in: \"{text[:80]}\"",
                    clip_ref=transcript.asset_id.hex,
                    start_seconds=seg.start_seconds,
                    end_seconds=seg.end_seconds,
                )
            )

    # 2. Silence gaps → dead_air markers
    for start, end in silence_gaps:
        duration = end - start
        if duration >= config.silence_threshold_seconds:
            raw_markers.append(
                Marker(
                    category=MarkerCategory.dead_air,
                    confidence_score=1.0,
                    source_method="silence_detection",
                    reason=f"Silence gap of {duration:.1f}s",
                    clip_ref=transcript.asset_id.hex,
                    start_seconds=start,
                    end_seconds=end,
                )
            )

    # 3. First 30 seconds of speech → intro_candidate
    if speech_start is not None:
        intro_end = speech_start + _INTRO_WINDOW_SECONDS
        raw_markers.append(
            Marker(
                category=MarkerCategory.intro_candidate,
                confidence_score=0.8,
                source_method="position_heuristic",
                reason="First 30 seconds of speech",
                clip_ref=transcript.asset_id.hex,
                start_seconds=speech_start,
                end_seconds=min(intro_end, speech_end if speech_end is not None else intro_end),
            )
        )

    # 4. Last 60 seconds → ending_reveal
    if speech_end is not None:
        ending_start = max(speech_start or 0.0, speech_end - _ENDING_WINDOW_SECONDS)
        # Only add if ending window doesn't fully overlap with intro window
        if ending_start >= (speech_start or 0.0) + _INTRO_WINDOW_SECONDS or (
            speech_end - (speech_start or 0.0) > _INTRO_WINDOW_SECONDS
        ):
            raw_markers.append(
                Marker(
                    category=MarkerCategory.ending_reveal,
                    confidence_score=0.75,
                    source_method="position_heuristic",
                    reason="Last 60 seconds of speech",
                    clip_ref=transcript.asset_id.hex,
                    start_seconds=ending_start,
                    end_seconds=speech_end,
                )
            )

    # 5. Merge nearby markers of same category
    merged = _merge_markers(raw_markers, config.segment_merge_gap_seconds)

    # Final sort by start_seconds for determinism
    merged.sort(key=lambda m: (m.start_seconds, str(m.category)))
    return merged
