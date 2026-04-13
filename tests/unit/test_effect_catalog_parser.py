"""Unit tests for effect_catalog_gen parser and data model."""
from __future__ import annotations

import dataclasses
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.pipelines.effect_catalog_gen import (
    EffectDef,
    ParamDef,
    ParamType,
    parse_effect_xml,
    parse_param,
)

FIXTURES = Path(__file__).parent / "fixtures" / "effect_xml"


def _find_param(effect: EffectDef, name: str) -> ParamDef:
    for p in effect.params:
        if p.name == name:
            return p
    raise AssertionError(f"param {name!r} not in effect {effect.kdenlive_id}")


# SS1-01
def test_paramtype_enum_covers_known_set():
    expected = {
        "CONSTANT", "DOUBLE", "INTEGER", "BOOL", "SWITCH", "COLOR",
        "KEYFRAME", "ANIMATED", "GEOMETRY", "LIST", "FIXED", "POSITION",
        "URL", "STRING", "READONLY", "HIDDEN",
    }
    assert {m.name for m in ParamType} == expected


# SS1-02
def test_effectdef_fields_present():
    e = EffectDef(
        kdenlive_id="x",
        mlt_service="y",
        display_name="Z",
        description="d",
        category="audio",
        params=(),
    )
    assert e.kdenlive_id == "x"
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.kdenlive_id = "other"  # type: ignore[misc]


# SS1-03
def test_paramdef_fields_present():
    p = ParamDef(
        name="a", display_name="A", type=ParamType.CONSTANT,
        default=None, min=None, max=None, decimals=None,
        values=(), value_labels=(), keyframable=False,
    )
    assert p.name == "a"
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.name = "b"  # type: ignore[misc]


# SS1-04
def test_parse_acompressor_fixture():
    e = parse_effect_xml(FIXTURES / "acompressor.xml")
    assert e.kdenlive_id == "acompressor"
    assert e.mlt_service == "avfilter.acompressor"
    assert e.display_name == "Compressor (avfilter)"
    assert e.category == "audio"
    assert e.description == "Audio Compressor"
    assert len(e.params) == 11


# SS1-05
def test_parse_list_param_with_display():
    e = parse_effect_xml(FIXTURES / "acompressor.xml")
    link = _find_param(e, "av.link")
    assert link.type is ParamType.LIST
    assert link.values == ("0", "1")
    assert link.value_labels == ("Average", "Maximum")


# SS1-06
def test_parse_list_param_without_display():
    e = parse_effect_xml(FIXTURES / "list_no_display.xml")
    p = _find_param(e, "mode")
    assert p.values == ("0", "1", "2")
    assert p.value_labels == ("0", "1", "2")


# SS1-07
def test_parse_animated_type_keyframable():
    e = parse_effect_xml(FIXTURES / "animated_param.xml")
    p = _find_param(e, "rect")
    assert p.type is ParamType.ANIMATED
    assert p.keyframable is True


# SS1-08
def test_parse_keyframes_attr_keyframable():
    e = parse_effect_xml(FIXTURES / "keyframes_attr.xml")
    p = _find_param(e, "opacity")
    assert p.type is ParamType.CONSTANT
    assert p.keyframable is True


# SS1-09
def test_parse_constant_no_keyframes_not_keyframable():
    e = parse_effect_xml(FIXTURES / "acompressor.xml")
    p = _find_param(e, "av.level_in")
    assert p.type is ParamType.CONSTANT
    assert p.keyframable is False


# SS1-10
def test_unknown_param_type_raises():
    with pytest.raises(ValueError) as exc_info:
        parse_effect_xml(FIXTURES / "unknown_type.xml")
    msg = str(exc_info.value)
    assert "quantum_flux" in msg
    assert "unknown_type.xml" in msg


# SS1-11
def test_kdenlive_id_from_filename_stem(tmp_path):
    dst = tmp_path / "foo.xml"
    shutil.copy(FIXTURES / "acompressor.xml", dst)
    e = parse_effect_xml(dst)
    assert e.kdenlive_id == "foo"


# SS1-12
def test_missing_default_attr():
    e = parse_effect_xml(FIXTURES / "animated_param.xml")
    # synthesize a constant w/o default by stripping
    elem = ET.fromstring(
        '<parameter type="constant" name="x"><name>X</name></parameter>'
    )
    p = parse_param(elem)
    assert p.default is None
    # also verify the animated fixture's param has its default set (sanity)
    assert _find_param(e, "rect").default == "0 0 100 100"


# SS1-13
def test_missing_min_max():
    elem = ET.fromstring(
        '<parameter type="constant" name="x" default="1"><name>X</name></parameter>'
    )
    p = parse_param(elem)
    assert p.min is None
    assert p.max is None
    assert p.decimals is None


# SS1-14
def test_localized_name_prefers_no_lang():
    e = parse_effect_xml(FIXTURES / "localized_name.xml")
    assert e.display_name == "Foo"
    p = _find_param(e, "x")
    assert p.display_name == "X"


# SS1-15
def test_empty_description_is_empty_string():
    e = parse_effect_xml(FIXTURES / "animated_param.xml")
    assert e.description == ""
    assert e.description is not None
