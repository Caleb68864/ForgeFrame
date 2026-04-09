"""B-Roll suggestions pipeline.

Scans transcript segments for visual description patterns and categorises each
hit into one of five B-roll categories, returning actionable shot suggestions
with timestamps, descriptions, and confidence scores.
"""
from __future__ import annotations

import re
from collections import defaultdict

from workshop_video_brain.core.models.transcript import Transcript

# ---------------------------------------------------------------------------
# Category labels (human-readable)
# ---------------------------------------------------------------------------

_CATEGORY_LABELS: dict[str, str] = {
    "process_shot": "Process Shot",
    "material_closeup": "Material Close-up",
    "tool_in_use": "Tool in Use",
    "result_reveal": "Result Reveal",
    "measurement_shot": "Measurement Shot",
}

# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

# process_shot: action verbs for making/assembly
_PROCESS_KEYWORDS: list[str] = [
    "sew", "cut", "glue", "fold", "attach", "install",
    "stitch", "press", "iron", "mark",
]

# material_closeup: specific materials + generic terms
_MATERIAL_KEYWORDS: list[str] = [
    "fabric", "thread", "zipper", "velcro", "webbing",
    "cordura", "x-pac", "dyneema", "material", "fabric",
]

# tool_in_use: tools mentioned by name
_TOOL_KEYWORDS: list[str] = [
    "machine", "scissors", "rotary cutter", "ruler",
    "awl", "needle", "iron", "lighter",
]

# result_reveal: phrases that flag the finished product
_RESULT_PHRASES: list[str] = [
    "here's what it looks like",
    "finished",
    "done",
    "final",
    "result",
    "turned out",
    "complete",
]

# measurement_shot: numbers with units or measurement verbs
_MEASUREMENT_UNIT_RE = re.compile(
    r"\b\d+(\.\d+)?\s*(inch(es)?|cm|mm|yard(s)?|\")\b",
    re.IGNORECASE,
)
_MEASUREMENT_KEYWORDS: list[str] = ["measure", "mark", "cut to"]


def _match_strength(text_lower: str, keyword: str) -> float:
    """Return confidence modifier for a keyword match.

    Exact phrase → 1.0; all individual words present but not as phrase → 0.7.
    """
    if keyword in text_lower:
        return 1.0
    words = keyword.split()
    if len(words) > 1 and all(w in text_lower for w in words):
        return 0.7
    return 0.0


def _detect_category(text: str) -> list[tuple[str, float]]:
    """Return (category, confidence) pairs for all categories that match *text*.

    Categories are tested independently so a single segment can produce
    multiple suggestions.
    """
    text_lower = text.lower()
    hits: list[tuple[str, float]] = []

    # --- process_shot ---
    for kw in _PROCESS_KEYWORDS:
        # Use word-boundary regex to avoid partial matches
        pattern = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
        if pattern.search(text):
            hits.append(("process_shot", 0.8))
            break

    # --- material_closeup ---
    for kw in _MATERIAL_KEYWORDS:
        strength = _match_strength(text_lower, kw)
        if strength > 0:
            hits.append(("material_closeup", round(0.75 * strength, 4)))
            break

    # --- tool_in_use ---
    for kw in _TOOL_KEYWORDS:
        strength = _match_strength(text_lower, kw)
        if strength > 0:
            hits.append(("tool_in_use", round(0.85 * strength, 4)))
            break

    # --- result_reveal ---
    for phrase in _RESULT_PHRASES:
        strength = _match_strength(text_lower, phrase)
        if strength > 0:
            hits.append(("result_reveal", round(0.9 * strength, 4)))
            break

    # --- measurement_shot ---
    if _MEASUREMENT_UNIT_RE.search(text):
        hits.append(("measurement_shot", 0.85))
    else:
        for kw in _MEASUREMENT_KEYWORDS:
            strength = _match_strength(text_lower, kw)
            if strength > 0:
                hits.append(("measurement_shot", round(0.75 * strength, 4)))
                break

    return hits


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_broll_opportunities(transcript: Transcript) -> list[dict]:
    """Scan transcript segments for B-roll opportunities.

    Each segment is tested for visual description patterns. Matching segments
    produce one suggestion dict per matched category.

    Args:
        transcript: A :class:`~workshop_video_brain.core.models.transcript.Transcript`
            containing one or more :class:`TranscriptSegment` objects.

    Returns:
        List of suggestion dicts with keys:
            timestamp (float), end_timestamp (float), category (str),
            description (str), context (str), confidence (float).
    """
    suggestions: list[dict] = []

    for seg in transcript.segments:
        text = seg.text.strip()
        if not text:
            continue

        category_hits = _detect_category(text)
        for category, confidence in category_hits:
            label = _CATEGORY_LABELS[category]
            # Truncate context text for readability
            context_preview = text if len(text) <= 120 else text[:117] + "..."
            suggestions.append({
                "timestamp": seg.start_seconds,
                "end_timestamp": seg.end_seconds,
                "category": category,
                "description": f"Show {label}: {text}",
                "context": context_preview,
                "confidence": confidence,
            })

    return suggestions


def format_broll_suggestions(suggestions: list[dict]) -> str:
    """Format B-roll suggestions as a grouped Markdown document.

    Suggestions are grouped by category, with timestamps and descriptions
    listed under each heading.

    Args:
        suggestions: List of suggestion dicts as returned by
            :func:`detect_broll_opportunities`.

    Returns:
        Markdown-formatted string.
    """
    if not suggestions:
        return "# B-Roll Suggestions\n\nNo B-roll opportunities detected in the transcript.\n"

    lines: list[str] = []
    lines.append("# B-Roll Suggestions")
    lines.append("")
    lines.append(f"Total suggestions: {len(suggestions)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Group by category preserving insertion order of first occurrence
    by_category: dict[str, list[dict]] = defaultdict(list)
    for s in suggestions:
        by_category[s["category"]].append(s)

    for category, items in by_category.items():
        label = _CATEGORY_LABELS.get(category, category)
        lines.append(f"## {label}")
        lines.append("")
        for item in sorted(items, key=lambda x: x["timestamp"]):
            start = item["timestamp"]
            end = item["end_timestamp"]
            mins_s = int(start) // 60
            secs_s = int(start) % 60
            mins_e = int(end) // 60
            secs_e = int(end) % 60
            ts = f"{mins_s}:{secs_s:02d} – {mins_e}:{secs_e:02d}"
            confidence = item["confidence"]
            lines.append(f"- **[{ts}]** (confidence: {confidence:.2f})")
            lines.append(f"  {item['description']}")
            lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)
