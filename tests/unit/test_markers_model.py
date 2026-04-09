"""Tests for Marker, MarkerGroup, MarkerRule, MarkerConfig (MD-04)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.markers import (
    Marker,
    MarkerConfig,
    MarkerGroup,
    MarkerRule,
)


# ---------------------------------------------------------------------------
# Marker
# ---------------------------------------------------------------------------

def test_marker_defaults():
    m = Marker(category=MarkerCategory.intro_candidate)
    assert m.confidence_score == 0.0
    assert m.source_method == ""
    assert m.reason == ""
    assert m.clip_ref == ""
    assert m.start_seconds == 0.0
    assert m.end_seconds == 0.0
    assert m.suggested_label == ""


def test_marker_id_auto_generated():
    m1 = Marker(category=MarkerCategory.hook_candidate)
    m2 = Marker(category=MarkerCategory.hook_candidate)
    assert m1.id != m2.id


def test_marker_category_required():
    with pytest.raises(ValidationError):
        Marker()  # type: ignore[call-arg]


def test_marker_enum_stored_as_string():
    m = Marker(category=MarkerCategory.intro_candidate)
    assert isinstance(m.category, str)
    assert m.category == "intro_candidate"
    assert not isinstance(m.category, MarkerCategory)


def test_marker_all_fields():
    m = Marker(
        category=MarkerCategory.step_explanation,
        confidence_score=0.8,
        source_method="transcript",
        reason="mentions step",
        clip_ref="clip_001.mp4",
        start_seconds=10.5,
        end_seconds=25.0,
        suggested_label="Step 3",
    )
    d = m.model_dump()
    assert d["confidence_score"] == 0.8
    assert d["source_method"] == "transcript"
    assert d["start_seconds"] == 10.5


def test_marker_json_round_trip():
    m = Marker(category=MarkerCategory.dead_air, start_seconds=5.0, end_seconds=8.0)
    m2 = Marker.from_json(m.to_json())
    assert m2 == m


def test_marker_yaml_round_trip():
    m = Marker(category=MarkerCategory.broll_candidate, confidence_score=0.7)
    m2 = Marker.from_yaml(m.to_yaml())
    assert m2 == m


# ---------------------------------------------------------------------------
# MarkerGroup
# ---------------------------------------------------------------------------

def test_marker_group_defaults():
    mg = MarkerGroup(category=MarkerCategory.chapter_candidate)
    assert mg.markers == []
    assert mg.source == ""


def test_marker_group_category_required():
    with pytest.raises(ValidationError):
        MarkerGroup()  # type: ignore[call-arg]


def test_marker_group_with_markers():
    m = Marker(category=MarkerCategory.intro_candidate)
    mg = MarkerGroup(category=MarkerCategory.intro_candidate, markers=[m])
    mg2 = MarkerGroup.from_json(mg.to_json())
    assert len(mg2.markers) == 1


# ---------------------------------------------------------------------------
# MarkerRule
# ---------------------------------------------------------------------------

def test_marker_rule_required():
    with pytest.raises(ValidationError):
        MarkerRule()  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        MarkerRule(keywords=["step"], category=MarkerCategory.step_explanation)  # type: ignore[call-arg]


def test_marker_rule_all_fields():
    r = MarkerRule(
        keywords=["step", "next"],
        category=MarkerCategory.step_explanation,
        base_confidence=0.9,
    )
    d = r.model_dump()
    assert d["keywords"] == ["step", "next"]
    assert d["base_confidence"] == 0.9


# ---------------------------------------------------------------------------
# MarkerConfig
# ---------------------------------------------------------------------------

def test_marker_config_defaults():
    mc = MarkerConfig()
    assert mc.rules == []
    assert mc.category_weights == {}
    assert mc.silence_threshold_seconds == 2.0
    assert mc.segment_merge_gap_seconds == 3.0


def test_marker_config_with_rules():
    rule = MarkerRule(
        keywords=["caution"],
        category=MarkerCategory.important_caution,
        base_confidence=0.85,
    )
    mc = MarkerConfig(rules=[rule])
    mc2 = MarkerConfig.from_json(mc.to_json())
    assert len(mc2.rules) == 1
    assert mc2.rules[0].keywords == ["caution"]


def test_marker_config_category_weights():
    mc = MarkerConfig(category_weights={"intro_candidate": 1.5, "dead_air": 0.5})
    d = mc.model_dump()
    assert d["category_weights"]["intro_candidate"] == 1.5


def test_marker_invalid_category():
    with pytest.raises(ValidationError):
        Marker(category="totally_invalid_category")


def test_marker_confidence_boundary():
    m1 = Marker(category=MarkerCategory.intro_candidate, confidence_score=0.0)
    m2 = Marker(category=MarkerCategory.intro_candidate, confidence_score=1.0)
    assert m1.confidence_score == 0.0
    assert m2.confidence_score == 1.0
