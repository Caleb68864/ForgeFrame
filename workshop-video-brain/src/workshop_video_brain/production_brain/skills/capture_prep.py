"""Capture prep checklist generator.

Pure function that takes a shot plan dict and returns a markdown checklist
with camera settings, audio setup, lighting notes, sync strategy, and
optimized shot order.

``load_shot_plan`` is the shared workspace loader used by the
``capture_prep_checklist`` MCP tool and the ``wvb plan capture-prep`` command.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

#: Where ``new_project`` saves the structured shot plan, relative to the workspace.
SHOT_PLAN_REPORT = Path("reports") / "shot_plan.json"

#: Plan used when a workspace has no shot plan yet: the checklist still covers
#: camera, audio, lighting and sync, with no shot order.
GENERIC_SHOT_PLAN: dict = {
    "title": "Generic Shoot",
    "a_roll": [], "overhead": [], "closeups": [], "measurements": [],
    "inserts": [], "glamour": [], "pickups": [],
}

SHOT_CATEGORIES = ("a_roll", "overhead", "closeups", "measurements",
                   "inserts", "glamour", "pickups")


def load_shot_plan(workspace_root: Path | str) -> tuple[dict, Path | None]:
    """Load ``reports/shot_plan.json`` from a workspace.

    Returns ``(plan, path)``. When the file does not exist, returns a fresh copy
    of :data:`GENERIC_SHOT_PLAN` and ``None``.

    Raises:
        ValueError: If the file exists but is not valid JSON or not an object.
    """
    path = Path(workspace_root) / SHOT_PLAN_REPORT
    if not path.is_file():
        return copy.deepcopy(GENERIC_SHOT_PLAN), None
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(plan, dict):
        raise ValueError(
            f"{path} must hold a JSON object, got {type(plan).__name__}"
        )
    return plan, path


def count_shots(shot_plan: dict) -> int:
    """Number of shots across all categories of a shot plan."""
    return sum(len(shot_plan.get(k) or []) for k in SHOT_CATEGORIES)


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

    Raises:
        ValueError: If ``shot_plan`` is not a dict, ``target_fps`` is not a
            positive integer, or ``target_resolution`` is not ``WxH``.
    """
    # Validate up front: target_fps=0 used to emit "Shutter speed: 1/0" and a
    # garbage resolution string went straight into the checklist.
    if not isinstance(shot_plan, dict):
        raise ValueError(
            f"shot_plan must be a dict (from generate_shot_plan or "
            f"reports/shot_plan.json), got {type(shot_plan).__name__}"
        )
    if isinstance(target_fps, bool) or not isinstance(target_fps, int) or target_fps <= 0:
        raise ValueError(f"target_fps must be a positive integer, got {target_fps!r}")
    w, sep, h = str(target_resolution).lower().partition("x")
    if not (sep and w.isdigit() and h.isdigit() and int(w) > 0 and int(h) > 0):
        raise ValueError(
            f"target_resolution must look like '1920x1080', got {target_resolution!r}"
        )

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
    lines.append(
        "- **Constant frame rate:** Phones and screen recorders often record "
        "variable frame rate (VFR), which drifts out of sync in the edit. Lock "
        "the frame rate if the device allows it; after ingest, run "
        "`media_check_vfr` and convert any VFR files with `media_transcode_cfr`."
    )
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


def capture_prep_payload(
    shot_plan: dict,
    shot_plan_path: Path | None,
    target_resolution: str = "1920x1080",
    target_fps: int = 30,
) -> dict:
    """Checklist plus summary fields, as returned by the tool and ``--json``.

    Validation is :func:`generate_capture_checklist`'s (raises ``ValueError``).
    """
    markdown = generate_capture_checklist(shot_plan, target_resolution, target_fps)
    payload = {
        "title": shot_plan.get("title", "Untitled Project"),
        "shot_plan_path": str(shot_plan_path) if shot_plan_path else None,
        "shot_count": count_shots(shot_plan),
        "target_resolution": target_resolution,
        "target_fps": target_fps,
        "markdown": markdown,
    }
    if shot_plan_path is None:
        payload["note"] = (
            f"No {SHOT_PLAN_REPORT.as_posix()} in the workspace; this is a generic "
            "checklist with no shot order. Create a shot plan (ff-shot-plan or "
            "ff-new-project) for a shot-by-shot order."
        )
    return payload
