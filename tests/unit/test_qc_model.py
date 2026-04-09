"""Tests for QCReport and TimeRange (MD-11)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from workshop_video_brain.core.models.qc import QCReport, TimeRange


# ---------------------------------------------------------------------------
# TimeRange
# ---------------------------------------------------------------------------

def test_time_range_required():
    with pytest.raises(ValidationError):
        TimeRange()  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        TimeRange(start_seconds=1.0)  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        TimeRange(end_seconds=4.0)  # type: ignore[call-arg]


def test_time_range_construction():
    tr = TimeRange(start_seconds=1.5, end_seconds=4.0)
    assert tr.start_seconds == 1.5
    assert tr.end_seconds == 4.0


def test_time_range_model_dump_round_trip():
    tr = TimeRange(start_seconds=1.5, end_seconds=4.0)
    tr2 = TimeRange.model_validate(tr.model_dump())
    assert tr2 == tr


def test_time_range_negative_values():
    # No non-negative validator in source
    tr = TimeRange(start_seconds=-1.0, end_seconds=0.0)
    assert tr.start_seconds == -1.0


def test_time_range_zero_duration():
    tr = TimeRange(start_seconds=0.0, end_seconds=0.0)
    assert tr.start_seconds == 0.0
    assert tr.end_seconds == 0.0


# ---------------------------------------------------------------------------
# QCReport
# ---------------------------------------------------------------------------

def test_qc_report_required():
    with pytest.raises(ValidationError):
        QCReport()  # type: ignore[call-arg]


def test_qc_report_defaults():
    r = QCReport(file_path="/footage/clip.mp4")
    assert r.black_frames == []
    assert r.silence_regions == []
    assert r.audio_clipping is False
    assert r.loudness_lufs is None
    assert r.true_peak_dbtp is None
    assert r.file_size_bytes == 0
    assert r.duration_seconds == 0.0
    assert r.checks_passed == []
    assert r.checks_failed == []
    assert r.checks_skipped == []
    assert r.overall_pass is True


def test_qc_report_loudness_none():
    r = QCReport(file_path="/footage/clip.mp4")
    d = r.model_dump()
    assert "loudness_lufs" in d
    assert d["loudness_lufs"] is None


def test_qc_report_loudness_set():
    r = QCReport(file_path="/footage/clip.mp4", loudness_lufs=-23.0)
    assert r.loudness_lufs == -23.0
    d = r.model_dump()
    assert d["loudness_lufs"] == -23.0


def test_qc_report_true_peak_none():
    r = QCReport(file_path="/footage/clip.mp4")
    assert r.true_peak_dbtp is None


def test_qc_report_true_peak_set():
    r = QCReport(file_path="/footage/clip.mp4", true_peak_dbtp=-1.0)
    assert r.true_peak_dbtp == -1.0


def test_qc_report_audio_clipping():
    r = QCReport(file_path="/footage/clip.mp4", audio_clipping=True)
    assert r.audio_clipping is True


def test_qc_report_overall_fail():
    r = QCReport(file_path="/footage/clip.mp4", overall_pass=False)
    assert r.overall_pass is False


def test_qc_report_black_frames():
    tr = TimeRange(start_seconds=1.0, end_seconds=2.0)
    r = QCReport(file_path="/footage/clip.mp4", black_frames=[tr])
    d = r.model_dump()
    assert len(d["black_frames"]) == 1
    assert isinstance(d["black_frames"][0], dict)
    assert d["black_frames"][0]["start_seconds"] == 1.0


def test_qc_report_silence_regions():
    tr = TimeRange(start_seconds=5.0, end_seconds=7.5)
    r = QCReport(file_path="/footage/clip.mp4", silence_regions=[tr])
    d = r.model_dump()
    assert len(d["silence_regions"]) == 1
    assert d["silence_regions"][0]["end_seconds"] == 7.5


def test_qc_report_checks_lists():
    r = QCReport(
        file_path="/footage/clip.mp4",
        checks_passed=["loudness", "resolution"],
        checks_failed=["true_peak"],
        checks_skipped=["subtitle_check"],
    )
    r2 = QCReport.model_validate(r.model_dump())
    assert r2.checks_passed == ["loudness", "resolution"]
    assert r2.checks_failed == ["true_peak"]
    assert r2.checks_skipped == ["subtitle_check"]


def test_qc_report_model_dump_round_trip():
    r = QCReport(
        file_path="/footage/clip.mp4",
        loudness_lufs=-23.5,
        overall_pass=True,
        checks_passed=["loudness"],
    )
    r2 = QCReport.model_validate(r.model_dump())
    assert r2 == r


def test_qc_report_no_serializable_mixin():
    r = QCReport(file_path="/footage/clip.mp4")
    assert not hasattr(r, "to_json")
    assert not hasattr(r, "to_yaml")
