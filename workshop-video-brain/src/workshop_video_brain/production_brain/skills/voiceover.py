"""Voiceover fixer skill engine.

Extracts transcript segments flagged for voiceover fixes, formats them for
Claude review, and saves approved rewrites back to the Obsidian vault note.
"""
from __future__ import annotations

import json
from pathlib import Path

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.markers import Marker
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment

# Categories that warrant a voiceover fix
_FIXABLE_CATEGORIES: frozenset[MarkerCategory] = frozenset([
    MarkerCategory.mistake_problem,
    MarkerCategory.repetition,
    MarkerCategory.dead_air,
])

# Minimum confidence to include a marker
_MIN_CONFIDENCE = 0.5

# How many transcript segments to include as context on each side
_CONTEXT_SEGMENTS = 2

# Maximum gap in seconds between markers to be grouped into one fix region
_GROUP_GAP_SECONDS = 5.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_fixable_segments(workspace_root: Path) -> list[dict]:
    """Read transcript and markers from workspace and return fixable segments.

    Filters markers to mistake_problem, repetition, and dead_air with
    confidence > 0.5. For each marker, pulls the matching transcript segment
    text plus 2 segments before and after for context. Groups
    overlapping/adjacent markers (within 5 seconds) into single fix regions.

    Args:
        workspace_root: Path to the workspace root directory.

    Returns:
        List of dicts with keys:
            start (float), end (float), original_text (str),
            context_before (str), context_after (str),
            reason (str), category (str), confidence (float)
    """
    transcripts_dir = workspace_root / "transcripts"
    markers_dir = workspace_root / "markers"

    if not transcripts_dir.exists() and not markers_dir.exists():
        return []

    # Load all transcript segments indexed by time
    all_segments: list[TranscriptSegment] = []
    if transcripts_dir.exists():
        for json_path in sorted(transcripts_dir.glob("*_transcript.json")):
            try:
                transcript = Transcript.from_json(
                    json_path.read_text(encoding="utf-8")
                )
                all_segments.extend(transcript.segments)
            except Exception:
                pass

    # Sort segments by start time for reliable indexing
    all_segments.sort(key=lambda s: s.start_seconds)

    # Load all markers, filter to fixable categories with sufficient confidence
    fixable_markers: list[Marker] = []
    if markers_dir.exists():
        for json_path in sorted(markers_dir.glob("*_markers.json")):
            try:
                raw = json.loads(json_path.read_text(encoding="utf-8"))
                for item in raw:
                    try:
                        marker = Marker(**item)
                        cat = MarkerCategory(marker.category)
                        if (
                            cat in _FIXABLE_CATEGORIES
                            and marker.confidence_score > _MIN_CONFIDENCE
                        ):
                            fixable_markers.append(marker)
                    except Exception:
                        pass
            except Exception:
                pass

    if not fixable_markers:
        return []

    # Sort markers by start time
    fixable_markers.sort(key=lambda m: m.start_seconds)

    # Group adjacent/overlapping markers into regions
    regions = _group_markers(fixable_markers)

    # Build result dicts
    results: list[dict] = []
    for region in regions:
        start = region["start"]
        end = region["end"]
        reason = region["reason"]
        category = region["category"]
        confidence = region["confidence"]

        # Find matching segments and context
        original_text, context_before, context_after = _extract_text_with_context(
            all_segments, start, end
        )

        if not original_text:
            continue

        results.append({
            "start": start,
            "end": end,
            "original_text": original_text,
            "context_before": context_before,
            "context_after": context_after,
            "reason": reason,
            "category": category,
            "confidence": confidence,
        })

    return results


def format_for_review(segments: list[dict]) -> str:
    """Format extracted segments as markdown for Claude to review.

    Each segment shows: timestamp range, reason flagged, original text,
    surrounding context.

    Args:
        segments: List of dicts as returned by extract_fixable_segments.

    Returns:
        Markdown string ready for review.
    """
    if not segments:
        return "No fixable voiceover segments found.\n"

    lines: list[str] = []
    lines.append("# Voiceover Segments Flagged for Review")
    lines.append("")
    lines.append(f"Total segments: {len(segments)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, seg in enumerate(segments, 1):
        start_ts = _seconds_to_timestamp(seg["start"])
        end_ts = _seconds_to_timestamp(seg["end"])
        lines.append(f"## Segment {i}: {start_ts} – {end_ts}")
        lines.append("")
        lines.append(f"**Category:** {seg['category']}")
        lines.append(f"**Confidence:** {seg['confidence']:.2f}")
        lines.append(f"**Reason:** {seg['reason']}")
        lines.append("")

        if seg.get("context_before"):
            lines.append("**Context before:**")
            lines.append(f"> {seg['context_before']}")
            lines.append("")

        lines.append("**Original:**")
        lines.append(f"> {seg['original_text']}")
        lines.append("")

        if seg.get("context_after"):
            lines.append("**Context after:**")
            lines.append(f"> {seg['context_after']}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def save_fixes_to_note(
    workspace_root: Path,
    vault_path: Path,
    fixes_markdown: str,
) -> Path:
    """Append fixes to the Obsidian video note under voiceover-fixes section.

    Uses the existing NoteUpdater. Creates a note from template if it does
    not exist.

    Args:
        workspace_root: Path to the workspace root directory.
        vault_path: Path to the Obsidian vault root.
        fixes_markdown: Markdown string of approved voiceover fixes.

    Returns:
        Path to the updated note.
    """
    from workshop_video_brain.production_brain.notes.updater import update_section

    # Determine note path from workspace slug / title
    note_path = _resolve_note_path(workspace_root, vault_path)

    # Ensure the note exists
    if not note_path.exists():
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(
            _default_note_content(workspace_root),
            encoding="utf-8",
        )

    update_section(note_path, "voiceover-fixes", fixes_markdown)
    return note_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _group_markers(markers: list[Marker]) -> list[dict]:
    """Group markers that are adjacent or overlapping within _GROUP_GAP_SECONDS.

    Returns list of region dicts:
        start, end, reason, category, confidence
    """
    if not markers:
        return []

    regions: list[dict] = []
    current_start = markers[0].start_seconds
    current_end = markers[0].end_seconds
    current_conf = markers[0].confidence_score
    current_reason = markers[0].reason
    current_cat = str(markers[0].category)

    for marker in markers[1:]:
        if marker.start_seconds - current_end <= _GROUP_GAP_SECONDS:
            # Extend region
            current_end = max(current_end, marker.end_seconds)
            if marker.confidence_score > current_conf:
                current_conf = marker.confidence_score
                current_reason = marker.reason
                current_cat = str(marker.category)
        else:
            regions.append({
                "start": current_start,
                "end": current_end,
                "reason": current_reason,
                "category": current_cat,
                "confidence": current_conf,
            })
            current_start = marker.start_seconds
            current_end = marker.end_seconds
            current_conf = marker.confidence_score
            current_reason = marker.reason
            current_cat = str(marker.category)

    regions.append({
        "start": current_start,
        "end": current_end,
        "reason": current_reason,
        "category": current_cat,
        "confidence": current_conf,
    })

    return regions


def _extract_text_with_context(
    segments: list[TranscriptSegment],
    start: float,
    end: float,
) -> tuple[str, str, str]:
    """Extract original text for a time range plus context segments.

    Args:
        segments: All transcript segments, sorted by start_seconds.
        start: Region start in seconds.
        end: Region end in seconds.

    Returns:
        (original_text, context_before, context_after)
    """
    # Find segments that overlap the region
    matching_indices: list[int] = []
    for i, seg in enumerate(segments):
        if seg.end_seconds > start and seg.start_seconds < end:
            matching_indices.append(i)

    if not matching_indices:
        return "", "", ""

    first_idx = matching_indices[0]
    last_idx = matching_indices[-1]

    # Collect original text
    original_parts = [segments[i].text.strip() for i in matching_indices]
    original_text = " ".join(p for p in original_parts if p)

    # Context before: up to _CONTEXT_SEGMENTS before the first matching segment
    before_start = max(0, first_idx - _CONTEXT_SEGMENTS)
    before_parts = [
        segments[i].text.strip()
        for i in range(before_start, first_idx)
        if segments[i].text.strip()
    ]
    context_before = " ".join(before_parts)

    # Context after: up to _CONTEXT_SEGMENTS after the last matching segment
    after_end = min(len(segments), last_idx + 1 + _CONTEXT_SEGMENTS)
    after_parts = [
        segments[i].text.strip()
        for i in range(last_idx + 1, after_end)
        if segments[i].text.strip()
    ]
    context_after = " ".join(after_parts)

    return original_text, context_before, context_after


def _seconds_to_timestamp(seconds: float) -> str:
    """Convert float seconds to MM:SS string."""
    total = int(seconds)
    mins = total // 60
    secs = total % 60
    return f"{mins}:{secs:02d}"


def _resolve_note_path(workspace_root: Path, vault_path: Path) -> Path:
    """Determine the Obsidian note path for this workspace."""
    # Try to read slug from workspace manifest
    try:
        from workshop_video_brain.workspace.manifest import read_manifest
        manifest = read_manifest(workspace_root)
        slug = manifest.slug or manifest.project_title.lower().replace(" ", "-")
    except Exception:
        slug = workspace_root.name

    return vault_path / "videos" / f"{slug}.md"


def _default_note_content(workspace_root: Path) -> str:
    """Generate minimal note content when no note exists yet."""
    title = workspace_root.name
    return (
        f"---\ntitle: {title}\nstatus: editing\n---\n\n"
        f"# {title}\n\n"
        f"Workspace: `{workspace_root}`\n"
    )
