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
