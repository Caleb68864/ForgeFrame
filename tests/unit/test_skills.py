"""Unit tests for production_brain skill engines."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# outline.py
# ---------------------------------------------------------------------------

class TestOutlineEngine:
    def test_returns_tuple_of_str_and_dict(self):
        from workshop_video_brain.production_brain.skills.outline import generate_outline
        result = generate_outline(idea="walnut cutting board")
        assert isinstance(result, tuple)
        assert len(result) == 2
        md, data = result
        assert isinstance(md, str)
        assert isinstance(data, dict)

    def test_dict_has_required_keys(self):
        from workshop_video_brain.production_brain.skills.outline import generate_outline
        _, data = generate_outline(idea="wall-mounted tool cabinet")
        required_keys = [
            "viewer_promise",
            "what_were_making",
            "materials",
            "tools",
            "teaching_beats",
            "pain_points",
            "chapter_structure",
            "intro_hook",
            "open_questions",
        ]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

    def test_teaching_beats_are_list_of_dicts(self):
        from workshop_video_brain.production_brain.skills.outline import generate_outline
        _, data = generate_outline(idea="simple box joint box")
        assert isinstance(data["teaching_beats"], list)
        assert len(data["teaching_beats"]) > 0
        for beat in data["teaching_beats"]:
            assert isinstance(beat, dict)
            assert "number" in beat
            assert "title" in beat
            assert "description" in beat

    def test_chapter_structure_is_list_of_dicts(self):
        from workshop_video_brain.production_brain.skills.outline import generate_outline
        _, data = generate_outline(idea="mortise and tenon joint")
        assert isinstance(data["chapter_structure"], list)
        for ch in data["chapter_structure"]:
            assert "timestamp" in ch
            assert "title" in ch

    def test_markdown_contains_expected_headings(self):
        from workshop_video_brain.production_brain.skills.outline import generate_outline
        md, _ = generate_outline(idea="wooden bench")
        assert "## Viewer Promise" in md
        assert "## Teaching Beats" in md
        assert "## Chapter Structure" in md
        assert "## Suggested Intro Hook" in md
        assert "## Open Questions" in md

    def test_optional_params_accepted(self):
        from workshop_video_brain.production_brain.skills.outline import generate_outline
        md, data = generate_outline(
            idea="leather wallet",
            project_type="leatherwork",
            audience="beginners",
            constraints="no sewing machine",
        )
        assert isinstance(md, str)
        assert data["project_type"] == "leatherwork"
        assert data["audience"] == "beginners"
        # Constraint should appear in open questions
        assert any("no sewing machine" in q for q in data["open_questions"])

    def test_materials_and_tools_are_lists(self):
        from workshop_video_brain.production_brain.skills.outline import generate_outline
        _, data = generate_outline(idea="floating shelf")
        assert isinstance(data["materials"], list)
        assert isinstance(data["tools"], list)
        assert len(data["materials"]) > 0
        assert len(data["tools"]) > 0


# ---------------------------------------------------------------------------
# script.py
# ---------------------------------------------------------------------------

class TestScriptEngine:
    def _get_outline(self):
        from workshop_video_brain.production_brain.skills.outline import generate_outline
        _, data = generate_outline(idea="turned wooden bowl")
        return data

    def test_returns_tuple_of_str_and_dict(self):
        from workshop_video_brain.production_brain.skills.script import generate_script
        outline = self._get_outline()
        result = generate_script(outline_data=outline)
        assert isinstance(result, tuple)
        md, data = result
        assert isinstance(md, str)
        assert isinstance(data, dict)

    def test_dict_has_required_keys(self):
        from workshop_video_brain.production_brain.skills.script import generate_script
        outline = self._get_outline()
        _, data = generate_script(outline_data=outline)
        required_keys = ["hook", "overview", "materials_section", "steps",
                         "common_mistakes", "conclusion"]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

    def test_steps_are_list_of_dicts_with_expected_keys(self):
        from workshop_video_brain.production_brain.skills.script import generate_script
        outline = self._get_outline()
        _, data = generate_script(outline_data=outline)
        assert isinstance(data["steps"], list)
        assert len(data["steps"]) > 0
        for step in data["steps"]:
            assert "number" in step
            assert "title" in step
            assert "script_text" in step
            assert "common_mistake" in step

    def test_markdown_contains_hook_section(self):
        from workshop_video_brain.production_brain.skills.script import generate_script
        outline = self._get_outline()
        md, _ = generate_script(outline_data=outline)
        assert "## HOOK" in md
        assert "## CONCLUSION" in md
        assert "## MATERIALS & TOOLS" in md

    def test_tone_and_target_length_accepted(self):
        from workshop_video_brain.production_brain.skills.script import generate_script
        outline = self._get_outline()
        _, data = generate_script(
            outline_data=outline, tone="casual", target_length="8min"
        )
        assert data["tone"] == "casual"
        assert data["target_length"] == "8min"

    def test_empty_outline_does_not_crash(self):
        from workshop_video_brain.production_brain.skills.script import generate_script
        md, data = generate_script(outline_data={})
        assert isinstance(md, str)
        assert "hook" in data

    def test_materials_section_has_sub_dicts(self):
        from workshop_video_brain.production_brain.skills.script import generate_script
        outline = self._get_outline()
        _, data = generate_script(outline_data=outline)
        ms = data["materials_section"]
        assert "materials" in ms
        assert "tools" in ms
        assert isinstance(ms["materials"], list)
        assert isinstance(ms["tools"], list)


# ---------------------------------------------------------------------------
# shot_plan.py
# ---------------------------------------------------------------------------

class TestShotPlanEngine:
    def _get_outline(self):
        from workshop_video_brain.production_brain.skills.outline import generate_outline
        _, data = generate_outline(idea="cedar garden planter box")
        return data

    def test_returns_tuple_of_str_and_dict(self):
        from workshop_video_brain.production_brain.skills.shot_plan import generate_shot_plan
        outline = self._get_outline()
        result = generate_shot_plan(outline_or_script=outline)
        assert isinstance(result, tuple)
        md, data = result
        assert isinstance(md, str)
        assert isinstance(data, dict)

    def test_dict_has_required_category_keys(self):
        from workshop_video_brain.production_brain.skills.shot_plan import generate_shot_plan
        outline = self._get_outline()
        _, data = generate_shot_plan(outline_or_script=outline)
        required_keys = ["a_roll", "overhead", "closeups", "measurements",
                         "inserts", "glamour", "pickups"]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

    def test_shots_have_required_fields(self):
        from workshop_video_brain.production_brain.skills.shot_plan import generate_shot_plan
        outline = self._get_outline()
        _, data = generate_shot_plan(outline_or_script=outline)
        all_shots = (
            data["a_roll"] + data["overhead"] + data["closeups"]
            + data["measurements"] + data["inserts"] + data["glamour"]
            + data["pickups"]
        )
        assert len(all_shots) > 0
        for shot in all_shots:
            assert "id" in shot
            assert "type" in shot
            assert "description" in shot
            assert "beat_ref" in shot
            assert "priority" in shot

    def test_gear_constraints_suppresses_overhead(self):
        from workshop_video_brain.production_brain.skills.shot_plan import generate_shot_plan
        outline = self._get_outline()
        _, data = generate_shot_plan(
            outline_or_script=outline,
            gear_constraints="no overhead rig",
        )
        # When no overhead rig, overhead list should be empty
        assert len(data["overhead"]) == 0
        # Pickups should have overhead workaround notes
        assert len(data["pickups"]) > 0

    def test_priority_values_are_valid(self):
        from workshop_video_brain.production_brain.skills.shot_plan import generate_shot_plan
        outline = self._get_outline()
        _, data = generate_shot_plan(outline_or_script=outline)
        valid_priorities = {"must-have", "should-have", "nice-to-have"}
        all_shots = (
            data["a_roll"] + data["overhead"] + data["closeups"]
            + data["measurements"] + data["inserts"] + data["glamour"]
            + data["pickups"]
        )
        for shot in all_shots:
            assert shot["priority"] in valid_priorities

    def test_markdown_contains_summary_table(self):
        from workshop_video_brain.production_brain.skills.shot_plan import generate_shot_plan
        outline = self._get_outline()
        md, _ = generate_shot_plan(outline_or_script=outline)
        assert "Shot Count Summary" in md


# ---------------------------------------------------------------------------
# review.py
# ---------------------------------------------------------------------------

class TestReviewEngine:
    SAMPLE_TRANSCRIPT = (
        "[0:00] Welcome to the workshop. Today we're making a walnut cutting board. "
        "This is a great project for a Saturday afternoon, and it makes a wonderful gift. "
        "I've made probably fifty of these over the years and I can tell you that you can see "
        "the quality of the glue joint right here. "
        "[1:30] Now let's talk about the wood selection. You want to look for boards "
        "that are flat, straight, and free from major defects. I'll show you what I mean "
        "in a moment. The key measurement here is three-quarter inch thickness. "
        "[3:00] Moving on to the glue-up. This is the most critical step. "
        "Apply glue to one face only. Check for bow before clamping. "
        "[3:00] Apply glue to one face only. Check for bow before the glue sets. "
        "This is the most critical step in the whole project."
        "[8:00] The finish is mineral oil. Apply two coats, wiping with the grain. "
        "Let it soak in overnight before the second coat."
    )

    def test_returns_tuple_of_str_and_dict(self):
        from workshop_video_brain.production_brain.skills.review import generate_review
        result = generate_review(
            transcript_text=self.SAMPLE_TRANSCRIPT,
            markers=[],
        )
        assert isinstance(result, tuple)
        md, data = result
        assert isinstance(md, str)
        assert isinstance(data, dict)

    def test_dict_has_required_keys(self):
        from workshop_video_brain.production_brain.skills.review import generate_review
        _, data = generate_review(
            transcript_text=self.SAMPLE_TRANSCRIPT,
            markers=[],
        )
        required_keys = [
            "pacing_notes",
            "repetition_flags",
            "insert_suggestions",
            "overlay_ideas",
            "chapter_breaks",
        ]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

    def test_all_values_are_lists(self):
        from workshop_video_brain.production_brain.skills.review import generate_review
        _, data = generate_review(
            transcript_text=self.SAMPLE_TRANSCRIPT,
            markers=[],
        )
        for key in ["pacing_notes", "repetition_flags", "insert_suggestions",
                    "overlay_ideas", "chapter_breaks"]:
            assert isinstance(data[key], list), f"{key} should be a list"

    def test_detects_overlay_opportunities_for_measurements(self):
        from workshop_video_brain.production_brain.skills.review import generate_review
        transcript = "[0:00] The board should be exactly three-quarter inch thick. " * 3
        _, data = generate_review(transcript_text=transcript, markers=[])
        overlay_types = [o["type"] for o in data["overlay_ideas"]]
        assert "measurement" in overlay_types

    def test_suggests_chapter_breaks_from_transition_language(self):
        from workshop_video_brain.production_brain.skills.review import generate_review
        transcript = (
            "[0:00] Intro content here. "
            "[2:00] Moving on to the glue-up section now. "
            "[5:00] Now let's talk about finishing the piece. "
        )
        _, data = generate_review(transcript_text=transcript, markers=[])
        assert len(data["chapter_breaks"]) >= 1

    def test_handles_empty_transcript(self):
        from workshop_video_brain.production_brain.skills.review import generate_review
        md, data = generate_review(transcript_text="", markers=[])
        assert isinstance(md, str)
        assert isinstance(data, dict)

    def test_accepts_edit_notes(self):
        from workshop_video_brain.production_brain.skills.review import generate_review
        md, _ = generate_review(
            transcript_text=self.SAMPLE_TRANSCRIPT,
            markers=[],
            edit_notes="Previous pass: removed 30s of dead air at 4:00",
        )
        assert isinstance(md, str)

    def test_insert_suggestions_have_required_fields(self):
        from workshop_video_brain.production_brain.skills.review import generate_review
        _, data = generate_review(
            transcript_text=self.SAMPLE_TRANSCRIPT,
            markers=[],
        )
        for suggestion in data["insert_suggestions"]:
            assert "id" in suggestion
            assert "transcript_excerpt" in suggestion
            assert "timestamp" in suggestion
            assert "needed_shot" in suggestion
            assert "priority" in suggestion
