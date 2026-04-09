"""MYOG Pattern Brain pipeline.

Extracts build data (materials, measurements, steps, tips/warnings) from
a workshop transcript and produces overlay text and printable build notes.
"""
from __future__ import annotations

import re

from workshop_video_brain.core.models.transcript import Transcript
from workshop_video_brain.core.models.patterns import (
    BuildData,
    BuildStep,
    BuildTip,
    MaterialItem,
    Measurement,
)

# ---------------------------------------------------------------------------
# Material detection
# ---------------------------------------------------------------------------

# Common MYOG fabric/hardware terms
_MATERIAL_NAMES: list[str] = [
    "x-pac", "xpac", "x pac",
    "dyneema", "cuben fiber",
    "cordura",
    "ripstop",
    "nylon",
    "polyester",
    "thread",
    "zipper",
    "webbing",
    "velcro",
    "grosgrain",
    "elastic",
    "buckle",
    "snap",
    "grommet",
    "fabric",
    "liner",
    "mesh",
    "foam",
    "batting",
    "interfacing",
]

# Quantity prefix patterns (order matters; longer patterns first)
_QUANTITY_PATTERNS: list[str] = [
    r"\d+\s*(?:yards?|yd)\s+(?:of\s+)?",
    r"\d+\s*(?:meters?|m)\s+(?:of\s+)?",
    r"\d+\s*(?:inches?|in)\s+(?:of\s+)?",
    r"\d+\s*(?:feet|ft)\s+(?:of\s+)?",
    r"\d+\s*(?:pieces?|pcs?)\s+(?:of\s+)?",
    r"\d+(?:\.\d+)?\s+",
    r"(?:a\s+piece\s+of\s+|a\s+length\s+of\s+|some\s+|a\s+bit\s+of\s+)",
]

_QUANTITY_RE = re.compile(
    r"(?:" + "|".join(_QUANTITY_PATTERNS) + r")",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Measurement detection
# ---------------------------------------------------------------------------

_MEASUREMENT_RE = re.compile(
    r"(\d+\.?\d*)\s*(inches?|in\b|cm\b|mm\b|millimeters?|centimeters?|yards?|yd\b|feet|ft\b|[\"'])",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Step transition detection
# ---------------------------------------------------------------------------

_STEP_TRANSITION_RE = re.compile(
    r"^\s*(?:first(?:\s+off)?|next(?:\s+up)?|then|now|step\s+\d+|after\s+that)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Tips and warnings detection
# ---------------------------------------------------------------------------

_TIP_PHRASES: list[str] = [
    "pro tip", "here's a tip", "quick tip", "tip:", "tip,",
    " tip ", " tip.", "trick:",
]

_WARNING_PHRASES: list[str] = [
    "careful", "don't ", "dont ", "watch out", "be sure", "important", "safety",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_quantity(text_lower: str, material_start: int) -> str:
    """Look backwards from material_start for a quantity prefix."""
    preceding = text_lower[max(0, material_start - 40):material_start]
    m = _QUANTITY_RE.search(preceding)
    if m and m.end() >= len(preceding) - 2:
        # quantity immediately precedes material
        return m.group(0).strip()
    return ""


def _normalize_unit(unit_str: str) -> str:
    """Normalize a unit abbreviation to a canonical form."""
    mapping: dict[str, str] = {
        '"': "inches",
        "'": "feet",
        "in": "inches",
        "inch": "inches",
        "cm": "cm",
        "centimeter": "cm",
        "centimeters": "cm",
        "mm": "mm",
        "millimeter": "mm",
        "millimeters": "mm",
        "ft": "feet",
        "yd": "yards",
        "yard": "yards",
        "yards": "yards",
    }
    key = unit_str.lower().rstrip("s")
    # Try plural strip, then direct lookup
    for k, v in mapping.items():
        if unit_str.lower().startswith(k):
            return v
    return unit_str.lower()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_build_data(transcript: Transcript, project_title: str = "") -> BuildData:
    """Extract build data (materials, measurements, steps, tips, warnings) from a transcript.

    Args:
        transcript: A Transcript with one or more TranscriptSegment objects.
        project_title: Optional project title to embed in the returned BuildData.

    Returns:
        A BuildData instance populated with extracted items.
    """
    materials: list[MaterialItem] = []
    measurements: list[Measurement] = []
    steps: list[BuildStep] = []
    tips: list[BuildTip] = []

    seen_materials: set[str] = set()
    step_counter = 0

    for seg in transcript.segments:
        text = seg.text.strip()
        if not text:
            continue
        text_lower = text.lower()
        ts = seg.start_seconds

        # --- Materials ---
        for mat_name in _MATERIAL_NAMES:
            idx = text_lower.find(mat_name)
            if idx == -1:
                continue
            quantity = _extract_quantity(text_lower, idx)
            # De-duplicate by (material name, quantity) so same mat in many segments
            key = f"{mat_name}|{quantity}"
            if key not in seen_materials:
                seen_materials.add(key)
                materials.append(MaterialItem(
                    name=mat_name,
                    quantity=quantity,
                    notes="",
                    timestamp=ts,
                ))

        # --- Measurements ---
        for m in _MEASUREMENT_RE.finditer(text):
            value = m.group(1)
            unit = _normalize_unit(m.group(2))
            measurements.append(Measurement(
                value=value,
                unit=unit,
                context=text,
                timestamp=ts,
            ))

        # --- Steps ---
        if _STEP_TRANSITION_RE.match(text):
            step_counter += 1
            steps.append(BuildStep(
                number=step_counter,
                description=text,
                timestamp=ts,
            ))

        # --- Tips ---
        text_lower_check = " " + text_lower + " "
        is_tip = any(phrase in text_lower_check for phrase in _TIP_PHRASES)
        is_warning = any(phrase in text_lower_check for phrase in _WARNING_PHRASES)

        if is_tip and not is_warning:
            tips.append(BuildTip(text=text, tip_type="tip", timestamp=ts))
        elif is_warning:
            tips.append(BuildTip(text=text, tip_type="warning", timestamp=ts))

    return BuildData(
        project_title=project_title,
        materials=materials,
        measurements=measurements,
        steps=steps,
        tips=tips,
    )


def generate_overlay_text(build_data: BuildData) -> list[dict]:
    """Generate overlay text entries from extracted build data.

    Each entry has keys: text, timestamp, duration_seconds (default 4), type.

    Args:
        build_data: A BuildData instance (typically from extract_build_data).

    Returns:
        List of overlay text dicts.
    """
    overlays: list[dict] = []

    # Materials overlay: one combined entry per distinct timestamp cluster
    if build_data.materials:
        mat_names = [m.name for m in build_data.materials]
        # Combine all into a single materials overlay at first timestamp
        first_ts = build_data.materials[0].timestamp
        overlays.append({
            "text": f"Materials: {', '.join(mat_names)}",
            "timestamp": first_ts,
            "duration_seconds": 4,
            "type": "materials",
        })

    # Measurement overlays
    for meas in build_data.measurements:
        overlays.append({
            "text": f"{meas.context}: {meas.value} {meas.unit}",
            "timestamp": meas.timestamp,
            "duration_seconds": 4,
            "type": "measurement",
        })

    # Step overlays
    for step in build_data.steps:
        # Truncate description to 60 chars for overlay
        short_desc = step.description if len(step.description) <= 60 else step.description[:57] + "..."
        overlays.append({
            "text": f"Step {step.number}: {short_desc}",
            "timestamp": step.timestamp,
            "duration_seconds": 4,
            "type": "step",
        })

    return overlays


def generate_build_notes(build_data: BuildData) -> str:
    """Generate a printable Markdown document from extracted build data.

    Args:
        build_data: A BuildData instance.

    Returns:
        A Markdown string ready to print or paste into a blog post.
    """
    lines: list[str] = []

    title = build_data.project_title or "Build Notes"
    lines.append(f"# {title}")
    lines.append("")

    # Materials table
    lines.append("## Materials")
    lines.append("")
    if build_data.materials:
        lines.append("| Material | Quantity | Notes |")
        lines.append("|----------|----------|-------|")
        for mat in build_data.materials:
            lines.append(f"| {mat.name} | {mat.quantity} | {mat.notes} |")
    else:
        lines.append("_No materials extracted._")
    lines.append("")

    # Measurements list
    lines.append("## Measurements")
    lines.append("")
    if build_data.measurements:
        for meas in build_data.measurements:
            lines.append(f"- **{meas.value} {meas.unit}** — {meas.context}")
    else:
        lines.append("_No measurements extracted._")
    lines.append("")

    # Numbered steps
    lines.append("## Build Steps")
    lines.append("")
    if build_data.steps:
        for step in build_data.steps:
            lines.append(f"{step.number}. {step.description}")
    else:
        lines.append("_No build steps extracted._")
    lines.append("")

    # Tips and warnings
    tips = [t for t in build_data.tips if t.tip_type == "tip"]
    warnings = [t for t in build_data.tips if t.tip_type == "warning"]

    if tips or warnings:
        lines.append("## Tips & Warnings")
        lines.append("")
        for tip in tips:
            lines.append(f"> **Tip:** {tip.text}")
            lines.append("")
        for warning in warnings:
            lines.append(f"> **Warning:** {warning.text}")
            lines.append("")

    return "\n".join(lines)
