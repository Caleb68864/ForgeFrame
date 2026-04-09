---
scenario_id: "SK-01"
title: "Outline Skill"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario SK-01: Outline Skill

## Description
Tests `generate_outline` in `production_brain/skills/outline.py`.

`generate_outline` is a pure template engine (no LLM call).  It returns
`(markdown_string, structured_dict)`.  The dict contains the keys:
`title`, `idea`, `project_type`, `audience`, `constraints`, `viewer_promise`,
`what_were_making`, `materials`, `tools`, `teaching_beats`, `pain_points`,
`chapter_structure`, `intro_hook`, `open_questions`.

Key test areas:
- Normal idea string → both outputs are non-empty and well-formed.
- `materials` and `tools` are non-empty lists; `teaching_beats` contains 7 items.
- `chapter_structure` contains dicts with `timestamp` and `title` keys.
- Empty string idea → function should still return without raising (graceful degradation).
- Optional kwargs (`project_type`, `audience`, `constraints`) are reflected in the output.
- When `constraints` is provided, an extra item is prepended to `open_questions`.
- Markdown output contains expected section headings.

## Preconditions
- Python 3.12+, `uv run pytest` available.
- Module is pure Python — no filesystem or network access required.

## Test Cases

```python
# tests/unit/test_outline_skill.py
import pytest

from workshop_video_brain.production_brain.skills.outline import generate_outline


SAMPLE_IDEA = "a walnut serving board with a juice groove and hand-rubbed oil finish"


class TestGenerateOutlineReturnTypes:
    def test_returns_tuple_of_two(self):
        result = generate_outline(SAMPLE_IDEA)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_first_element_is_string(self):
        md, _ = generate_outline(SAMPLE_IDEA)
        assert isinstance(md, str)

    def test_second_element_is_dict(self):
        _, data = generate_outline(SAMPLE_IDEA)
        assert isinstance(data, dict)


class TestGenerateOutlineDictKeys:
    def test_required_keys_present(self):
        _, data = generate_outline(SAMPLE_IDEA)
        required_keys = {
            "title", "idea", "project_type", "audience", "constraints",
            "viewer_promise", "what_were_making", "materials", "tools",
            "teaching_beats", "pain_points", "chapter_structure",
            "intro_hook", "open_questions",
        }
        assert required_keys.issubset(data.keys())

    def test_materials_is_non_empty_list(self):
        _, data = generate_outline(SAMPLE_IDEA)
        assert isinstance(data["materials"], list)
        assert len(data["materials"]) > 0

    def test_tools_is_non_empty_list(self):
        _, data = generate_outline(SAMPLE_IDEA)
        assert isinstance(data["tools"], list)
        assert len(data["tools"]) > 0

    def test_teaching_beats_has_seven_items(self):
        _, data = generate_outline(SAMPLE_IDEA)
        assert len(data["teaching_beats"]) == 7

    def test_teaching_beats_have_required_keys(self):
        _, data = generate_outline(SAMPLE_IDEA)
        for beat in data["teaching_beats"]:
            assert "number" in beat
            assert "title" in beat
            assert "description" in beat

    def test_chapter_structure_is_list(self):
        _, data = generate_outline(SAMPLE_IDEA)
        assert isinstance(data["chapter_structure"], list)

    def test_chapter_structure_entries_have_timestamp_and_title(self):
        _, data = generate_outline(SAMPLE_IDEA)
        for chapter in data["chapter_structure"]:
            assert "timestamp" in chapter
            assert "title" in chapter

    def test_pain_points_is_non_empty_list(self):
        _, data = generate_outline(SAMPLE_IDEA)
        assert isinstance(data["pain_points"], list)
        assert len(data["pain_points"]) > 0

    def test_open_questions_is_non_empty_list(self):
        _, data = generate_outline(SAMPLE_IDEA)
        assert isinstance(data["open_questions"], list)
        assert len(data["open_questions"]) > 0

    def test_viewer_promise_is_non_empty_string(self):
        _, data = generate_outline(SAMPLE_IDEA)
        assert isinstance(data["viewer_promise"], str)
        assert len(data["viewer_promise"]) > 0


class TestGenerateOutlineOptionalArgs:
    def test_project_type_reflected_in_dict(self):
        _, data = generate_outline(SAMPLE_IDEA, project_type="jig")
        assert data["project_type"] == "jig"

    def test_project_type_defaults_to_tutorial(self):
        _, data = generate_outline(SAMPLE_IDEA)
        assert data["project_type"] == "tutorial"

    def test_audience_reflected_in_dict(self):
        _, data = generate_outline(SAMPLE_IDEA, audience="beginner woodworkers")
        assert data["audience"] == "beginner woodworkers"

    def test_constraints_reflected_in_dict(self):
        _, data = generate_outline(SAMPLE_IDEA, constraints="no router")
        assert data["constraints"] == "no router"

    def test_constraints_prepended_to_open_questions(self):
        _, data = generate_outline(SAMPLE_IDEA, constraints="no router")
        assert any("no router" in q for q in data["open_questions"])

    def test_no_constraints_leaves_open_questions_unchanged(self):
        _, without = generate_outline(SAMPLE_IDEA)
        _, with_none = generate_outline(SAMPLE_IDEA, constraints=None)
        assert len(without["open_questions"]) == len(with_none["open_questions"])


class TestGenerateOutlineMarkdown:
    def test_markdown_contains_viewer_promise_heading(self):
        md, _ = generate_outline(SAMPLE_IDEA)
        assert "## Viewer Promise" in md

    def test_markdown_contains_teaching_beats_heading(self):
        md, _ = generate_outline(SAMPLE_IDEA)
        assert "## Teaching Beats" in md

    def test_markdown_contains_chapter_structure_heading(self):
        md, _ = generate_outline(SAMPLE_IDEA)
        assert "## Chapter Structure" in md

    def test_markdown_starts_with_title_heading(self):
        md, _ = generate_outline(SAMPLE_IDEA)
        assert md.startswith("# ")

    def test_markdown_contains_open_questions_heading(self):
        md, _ = generate_outline(SAMPLE_IDEA)
        assert "## Open Questions" in md

    def test_markdown_footer_present_when_constraints_given(self):
        md, _ = generate_outline(SAMPLE_IDEA, constraints="hand tools only")
        assert "hand tools only" in md


class TestGenerateOutlineEdgeCases:
    def test_empty_string_idea_does_not_raise(self):
        md, data = generate_outline("")
        assert isinstance(md, str)
        assert isinstance(data, dict)

    def test_very_long_idea_truncated_in_title(self):
        long_idea = "a " + ("very long idea " * 20)
        _, data = generate_outline(long_idea)
        assert len(data["title"]) <= 60

    def test_idea_with_trailing_period_cleaned_in_title(self):
        _, data = generate_outline("a simple shelf.")
        assert not data["title"].endswith(".")
```

## Steps
1. Read source module at `workshop-video-brain/src/workshop_video_brain/production_brain/skills/outline.py`
2. Create `tests/unit/test_outline_skill.py`
3. Implement test cases above
4. Run: `uv run pytest tests/unit/test_outline_skill.py -v`

## Expected Results
- `generate_outline` returns a `(str, dict)` tuple.
- The dict contains all 14 required keys.
- `teaching_beats` always has exactly 7 items.
- `constraints` kwarg prepends a note to `open_questions`.
- Markdown includes all major section headings.
- Empty idea does not raise; title truncation works correctly.

## Pass / Fail Criteria
- Pass: All tests pass
- Fail: Any test fails
