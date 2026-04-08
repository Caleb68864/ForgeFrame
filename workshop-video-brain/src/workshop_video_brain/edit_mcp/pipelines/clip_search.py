"""Clip search pipeline: score and rank ClipLabel objects against a query."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from workshop_video_brain.core.models.clips import ClipLabel

logger = logging.getLogger(__name__)


def search_clips(workspace_root: Path, query: str) -> list[dict]:
    """Search clips by content, returning ranked matches.

    Scoring per query word:
    - Exact tag match: 1.0
    - Topic contains query word: 0.8
    - Summary contains query word: 0.5
    - Content_type matches query word: 0.8

    Args:
        workspace_root: Path to workspace root.
        query: Search string. Case-insensitive, split on spaces.

    Returns:
        List of dicts sorted descending by score, each containing
        clip_ref, content_type, topics, summary, score, source_path, duration.
    """
    workspace_root = Path(workspace_root)
    clips_dir = workspace_root / "clips"

    if not clips_dir.exists():
        return []

    # Normalize query words
    query_words = [w.lower() for w in query.split() if w.strip()]
    if not query_words:
        return []

    results: list[dict] = []

    for label_path in sorted(clips_dir.glob("*_label.json")):
        try:
            raw = label_path.read_text(encoding="utf-8")
            label = ClipLabel.from_json(raw)
        except Exception as exc:
            logger.warning("Skipping malformed label file %s: %s", label_path, exc)
            continue

        score = _score_label(label, query_words)
        if score > 0:
            results.append({
                "clip_ref": label.clip_ref,
                "content_type": label.content_type,
                "topics": label.topics,
                "summary": label.summary,
                "score": score,
                "source_path": label.source_path,
                "duration": label.duration,
            })

    # Sort descending by score
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def _score_label(label: ClipLabel, query_words: list[str]) -> float:
    """Score a ClipLabel against a list of query words.

    Query words are normalized to lowercase internally.
    """
    total_score = 0.0

    tags_lower = {t.lower() for t in label.tags}
    topics_lower = [t.lower() for t in label.topics]
    summary_lower = label.summary.lower()
    content_type_lower = label.content_type.lower()

    for word in (w.lower() for w in query_words):
        # Exact tag match: 1.0
        if word in tags_lower:
            total_score += 1.0

        # Topic contains query word: 0.8
        for topic in topics_lower:
            if word in topic:
                total_score += 0.8
                break  # only count once per query word

        # Summary contains query word: 0.5
        if word in summary_lower:
            total_score += 0.5

        # Content_type matches: 0.8
        if word in content_type_lower:
            total_score += 0.8

    return round(total_score, 4)
