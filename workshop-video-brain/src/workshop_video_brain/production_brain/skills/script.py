"""Script skill engine.

Produces dual output (markdown string + structured dict) for a tutorial script.
Takes an outline dict and formats it into a production-ready script structure.
"""
from __future__ import annotations


def generate_script(
    outline_data: dict,
    tone: str = "practical",
    target_length: str | None = None,
) -> tuple[str, dict]:
    """Generate a tutorial script from an outline dict.

    Args:
        outline_data: Dict produced by outline.generate_outline or compatible.
        tone: Voice tone — "practical", "educational", "casual". Default: practical.
        target_length: Approximate target length, e.g. "10min", "5min". Optional.

    Returns:
        (markdown_string, structured_dict)

    Dict keys: hook, overview, materials_section, steps (list), common_mistakes (list),
               conclusion.
    """
    data = _build_script_dict(outline_data, tone, target_length)
    md = _render_script_markdown(data)
    return md, data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_script_dict(
    outline_data: dict,
    tone: str,
    target_length: str | None,
) -> dict:
    """Build the structured script dictionary from outline data."""
    title = outline_data.get("title", "Untitled Project")
    viewer_promise = outline_data.get("viewer_promise", "")
    what_were_making = outline_data.get("what_were_making", "")
    materials = outline_data.get("materials", [])
    tools = outline_data.get("tools", [])
    teaching_beats = outline_data.get("teaching_beats", [])
    pain_points = outline_data.get("pain_points", [])
    intro_hook_text = outline_data.get("intro_hook", "")
    audience = outline_data.get("audience", "")

    # Build the hook section
    hook = intro_hook_text or (
        f"This is {title}. Let's build it from scratch. "
        f"{viewer_promise} "
        "I'll cover every step, including the parts most tutorials rush past."
    )

    # Build the overview
    overview = (
        f"{what_were_making} "
        + (f"This is suitable for {audience}. " if audience else "")
        + "We'll work through it step by step — no steps skipped."
    )

    # Build materials section
    materials_section = {
        "materials": list(materials),
        "tools": list(tools),
    }

    # Convert teaching beats to script steps
    steps = []
    for beat in teaching_beats:
        num = beat.get("number", 0)
        beat_title = beat.get("title", f"Step {num}")
        description = beat.get("description", "")

        # Find relevant pain point for this beat (first unmatched one)
        common_mistake = "None notable for this step."
        if pain_points:
            # Use pain points in order, cycling if needed
            idx = (num - 1) % len(pain_points)
            common_mistake = pain_points[idx]

        steps.append({
            "number": num,
            "title": beat_title,
            "direction": f"ON CAMERA — bench or workspace, demonstrating {beat_title.lower()}",
            "script_text": (
                f"Now we're working on {beat_title.lower()}. "
                f"{description} "
                "Take your time here — this step sets up everything that follows."
            ),
            "key_points": [
                f"What matters most: {description}",
                "Check your work before moving on.",
            ],
            "common_mistake": common_mistake,
        })

    # Collect all pain points as common mistakes list
    common_mistakes = list(pain_points)

    # Build conclusion
    conclusion = (
        f"And that's {title} — finished and ready to use. "
        "The key things we covered today: material prep, the assembly sequence, "
        "and the finishing process. "
        + (_target_length_note(target_length))
        + "If you have questions about any step, leave them below. "
        "Take your time with this one — the result is worth it."
    )

    return {
        "title": title,
        "tone": tone,
        "target_length": target_length or "unspecified",
        "hook": hook,
        "overview": overview,
        "materials_section": materials_section,
        "steps": steps,
        "common_mistakes": common_mistakes,
        "conclusion": conclusion,
    }


def _target_length_note(target_length: str | None) -> str:
    if not target_length:
        return ""
    return f"The full process runs about {target_length}. "


def _render_script_markdown(data: dict) -> str:
    """Render the script dict as a markdown string."""
    lines: list[str] = []
    title = data["title"]

    lines.append(f"# Script: {title}")
    lines.append("")
    lines.append(f"*Tone: {data['tone']} | Target length: {data['target_length']}*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Hook
    lines.append("## HOOK (0:00-0:30)")
    lines.append("")
    lines.append("[ON CAMERA — workshop, showing finished piece]")
    lines.append("")
    lines.append(data["hook"])
    lines.append("")
    lines.append("---")
    lines.append("")

    # Overview
    lines.append("## PROJECT OVERVIEW (0:30-1:30)")
    lines.append("")
    lines.append("[ON CAMERA — bench with materials laid out]")
    lines.append("")
    lines.append(data["overview"])
    lines.append("")
    lines.append("---")
    lines.append("")

    # Materials & Tools
    lines.append("## MATERIALS & TOOLS (1:30-2:30)")
    lines.append("")
    lines.append("[ON CAMERA — overhead materials shot]")
    lines.append("")
    lines.append("**Materials:**")
    for m in data["materials_section"]["materials"]:
        lines.append(f"- {m}")
    lines.append("")
    lines.append("**Tools:**")
    for t in data["materials_section"]["tools"]:
        lines.append(f"- {t}")
    lines.append("")
    lines.append("Let's get started.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Steps
    for step in data["steps"]:
        num = step["number"]
        step_title = step["title"]
        lines.append(f"## STEP {num}: {step_title.upper()}")
        lines.append("")
        lines.append(f"[{step['direction']}]")
        lines.append("")
        lines.append("**What to do:**")
        lines.append(step["script_text"])
        lines.append("")
        lines.append("**What to say (key points):**")
        for kp in step["key_points"]:
            lines.append(f"- {kp}")
        lines.append("")
        lines.append("**Common mistake:**")
        lines.append(step["common_mistake"])
        lines.append("")
        lines.append("---")
        lines.append("")

    # Safety warnings placeholder
    lines.append("## SAFETY WARNINGS")
    lines.append("")
    lines.append(
        "*Review steps above for any safety-critical notes. "
        "Add project-specific warnings here.*"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Conclusion
    lines.append("## CONCLUSION")
    lines.append("")
    lines.append("[ON CAMERA — finished piece, ideally in use]")
    lines.append("")
    lines.append(data["conclusion"])
    lines.append("")
    lines.append("---")
    lines.append("")

    # Voiceover notes
    lines.append("## VOICEOVER NOTES")
    lines.append("")
    lines.append(f"- Pacing: {_pacing_for_tone(data['tone'])} overall")
    lines.append("- Ambient sound welcome during hands-on steps")
    lines.append("- Slow down for any measurement or safety callout")
    lines.append("- Safety warnings: deliver clearly and directly, no rushing")
    lines.append("")

    return "\n".join(lines)


def _pacing_for_tone(tone: str) -> str:
    mapping = {
        "practical": "medium — clear and purposeful, no rushing",
        "educational": "measured — pause after key concepts",
        "casual": "relaxed — conversational, natural pauses",
    }
    return mapping.get(tone, "medium")
