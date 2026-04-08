"""Auto-marking pipeline: generate Marker objects from a Transcript."""
from __future__ import annotations

import json
import re
import string
from pathlib import Path

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.markers import Marker, MarkerConfig, MarkerRule
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment

_INTRO_WINDOW_SECONDS = 30.0
_ENDING_WINDOW_SECONDS = 60.0

# ---------------------------------------------------------------------------
# Phrase detection
# ---------------------------------------------------------------------------

_REDO_PHRASES: list[str] = [
    "let me redo",
    "actually wait",
    "hold on",
    "let me start over",
    "that's wrong",
    "scratch that",
    "one more time",
    "let me try again",
    "wait no",
    "sorry",
]

_FILLER_WORDS: list[str] = ["um", "uh", "like", "you know"]
_FILLER_MIN_COUNT = 3
_FILLER_WINDOW_SECONDS = 10.0
_FALSE_START_WINDOW_SECONDS = 15.0
_FALSE_START_MIN_WORDS = 3


def _strip_punctuation(text: str) -> str:
    return text.translate(str.maketrans("", "", string.punctuation))


def _word_tokens(text: str) -> list[str]:
    return _strip_punctuation(text.lower()).split()


def detect_phrases(transcript: Transcript) -> list[Marker]:
    """Detect redo/filler phrases and false starts in transcript segments.

    Returns a list of Marker objects with category ``mistake_problem``.
    """
    markers: list[Marker] = []
    segments = transcript.segments
    asset_hex = transcript.asset_id.hex

    # 1. Redo phrase detection
    redo_pattern = re.compile(
        r"\b(" + "|".join(re.escape(p) for p in _REDO_PHRASES) + r")\b",
        re.IGNORECASE,
    )
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        match = redo_pattern.search(text)
        if match:
            markers.append(
                Marker(
                    category=MarkerCategory.mistake_problem,
                    confidence_score=0.9,
                    source_method="phrase_detection",
                    reason=f'Redo phrase detected: "{match.group(0).lower()}"',
                    clip_ref=asset_hex,
                    start_seconds=seg.start_seconds,
                    end_seconds=seg.end_seconds,
                )
            )

    # 2. Filler cluster detection (within a single segment or consecutive segs within 10s)
    def _count_fillers(text: str) -> int:
        tokens = _word_tokens(text)
        return sum(1 for t in tokens if t in _FILLER_WORDS)

    # Check individual segments first
    for seg in segments:
        if _count_fillers(seg.text) >= _FILLER_MIN_COUNT:
            markers.append(
                Marker(
                    category=MarkerCategory.mistake_problem,
                    confidence_score=0.6,
                    source_method="phrase_detection",
                    reason="Filler word cluster detected",
                    clip_ref=asset_hex,
                    start_seconds=seg.start_seconds,
                    end_seconds=seg.end_seconds,
                )
            )

    # Check consecutive segments within window
    for i in range(len(segments) - 1):
        seg_a = segments[i]
        seg_b = segments[i + 1]
        if seg_b.start_seconds - seg_a.start_seconds <= _FILLER_WINDOW_SECONDS:
            combined = seg_a.text + " " + seg_b.text
            if (
                _count_fillers(combined) >= _FILLER_MIN_COUNT
                and _count_fillers(seg_a.text) < _FILLER_MIN_COUNT
                and _count_fillers(seg_b.text) < _FILLER_MIN_COUNT
            ):
                markers.append(
                    Marker(
                        category=MarkerCategory.mistake_problem,
                        confidence_score=0.6,
                        source_method="phrase_detection",
                        reason="Filler word cluster detected across consecutive segments",
                        clip_ref=asset_hex,
                        start_seconds=seg_a.start_seconds,
                        end_seconds=seg_b.end_seconds,
                    )
                )

    # 3. False start detection: same first 3+ words within 15 seconds
    for i, seg_a in enumerate(segments):
        tokens_a = _word_tokens(seg_a.text)
        if len(tokens_a) < _FALSE_START_MIN_WORDS:
            continue
        prefix_a = tuple(tokens_a[:_FALSE_START_MIN_WORDS])
        for seg_b in segments[i + 1 :]:
            if seg_b.start_seconds - seg_a.start_seconds > _FALSE_START_WINDOW_SECONDS:
                break
            tokens_b = _word_tokens(seg_b.text)
            if len(tokens_b) < _FALSE_START_MIN_WORDS:
                continue
            if tuple(tokens_b[:_FALSE_START_MIN_WORDS]) == prefix_a:
                # Flag the later segment as the false-start restart
                markers.append(
                    Marker(
                        category=MarkerCategory.mistake_problem,
                        confidence_score=0.5,
                        source_method="phrase_detection",
                        reason=(
                            f"False start: segment restarts with same opening words as "
                            f"segment at {seg_a.start_seconds:.1f}s"
                        ),
                        clip_ref=asset_hex,
                        start_seconds=seg_a.start_seconds,
                        end_seconds=seg_b.end_seconds,
                    )
                )

    return markers


# ---------------------------------------------------------------------------
# Repetition detection
# ---------------------------------------------------------------------------


def detect_repetition(
    transcript: Transcript,
    window: int = 5,
    threshold: float = 0.6,
) -> list[Marker]:
    """Detect repeated segments using Jaccard similarity on word sets.

    Compares each segment against the next *window* segments. If similarity
    exceeds *threshold* and the segments are within 60 seconds, the later
    segment is flagged.
    """
    markers: list[Marker] = []
    segments = transcript.segments
    asset_hex = transcript.asset_id.hex

    def _jaccard(a: str, b: str) -> float:
        set_a = set(_word_tokens(a))
        set_b = set(_word_tokens(b))
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union else 0.0

    flagged: set[int] = set()

    for i, earlier in enumerate(segments):
        if not earlier.text.strip():
            continue
        for j in range(i + 1, min(i + 1 + window, len(segments))):
            later = segments[j]
            if not later.text.strip():
                continue
            if later.start_seconds - earlier.start_seconds > 60.0:
                break
            if j in flagged:
                continue
            sim = _jaccard(earlier.text, later.text)
            if sim >= threshold:
                flagged.add(j)
                preview = earlier.text[:50]
                markers.append(
                    Marker(
                        category=MarkerCategory.repetition,
                        confidence_score=round(sim, 6),
                        source_method="repetition_detection",
                        reason=(
                            f'Similar to segment at {earlier.start_seconds:.1f}s: "{preview}..."'
                        ),
                        clip_ref=asset_hex,
                        start_seconds=later.start_seconds,
                        end_seconds=later.end_seconds,
                    )
                )

    return markers


# ---------------------------------------------------------------------------
# Mistake export
# ---------------------------------------------------------------------------

_MISTAKE_CATEGORIES: frozenset[MarkerCategory] = frozenset(
    [
        MarkerCategory.dead_air,
        MarkerCategory.mistake_problem,
        MarkerCategory.repetition,
    ]
)


def export_mistakes(markers: list[Marker], output_path: Path) -> Path:
    """Filter *markers* to mistake-related categories and write a JSON file.

    Returns the path of the written file.
    """
    mistake_markers = [m for m in markers if MarkerCategory(m.category) in _MISTAKE_CATEGORIES]
    payload = [json.loads(m.to_json()) for m in mistake_markers]
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


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
    5. Phrase detection (redo phrases, filler clusters, false starts).
    6. Repetition detection (Jaccard similarity on word sets).
    7. Merge nearby markers of the same category.
    8. Apply extra_keywords as additional rules if provided.
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

    # 5. Phrase and repetition detection (after keyword markers, before merge)
    raw_markers.extend(detect_phrases(transcript))
    raw_markers.extend(detect_repetition(transcript))

    # 6. Merge nearby markers of same category
    merged = _merge_markers(raw_markers, config.segment_merge_gap_seconds)

    # Final sort by start_seconds for determinism
    merged.sort(key=lambda m: (m.start_seconds, str(m.category)))
    return merged
