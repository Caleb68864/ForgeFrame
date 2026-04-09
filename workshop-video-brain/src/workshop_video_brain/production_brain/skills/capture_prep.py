"""Capture prep checklist generator.

Pure function that takes a shot plan dict and returns a markdown checklist
with camera settings, audio setup, lighting notes, sync strategy, and
optimized shot order.
"""
from __future__ import annotations

from collections import defaultdict


def generate_capture_checklist(
    shot_plan: dict,
    target_resolution: str = "1920x1080",
    target_fps: int = 30,
) -> str:
    """Generate a pre-shoot capture checklist from a shot plan.

    Args:
        shot_plan: Structured dict from shot_plan.generate_shot_plan() or
                   loaded from reports/shot_plan.json.  Keys: title, a_roll,
                   overhead, closeups, measurements, inserts, glamour, pickups.
        target_resolution: Camera resolution string, e.g. "1920x1080".
        target_fps: Target frame rate, e.g. 30.

    Returns:
        Markdown string with sections: Camera Settings, Audio Setup,
        Lighting Notes, Sync Strategy, Shot Order.
    """
    title = shot_plan.get("title", "Untitled Project")
    lines: list[str] = []

    lines.append(f"# Capture Prep Checklist: {title}")
    lines.append("")

    # ---- Camera Settings ----
    lines.append("## Camera Settings")
    lines.append("")
    lines.append(f"- **Resolution:** {target_resolution}")
    lines.append(f"- **Frame rate:** {target_fps} fps")
    lines.append("- **Color profile:** BT.709 (Rec. 709) for SDR delivery")
    lines.append("- **White balance:** Set manually to match lighting (avoid auto)")
    lines.append("- **Shutter speed:** 1/{0} for natural motion blur".format(
        target_fps * 2,
    ))
    lines.append("- **Format:** Record in the highest quality your card supports")
    lines.append("")

    # ---- Audio Setup ----
    has_a_roll = bool(shot_plan.get("a_roll"))
    has_workshop = bool(
        shot_plan.get("overhead")
        or shot_plan.get("closeups")
        or shot_plan.get("measurements")
    )

    lines.append("## Audio Setup")
    lines.append("")
    if has_a_roll:
        lines.append(
            "- **Talking head (A-roll):** Lapel / lav mic or USB condenser mic, "
            "gain set so peaks hit -12 dB"
        )
    if has_workshop:
        lines.append(
            "- **Workshop / bench shots:** Shotgun or boom mic aimed at work area, "
            "gain set so ambient peaks hit -18 dB"
        )
    lines.append("- **Monitoring:** Wear headphones during recording to catch issues early")
    lines.append("- **Room tone:** Record 10 seconds of silence in the space for post")
    if not has_a_roll and not has_workshop:
        lines.append("- *No shots in plan -- record room tone and test levels before shooting*")
    lines.append("")

    # ---- Lighting Notes ----
    lines.append("## Lighting Notes")
    lines.append("")
    _lighting_for_types(lines, shot_plan)
    lines.append("")

    # ---- Sync Strategy ----
    lines.append("## Sync Strategy")
    lines.append("")
    _sync_strategy(lines, shot_plan)
    lines.append("")

    # ---- Shot Order (optimized for setup changes) ----
    lines.append("## Shot Order")
    lines.append("")
    _optimized_shot_order(lines, shot_plan)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _lighting_for_types(lines: list[str], shot_plan: dict) -> None:
    """Add per-shot-type lighting guidance."""
    if shot_plan.get("a_roll"):
        lines.append(
            "- **A-roll (talking head):** Key light at 45 degrees + fill light "
            "opposite side, soft diffusion"
        )
    if shot_plan.get("overhead"):
        lines.append(
            "- **Overhead / bench:** Even, diffused lighting across the full bench "
            "-- minimize harsh shadows"
        )
    if shot_plan.get("closeups"):
        lines.append(
            "- **Detail closeups:** Focused directional light to highlight texture "
            "and detail; consider a small LED panel"
        )
    if shot_plan.get("glamour"):
        lines.append(
            "- **Glamour / B-roll:** Best available natural or styled light; "
            "backlight for depth separation"
        )
    if not any(
        shot_plan.get(k) for k in ("a_roll", "overhead", "closeups", "glamour")
    ):
        lines.append("- *No specific shot types in plan -- ensure even, soft lighting*")


def _sync_strategy(lines: list[str], shot_plan: dict) -> None:
    """Add sync strategy recommendations."""
    all_shots = []
    for category in ("a_roll", "overhead", "closeups", "measurements",
                     "inserts", "glamour", "pickups"):
        all_shots.extend(shot_plan.get(category, []))

    device_count_hint = 1
    if shot_plan.get("a_roll") and shot_plan.get("overhead"):
        device_count_hint = 2  # likely separate camera setups

    if device_count_hint >= 2:
        lines.append(
            "- **Multi-device sync:** Use an audible clap or slate at the start "
            "of each setup change"
        )
    lines.append("- **Timecode:** If your camera supports it, enable free-run timecode for easier alignment")
    lines.append(
        "- **File naming:** Note the clip number after each shot group "
        "to speed up ingest"
    )


def _optimized_shot_order(lines: list[str], shot_plan: dict) -> None:
    """Reorder shots to minimize setup changes, grouped by setup type."""
    # Group order: overhead first (rig setup), then closeups (same bench,
    # different lens), measurements, inserts, a-roll (different framing),
    # glamour (styled), pickups last.
    setup_groups = [
        ("Overhead / Bench Setup", shot_plan.get("overhead", [])),
        ("Detail Closeups", shot_plan.get("closeups", [])),
        ("Measurements", shot_plan.get("measurements", [])),
        ("Inserts", shot_plan.get("inserts", [])),
        ("A-Roll (Talking Head)", shot_plan.get("a_roll", [])),
        ("Glamour / B-Roll", shot_plan.get("glamour", [])),
        ("Pickup Shots", shot_plan.get("pickups", [])),
    ]

    order_num = 1
    for group_name, shots in setup_groups:
        if not shots:
            continue
        lines.append(f"### {group_name}")
        lines.append("")
        for shot in shots:
            lines.append(
                f"{order_num}. **{shot['id']}** -- {shot['description']} "
                f"({shot['beat_ref']}, {shot['priority']})"
            )
            order_num += 1
        lines.append("")

    if order_num == 1:
        lines.append("*No shots in plan -- shoot in any convenient order.*")
        lines.append("")
