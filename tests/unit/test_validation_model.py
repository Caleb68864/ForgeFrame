"""Tests for ValidationItem and ValidationReport (MD-15)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from workshop_video_brain.core.models.validation import ValidationItem, ValidationReport


# ---------------------------------------------------------------------------
# ValidationItem
# ---------------------------------------------------------------------------

def test_validation_item_required():
    with pytest.raises(ValidationError):
        ValidationItem()  # type: ignore[call-arg]


def test_validation_item_enum_stored_as_string():
    item = ValidationItem(severity="info")
    assert isinstance(item.severity, str)
    assert item.severity == "info"


def test_validation_item_defaults():
    item = ValidationItem(severity="warning")
    assert item.category == ""
    assert item.message == ""
    assert item.location == ""


def test_validation_item_all_severities():
    for sev in ["info", "warning", "error", "blocking_error"]:
        item = ValidationItem(severity=sev)
        assert item.severity == sev


def test_validation_item_invalid_severity():
    with pytest.raises(ValidationError):
        ValidationItem(severity="critical")


def test_validation_item_all_fields():
    item = ValidationItem(
        severity="error",
        category="audio",
        message="Loudness out of range",
        location="00:02:15",
    )
    d = item.model_dump()
    assert d["severity"] == "error"
    assert d["category"] == "audio"
    assert d["message"] == "Loudness out of range"
    assert d["location"] == "00:02:15"


def test_validation_item_json_round_trip():
    item = ValidationItem(severity="blocking_error", message="Missing audio track")
    item2 = ValidationItem.from_json(item.to_json())
    assert item2 == item


def test_validation_item_yaml_round_trip():
    item = ValidationItem(severity="warning", category="video", location="00:01:00")
    item2 = ValidationItem.from_yaml(item.to_yaml())
    assert item2 == item


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------

def test_validation_report_default_construction():
    vr = ValidationReport()
    assert vr is not None


def test_validation_report_defaults():
    vr = ValidationReport()
    assert vr.items == []
    assert vr.summary == ""


def test_validation_report_with_items():
    items = [
        ValidationItem(severity="info", message="All good"),
        ValidationItem(severity="warning", message="Minor issue"),
    ]
    vr = ValidationReport(items=items)
    vr2 = ValidationReport.from_json(vr.to_json())
    assert len(vr2.items) == 2
    assert vr2.items[0].severity == "info"


def test_validation_report_summary():
    vr = ValidationReport(summary="2 issues found")
    vr2 = ValidationReport.from_json(vr.to_json())
    assert vr2.summary == "2 issues found"


def test_validation_report_mutable_default_isolation():
    vr1 = ValidationReport()
    vr2 = ValidationReport()
    vr1.items.append(ValidationItem(severity="info"))
    assert vr2.items == []


def test_validation_report_mixed_severities():
    items = [
        ValidationItem(severity="info", message="Info"),
        ValidationItem(severity="warning", message="Warning"),
        ValidationItem(severity="error", message="Error"),
        ValidationItem(severity="blocking_error", message="Blocking"),
    ]
    vr = ValidationReport(items=items)
    vr2 = ValidationReport.from_json(vr.to_json())
    severities = [i.severity for i in vr2.items]
    assert "info" in severities
    assert "warning" in severities
    assert "error" in severities
    assert "blocking_error" in severities


def test_validation_report_json_round_trip():
    vr = ValidationReport(
        items=[ValidationItem(severity="error", message="Audio missing")],
        summary="1 error",
    )
    vr2 = ValidationReport.from_json(vr.to_json())
    assert vr2 == vr


def test_validation_report_yaml_round_trip():
    vr = ValidationReport(
        items=[ValidationItem(severity="warning", category="video")],
        summary="1 warning",
    )
    vr2 = ValidationReport.from_yaml(vr.to_yaml())
    assert vr2 == vr
