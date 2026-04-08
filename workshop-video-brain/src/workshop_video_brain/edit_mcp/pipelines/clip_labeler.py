"""Clip labeler pipeline: generate ClipLabel objects from transcripts and markers."""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path

from workshop_video_brain.core.models.clips import ClipLabel
from workshop_video_brain.core.models.transcript import Transcript
from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.utils.paths import ensure_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stop words for noun extraction
# ---------------------------------------------------------------------------

_STOP_WORDS: frozenset[str] = frozenset([
    "about", "above", "after", "again", "against", "ahead", "already", "also",
    "always", "another", "before", "being", "below", "between", "cannot",
    "could", "doing", "during", "every", "going", "going", "gonna", "gotten",
    "having", "here", "itself", "just", "know", "like", "little", "make",
    "might", "more", "most", "much", "need", "never", "next", "okay",
    "other", "over", "really", "right", "should", "since", "some", "still",
    "take", "that", "their", "them", "then", "there", "these", "they",
    "thing", "think", "this", "those", "through", "time", "under", "until",
    "very", "want", "well", "what", "when", "where", "which", "while",
    "with", "would", "your", "you're", "going", "gonna", "got", "get",
    "just", "like", "make", "take", "want", "need", "come", "look",
    "here", "okay", "actually", "basically", "literally", "pretty",
    "really", "kind", "sort", "stuff", "thing", "things", "something",
    "anything", "everything", "nothing", "someone", "anyone",
])

# Transition words used to chunk transcript text
_TRANSITION_WORDS: list[str] = ["next", "now", "then", "first", "okay", "so"]


# ---------------------------------------------------------------------------
# Topic extraction
# ---------------------------------------------------------------------------


def _extract_topics(text: str, max_topics: int = 8) -> list[str]:
    """Extract noun-like topics from transcript text.

    Splits on transition words, then extracts words > 4 chars that aren't
    stop words. Returns top 5-8 most frequent.
    """
    if not text:
        return []

    # Split on transition words (word boundaries)
    pattern = r"\b(?:" + "|".join(_TRANSITION_WORDS) + r")\b"
    chunks = re.split(pattern, text, flags=re.IGNORECASE)

    word_counts: Counter[str] = Counter()
    for chunk in chunks:
        # Extract words that are > 4 chars and likely noun-ish
        words = re.findall(r"\b[a-zA-Z]{5,}\b", chunk.lower())
        for word in words:
            if word not in _STOP_WORDS:
                word_counts[word] += 1

    min_topics = 5
    candidates = word_counts.most_common(max_topics)
    # Return at least min_topics if available, otherwise all
    result = [word for word, _ in candidates]
    return result[:max_topics]


# ---------------------------------------------------------------------------
# Speech density
# ---------------------------------------------------------------------------


def _calculate_speech_density(transcript: Transcript, total_duration: float) -> float:
    """Calculate ratio of speech time to total duration, clamped to 0.0-1.0."""
    if total_duration <= 0:
        return 0.0
    speech_time = sum(
        max(0.0, seg.end_seconds - seg.start_seconds)
        for seg in transcript.segments
        if seg.text.strip()
    )
    return min(1.0, max(0.0, speech_time / total_duration))


# ---------------------------------------------------------------------------
# Content type detection
# ---------------------------------------------------------------------------


def _detect_content_type(
    markers: list[dict],
    speech_density: float,
) -> str:
    """Determine content_type from marker categories and speech density."""
    step_count = sum(
        1 for m in markers
        if m.get("category") == MarkerCategory.step_explanation.value
    )
    materials_count = sum(
        1 for m in markers
        if m.get("category") == MarkerCategory.materials_mention.value
    )

    total_markers = len(markers)

    if total_markers == 0:
        if speech_density >= 0.5:
            return "talking_head"
        return "b_roll"

    if materials_count > step_count and materials_count > total_markers * 0.3:
        return "materials_overview"

    if step_count >= materials_count and step_count > 0:
        return "tutorial_step"

    if speech_density >= 0.6 and total_markers < 3:
        return "talking_head"

    if speech_density < 0.2:
        return "b_roll"

    return "tutorial_step"


# ---------------------------------------------------------------------------
# Shot type detection
# ---------------------------------------------------------------------------


def _detect_shot_type(markers: list[dict]) -> str:
    """Determine shot_type from markers."""
    for m in markers:
        cat = m.get("category", "")
        if cat == MarkerCategory.closeup_needed.value:
            return "closeup"

    for m in markers:
        cat = m.get("category", "")
        if cat == MarkerCategory.broll_candidate.value:
            return "b_roll"

    return "medium"


# ---------------------------------------------------------------------------
# Summary cleaning
# ---------------------------------------------------------------------------


def _clean_summary(raw_text: str, max_len: int = 100) -> str:
    """Extract and clean the first ~100 chars of transcript text."""
    if not raw_text:
        return ""
    # Remove double spaces
    cleaned = re.sub(r" {2,}", " ", raw_text.strip())
    if len(cleaned) <= max_len:
        return cleaned
    # Truncate without breaking in the middle of a word
    truncated = cleaned[:max_len]
    # Find the last space before the limit to avoid partial words
    last_space = truncated.rfind(" ")
    if last_space > max_len // 2:
        truncated = truncated[:last_space]
    return truncated.strip()


# ---------------------------------------------------------------------------
# Unlabeled label from filename
# ---------------------------------------------------------------------------


def _label_from_filename(clip_ref: str) -> list[str]:
    """Extract tags from a filename by splitting on _ and -."""
    stem = Path(clip_ref).stem
    parts = re.split(r"[_\-]", stem)
    return [p.lower() for p in parts if len(p) > 1]


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def generate_labels(workspace_root: Path) -> list[ClipLabel]:
    """Generate ClipLabel objects for all assets in the workspace.

    Reads transcripts from ``transcripts/`` and markers from ``markers/``.
    Saves each label as JSON to ``clips/{asset_stem}_label.json``.

    Returns the list of all generated ClipLabels.
    """
    workspace_root = Path(workspace_root)
    transcripts_dir = workspace_root / "transcripts"
    markers_dir = workspace_root / "markers"
    clips_dir = ensure_dir(workspace_root / "clips")

    labels: list[ClipLabel] = []

    # Process assets with transcripts
    processed_stems: set[str] = set()

    if transcripts_dir.exists():
        for transcript_path in sorted(transcripts_dir.glob("*_transcript.json")):
            stem = transcript_path.stem.replace("_transcript", "")
            processed_stems.add(stem)

            try:
                transcript = Transcript.from_json(
                    transcript_path.read_text(encoding="utf-8")
                )
            except Exception as exc:
                logger.warning("Failed to parse transcript %s: %s", transcript_path, exc)
                continue

            # Load markers for this asset
            markers: list[dict] = []
            marker_path = markers_dir / f"{stem}_markers.json"
            if marker_path.exists():
                try:
                    markers = json.loads(marker_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    logger.warning("Failed to parse markers %s: %s", marker_path, exc)

            # Determine total duration from transcript segments
            total_duration = 0.0
            if transcript.segments:
                total_duration = max(
                    (seg.end_seconds for seg in transcript.segments),
                    default=0.0,
                )

            speech_density = _calculate_speech_density(transcript, total_duration)
            has_speech = speech_density > 0.0

            content_type = _detect_content_type(markers, speech_density)
            shot_type = _detect_shot_type(markers)
            topics = _extract_topics(transcript.raw_text)
            summary = _clean_summary(transcript.raw_text)

            tags = sorted(
                {t.lower() for t in topics}
                | {content_type.lower(), shot_type.lower()}
            )

            label = ClipLabel(
                clip_ref=stem,
                content_type=content_type,
                topics=topics,
                shot_type=shot_type,
                has_speech=has_speech,
                speech_density=round(speech_density, 4),
                summary=summary,
                tags=tags,
                duration=round(total_duration, 4),
                source_path=str(transcript_path),
            )

            out_path = clips_dir / f"{stem}_label.json"
            out_path.write_text(label.to_json(), encoding="utf-8")
            labels.append(label)
            logger.info("Labeled clip %s → %s", stem, content_type)

    # Process assets without transcripts (check markers/ for any un-processed stems)
    if markers_dir.exists():
        for marker_path in sorted(markers_dir.glob("*_markers.json")):
            stem = marker_path.stem.replace("_markers", "")
            if stem in processed_stems:
                continue
            processed_stems.add(stem)

            filename_tags = _label_from_filename(stem)
            label = ClipLabel(
                clip_ref=stem,
                content_type="unlabeled",
                topics=[],
                shot_type="medium",
                has_speech=False,
                speech_density=0.0,
                summary="",
                tags=sorted(set(filename_tags) | {"unlabeled"}),
                duration=0.0,
                source_path="",
            )
            out_path = clips_dir / f"{stem}_label.json"
            out_path.write_text(label.to_json(), encoding="utf-8")
            labels.append(label)

    return labels
