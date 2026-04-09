# tests/unit/test_script_skill.py
import pytest

from workshop_video_brain.production_brain.skills.outline import generate_outline
from workshop_video_brain.production_brain.skills.script import generate_script


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def outline_data() -> dict:
    _, data = generate_outline("a walnut serving board with a juice groove")
    return data


@pytest.fixture()
def minimal_outline() -> dict:
    """Absolute minimum dict — all optional keys absent."""
    return {}


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

class TestGenerateScriptReturnTypes:
    def test_returns_tuple_of_two(self, outline_data):
        result = generate_script(outline_data)
        assert isinstance(result, tuple) and len(result) == 2

    def test_first_element_is_string(self, outline_data):
        md, _ = generate_script(outline_data)
        assert isinstance(md, str)

    def test_second_element_is_dict(self, outline_data):
        _, data = generate_script(outline_data)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Dict keys and structure
# ---------------------------------------------------------------------------

class TestGenerateScriptDictKeys:
    REQUIRED_KEYS = {
        "title", "tone", "target_length", "hook", "overview",
        "materials_section", "steps", "common_mistakes", "conclusion",
    }

    def test_required_keys_present(self, outline_data):
        _, data = generate_script(outline_data)
        assert self.REQUIRED_KEYS.issubset(data.keys())

    def test_materials_section_has_materials_and_tools(self, outline_data):
        _, data = generate_script(outline_data)
        assert "materials" in data["materials_section"]
        assert "tools" in data["materials_section"]

    def test_steps_is_list(self, outline_data):
        _, data = generate_script(outline_data)
        assert isinstance(data["steps"], list)

    def test_steps_count_matches_teaching_beats(self, outline_data):
        _, data = generate_script(outline_data)
        assert len(data["steps"]) == len(outline_data["teaching_beats"])

    def test_each_step_has_required_keys(self, outline_data):
        _, data = generate_script(outline_data)
        for step in data["steps"]:
            for key in ("number", "title", "direction", "script_text", "key_points", "common_mistake"):
                assert key in step, f"Step missing key: {key}"

    def test_key_points_is_list(self, outline_data):
        _, data = generate_script(outline_data)
        for step in data["steps"]:
            assert isinstance(step["key_points"], list)

    def test_common_mistakes_list_matches_pain_points(self, outline_data):
        _, data = generate_script(outline_data)
        assert data["common_mistakes"] == outline_data["pain_points"]


# ---------------------------------------------------------------------------
# Optional arguments
# ---------------------------------------------------------------------------

class TestGenerateScriptOptionalArgs:
    def test_tone_stored_in_dict(self, outline_data):
        _, data = generate_script(outline_data, tone="educational")
        assert data["tone"] == "educational"

    def test_default_tone_is_practical(self, outline_data):
        _, data = generate_script(outline_data)
        assert data["tone"] == "practical"

    def test_target_length_stored(self, outline_data):
        _, data = generate_script(outline_data, target_length="10min")
        assert data["target_length"] == "10min"

    def test_target_length_absent_stored_as_unspecified(self, outline_data):
        _, data = generate_script(outline_data)
        assert data["target_length"] == "unspecified"

    def test_target_length_included_in_conclusion(self, outline_data):
        _, data = generate_script(outline_data, target_length="15min")
        assert "15min" in data["conclusion"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestGenerateScriptEdgeCases:
    def test_empty_outline_does_not_raise(self, minimal_outline):
        md, data = generate_script(minimal_outline)
        assert isinstance(md, str)
        assert isinstance(data, dict)

    def test_empty_teaching_beats_gives_empty_steps(self, minimal_outline):
        minimal_outline["teaching_beats"] = []
        _, data = generate_script(minimal_outline)
        assert data["steps"] == []

    def test_title_defaults_to_untitled_when_absent(self, minimal_outline):
        _, data = generate_script(minimal_outline)
        assert "Untitled" in data["title"]

    def test_no_crash_when_pain_points_empty(self, outline_data):
        outline_data["pain_points"] = []
        outline_data["teaching_beats"] = outline_data["teaching_beats"][:2]
        _, data = generate_script(outline_data)
        assert isinstance(data["steps"], list)


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

class TestGenerateScriptMarkdown:
    def test_markdown_contains_hook_heading(self, outline_data):
        md, _ = generate_script(outline_data)
        assert "## HOOK" in md

    def test_markdown_contains_project_overview(self, outline_data):
        md, _ = generate_script(outline_data)
        assert "## PROJECT OVERVIEW" in md

    def test_markdown_contains_conclusion(self, outline_data):
        md, _ = generate_script(outline_data)
        assert "## CONCLUSION" in md

    def test_markdown_contains_step_headings(self, outline_data):
        md, _ = generate_script(outline_data)
        assert "## STEP 1:" in md

    def test_markdown_contains_materials_section(self, outline_data):
        md, _ = generate_script(outline_data)
        assert "## MATERIALS & TOOLS" in md

    def test_markdown_starts_with_script_title(self, outline_data):
        md, _ = generate_script(outline_data)
        assert md.startswith("# Script:")

    def test_tone_appears_in_markdown_metadata(self, outline_data):
        md, _ = generate_script(outline_data, tone="casual")
        assert "casual" in md

    def test_voiceover_notes_section_present(self, outline_data):
        md, _ = generate_script(outline_data)
        assert "## VOICEOVER NOTES" in md
