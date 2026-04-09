"""Tests for SerializableMixin JSON/YAML round-trip (MD-01)."""
from __future__ import annotations

import json

import pytest
import yaml
from workshop_video_brain.core.models._base import SerializableMixin


class _Fixture(SerializableMixin):
    name: str
    value: int = 0


def test_to_json():
    f = _Fixture(name="test", value=42)
    result = f.to_json()
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert parsed == f.model_dump(mode="json")


def test_from_json():
    f = _Fixture(name="hello", value=7)
    result = _Fixture.from_json(f.to_json())
    assert result == f


def test_json_round_trip():
    f = _Fixture(name="round", value=99)
    assert _Fixture.from_json(f.to_json()) == f


def test_to_yaml():
    f = _Fixture(name="yaml_test", value=1)
    result = f.to_yaml()
    assert isinstance(result, str)
    parsed = yaml.safe_load(result)
    assert isinstance(parsed, dict)
    assert parsed["name"] == "yaml_test"


def test_from_yaml():
    f = _Fixture(name="yaml_test", value=5)
    result = _Fixture.from_yaml(f.to_yaml())
    assert result == f


def test_yaml_round_trip():
    f = _Fixture(name="trip", value=3)
    assert _Fixture.from_yaml(f.to_yaml()) == f


def test_yaml_unicode():
    f = _Fixture(name="café", value=0)
    result = _Fixture.from_yaml(f.to_yaml())
    assert result.name == "café"


def test_yaml_no_enum_instances():
    f = _Fixture(name="plain", value=2)
    yaml_str = f.to_yaml()
    parsed = yaml.safe_load(yaml_str)
    # All values should be plain Python scalars
    for v in parsed.values():
        assert isinstance(v, (str, int, float, bool, type(None)))


def test_from_json_bytes():
    f = _Fixture(name="bytes_test", value=0)
    result = _Fixture.from_json(f.to_json().encode())
    assert result == f


def test_from_yaml_bytes():
    f = _Fixture(name="ybytes_test", value=0)
    result = _Fixture.from_yaml(f.to_yaml().encode())
    assert result == f
