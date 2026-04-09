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
