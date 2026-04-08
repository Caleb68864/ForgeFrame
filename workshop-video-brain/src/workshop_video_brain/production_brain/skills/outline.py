"""Outline skill engine.

Produces dual output (markdown string + structured dict) for a tutorial outline.
This is a template engine — it structures provided data, not an LLM call.
"""
from __future__ import annotations

import json
import textwrap


def generate_outline(
    idea: str,
    project_type: str | None = None,
    audience: str | None = None,
    constraints: str | None = None,
) -> tuple[str, dict]:
    """Generate a structured tutorial outline from a rough idea.

    Returns:
        (markdown_string, structured_dict)

    The dict keys:
        viewer_promise, what_were_making, materials (list), tools (list),
        teaching_beats (list of dicts), pain_points (list),
        chapter_structure (list of dicts), intro_hook, open_questions (list)
    """
    data = _build_outline_dict(idea, project_type, audience, constraints)
    md = _render_outline_markdown(data)
    return md, data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_outline_dict(
    idea: str,
    project_type: str | None,
    audience: str | None,
    constraints: str | None,
) -> dict:
    """Build the structured outline dictionary."""
    # Derive a working title from the idea (first sentence or truncated)
    title = _derive_title(idea)

    # Audience defaults
    audience_label = audience or "general maker / intermediate skill level"

    # Build the outline structure
    data: dict = {
        "title": title,
        "idea": idea,
        "project_type": project_type or "tutorial",
        "audience": audience_label,
        "constraints": constraints or "",
        "viewer_promise": (
            f"By the end of this video you will be able to complete {title} "
            f"from start to finish."
        ),
        "what_were_making": (
            f"In this project we are making {idea.rstrip('.')}. "
            "The finished result will be a functional, well-crafted piece "
            "built using common shop tools and materials."
        ),
        "materials": [
            "Primary material (species/grade/spec as appropriate)",
            "Secondary material (if applicable)",
            "Fasteners or adhesive",
            "Finish (food-safe, protective, or decorative)",
        ],
        "tools": [
            "Primary shaping tool (saw, router, lathe, etc.)",
            "Measuring and marking tools",
            "Clamping and assembly tools",
            "Finishing tools (sanders, applicators)",
        ],
        "teaching_beats": [
            {"number": 1, "title": "Material selection and preparation",
             "description": "Choose and inspect materials, mark for waste."},
            {"number": 2, "title": "Primary dimensioning",
             "description": "Cut parts to rough size using primary tools."},
            {"number": 3, "title": "Detail work and shaping",
             "description": "Refine surfaces, edges, and profiles."},
            {"number": 4, "title": "Dry fit and assembly check",
             "description": "Test fit all parts before committing to glue/fasteners."},
            {"number": 5, "title": "Final assembly",
             "description": "Glue, fasten, or join parts permanently."},
            {"number": 6, "title": "Surface prep and finishing",
             "description": "Sand through grits, apply chosen finish."},
            {"number": 7, "title": "Final inspection and reveal",
             "description": "Check for issues, photograph, present result."},
        ],
        "pain_points": [
            "Skipping the dry fit — leads to discovering problems after glue is applied.",
            "Inconsistent grain direction between parts — causes tearout during surfacing.",
            "Applying finish over unsanded spots — magnifies defects under the finish.",
            "Rushing clamp time — joint fails under stress later.",
        ],
        "chapter_structure": [
            {"timestamp": "0:00", "title": "Intro — what we're making"},
            {"timestamp": "~0:45", "title": "Materials and tools overview"},
            {"timestamp": "~2:00", "title": "Material prep and layout"},
            {"timestamp": "~5:00", "title": "Primary build steps"},
            {"timestamp": "~10:00", "title": "Assembly"},
            {"timestamp": "~14:00", "title": "Finishing"},
            {"timestamp": "~18:00", "title": "Result and wrap-up"},
        ],
        "intro_hook": (
            f"This is {title} — and here's what it looks like finished. "
            "We're going to build this from scratch today, and I'll walk you "
            "through every step including the parts most tutorials skip. "
            "If you've tried this before and run into trouble, I'll show you "
            "where most people go wrong."
        ),
        "open_questions": [
            "What is the target video length? (affects level of detail per beat)",
            "Are there specific tools or materials to avoid (budget / availability)?",
            "What is the filming environment — dedicated shop or improvised space?",
            "Is this for a beginner audience or can we assume prior experience?",
        ],
    }

    # Add constraints note if provided
    if constraints:
        data["open_questions"].insert(
            0, f"Constraint noted: {constraints} — confirm this is still accurate."
        )

    return data


def _derive_title(idea: str) -> str:
    """Extract a working title from the idea string."""
    # Take up to first 60 chars, end at last complete word
    clean = idea.strip().rstrip(".")
    if len(clean) <= 60:
        return clean
    truncated = clean[:60]
    last_space = truncated.rfind(" ")
    if last_space > 20:
        return truncated[:last_space]
    return truncated


def _render_outline_markdown(data: dict) -> str:
    """Render the outline dict as a markdown string."""
    lines: list[str] = []

    lines.append(f"# {data['title']}")
    lines.append("")

    # Viewer Promise
    lines.append("## Viewer Promise")
    lines.append("")
    lines.append(data["viewer_promise"])
    lines.append("")

    # What We're Making
    lines.append("## What We're Making")
    lines.append("")
    lines.append(data["what_were_making"])
    lines.append("")

    # Why It Matters (derived from project type)
    lines.append("## Why It Matters")
    lines.append("")
    lines.append(f"- Practical skill applicable to many {data['project_type']} projects")
    lines.append("- Results in a finished piece you can use or give as a gift")
    lines.append("- Builds confidence with the core tools and techniques involved")
    lines.append("")

    # Materials & Tools
    lines.append("## Materials & Tools")
    lines.append("")
    lines.append("### Materials")
    for m in data["materials"]:
        lines.append(f"- {m}")
    lines.append("")
    lines.append("### Tools")
    for t in data["tools"]:
        lines.append(f"- {t}")
    lines.append("")

    # Teaching Beats
    lines.append("## Teaching Beats")
    lines.append("")
    for beat in data["teaching_beats"]:
        lines.append(f"{beat['number']}. **{beat['title']}** — {beat['description']}")
    lines.append("")

    # Pain Points
    lines.append("## Pain Points / Gotchas")
    lines.append("")
    for pp in data["pain_points"]:
        lines.append(f"- {pp}")
    lines.append("")

    # Chapter Structure
    lines.append("## Chapter Structure")
    lines.append("")
    for ch in data["chapter_structure"]:
        lines.append(f"- {ch['timestamp']} — {ch['title']}")
    lines.append("")

    # Intro Hook
    lines.append("## Suggested Intro Hook")
    lines.append("")
    lines.append(data["intro_hook"])
    lines.append("")

    # Open Questions
    lines.append("## Open Questions")
    lines.append("")
    for q in data["open_questions"]:
        lines.append(f"- {q}")
    lines.append("")

    # Metadata footer
    if data.get("constraints"):
        lines.append(f"---")
        lines.append(f"*Constraints noted: {data['constraints']}*")
        lines.append(f"*Audience: {data['audience']}*")
        lines.append("")

    return "\n".join(lines)
