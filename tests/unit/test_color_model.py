"""Tests for ColorAnalysis construction, None optionals, and serialization (MD-07)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from workshop_video_brain.core.models.color import ColorAnalysis


def test_color_analysis_required():
    with pytest.raises(ValidationError):
        ColorAnalysis()  # type: ignore[call-arg]


def test_color_analysis_defaults():
    ca = ColorAnalysis(file_path="/footage/clip.mp4")
    assert ca.color_space is None
    assert ca.color_primaries is None
    assert ca.color_transfer is None
    assert ca.bit_depth is None
    assert ca.is_hdr is False
    assert ca.recommendations == []


def test_color_analysis_all_fields():
    ca = ColorAnalysis(
        file_path="/footage/hdr.mp4",
        color_space="bt2020nc",
        color_primaries="bt2020",
        color_transfer="smpte2084",
        bit_depth=10,
        is_hdr=True,
        recommendations=["Apply LUT", "Check tone mapping"],
    )
    d = ca.model_dump()
    assert d["file_path"] == "/footage/hdr.mp4"
    assert d["color_space"] == "bt2020nc"
    assert d["bit_depth"] == 10
    assert d["is_hdr"] is True
    assert d["recommendations"] == ["Apply LUT", "Check tone mapping"]


def test_color_analysis_is_hdr_true():
    ca = ColorAnalysis(file_path="/footage/hdr.mp4", is_hdr=True)
    assert ca.is_hdr is True


def test_color_analysis_bit_depth_values():
    for depth in [8, 10, 12]:
        ca = ColorAnalysis(file_path="/f.mp4", bit_depth=depth)
        assert ca.bit_depth == depth


def test_color_analysis_bit_depth_none():
    ca = ColorAnalysis(file_path="/f.mp4", bit_depth=None)
    d = ca.model_dump()
    assert d["bit_depth"] is None


def test_color_analysis_recommendations():
    ca = ColorAnalysis(file_path="/f.mp4", recommendations=["r1", "r2"])
    d = ca.model_dump()
    assert d["recommendations"] == ["r1", "r2"]
    ca2 = ColorAnalysis.model_validate(d)
    assert ca2.recommendations == ["r1", "r2"]


def test_color_analysis_default_recommendations_mutable_isolation():
    ca1 = ColorAnalysis(file_path="/f1.mp4")
    ca2 = ColorAnalysis(file_path="/f2.mp4")
    ca1.recommendations.append("test")
    assert ca2.recommendations == []


def test_color_analysis_no_serializable_mixin():
    ca = ColorAnalysis(file_path="/f.mp4")
    assert not hasattr(ca, "to_json")
    assert not hasattr(ca, "to_yaml")
    assert not hasattr(ca, "from_json")
    assert not hasattr(ca, "from_yaml")


def test_color_analysis_model_dump_round_trip():
    ca = ColorAnalysis(file_path="/f.mp4", bit_depth=10, is_hdr=True)
    ca2 = ColorAnalysis.model_validate(ca.model_dump())
    assert ca2 == ca


def test_color_analysis_model_dump_json_round_trip():
    ca = ColorAnalysis(file_path="/f.mp4", color_space="bt709")
    ca2 = ColorAnalysis.model_validate_json(ca.model_dump_json())
    assert ca2 == ca


def test_color_analysis_none_fields_in_dump():
    ca = ColorAnalysis(file_path="/f.mp4")
    d = ca.model_dump()
    assert "color_space" in d
    assert d["color_space"] is None
    assert "bit_depth" in d
    assert d["bit_depth"] is None
