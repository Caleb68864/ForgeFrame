"""Tests for blend-mode composite pipeline (apply_composite + mapping).

Deviation note: ``BLEND_MODE_TO_MLT`` is ``dict[str, MltBlendTarget]`` (not
``dict[str, str]``) because Kdenlive blend modes are split across two MLT
services -- ``frei0r.cairoblend`` (string-enum on property ``"1"``) and
``qtblend`` (integer-enum on property ``compositing``). The authoritative
``BLEND_MODES`` set has 20 members (``subtract`` dropped -- no native MLT
mapping).
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.edit_mcp.pipelines.compositing import (
    BLEND_MODES,
    BLEND_MODE_TO_MLT,
    MltBlendTarget,
    apply_composite,
)


EXPECTED_MODES = frozenset({
    "cairoblend",
    "screen", "lighten", "darken", "multiply", "add", "overlay",
    "destination_in", "destination_out", "source_over",
    "hard_light", "soft_light", "color_dodge", "color_burn",
    "difference", "exclusion",
    "hue", "saturation", "color", "luminosity",
})


def _make_project(width: int = 1920, height: int = 1080) -> KdenliveProject:
    return KdenliveProject.model_validate({
        "profile": {"width": width, "height": height, "colorspace": "709"},
        "tracks": [{"id": "0"}, {"id": "1"}, {"id": "2"}],
    })


# ---------------------------------------------------------------------------
# SR-01..SR-05: constant surface
# ---------------------------------------------------------------------------

class TestBlendModeConstants:
    def test_blend_modes_set_exact_membership(self):
        """SR-01: BLEND_MODES is exactly the 20 authoritative names."""
        assert BLEND_MODES == EXPECTED_MODES
        assert len(BLEND_MODES) == 20

    def test_blend_modes_does_not_contain_subtract(self):
        """SR-01b: subtract explicitly removed (no native MLT mapping)."""
        assert "subtract" not in BLEND_MODES

    def test_blend_mode_to_mlt_has_all_modes(self):
        """SR-02: every BLEND_MODES member has a mapping entry."""
        for mode in BLEND_MODES:
            assert mode in BLEND_MODE_TO_MLT, f"missing mapping for {mode!r}"

    def test_blend_mode_mapping_screen(self):
        """SR-03: screen -> frei0r.cairoblend / "1" / "screen"."""
        target = BLEND_MODE_TO_MLT["screen"]
        assert isinstance(target, MltBlendTarget)
        assert target.service == "frei0r.cairoblend"
        assert target.property_name == "1"
        assert target.value == "screen"

    def test_blend_mode_mapping_destination_in(self):
        """SR-04: destination_in -> qtblend / "compositing" / "6"."""
        target = BLEND_MODE_TO_MLT["destination_in"]
        assert target.service == "qtblend"
        assert target.property_name == "compositing"
        assert target.value == "6"

    def test_blend_mode_mapping_destination_out(self):
        target = BLEND_MODE_TO_MLT["destination_out"]
        assert target.service == "qtblend"
        assert target.property_name == "compositing"
        assert target.value == "8"

    def test_blend_mode_mapping_source_over(self):
        """SR-05: source_over -> qtblend / "compositing" / "0"."""
        target = BLEND_MODE_TO_MLT["source_over"]
        assert target.service == "qtblend"
        assert target.property_name == "compositing"
        assert target.value == "0"

    def test_blend_mode_mapping_cairoblend_normal(self):
        target = BLEND_MODE_TO_MLT["cairoblend"]
        assert target.service == "frei0r.cairoblend"
        assert target.property_name == "1"
        assert target.value == "normal"

    @pytest.mark.parametrize("mode,expected_value", [
        ("hard_light", "hardlight"),
        ("soft_light", "softlight"),
        ("color_dodge", "colordodge"),
        ("color_burn", "colorburn"),
        ("hue", "hslhue"),
        ("saturation", "hslsaturation"),
        ("color", "hslcolor"),
        ("luminosity", "hslluminosity"),
    ])
    def test_cairoblend_name_normalization(self, mode, expected_value):
        target = BLEND_MODE_TO_MLT[mode]
        assert target.service == "frei0r.cairoblend"
        assert target.property_name == "1"
        assert target.value == expected_value


# ---------------------------------------------------------------------------
# SR-06..SR-10: apply_composite emission behavior
# ---------------------------------------------------------------------------

class TestApplyCompositeEmission:
    def test_apply_composite_emits_screen(self):
        """SR-06: apply_composite(blend_mode='screen') emits a transition
        with mlt_service='frei0r.cairoblend' and property '1'='screen'."""
        project = _make_project()
        result = apply_composite(project, 1, 2, 0, 120, blend_mode="screen")

        new_elems = [e for e in result.opaque_elements if e.tag == "transition"]
        assert len(new_elems) == 1
        xml = new_elems[0].xml_string
        assert 'mlt_service="frei0r.cairoblend"' in xml
        assert '<property name="1">screen</property>' in xml
        assert '<property name="a_track">1</property>' in xml
        assert '<property name="b_track">2</property>' in xml
        assert '<property name="in">0</property>' in xml
        assert '<property name="out">120</property>' in xml

    def test_apply_composite_emits_destination_in(self):
        """SR-07: destination_in routes through qtblend / compositing=6."""
        project = _make_project()
        result = apply_composite(project, 0, 1, 10, 200, blend_mode="destination_in")
        xml = [e for e in result.opaque_elements if e.tag == "transition"][0].xml_string
        assert 'mlt_service="qtblend"' in xml
        assert '<property name="compositing">6</property>' in xml

    def test_apply_composite_default_geometry(self):
        """SR-08: geometry=None produces '0/0:WxH:100' from project profile."""
        project = _make_project(width=1920, height=1080)
        result = apply_composite(project, 0, 1, 0, 60, blend_mode="multiply")
        xml = [e for e in result.opaque_elements if e.tag == "transition"][0].xml_string
        assert '<property name="geometry">0/0:1920x1080:100</property>' in xml

    def test_apply_composite_default_geometry_4k(self):
        project = _make_project(width=3840, height=2160)
        result = apply_composite(project, 0, 1, 0, 60, blend_mode="overlay")
        xml = [e for e in result.opaque_elements if e.tag == "transition"][0].xml_string
        assert '<property name="geometry">0/0:3840x2160:100</property>' in xml

    def test_apply_composite_custom_geometry(self):
        """SR-09: explicit geometry passes through unchanged."""
        project = _make_project()
        result = apply_composite(
            project, 0, 1, 0, 60,
            blend_mode="darken",
            geometry="100/50:1920x1080:75",
        )
        xml = [e for e in result.opaque_elements if e.tag == "transition"][0].xml_string
        assert '<property name="geometry">100/50:1920x1080:75</property>' in xml

    def test_apply_composite_default_blend_mode_is_cairoblend(self):
        """SR-10: default blend_mode='cairoblend' -> frei0r.cairoblend normal."""
        project = _make_project()
        result = apply_composite(project, 0, 1, 0, 60)
        xml = [e for e in result.opaque_elements if e.tag == "transition"][0].xml_string
        assert 'mlt_service="frei0r.cairoblend"' in xml
        assert '<property name="1">normal</property>' in xml


# ---------------------------------------------------------------------------
# SR-11..SR-13: validation
# ---------------------------------------------------------------------------

class TestApplyCompositeValidation:
    def test_apply_composite_unknown_mode_raises(self):
        """SR-11: unknown blend_mode raises ValueError naming bad mode + valids."""
        project = _make_project()
        with pytest.raises(ValueError) as exc:
            apply_composite(project, 0, 1, 0, 60, blend_mode="bogus")
        msg = str(exc.value)
        assert "bogus" in msg
        # Sample check: at least a few valid modes listed
        assert "screen" in msg
        assert "destination_in" in msg

    def test_apply_composite_subtract_raises(self):
        """subtract is NOT in BLEND_MODES -> ValueError."""
        project = _make_project()
        with pytest.raises(ValueError, match="subtract"):
            apply_composite(project, 0, 1, 0, 60, blend_mode="subtract")

    def test_apply_composite_same_track_raises(self):
        """SR-12: track_a == track_b raises ValueError."""
        project = _make_project()
        with pytest.raises(ValueError, match="different tracks"):
            apply_composite(project, 1, 1, 0, 60, blend_mode="screen")

    def test_apply_composite_bad_frames_raises(self):
        """SR-13: end_frame <= start_frame raises ValueError."""
        project = _make_project()
        with pytest.raises(ValueError, match="greater than"):
            apply_composite(project, 0, 1, 100, 100, blend_mode="screen")
        with pytest.raises(ValueError, match="greater than"):
            apply_composite(project, 0, 1, 100, 50, blend_mode="screen")


# ---------------------------------------------------------------------------
# SR-14: immutability / deep-copy
# ---------------------------------------------------------------------------

class TestApplyCompositeImmutability:
    def test_apply_composite_does_not_mutate_input(self):
        """SR-14: original project untouched; result has exactly one new element."""
        project = _make_project()
        before_count = len(project.opaque_elements)
        snapshot = deepcopy(project)

        result = apply_composite(project, 0, 1, 0, 60, blend_mode="screen")

        # original untouched
        assert len(project.opaque_elements) == before_count
        assert project.model_dump() == snapshot.model_dump()
        # result has one new element
        assert len(result.opaque_elements) == before_count + 1
        assert result is not project
