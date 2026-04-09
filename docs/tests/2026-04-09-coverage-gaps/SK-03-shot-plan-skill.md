---
scenario_id: "SK-03"
title: "Shot Plan Skill"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario SK-03: Shot Plan Skill

## Description
Tests `generate_shot_plan` in `production_brain/skills/shot_plan.py`.

`generate_shot_plan(outline_or_script, gear_constraints)` returns
`(markdown_string, structured_dict)`.

The dict contains seven shot-category keys:
`a_roll`, `overhead`, `closeups`, `measurements`, `inserts`, `glamour`, `pickups`.

Each element in those lists is a shot dict with keys:
`id`, `type`, `description`, `beat_ref`, `priority`, `notes`.

Key test areas:
- All seven category keys present in output dict.
- `a_roll` always contains the three mandatory GENERAL shots (A1/A2/A3).
- `glamour` always contains G1, G2, G3.
- `overhead` and `closeups` grow with number of beats.
- `gear_constraints="no overhead rig"` suppresses `overhead` shots and
  instead adds pickup workarounds.
- Empty beats input → minimal a_roll + glamour only (no beat-derived shots).
- Input dict from `generate_outline` is accepted.
- Input dict from `generate_script` is accepted (reads `steps` fallback).
- Markdown contains all seven category headings plus the summary table.
- Shot `priority` values are one of `must-have`, `should-have`, `nice-to-have`.

## Preconditions
- Python 3.12+, `uv run pytest` available.
- No filesystem or network access required.

## Test Cases

```python
# tests/unit/test_shot_plan_skill.py
import pytest

from workshop_video_brain.production_brain.skills.outline import generate_outline
from workshop_video_brain.production_brain.skills.script import generate_script
from workshop_video_brain.production_brain.skills.shot_plan import (
    generate_shot_plan,
    TYPE_A_ROLL,
    TYPE_OVERHEAD,
    TYPE_CLOSEUP,
    TYPE_GLAMOUR,
    TYPE_PICKUP,
)

VALID_PRIORITIES = {"must-have", "should-have", "nice-to-have"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def outline_data() -> dict:
    _, data = generate_outline("a walnut serving board")
    return data


@pytest.fixture()
def script_data(outline_data) -> dict:
    _, data = generate_script(outline_data)
    return data


@pytest.fixture()
def empty_source() -> dict:
    return {"title": "Empty Project"}


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

class TestGenerateShotPlanReturnTypes:
    def test_returns_tuple_of_two(self, outline_data):
        result = generate_shot_plan(outline_data)
        assert isinstance(result, tuple) and len(result) == 2

    def test_first_element_is_string(self, outline_data):
        md, _ = generate_shot_plan(outline_data)
        assert isinstance(md, str)

    def test_second_element_is_dict(self, outline_data):
        _, data = generate_shot_plan(outline_data)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Dict keys
# ---------------------------------------------------------------------------

class TestGenerateShotPlanDictKeys:
    CATEGORY_KEYS = {"a_roll", "overhead", "closeups", "measurements", "inserts", "glamour", "pickups"}

    def test_all_category_keys_present(self, outline_data):
        _, data = generate_shot_plan(outline_data)
        assert self.CATEGORY_KEYS.issubset(data.keys())

    def test_title_key_present(self, outline_data):
        _, data = generate_shot_plan(outline_data)
        assert "title" in data


# ---------------------------------------------------------------------------
# Shot structure
# ---------------------------------------------------------------------------

class TestShotStructure:
    def test_each_shot_has_required_keys(self, outline_data):
        _, data = generate_shot_plan(outline_data)
        all_shots = (
            data["a_roll"] + data["overhead"] + data["closeups"] +
            data["measurements"] + data["inserts"] + data["glamour"] + data["pickups"]
        )
        for shot in all_shots:
            for key in ("id", "type", "description", "beat_ref", "priority"):
                assert key in shot, f"Shot missing key: {key}"

    def test_all_priorities_are_valid(self, outline_data):
        _, data = generate_shot_plan(outline_data)
        all_shots = (
            data["a_roll"] + data["overhead"] + data["closeups"] +
            data["measurements"] + data["inserts"] + data["glamour"] + data["pickups"]
        )
        for shot in all_shots:
            assert shot["priority"] in VALID_PRIORITIES, \
                f"Invalid priority: {shot['priority']}"


# ---------------------------------------------------------------------------
# Mandatory general shots
# ---------------------------------------------------------------------------

class TestMandatoryShots:
    def test_a_roll_contains_at_least_three_shots(self, outline_data):
        _, data = generate_shot_plan(outline_data)
        assert len(data["a_roll"]) >= 3

    def test_a_roll_first_shot_is_general(self, outline_data):
        _, data = generate_shot_plan(outline_data)
        assert data["a_roll"][0]["beat_ref"] == "GENERAL"

    def test_glamour_contains_three_shots(self, outline_data):
        _, data = generate_shot_plan(outline_data)
        assert len(data["glamour"]) == 3

    def test_glamour_ids_are_g1_g2_g3(self, outline_data):
        _, data = generate_shot_plan(outline_data)
        ids = [s["id"] for s in data["glamour"]]
        assert "G1" in ids
        assert "G2" in ids
        assert "G3" in ids

    def test_pickups_always_has_at_least_two(self, outline_data):
        _, data = generate_shot_plan(outline_data)
        assert len(data["pickups"]) >= 2


# ---------------------------------------------------------------------------
# Beat-derived shots
# ---------------------------------------------------------------------------

class TestBeatDerivedShots:
    def test_overhead_count_equals_beat_count_by_default(self, outline_data):
        beats = outline_data["teaching_beats"]
        _, data = generate_shot_plan(outline_data)
        assert len(data["overhead"]) == len(beats)

    def test_closeup_count_equals_beat_count(self, outline_data):
        beats = outline_data["teaching_beats"]
        _, data = generate_shot_plan(outline_data)
        assert len(data["closeups"]) == len(beats)


# ---------------------------------------------------------------------------
# Gear constraints
# ---------------------------------------------------------------------------

class TestGearConstraints:
    def test_no_overhead_constraint_empties_overhead_list(self, outline_data):
        _, data = generate_shot_plan(outline_data, gear_constraints="no overhead rig")
        assert data["overhead"] == []

    def test_no_overhead_adds_pickup_workarounds(self, outline_data):
        _, data = generate_shot_plan(outline_data, gear_constraints="no overhead rig")
        # Should have beat-count pickup workarounds plus the standard 2 pickups
        beats = outline_data["teaching_beats"]
        # At least beats pickups added as workarounds
        assert len(data["pickups"]) >= len(beats)

    def test_overhead_constraint_workarounds_mention_no_overhead(self, outline_data):
        _, data = generate_shot_plan(outline_data, gear_constraints="no overhead rig")
        overhead_pickups = [s for s in data["pickups"] if "OVERHEAD" in s["description"].upper()]
        assert len(overhead_pickups) > 0

    def test_no_constraints_keeps_overhead_shots(self, outline_data):
        _, data = generate_shot_plan(outline_data, gear_constraints=None)
        assert len(data["overhead"]) > 0


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_source_does_not_raise(self, empty_source):
        md, data = generate_shot_plan(empty_source)
        assert isinstance(md, str)
        assert isinstance(data, dict)

    def test_empty_beats_gives_zero_closeups(self, empty_source):
        _, data = generate_shot_plan(empty_source)
        assert data["closeups"] == []

    def test_empty_beats_still_has_glamour(self, empty_source):
        _, data = generate_shot_plan(empty_source)
        assert len(data["glamour"]) == 3


# ---------------------------------------------------------------------------
# Input compatibility: script dict
# ---------------------------------------------------------------------------

class TestScriptInputCompatibility:
    def test_accepts_script_dict_without_raising(self, script_data):
        md, data = generate_shot_plan(script_data)
        assert isinstance(data, dict)

    def test_script_dict_produces_closeups(self, script_data):
        _, data = generate_shot_plan(script_data)
        assert len(data["closeups"]) > 0


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

class TestGenerateShotPlanMarkdown:
    def test_markdown_contains_a_roll_heading(self, outline_data):
        md, _ = generate_shot_plan(outline_data)
        assert "A-Roll" in md

    def test_markdown_contains_overhead_heading(self, outline_data):
        md, _ = generate_shot_plan(outline_data)
        assert "Overhead" in md

    def test_markdown_contains_glamour_heading(self, outline_data):
        md, _ = generate_shot_plan(outline_data)
        assert "Glamour" in md

    def test_markdown_contains_shot_count_summary(self, outline_data):
        md, _ = generate_shot_plan(outline_data)
        assert "Shot Count Summary" in md

    def test_markdown_mentions_gear_constraints(self, outline_data):
        md, _ = generate_shot_plan(outline_data, gear_constraints="phone only")
        assert "phone only" in md

    def test_markdown_starts_with_shot_plan_heading(self, outline_data):
        md, _ = generate_shot_plan(outline_data)
        assert md.startswith("# Shot Plan:")
```

## Steps
1. Read source module at `workshop-video-brain/src/workshop_video_brain/production_brain/skills/shot_plan.py`
2. Create `tests/unit/test_shot_plan_skill.py`
3. Implement test cases above
4. Run: `uv run pytest tests/unit/test_shot_plan_skill.py -v`

## Expected Results
- `generate_shot_plan` returns a `(str, dict)` tuple with all seven category keys.
- A-roll always has at least 3 GENERAL shots; glamour always has exactly G1/G2/G3.
- `overhead` and `closeups` lists grow proportionally to the number of input beats.
- `gear_constraints="no overhead rig"` zeroes out `overhead` and adds pickup workarounds.
- Empty beats input produces no beat-derived closeups but still returns glamour shots.
- Both `generate_outline` and `generate_script` dicts are accepted as input.
- All shot `priority` values are one of the three valid strings.

## Pass / Fail Criteria
- Pass: All tests pass
- Fail: Any test fails
