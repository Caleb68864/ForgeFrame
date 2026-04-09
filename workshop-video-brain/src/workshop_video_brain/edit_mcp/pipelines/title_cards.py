"""Title card generator pipeline."""
from __future__ import annotations

import json
import re
from pathlib import Path

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.kdenlive import Guide, KdenliveProject
from workshop_video_brain.core.models.markers import Marker
from workshop_video_brain.core.models.title_cards import TitleCard


# ---------------------------------------------------------------------------
# Label cleaning helpers
# ---------------------------------------------------------------------------

_CHAPTER_CANDIDATE_PREFIX = re.compile(
    r"^chapter_candidate\s*:\s*", re.IGNORECASE
)
_CONFIDENCE_PATTERN = re.compile(
    r"\[confidence[:\s]*[\d.]+\]", re.IGNORECASE
)
_BRACKETS_PATTERN = re.compile(r"\[[^\]]*\]")


def _clean_label(label: str) -> str:
    """Remove chapter_candidate prefix, confidence scores, and brackets from a label."""
    text = label.strip()
    text = _CHAPTER_CANDIDATE_PREFIX.sub("", text)
    text = _CONFIDENCE_PATTERN.sub("", text)
    text = _BRACKETS_PATTERN.sub("", text)
    return text.strip()


def _clean_subtitle(reason: str, max_chars: int = 50) -> str:
    """Extract a short subtitle from a marker reason field."""
    text = _CONFIDENCE_PATTERN.sub("", reason)
    text = _BRACKETS_PATTERN.sub("", text)
    text = text.strip()
    return text[:max_chars]


# ---------------------------------------------------------------------------
# Core pipeline functions
# ---------------------------------------------------------------------------


def generate_title_cards(workspace_root: Path) -> list[TitleCard]:
    """Generate TitleCard objects from chapter_candidate markers in the workspace.

    Reads all *_markers.json files in the markers/ directory and extracts
    markers with category ``chapter_candidate``.  An "Intro" card is inserted
    at timestamp 0.0 unless a chapter marker already exists at that point.
    The returned list is sorted by timestamp.

    Args:
        workspace_root: Path to the workspace root directory.

    Returns:
        Sorted list of TitleCard objects.
    """
    markers_dir = workspace_root / "markers"
    chapter_markers: list[Marker] = []

    if markers_dir.exists():
        for marker_file in sorted(markers_dir.glob("*.json")):
            try:
                raw = json.loads(marker_file.read_text(encoding="utf-8"))
                for item in raw:
                    try:
                        marker = Marker(**item)
                        if MarkerCategory(marker.category) == MarkerCategory.chapter_candidate:
                            chapter_markers.append(marker)
                    except Exception:
                        pass
            except Exception:
                pass

    cards: list[TitleCard] = []
    for marker in chapter_markers:
        raw_label = marker.suggested_label or marker.reason or ""
        chapter_title = _clean_label(raw_label) if raw_label else "Chapter"
        subtitle = _clean_subtitle(marker.reason) if marker.reason else ""
        cards.append(
            TitleCard(
                chapter_title=chapter_title,
                timestamp_seconds=marker.start_seconds,
                subtitle=subtitle,
            )
        )

    # Insert "Intro" card at 0.0 if none exists there
    has_zero = any(c.timestamp_seconds == 0.0 for c in cards)
    if not has_zero:
        cards.insert(0, TitleCard(chapter_title="Intro", timestamp_seconds=0.0))

    # Sort by timestamp
    cards.sort(key=lambda c: c.timestamp_seconds)
    return cards


def title_cards_to_json(cards: list[TitleCard]) -> str:
    """Serialise a list of TitleCard objects to a JSON array string.

    Args:
        cards: List of TitleCard objects to serialise.

    Returns:
        A JSON-encoded string representing the array.
    """
    payload = [json.loads(card.to_json()) for card in cards]
    return json.dumps(payload, indent=2)


def apply_title_cards_to_project(
    project: KdenliveProject,
    cards: list[TitleCard],
) -> KdenliveProject:
    """Add title card guides to a KdenliveProject.

    For each TitleCard a Guide is added at the appropriate frame position with
    the label ``TITLE: <chapter_title>``.  The original project is not mutated;
    a new KdenliveProject instance is returned.

    Args:
        project: The source KdenliveProject.
        cards: List of TitleCard objects to apply.

    Returns:
        A new KdenliveProject with the title card guides appended.
    """
    fps = project.profile.fps if project.profile.fps else 25.0
    new_guides = list(project.guides)
    for card in cards:
        position = int(card.timestamp_seconds * fps)
        new_guides.append(
            Guide(
                position=position,
                label=f"TITLE: {card.chapter_title}",
            )
        )
    # Build a new instance with updated guides (don't mutate original)
    data = project.model_dump()
    data["guides"] = [g.model_dump() for g in new_guides]
    return KdenliveProject.model_validate(data)


def save_title_cards(cards: list[TitleCard], workspace_root: Path) -> Path:
    """Save title cards to ``reports/title_cards.json`` inside the workspace.

    Args:
        cards: List of TitleCard objects to save.
        workspace_root: Path to the workspace root directory.

    Returns:
        Path to the written JSON file.
    """
    reports_dir = workspace_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "title_cards.json"
    out_path.write_text(title_cards_to_json(cards), encoding="utf-8")
    return out_path
