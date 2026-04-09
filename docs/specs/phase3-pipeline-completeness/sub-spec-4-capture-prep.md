---
type: phase-spec
master_spec: "../2026-04-09-phase3-pipeline-completeness.md"
sub_spec: 4
title: "Capture Prep Skill"
dependencies: []
date: 2026-04-09
---

# Sub-Spec 4: Capture Prep Skill

## Scope

New skill `ff-capture-prep` that reads the shot plan from a workspace and generates a pre-shoot checklist covering camera settings, audio setup, lighting notes, sync strategy, and optimized shot order. The checklist is a pure function returning markdown, invoked by the SKILL.md prompt.

## Shared Context

- **Source root:** `workshop-video-brain/src/workshop_video_brain/`
- **Test command:** `uv run pytest tests/ -v`
- **MCP pattern:** `@mcp.tool()`, return `_ok(data)` / `_err(message)`
- **Skill pattern:** `ff-` prefix, SKILL.md in `workshop-video-brain/skills/ff-*/`
- **Shot plan engine:** `production_brain/skills/shot_plan.py` produces `(markdown, dict)` with keys `a_roll`, `overhead`, `closeups`, `measurements`, `inserts`, `glamour`, `pickups`
- **ShotPlan dict shape:** `{"title": str, "a_roll": [{"id", "type", "description", "beat_ref", "priority", "notes"}], ...}`

## Interface Contracts

### Provides

- **`generate_capture_checklist(shot_plan: dict, target_resolution: str, target_fps: int) -> str`**
  - Pure function returning a markdown checklist string
  - Accepts the structured dict from `shot_plan.generate_shot_plan()` (or loaded from `reports/shot_plan.json`)
  - Sections: Camera Settings, Audio Setup, Lighting Notes, Sync Strategy, Shot Order

- **`workshop-video-brain/skills/ff-capture-prep/SKILL.md`**
  - Skill file registered in plugin.json
  - Instructs Claude to read workspace, call the engine, present with personalized notes

### Requires

- Nothing external (no infrastructure sub-spec dependencies)
- Reads `reports/shot_plan.json` from workspace if available (produced by `ff-shot-plan` skill)

## Implementation Steps

### Step 1: Write tests -- `tests/unit/test_capture_prep.py`

Write tests first. Cover: full shot plan, empty shot plan, various resolution/fps combos, shot reordering logic, and section content.

```python
"""Tests for capture prep checklist generator."""
from __future__ import annotations

import pytest

from workshop_video_brain.production_brain.skills.capture_prep import (
    generate_capture_checklist,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def full_shot_plan() -> dict:
    """A realistic shot plan dict matching shot_plan.generate_shot_plan() output."""
    return {
        "title": "Dovetail Joint Tutorial",
        "a_roll": [
            {"id": "A1", "type": "a_roll", "description": "Intro on-camera",
             "beat_ref": "GENERAL", "priority": "must-have", "notes": ""},
            {"id": "A2", "type": "a_roll", "description": "Materials overview",
             "beat_ref": "GENERAL", "priority": "must-have", "notes": ""},
        ],
        "overhead": [
            {"id": "O1", "type": "overhead", "description": "Layout marking",
             "beat_ref": "Step 1", "priority": "must-have", "notes": "Continuous"},
            {"id": "O2", "type": "overhead", "description": "Chisel work",
             "beat_ref": "Step 2", "priority": "must-have", "notes": ""},
        ],
        "closeups": [
            {"id": "C1", "type": "closeup", "description": "Joint fit check",
             "beat_ref": "Step 3", "priority": "must-have", "notes": "Macro preferred"},
        ],
        "measurements": [
            {"id": "M1", "type": "measurement", "description": "Board dimensions",
             "beat_ref": "Step 1", "priority": "must-have", "notes": ""},
        ],
        "inserts": [
            {"id": "I1", "type": "insert", "description": "Glue application",
             "beat_ref": "Step 4", "priority": "must-have", "notes": ""},
        ],
        "glamour": [
            {"id": "G1", "type": "glamour", "description": "Finished piece",
             "beat_ref": "GENERAL", "priority": "must-have", "notes": ""},
        ],
        "pickups": [
            {"id": "P1", "type": "pickup", "description": "Hand detail",
             "beat_ref": "Step 2", "priority": "should-have", "notes": ""},
        ],
    }


@pytest.fixture
def empty_shot_plan() -> dict:
    return {
        "title": "Untitled",
        "a_roll": [],
        "overhead": [],
        "closeups": [],
        "measurements": [],
        "inserts": [],
        "glamour": [],
        "pickups": [],
    }


# ---------------------------------------------------------------------------
# Section presence tests
# ---------------------------------------------------------------------------

class TestCaptureChecklistSections:
    """Verify all required sections appear in the output."""

    def test_all_sections_present(self, full_shot_plan: dict):
        md = generate_capture_checklist(full_shot_plan)
        assert "## Camera Settings" in md
        assert "## Audio Setup" in md
        assert "## Lighting Notes" in md
        assert "## Sync Strategy" in md
        assert "## Shot Order" in md

    def test_empty_plan_still_has_all_sections(self, empty_shot_plan: dict):
        md = generate_capture_checklist(empty_shot_plan)
        assert "## Camera Settings" in md
        assert "## Audio Setup" in md
        assert "## Lighting Notes" in md
        assert "## Sync Strategy" in md
        assert "## Shot Order" in md


# ---------------------------------------------------------------------------
# Camera settings
# ---------------------------------------------------------------------------

class TestCameraSettings:
    """Verify camera settings reflect input parameters."""

    def test_default_resolution_and_fps(self, full_shot_plan: dict):
        md = generate_capture_checklist(full_shot_plan)
        assert "1920x1080" in md
        assert "30" in md

    def test_custom_resolution(self, full_shot_plan: dict):
        md = generate_capture_checklist(
            full_shot_plan, target_resolution="3840x2160", target_fps=24,
        )
        assert "3840x2160" in md
        assert "24" in md

    def test_color_profile_recommendation(self, full_shot_plan: dict):
        md = generate_capture_checklist(full_shot_plan)
        assert "BT.709" in md


# ---------------------------------------------------------------------------
# Audio setup
# ---------------------------------------------------------------------------

class TestAudioSetup:
    """Verify audio recommendations based on shot types."""

    def test_talking_head_mic_recommendation(self, full_shot_plan: dict):
        """A-roll shots should trigger lapel/USB mic recommendation."""
        md = generate_capture_checklist(full_shot_plan)
        # Should recommend a mic type for talking head
        lower = md.lower()
        assert "lapel" in lower or "usb" in lower or "lav" in lower

    def test_workshop_mic_recommendation(self, full_shot_plan: dict):
        """Overhead/workshop shots should trigger shotgun mic recommendation."""
        md = generate_capture_checklist(full_shot_plan)
        lower = md.lower()
        assert "shotgun" in lower or "boom" in lower

    def test_monitoring_reminder(self, full_shot_plan: dict):
        md = generate_capture_checklist(full_shot_plan)
        lower = md.lower()
        assert "monitor" in lower or "headphone" in lower


# ---------------------------------------------------------------------------
# Lighting notes
# ---------------------------------------------------------------------------

class TestLightingNotes:
    """Verify per-shot-type lighting guidance."""

    def test_a_roll_lighting(self, full_shot_plan: dict):
        md = generate_capture_checklist(full_shot_plan)
        lower = md.lower()
        assert "key" in lower  # key light reference

    def test_overhead_lighting(self, full_shot_plan: dict):
        md = generate_capture_checklist(full_shot_plan)
        lower = md.lower()
        assert "diffuse" in lower or "even" in lower

    def test_closeup_lighting(self, full_shot_plan: dict):
        md = generate_capture_checklist(full_shot_plan)
        lower = md.lower()
        assert "focus" in lower


# ---------------------------------------------------------------------------
# Sync strategy
# ---------------------------------------------------------------------------

class TestSyncStrategy:
    """Verify sync recommendations."""

    def test_clap_recommendation(self, full_shot_plan: dict):
        md = generate_capture_checklist(full_shot_plan)
        lower = md.lower()
        assert "clap" in lower or "slate" in lower or "cue" in lower

    def test_timecode_mention(self, full_shot_plan: dict):
        md = generate_capture_checklist(full_shot_plan)
        lower = md.lower()
        assert "timecode" in lower


# ---------------------------------------------------------------------------
# Shot order optimization
# ---------------------------------------------------------------------------

class TestShotOrder:
    """Verify shot reordering minimizes setup changes."""

    def test_shots_grouped_by_type(self, full_shot_plan: dict):
        """Shots should be grouped by setup type, not interleaved."""
        md = generate_capture_checklist(full_shot_plan)
        # The Shot Order section should exist and contain grouped headings
        assert "Shot Order" in md
        # Should contain at least some shot IDs from the plan
        assert "A1" in md or "O1" in md or "C1" in md

    def test_empty_plan_shot_order(self, empty_shot_plan: dict):
        md = generate_capture_checklist(empty_shot_plan)
        # Should handle gracefully
        assert "Shot Order" in md


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class TestReturnType:
    def test_returns_string(self, full_shot_plan: dict):
        result = generate_capture_checklist(full_shot_plan)
        assert isinstance(result, str)

    def test_non_empty_for_full_plan(self, full_shot_plan: dict):
        result = generate_capture_checklist(full_shot_plan)
        assert len(result) > 100
```

### Step 2: Implement `capture_prep.py`

**Create** `workshop-video-brain/src/workshop_video_brain/production_brain/skills/capture_prep.py`:

```python
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
```

### Step 3: Create SKILL.md

**Create** `workshop-video-brain/skills/ff-capture-prep/SKILL.md`:

```markdown
---
name: ff-capture-prep
description: "Generate a pre-shoot capture checklist from a shot plan: camera settings, audio, lighting, sync, and optimized shot order. Use when preparing to film."
---

# ff-capture-prep

Generate a capture prep checklist for an upcoming video shoot.

## When to Use

Use this skill when the user:
- Is about to start filming and wants a pre-shoot checklist
- Asks for camera settings, audio setup, or lighting recommendations
- Wants to optimize their shooting order to minimize setup changes
- Says "capture prep", "shoot prep", "pre-shoot", or "filming checklist"

## Steps

1. **Find the workspace.** Ask the user for the workspace path if not already known.

2. **Load the shot plan.** Check for `reports/shot_plan.json` in the workspace:
   ```python
   import json
   from pathlib import Path
   shot_plan_path = Path(workspace_root) / "reports" / "shot_plan.json"
   if shot_plan_path.exists():
       shot_plan = json.loads(shot_plan_path.read_text())
   ```
   If no shot plan exists, generate a generic checklist using an empty plan dict:
   ```python
   shot_plan = {"title": "Generic Shoot", "a_roll": [], "overhead": [], "closeups": [], "measurements": [], "inserts": [], "glamour": [], "pickups": []}
   ```

3. **Ask about target settings** (or use defaults):
   - Resolution: default `"1920x1080"`, ask if shooting 4K (`"3840x2160"`)
   - Frame rate: default `30`, ask if they prefer 24 or 60

4. **Generate the checklist:**
   ```python
   from workshop_video_brain.production_brain.skills.capture_prep import generate_capture_checklist
   checklist_md = generate_capture_checklist(shot_plan, target_resolution, target_fps)
   ```

5. **Present the checklist** with additional personalized notes:
   - If the user mentioned specific gear, add notes about that gear
   - If the workspace has previous shoots, mention lessons from those
   - Highlight any must-have shots they might miss
   - If shooting conditions are mentioned (outdoor, low light), adjust lighting notes

## Output Format

Present the markdown checklist directly. Add a brief intro like:

> Here is your capture prep checklist for **{title}**. I have optimized the shot order to minimize setup changes.

Then the full checklist markdown, followed by any personalized notes.

## Example

User: "I'm about to film the dovetail tutorial, can you get me a checklist?"

Response: Load the shot plan from the workspace, generate the checklist at 1080p/30fps, present it with notes about the specific shots in the plan.
```

### Step 4: Register skill in plugin.json

**Modify** `workshop-video-brain/plugin.json` -- add `ff-capture-prep` to the skills array.

### Step 5: Run tests and verify

```bash
uv run pytest tests/unit/test_capture_prep.py -v
```

## Verification Commands

```bash
# Run new tests
uv run pytest tests/unit/test_capture_prep.py -v

# Run full suite to confirm no regressions
uv run pytest tests/ -v

# Verify SKILL.md has valid frontmatter
python3 -c "
import yaml
with open('workshop-video-brain/skills/ff-capture-prep/SKILL.md') as f:
    content = f.read()
    assert content.startswith('---')
    fm = content.split('---')[1]
    data = yaml.safe_load(fm)
    assert data['name'] == 'ff-capture-prep'
    assert len(data['description']) <= 250
    print('ff-capture-prep SKILL.md: PASS')
"

# Verify module importable
python3 -c "
from workshop_video_brain.production_brain.skills.capture_prep import generate_capture_checklist
print('Import: PASS')
"
```

## Acceptance Criteria

- [ ] `generate_capture_checklist(shot_plan, target_resolution, target_fps) -> str` returns markdown
- [ ] Output contains all 5 sections: Camera Settings, Audio Setup, Lighting Notes, Sync Strategy, Shot Order
- [ ] Camera Settings section includes resolution, fps, BT.709 color profile recommendation
- [ ] Audio Setup recommends lapel/USB mic for talking head shots, shotgun/boom for workshop shots
- [ ] Audio Setup includes monitoring reminder (headphones)
- [ ] Lighting Notes vary by shot type: key+fill for A-roll, even diffused for overhead, focused for closeup
- [ ] Sync Strategy recommends clap/slate for multi-device, mentions timecode
- [ ] Shot Order groups shots by setup type to minimize changes (overhead first, A-roll later, pickups last)
- [ ] Empty shot plan produces valid checklist with generic guidance
- [ ] Custom resolution/fps values appear correctly in output
- [ ] SKILL.md has valid frontmatter with `name: ff-capture-prep` and description under 250 chars
- [ ] Skill registered in plugin.json
- [ ] All new tests pass: `uv run pytest tests/unit/test_capture_prep.py -v`
- [ ] All existing tests still pass: `uv run pytest tests/ -v`
