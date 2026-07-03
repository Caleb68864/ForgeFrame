"""Unit tests for animated rotoscoping (keyframed spline) + mode selection."""
from __future__ import annotations

import json
import re

import pytest

from workshop_video_brain.edit_mcp.pipelines import masking


def _spline_of(xml: str, prop: str = "spline") -> dict:
    m = re.search(rf'name="{re.escape(prop)}">(.*?)</property>', xml, re.S)
    assert m, f"no {prop} property in xml"
    return json.loads(m.group(1))


_BOX_A = ((0.1, 0.25), (0.4, 0.25), (0.4, 0.75), (0.1, 0.75))
_BOX_B = ((0.6, 0.25), (0.9, 0.25), (0.9, 0.75), (0.6, 0.75))


def test_static_points_emit_frame0_only():
    mask = masking.MaskParams(points=_BOX_A)
    spline = _spline_of(masking.build_rotoscoping_xml((1, 0), mask))
    assert list(spline.keys()) == ["0"]


def test_keyframed_spline_emits_multiple_frames():
    mask = masking.MaskParams(spline_keyframes={0: _BOX_A, 48: _BOX_B})
    spline = _spline_of(masking.build_rotoscoping_xml((1, 0), mask))
    assert list(spline.keys()) == ["0", "48"]
    # Each point is [anchor, handle_in, handle_out].
    assert spline["0"][0] == [[0.1, 0.25], [0.1, 0.25], [0.1, 0.25]]
    assert spline["48"][0][0] == [0.6, 0.25]


def test_keyframes_sorted_ascending():
    mask = masking.MaskParams(spline_keyframes={48: _BOX_B, 0: _BOX_A, 24: _BOX_A})
    spline = _spline_of(masking.build_rotoscoping_xml((1, 0), mask))
    assert list(spline.keys()) == ["0", "24", "48"]


def test_mode_defaults_alpha_and_can_be_luma():
    assert 'name="mode">alpha' in masking.build_rotoscoping_xml((1, 0), masking.MaskParams(points=_BOX_A))
    luma = masking.build_rotoscoping_xml((1, 0), masking.MaskParams(points=_BOX_A, mode="luma"))
    assert 'name="mode">luma' in luma


def test_mask_start_form_carries_keyframes_and_mode():
    mask = masking.MaskParams(spline_keyframes={0: _BOX_A, 48: _BOX_B}, mode="luma")
    xml = masking.build_mask_start_rotoscoping_xml((1, 0), mask)
    assert 'name="filter.mode">luma' in xml
    spline = _spline_of(xml, prop="filter.spline")
    assert list(spline.keys()) == ["0", "48"]


def test_requires_points_or_keyframes():
    with pytest.raises(Exception):
        masking.MaskParams()


def test_keyframe_frame_and_point_validation():
    with pytest.raises(Exception):
        masking.MaskParams(spline_keyframes={-1: _BOX_A})
    with pytest.raises(Exception):
        masking.MaskParams(spline_keyframes={0: ((0.1, 0.1), (0.2, 0.2))})  # < 3 points
    with pytest.raises(Exception):
        masking.MaskParams(spline_keyframes={0: ((1.5, 0.1), (0.2, 0.2), (0.3, 0.3))})  # out of range


def test_invalid_mode_rejected():
    with pytest.raises(Exception):
        masking.MaskParams(points=_BOX_A, mode="sideways")
