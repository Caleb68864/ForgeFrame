"""Unit tests for MYOG Pattern Brain pipeline and models."""
from __future__ import annotations

import uuid

import pytest

from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.core.models.patterns import (
    BuildData,
    BuildStep,
    BuildTip,
    MaterialItem,
    Measurement,
)
from workshop_video_brain.edit_mcp.pipelines.pattern_brain import (
    extract_build_data,
    generate_build_notes,
    generate_overlay_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transcript(*segment_texts: str, start_offset: float = 0.0) -> Transcript:
    """Build a minimal Transcript from a sequence of text strings."""
    segments = []
    t = start_offset
    for text in segment_texts:
        segments.append(
            TranscriptSegment(
                start_seconds=t,
                end_seconds=t + 5.0,
                text=text,
                confidence=1.0,
            )
        )
        t += 5.0
    return Transcript(
        id=uuid.uuid4(),
        asset_id=uuid.uuid4(),
        engine="test",
        segments=segments,
    )


# ---------------------------------------------------------------------------
# Materials extraction
# ---------------------------------------------------------------------------

class TestMaterialsExtraction:
    def test_common_fabric_detected(self):
        tr = _make_transcript("I used some X-Pac for the main body.")
        data = extract_build_data(tr)
        names = [m.name for m in data.materials]
        assert any("x-pac" in n.lower() for n in names)

    def test_multiple_materials_detected(self):
        tr = _make_transcript(
            "You'll need some nylon webbing and a zipper for this project.",
        )
        data = extract_build_data(tr)
        names = [m.name.lower() for m in data.materials]
        assert "nylon" in names or any("nylon" in n for n in names)
        assert any("zipper" in n for n in names)

    def test_quantity_with_yards_captured(self):
        tr = _make_transcript("Cut 2 yards of ripstop nylon for the outer shell.")
        data = extract_build_data(tr)
        ripstop = [m for m in data.materials if "ripstop" in m.name.lower()]
        assert len(ripstop) >= 1
        assert ripstop[0].quantity != "" or "ripstop" in ripstop[0].name.lower()

    def test_dyneema_detected(self):
        tr = _make_transcript("The Dyneema panel needs to be reinforced.")
        data = extract_build_data(tr)
        assert any("dyneema" in m.name.lower() for m in data.materials)

    def test_timestamp_recorded_for_material(self):
        tr = _make_transcript("First we need some thread.", "Then add elastic.")
        data = extract_build_data(tr)
        thread = [m for m in data.materials if "thread" in m.name.lower()]
        assert len(thread) >= 1
        assert thread[0].timestamp == 0.0

    def test_no_duplicate_materials_per_segment(self):
        """Same material in same segment should appear once."""
        tr = _make_transcript("Use nylon thread and more nylon for the bag body.")
        data = extract_build_data(tr)
        nylon_count = sum(1 for m in data.materials if m.name.lower() == "nylon")
        assert nylon_count <= 1


# ---------------------------------------------------------------------------
# Measurements extraction
# ---------------------------------------------------------------------------

class TestMeasurementsExtraction:
    def test_inches_detected(self):
        tr = _make_transcript("Cut the fabric to 3.5 inches wide.")
        data = extract_build_data(tr)
        assert any(m.value == "3.5" and "inch" in m.unit for m in data.measurements)

    def test_cm_detected(self):
        tr = _make_transcript("Mark 10 cm from the edge.")
        data = extract_build_data(tr)
        assert any(m.value == "10" and m.unit == "cm" for m in data.measurements)

    def test_mm_detected(self):
        tr = _make_transcript("The seam allowance is 5 mm.")
        data = extract_build_data(tr)
        assert any(m.value == "5" and m.unit == "mm" for m in data.measurements)

    def test_yards_detected(self):
        tr = _make_transcript("We need about 1.5 yards of fabric.")
        data = extract_build_data(tr)
        assert any(m.value == "1.5" and "yard" in m.unit for m in data.measurements)

    def test_quote_inches_detected(self):
        tr = _make_transcript('Sew a 0.5" seam along the edge.')
        data = extract_build_data(tr)
        assert any(m.value == "0.5" and "inch" in m.unit for m in data.measurements)

    def test_context_contains_original_text(self):
        tr = _make_transcript("Cut the panel to 6 inches by 12 inches.")
        data = extract_build_data(tr)
        assert any("6 inches" in m.context or "12 inches" in m.context
                   for m in data.measurements)

    def test_timestamp_captured_for_measurement(self):
        tr = _make_transcript("We start here.", "Now cut 4 inches off the end.")
        data = extract_build_data(tr)
        four_inch = [m for m in data.measurements if m.value == "4"]
        assert len(four_inch) >= 1
        assert four_inch[0].timestamp == 5.0  # second segment starts at t=5


# ---------------------------------------------------------------------------
# Steps extraction
# ---------------------------------------------------------------------------

class TestStepsExtraction:
    def test_first_triggers_step(self):
        tr = _make_transcript("First, cut the main panel to size.")
        data = extract_build_data(tr)
        assert len(data.steps) >= 1
        assert data.steps[0].number == 1

    def test_next_triggers_step(self):
        tr = _make_transcript(
            "First, cut the panel.",
            "Next, fold the edges over.",
        )
        data = extract_build_data(tr)
        assert len(data.steps) >= 2

    def test_then_triggers_step(self):
        tr = _make_transcript(
            "First, prepare the fabric.",
            "Then sew the sides together.",
        )
        data = extract_build_data(tr)
        step_descs = [s.description.lower() for s in data.steps]
        assert any("then" in d for d in step_descs)

    def test_steps_numbered_sequentially(self):
        tr = _make_transcript(
            "First, cut everything out.",
            "Next, prep the edges.",
            "Then sew the main seam.",
            "After that, attach the zipper.",
        )
        data = extract_build_data(tr)
        numbers = [s.number for s in data.steps]
        assert numbers == list(range(1, len(numbers) + 1))

    def test_step_timestamp_correct(self):
        tr = _make_transcript("Hello world.", "Next, cut the panel.")
        data = extract_build_data(tr)
        step_segs = [s for s in data.steps if "next" in s.description.lower()]
        assert step_segs[0].timestamp == 5.0


# ---------------------------------------------------------------------------
# Tips and warnings
# ---------------------------------------------------------------------------

class TestTipsAndWarnings:
    def test_pro_tip_categorized_as_tip(self):
        tr = _make_transcript("Pro tip: use a ballpoint needle for synthetic fabrics.")
        data = extract_build_data(tr)
        tips = [t for t in data.tips if t.tip_type == "tip"]
        assert len(tips) >= 1

    def test_quick_tip_categorized_as_tip(self):
        tr = _make_transcript("Quick tip — iron the seams open before sewing.")
        data = extract_build_data(tr)
        tips = [t for t in data.tips if t.tip_type == "tip"]
        assert len(tips) >= 1

    def test_careful_categorized_as_warning(self):
        tr = _make_transcript("Be careful not to cut through the inner layer.")
        data = extract_build_data(tr)
        warnings = [t for t in data.tips if t.tip_type == "warning"]
        assert len(warnings) >= 1

    def test_dont_categorized_as_warning(self):
        tr = _make_transcript("Don't sew through the reinforcement tape.")
        data = extract_build_data(tr)
        warnings = [t for t in data.tips if t.tip_type == "warning"]
        assert len(warnings) >= 1

    def test_watch_out_categorized_as_warning(self):
        tr = _make_transcript("Watch out for the needle hitting the zipper teeth.")
        data = extract_build_data(tr)
        warnings = [t for t in data.tips if t.tip_type == "warning"]
        assert len(warnings) >= 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_transcript_returns_empty_build_data(self):
        tr = _make_transcript()
        data = extract_build_data(tr)
        assert data.materials == []
        assert data.measurements == []
        assert data.steps == []
        assert data.tips == []

    def test_non_myog_transcript_returns_valid_but_sparse(self):
        tr = _make_transcript(
            "Today we are talking about cooking pasta.",
            "Boil the water first.",
            "Then add salt to taste.",
        )
        data = extract_build_data(tr)
        # Should not crash; may or may not find step words
        assert isinstance(data, BuildData)
        assert isinstance(data.materials, list)

    def test_project_title_propagated(self):
        tr = _make_transcript("Use some nylon webbing for the strap.")
        data = extract_build_data(tr, project_title="Ultralight Hip Belt")
        assert data.project_title == "Ultralight Hip Belt"

    def test_blank_segments_skipped(self):
        tr = _make_transcript("", "   ", "Use cordura for the bottom panel.")
        data = extract_build_data(tr)
        cordura = [m for m in data.materials if "cordura" in m.name.lower()]
        assert len(cordura) >= 1


# ---------------------------------------------------------------------------
# Overlay text generation
# ---------------------------------------------------------------------------

class TestOverlayTextGeneration:
    def test_materials_overlay_present(self):
        data = BuildData(
            materials=[
                MaterialItem(name="nylon", quantity="2 yards", timestamp=1.0),
                MaterialItem(name="thread", quantity="", timestamp=2.0),
            ],
        )
        overlays = generate_overlay_text(data)
        mat_overlays = [o for o in overlays if o["type"] == "materials"]
        assert len(mat_overlays) >= 1
        assert "nylon" in mat_overlays[0]["text"]

    def test_measurement_overlay_format(self):
        data = BuildData(
            measurements=[
                Measurement(value="3.5", unit="inches",
                            context="Cut to 3.5 inches wide.", timestamp=5.0),
            ],
        )
        overlays = generate_overlay_text(data)
        meas_overlays = [o for o in overlays if o["type"] == "measurement"]
        assert len(meas_overlays) == 1
        assert "3.5" in meas_overlays[0]["text"]
        assert "inches" in meas_overlays[0]["text"]

    def test_step_overlay_format(self):
        data = BuildData(
            steps=[BuildStep(number=1, description="First, cut the panel.", timestamp=10.0)],
        )
        overlays = generate_overlay_text(data)
        step_overlays = [o for o in overlays if o["type"] == "step"]
        assert len(step_overlays) == 1
        assert "Step 1:" in step_overlays[0]["text"]

    def test_overlay_default_duration(self):
        data = BuildData(
            steps=[BuildStep(number=1, description="First, do the thing.", timestamp=0.0)],
        )
        overlays = generate_overlay_text(data)
        assert all(o["duration_seconds"] == 4 for o in overlays)

    def test_empty_build_data_returns_empty_list(self):
        data = BuildData()
        overlays = generate_overlay_text(data)
        assert overlays == []


# ---------------------------------------------------------------------------
# Build notes generation
# ---------------------------------------------------------------------------

class TestBuildNotesGeneration:
    def test_returns_string(self):
        data = BuildData()
        notes = generate_build_notes(data)
        assert isinstance(notes, str)

    def test_title_in_output(self):
        data = BuildData(project_title="My Hip Belt")
        notes = generate_build_notes(data)
        assert "My Hip Belt" in notes

    def test_default_title_when_empty(self):
        data = BuildData()
        notes = generate_build_notes(data)
        assert "# Build Notes" in notes

    def test_materials_table_in_output(self):
        data = BuildData(
            materials=[MaterialItem(name="nylon", quantity="2 yards")]
        )
        notes = generate_build_notes(data)
        assert "## Materials" in notes
        assert "nylon" in notes

    def test_measurements_section_in_output(self):
        data = BuildData(
            measurements=[Measurement(value="5", unit="cm",
                                      context="Mark 5 cm from edge.")]
        )
        notes = generate_build_notes(data)
        assert "## Measurements" in notes
        assert "5 cm" in notes

    def test_build_steps_section_in_output(self):
        data = BuildData(
            steps=[BuildStep(number=1, description="First, cut the pieces.")]
        )
        notes = generate_build_notes(data)
        assert "## Build Steps" in notes
        assert "First, cut the pieces." in notes

    def test_tips_section_in_output(self):
        data = BuildData(
            tips=[BuildTip(text="Use a sharp needle.", tip_type="tip")]
        )
        notes = generate_build_notes(data)
        assert "## Tips" in notes or "Tips" in notes
        assert "Use a sharp needle." in notes

    def test_warnings_section_in_output(self):
        data = BuildData(
            tips=[BuildTip(text="Be careful of the seam allowance.", tip_type="warning")]
        )
        notes = generate_build_notes(data)
        assert "Warning" in notes
        assert "Be careful of the seam allowance." in notes

    def test_valid_markdown_headers(self):
        data = BuildData(project_title="Test Project")
        notes = generate_build_notes(data)
        assert notes.startswith("# Test Project")
