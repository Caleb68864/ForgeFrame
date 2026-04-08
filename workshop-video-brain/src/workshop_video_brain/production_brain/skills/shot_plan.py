"""Shot plan skill engine.

Produces dual output (markdown string + structured dict) for a production shot list.
Maps tutorial beats to seven shot categories.
"""
from __future__ import annotations


# Shot type constants
TYPE_A_ROLL = "a_roll"
TYPE_OVERHEAD = "overhead"
TYPE_CLOSEUP = "closeup"
TYPE_MEASUREMENT = "measurement"
TYPE_INSERT = "insert"
TYPE_GLAMOUR = "glamour"
TYPE_PICKUP = "pickup"


def generate_shot_plan(
    outline_or_script: dict,
    gear_constraints: str | None = None,
) -> tuple[str, dict]:
    """Generate a production shot plan from an outline or script dict.

    Args:
        outline_or_script: Dict from outline.generate_outline or script.generate_script.
        gear_constraints: Optional string describing gear limitations,
                          e.g. "no overhead rig", "phone only".

    Returns:
        (markdown_string, structured_dict)

    Dict keys: a_roll, overhead, closeups, measurements, inserts, glamour, pickups.
    Each list contains dicts with: id, type, description, beat_ref, priority, notes.
    """
    data = _build_shot_plan_dict(outline_or_script, gear_constraints)
    md = _render_shot_plan_markdown(data, gear_constraints)
    return md, data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_shot_plan_dict(source: dict, gear_constraints: str | None) -> dict:
    """Build the structured shot plan dict."""
    title = source.get("title", "Untitled Project")
    # Support both outline (teaching_beats) and script (steps) dicts
    beats = source.get("teaching_beats") or source.get("steps") or []
    materials = source.get("materials") or source.get("materials_section", {}).get("materials", [])
    tools = source.get("tools") or source.get("materials_section", {}).get("tools", [])

    no_overhead = gear_constraints and "overhead" in gear_constraints.lower()

    a_roll: list[dict] = []
    overhead: list[dict] = []
    closeups: list[dict] = []
    measurements: list[dict] = []
    inserts: list[dict] = []
    glamour: list[dict] = []
    pickups: list[dict] = []

    # General / non-beat shots
    a_roll.append(_shot(
        "A1", TYPE_A_ROLL, "Intro on-camera with finished piece visible",
        "GENERAL", "must-have", "Film last — hold the finished piece"
    ))
    a_roll.append(_shot(
        "A2", TYPE_A_ROLL, "Materials and tools overview on-camera",
        "GENERAL", "must-have", "Bench visible, pieces laid out"
    ))
    a_roll.append(_shot(
        "A3", TYPE_A_ROLL, "Conclusion on-camera with result",
        "GENERAL", "must-have", "Film last"
    ))

    glamour.extend([
        _shot("G1", TYPE_GLAMOUR, "Finished piece — 3/4 view, best light",
              "GENERAL", "must-have", "Film last; try multiple angles"),
        _shot("G2", TYPE_GLAMOUR, "Finished piece — detail surface texture",
              "GENERAL", "should-have", "Macro lens if available"),
        _shot("G3", TYPE_GLAMOUR, "Finished piece — in use or in context",
              "GENERAL", "should-have", "Requires props/staging"),
    ])

    # Per-beat shots
    for i, beat in enumerate(beats):
        num = beat.get("number", i + 1)
        beat_title = beat.get("title", f"Step {num}")
        description = beat.get("description", "")
        beat_ref = f"Step {num}"

        # A-roll for complex explanation beats
        if i == 0 or "assembly" in beat_title.lower() or "finish" in beat_title.lower():
            a_roll.append(_shot(
                f"A{len(a_roll) + 1}", TYPE_A_ROLL,
                f"On-camera explanation: {beat_title}",
                beat_ref, "should-have",
                "Can be filmed after the work is complete"
            ))

        # Overhead for every assembly/layout beat
        if not no_overhead:
            overhead.append(_shot(
                f"O{len(overhead) + 1}", TYPE_OVERHEAD,
                f"Overhead: {beat_title} — full bench view",
                beat_ref, "must-have" if i < 3 else "should-have",
                "Continuous shot if possible"
            ))
        else:
            # Fallback when no overhead rig
            pickups.append(_shot(
                f"P{len(pickups) + 1}", TYPE_PICKUP,
                f"[NO OVERHEAD RIG] High-angle bench: {beat_title}",
                beat_ref, "should-have",
                "Workaround: extend arm or improvise elevated position"
            ))

        # Closeup for all surface/detail work
        closeups.append(_shot(
            f"C{len(closeups) + 1}", TYPE_CLOSEUP,
            f"Detail closeup: result of {beat_title.lower()}",
            beat_ref, "must-have" if i < 4 else "should-have",
            "Macro preferred; check focus before shooting"
        ))

        # Measurement shots for layout/prep beats
        if any(w in beat_title.lower() for w in ["prep", "layout", "select", "dimension", "cut", "measur"]):
            measurements.append(_shot(
                f"M{len(measurements) + 1}", TYPE_MEASUREMENT,
                f"Measurement visible: {beat_title}",
                beat_ref, "must-have",
                "Ensure dimension is legible; add text overlay in post"
            ))

        # Insert shots — standard inserts for finishing beats
        if any(w in beat_title.lower() for w in ["finish", "assembl", "glue", "fasten", "apply"]):
            inserts.append(_shot(
                f"I{len(inserts) + 1}", TYPE_INSERT,
                f"Insert: applying/wiping during {beat_title.lower()}",
                beat_ref, "must-have",
                "2-3 second clip; easy to miss during main shoot"
            ))

    # Standard pickups that are often missed
    pickups.append(_shot(
        f"P{len(pickups) + 1}", TYPE_PICKUP,
        "Close-up of hands during the most technical step",
        "Step 3", "should-have",
        "Hard to get while working — plan a second pass"
    ))
    pickups.append(_shot(
        f"P{len(pickups) + 1}", TYPE_PICKUP,
        "Result immediately after the most satisfying step",
        "GENERAL", "nice-to-have",
        "Reaction/reveal shot"
    ))

    return {
        "title": title,
        "a_roll": a_roll,
        "overhead": overhead,
        "closeups": closeups,
        "measurements": measurements,
        "inserts": inserts,
        "glamour": glamour,
        "pickups": pickups,
    }


def _shot(
    shot_id: str,
    shot_type: str,
    description: str,
    beat_ref: str,
    priority: str,
    notes: str = "",
) -> dict:
    return {
        "id": shot_id,
        "type": shot_type,
        "description": description,
        "beat_ref": beat_ref,
        "priority": priority,
        "notes": notes,
    }


def _render_shot_plan_markdown(data: dict, gear_constraints: str | None) -> str:
    """Render the shot plan dict as a markdown string."""
    lines: list[str] = []
    title = data["title"]

    lines.append(f"# Shot Plan: {title}")
    lines.append("")
    lines.append(f"Gear constraints: {gear_constraints or 'none'}")
    lines.append("")
    lines.append("---")
    lines.append("")

    categories = [
        ("A-Roll (Talking Head)", data["a_roll"]),
        ("Overhead / Bench", data["overhead"]),
        ("Detail Closeups", data["closeups"]),
        ("Measurement / Cutting", data["measurements"]),
        ('"Don\'t Forget" Inserts', data["inserts"]),
        ("Glamour / Result B-Roll", data["glamour"]),
        ("Likely Pickup Shots", data["pickups"]),
    ]

    for section_title, shots in categories:
        lines.append(f"## {section_title}")
        lines.append("")
        if not shots:
            lines.append("*No shots in this category.*")
            lines.append("")
            continue
        # Table header
        lines.append("| # | Beat | Description | Priority | Notes |")
        lines.append("|---|------|-------------|----------|-------|")
        for s in shots:
            desc = s["description"].replace("|", "/")
            notes = s.get("notes", "").replace("|", "/")
            lines.append(
                f"| {s['id']} | {s['beat_ref']} | {desc} "
                f"| {s['priority']} | {notes} |"
            )
        lines.append("")

    # Summary table
    lines.append("## Shot Count Summary")
    lines.append("")
    lines.append("| Category | Must-Have | Should-Have | Nice-to-Have | Total |")
    lines.append("|----------|-----------|-------------|--------------|-------|")

    cat_data = [
        ("A-Roll", data["a_roll"]),
        ("Overhead", data["overhead"]),
        ("Closeup", data["closeups"]),
        ("Measurement", data["measurements"]),
        ("Inserts", data["inserts"]),
        ("Glamour", data["glamour"]),
        ("Pickups", data["pickups"]),
    ]
    totals = [0, 0, 0, 0]
    for cat_name, shots in cat_data:
        must = sum(1 for s in shots if s["priority"] == "must-have")
        should = sum(1 for s in shots if s["priority"] == "should-have")
        nice = sum(1 for s in shots if s["priority"] == "nice-to-have")
        total = len(shots)
        totals[0] += must
        totals[1] += should
        totals[2] += nice
        totals[3] += total
        lines.append(f"| {cat_name} | {must} | {should} | {nice} | {total} |")

    lines.append(
        f"| **Total** | **{totals[0]}** | **{totals[1]}** | **{totals[2]}** "
        f"| **{totals[3]}** |"
    )
    lines.append("")

    return "\n".join(lines)
