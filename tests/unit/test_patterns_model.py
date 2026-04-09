"""Tests for BuildData, BuildStep, MaterialItem, Measurement, BuildTip (MD-08)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from workshop_video_brain.core.models.patterns import (
    BuildData,
    BuildStep,
    BuildTip,
    MaterialItem,
    Measurement,
)


# ---------------------------------------------------------------------------
# MaterialItem
# ---------------------------------------------------------------------------

def test_material_item_required():
    with pytest.raises(ValidationError):
        MaterialItem()  # type: ignore[call-arg]


def test_material_item_defaults():
    m = MaterialItem(name="Canvas")
    assert m.quantity == ""
    assert m.notes == ""
    assert m.timestamp == 0.0


def test_material_item_all_fields():
    m = MaterialItem(name="Webbing", quantity="2 yards", notes="1-inch wide", timestamp=5.5)
    d = m.model_dump()
    assert d["name"] == "Webbing"
    assert d["quantity"] == "2 yards"
    m2 = MaterialItem.model_validate(d)
    assert m2 == m


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def test_measurement_required():
    with pytest.raises(ValidationError):
        Measurement()  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        Measurement(value="3.5", unit="inches")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        Measurement(value="3.5", context="cut to 3.5")  # type: ignore[call-arg]


def test_measurement_defaults():
    m = Measurement(value="3.5", unit="inches", context="cut the strap")
    assert m.timestamp == 0.0


def test_measurement_all_fields():
    m = Measurement(value="6", unit="oz", context="use 6oz canvas", timestamp=12.0)
    d = m.model_dump()
    assert d["value"] == "6"
    assert d["unit"] == "oz"
    assert d["timestamp"] == 12.0
    m2 = Measurement.from_json(m.to_json())
    assert m2 == m


# ---------------------------------------------------------------------------
# BuildStep
# ---------------------------------------------------------------------------

def test_build_step_required():
    with pytest.raises(ValidationError):
        BuildStep()  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        BuildStep(number=1)  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        BuildStep(description="Sand edges")  # type: ignore[call-arg]


def test_build_step_defaults():
    s = BuildStep(number=1, description="Cut fabric")
    assert s.timestamp == 0.0


def test_build_step_all_fields():
    s = BuildStep(number=3, description="Sand edges", timestamp=42.5)
    d = s.model_dump()
    assert d["number"] == 3
    assert d["description"] == "Sand edges"
    assert d["timestamp"] == 42.5
    s2 = BuildStep.model_validate(d)
    assert s2 == s


def test_build_step_number_zero():
    s = BuildStep(number=0, description="Introduction")
    assert s.number == 0


# ---------------------------------------------------------------------------
# BuildTip
# ---------------------------------------------------------------------------

def test_build_tip_required():
    with pytest.raises(ValidationError):
        BuildTip()  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        BuildTip(text="Watch out")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        BuildTip(tip_type="warning")  # type: ignore[call-arg]


def test_build_tip_defaults():
    t = BuildTip(text="Go slow", tip_type="tip")
    assert t.timestamp == 0.0


def test_build_tip_types():
    t1 = BuildTip(text="Watch out", tip_type="tip")
    t2 = BuildTip(text="Danger!", tip_type="warning")
    assert t1.tip_type == "tip"
    assert t2.tip_type == "warning"


# ---------------------------------------------------------------------------
# BuildData
# ---------------------------------------------------------------------------

def test_build_data_default_construction():
    bd = BuildData()
    assert bd is not None


def test_build_data_defaults():
    bd = BuildData()
    assert bd.project_title == ""
    assert bd.materials == []
    assert bd.measurements == []
    assert bd.steps == []
    assert bd.tips == []


def test_build_data_mutable_default_isolation():
    bd1 = BuildData()
    bd2 = BuildData()
    assert bd1.materials is not bd2.materials
    assert bd1.steps is not bd2.steps
    bd1.steps.append(BuildStep(number=1, description="test"))
    assert bd2.steps == []


def test_build_data_all_fields():
    bd = BuildData(
        project_title="My Bag",
        materials=[MaterialItem(name="Canvas")],
        measurements=[Measurement(value="12", unit="inches", context="cut")],
        steps=[BuildStep(number=1, description="Cut")],
        tips=[BuildTip(text="Be careful", tip_type="warning")],
    )
    d = bd.model_dump()
    assert d["project_title"] == "My Bag"
    assert len(d["materials"]) == 1
    assert len(d["measurements"]) == 1
    assert len(d["steps"]) == 1
    assert len(d["tips"]) == 1


def test_build_data_json_round_trip():
    bd = BuildData(
        project_title="Pack Build",
        steps=[BuildStep(number=1, description="Trace pattern", timestamp=5.0)],
    )
    bd2 = BuildData.from_json(bd.to_json())
    assert bd2.project_title == "Pack Build"
    assert len(bd2.steps) == 1
    assert bd2.steps[0].description == "Trace pattern"


def test_build_data_yaml_round_trip():
    bd = BuildData(
        materials=[MaterialItem(name="Buckle", quantity="2")],
        tips=[BuildTip(text="Use sharp needle", tip_type="tip")],
    )
    bd2 = BuildData.from_yaml(bd.to_yaml())
    assert bd2 == bd


def test_build_data_timestamp_float():
    s = BuildStep(number=1, description="Sew seam", timestamp=12.345)
    bd = BuildData(steps=[s])
    bd2 = BuildData.from_json(bd.to_json())
    assert bd2.steps[0].timestamp == 12.345
