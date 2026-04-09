"""Tests for ClipLabel construction, defaults, and serialization (MD-06)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from workshop_video_brain.core.models.clips import ClipLabel


def test_clip_label_default_construction():
    label = ClipLabel()
    assert label is not None


def test_clip_label_defaults():
    label = ClipLabel()
    assert label.clip_ref == ""
    assert label.content_type == "unlabeled"
    assert label.shot_type == "medium"
    assert label.has_speech is False
    assert label.speech_density == 0.0
    assert label.summary == ""
    assert label.duration == 0.0
    assert label.source_path == ""


def test_clip_label_default_topics_empty():
    label = ClipLabel()
    assert label.topics == []


def test_clip_label_default_tags_empty():
    label = ClipLabel()
    assert label.tags == []


def test_clip_label_mutable_default_isolation():
    label1 = ClipLabel()
    label2 = ClipLabel()
    assert label1.topics is not label2.topics
    label1.topics.append("test")
    assert label2.topics == []


def test_clip_label_all_fields():
    label = ClipLabel(
        clip_ref="clip_001.mp4",
        content_type="tutorial_step",
        topics=["wood", "joinery"],
        shot_type="closeup",
        has_speech=True,
        speech_density=0.75,
        summary="Cut the wood to length",
        tags=["tutorial_step", "closeup", "wood"],
        duration=15.5,
        source_path="/footage/clip_001.mp4",
    )
    d = label.model_dump()
    assert d["clip_ref"] == "clip_001.mp4"
    assert d["content_type"] == "tutorial_step"
    assert d["speech_density"] == 0.75


def test_clip_label_content_types():
    for ct in ["tutorial_step", "materials_overview", "talking_head", "b_roll", "unlabeled"]:
        label = ClipLabel(content_type=ct)
        assert label.content_type == ct


def test_clip_label_speech_density_boundary():
    label1 = ClipLabel(speech_density=0.0)
    label2 = ClipLabel(speech_density=1.0)
    assert label1.speech_density == 0.0
    assert label2.speech_density == 1.0


def test_clip_label_speech_density_beyond_range():
    # No range validator in source -- values beyond 1.0 are accepted
    label = ClipLabel(speech_density=1.5)
    assert label.speech_density == 1.5


def test_clip_label_has_speech_true():
    label = ClipLabel(has_speech=True)
    assert label.has_speech is True


def test_clip_label_topics_populated():
    label = ClipLabel(topics=["mortise", "tenon", "woodworking"])
    d = label.model_dump()
    assert d["topics"] == ["mortise", "tenon", "woodworking"]
    label2 = ClipLabel.model_validate(d)
    assert label2.topics == ["mortise", "tenon", "woodworking"]


def test_clip_label_json_round_trip():
    label = ClipLabel(clip_ref="c1.mp4", has_speech=True, topics=["saw", "blade"])
    label2 = ClipLabel.from_json(label.to_json())
    assert label2 == label


def test_clip_label_yaml_round_trip():
    label = ClipLabel(content_type="b_roll", duration=5.0)
    label2 = ClipLabel.from_yaml(label.to_yaml())
    assert label2 == label


def test_clip_label_empty_string_fields():
    label = ClipLabel(
        clip_ref="",
        content_type="",
        shot_type="",
        summary="",
        source_path="",
    )
    assert label.clip_ref == ""
    assert label.content_type == ""
