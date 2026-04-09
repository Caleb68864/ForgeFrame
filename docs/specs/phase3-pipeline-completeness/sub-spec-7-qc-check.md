---
type: phase-spec
master_spec: "../2026-04-09-phase3-pipeline-completeness.md"
sub_spec: 7
title: "QC Automation Tool"
dependencies: [1]
date: 2026-04-09
---

# Sub-Spec 7: QC Automation Tool

## Scope

Automated post-render quality checks: black frame detection, silence region detection, audio clipping scan, loudness measurement (via Sub-Spec 1's `measure_loudness()`), and file size sanity. Returns a structured `QCReport` with per-check pass/fail/skip status and an overall verdict.

## Interface Contracts

### Provides

- **QC models** in `core/models/qc.py`:
  - `TimeRange(start_seconds: float, end_seconds: float)`
  - `QCReport(file_path, black_frames, silence_regions, audio_clipping, loudness_lufs, true_peak_dbtp, file_size_bytes, duration_seconds, checks_passed, checks_failed, checks_skipped, overall_pass)`

- **QC pipeline** in `edit_mcp/pipelines/qc_check.py`:
  - `run_qc(file_path: Path, checks: list[str] | None = None) -> QCReport`

- **MCP tool** in `edit_mcp/server/tools.py`:
  - `qc_check(file_path: str, checks: str = "") -> dict`

### Requires (from Sub-Spec 1)

- `measure_loudness(path: Path) -> dict` from `edit_mcp/adapters/ffmpeg/probe.py`
  - Returns `{"input_i": float, "input_tp": float, "input_lra": float}`

## Shared Context

- All FFmpeg commands run via `subprocess.run(capture_output=True, text=True)` and parse stderr
- If a subprocess call raises `FileNotFoundError` or returns a non-zero exit code indicating a missing filter, the check is added to `checks_skipped` -- never to `checks_failed`
- The pipeline is a pure function: no side effects beyond reading the input file
- `QCReport` is Pydantic, re-exported via `core/models/__init__.py` `__all__`

## Implementation Steps

### Step 1: Create QC models

**Create** `workshop-video-brain/src/workshop_video_brain/core/models/qc.py`:

```python
"""Quality-check report models."""
from __future__ import annotations

from pydantic import BaseModel


class TimeRange(BaseModel):
    """A contiguous time span in seconds."""
    start_seconds: float
    end_seconds: float


class QCReport(BaseModel):
    """Structured result of run_qc()."""
    file_path: str
    black_frames: list[TimeRange] = []
    silence_regions: list[TimeRange] = []
    audio_clipping: bool = False
    loudness_lufs: float | None = None
    true_peak_dbtp: float | None = None
    file_size_bytes: int = 0
    duration_seconds: float = 0.0
    checks_passed: list[str] = []
    checks_failed: list[str] = []
    checks_skipped: list[str] = []
    overall_pass: bool = True
```

### Step 2: Re-export models

**Modify** `workshop-video-brain/src/workshop_video_brain/core/models/__init__.py`:

- Add import: `from .qc import QCReport, TimeRange`
- Add to `__all__`: `"QCReport"`, `"TimeRange"` under a `# qc` comment block

### Step 3: Create QC pipeline

**Create** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/qc_check.py`:

```python
"""Post-render quality-check pipeline."""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from workshop_video_brain.core.models.qc import QCReport, TimeRange

logger = logging.getLogger(__name__)

ALL_CHECKS = ["black_frames", "silence", "loudness", "clipping", "file_size"]


def run_qc(file_path: Path, checks: list[str] | None = None) -> QCReport:
    """Run quality checks on a rendered file.

    Parameters
    ----------
    file_path:
        Path to the media file to check.
    checks:
        Subset of ALL_CHECKS to run, or None for all.

    Returns
    -------
    QCReport with per-check results and overall_pass verdict.
    """
    selected = checks if checks else list(ALL_CHECKS)
    report = QCReport(file_path=str(file_path))

    # Populate basic file info
    if file_path.exists():
        report.file_size_bytes = file_path.stat().st_size

    for check in selected:
        try:
            if check == "black_frames":
                _check_black_frames(file_path, report)
            elif check == "silence":
                _check_silence(file_path, report)
            elif check == "loudness":
                _check_loudness(file_path, report)
            elif check == "clipping":
                _check_clipping(file_path, report)
            elif check == "file_size":
                _check_file_size(file_path, report)
            else:
                logger.warning("Unknown QC check: %s", check)
                report.checks_skipped.append(check)
        except (FileNotFoundError, OSError) as exc:
            logger.warning("Check '%s' skipped -- filter unavailable: %s", check, exc)
            report.checks_skipped.append(check)

    report.overall_pass = len(report.checks_failed) == 0
    return report


# ---- individual checks ----------------------------------------------------

def _run_ffmpeg(args: list[str]) -> str:
    """Run an ffmpeg command and return stderr output."""
    result = subprocess.run(
        ["ffmpeg", *args],
        capture_output=True,
        text=True,
    )
    return result.stderr


def _check_black_frames(path: Path, report: QCReport) -> None:
    stderr = _run_ffmpeg([
        "-i", str(path),
        "-vf", "blackdetect=d=0.5:pix_th=0.10",
        "-an", "-f", "null", "-",
    ])
    pattern = re.compile(
        r"black_start:(\d+\.?\d*)\s+black_end:(\d+\.?\d*)"
    )
    regions = [
        TimeRange(start_seconds=float(m.group(1)), end_seconds=float(m.group(2)))
        for m in pattern.finditer(stderr)
    ]
    report.black_frames = regions
    if regions:
        report.checks_failed.append("black_frames")
    else:
        report.checks_passed.append("black_frames")


def _check_silence(path: Path, report: QCReport) -> None:
    stderr = _run_ffmpeg([
        "-i", str(path),
        "-af", "silencedetect=n=-50dB:d=1.0",
        "-vn", "-f", "null", "-",
    ])
    starts = re.findall(r"silence_start:\s*(\d+\.?\d*)", stderr)
    ends = re.findall(r"silence_end:\s*(\d+\.?\d*)", stderr)
    regions = [
        TimeRange(start_seconds=float(s), end_seconds=float(e))
        for s, e in zip(starts, ends)
    ]
    report.silence_regions = regions
    if regions:
        report.checks_failed.append("silence")
    else:
        report.checks_passed.append("silence")


def _check_loudness(path: Path, report: QCReport) -> None:
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import measure_loudness

    data = measure_loudness(path)
    report.loudness_lufs = data.get("input_i")
    report.true_peak_dbtp = data.get("input_tp")

    failed = False
    if report.loudness_lufs is not None and report.loudness_lufs < -24.0:
        failed = True  # too quiet for YouTube (-14 LUFS target)
    if report.true_peak_dbtp is not None and report.true_peak_dbtp > -1.0:
        failed = True  # true peak too hot

    if failed:
        report.checks_failed.append("loudness")
    else:
        report.checks_passed.append("loudness")


def _check_clipping(path: Path, report: QCReport) -> None:
    stderr = _run_ffmpeg([
        "-i", str(path),
        "-af", "astats=metadata=1:reset=1",
        "-vn", "-f", "null", "-",
    ])
    # astats reports "Number of Nans", "Number of Infs", "Number of denormals"
    # and per-channel peak levels. Check for Flat_factor or clipping indicators.
    clipping = "Flat_factor" in stderr or "clipping" in stderr.lower()
    report.audio_clipping = clipping
    if clipping:
        report.checks_failed.append("clipping")
    else:
        report.checks_passed.append("clipping")


def _check_file_size(path: Path, report: QCReport) -> None:
    size = report.file_size_bytes
    if size < 1024:
        report.checks_failed.append("file_size")
    elif size > 10 * 1024 * 1024 * 1024:  # 10 GB
        report.checks_failed.append("file_size")
    else:
        report.checks_passed.append("file_size")
```

### Step 4: Register MCP tool

**Modify** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`:

Add the following tool registration at the end of the file:

```python
@mcp.tool()
def qc_check(file_path: str, checks: str = "") -> dict:
    """Run automated quality checks on a rendered media file.

    Checks: black_frames, silence, loudness, clipping, file_size.
    Pass a comma-separated subset or leave empty for all checks.
    """
    from workshop_video_brain.edit_mcp.pipelines.qc_check import run_qc

    p = Path(file_path)
    if not p.exists():
        return _err(f"File not found: {file_path}")

    check_list: list[str] | None = None
    if checks.strip():
        check_list = [c.strip() for c in checks.split(",") if c.strip()]

    report = run_qc(p, check_list)
    return _ok(report.model_dump())
```

### Step 5: Write tests (TDD -- write first, implement to satisfy)

**Create** `tests/unit/test_qc_check.py`:

Tests use `unittest.mock.patch` to mock `subprocess.run` and `measure_loudness`.

```python
"""TDD tests for QC automation pipeline."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.core.models.qc import QCReport, TimeRange
from workshop_video_brain.edit_mcp.pipelines.qc_check import ALL_CHECKS, run_qc


# --- fixtures ---------------------------------------------------------------

SAMPLE_PATH = Path("/tmp/test_render.mp4")

BLACK_DETECT_STDERR = (
    "[blackdetect @ 0x1234] black_start:0.00 black_end:2.50 black_duration:2.50\n"
    "[blackdetect @ 0x1234] black_start:58.00 black_end:60.00 black_duration:2.00\n"
)

SILENCE_DETECT_STDERR = (
    "[silencedetect @ 0x5678] silence_start: 10.5\n"
    "[silencedetect @ 0x5678] silence_end: 15.2 | silence_duration: 4.7\n"
)

CLIPPING_STDERR = "Flat_factor detected on channel 0\n"

CLEAN_STDERR = "size=N/A time=00:01:00.00 bitrate=N/A speed=120x\n"


def _mock_subprocess(stderr: str):
    """Return a mock subprocess.run result with the given stderr."""
    result = MagicMock()
    result.stderr = stderr
    result.returncode = 0
    return result


# --- black frames -----------------------------------------------------------

@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_black_frames_detected(mock_run):
    mock_run.return_value = _mock_subprocess(BLACK_DETECT_STDERR)
    report = run_qc(SAMPLE_PATH, checks=["black_frames"])

    assert len(report.black_frames) == 2
    assert report.black_frames[0].start_seconds == 0.0
    assert report.black_frames[0].end_seconds == 2.5
    assert "black_frames" in report.checks_failed
    assert not report.overall_pass


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_no_black_frames(mock_run):
    mock_run.return_value = _mock_subprocess(CLEAN_STDERR)
    report = run_qc(SAMPLE_PATH, checks=["black_frames"])

    assert len(report.black_frames) == 0
    assert "black_frames" in report.checks_passed
    assert report.overall_pass


# --- silence ----------------------------------------------------------------

@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_silence_detected(mock_run):
    mock_run.return_value = _mock_subprocess(SILENCE_DETECT_STDERR)
    report = run_qc(SAMPLE_PATH, checks=["silence"])

    assert len(report.silence_regions) == 1
    assert report.silence_regions[0].start_seconds == pytest.approx(10.5)
    assert report.silence_regions[0].end_seconds == pytest.approx(15.2)
    assert "silence" in report.checks_failed


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_no_silence(mock_run):
    mock_run.return_value = _mock_subprocess(CLEAN_STDERR)
    report = run_qc(SAMPLE_PATH, checks=["silence"])

    assert len(report.silence_regions) == 0
    assert "silence" in report.checks_passed


# --- loudness ---------------------------------------------------------------

@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
@patch(
    "workshop_video_brain.edit_mcp.pipelines.qc_check.measure_loudness",
    create=True,
)
def test_loudness_good(mock_loudness, mock_run):
    mock_loudness.return_value = {"input_i": -16.0, "input_tp": -3.0, "input_lra": 7.0}
    with patch(
        "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.measure_loudness",
        mock_loudness,
        create=True,
    ):
        report = run_qc(SAMPLE_PATH, checks=["loudness"])

    assert report.loudness_lufs == -16.0
    assert report.true_peak_dbtp == -3.0
    assert "loudness" in report.checks_passed


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_loudness_too_quiet(mock_run):
    mock_loudness = MagicMock(return_value={"input_i": -28.0, "input_tp": -6.0, "input_lra": 12.0})
    with patch(
        "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.measure_loudness",
        mock_loudness,
        create=True,
    ):
        report = run_qc(SAMPLE_PATH, checks=["loudness"])

    assert report.loudness_lufs == -28.0
    assert "loudness" in report.checks_failed


# --- clipping ---------------------------------------------------------------

@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_clipping_detected(mock_run):
    mock_run.return_value = _mock_subprocess(CLIPPING_STDERR)
    report = run_qc(SAMPLE_PATH, checks=["clipping"])

    assert report.audio_clipping is True
    assert "clipping" in report.checks_failed


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_no_clipping(mock_run):
    mock_run.return_value = _mock_subprocess(CLEAN_STDERR)
    report = run_qc(SAMPLE_PATH, checks=["clipping"])

    assert report.audio_clipping is False
    assert "clipping" in report.checks_passed


# --- file size --------------------------------------------------------------

def test_file_size_too_small(tmp_path):
    tiny = tmp_path / "tiny.mp4"
    tiny.write_bytes(b"\x00" * 100)  # 100 bytes
    report = run_qc(tiny, checks=["file_size"])

    assert "file_size" in report.checks_failed
    assert not report.overall_pass


def test_file_size_reasonable(tmp_path):
    normal = tmp_path / "normal.mp4"
    normal.write_bytes(b"\x00" * 50_000)  # 50 KB
    report = run_qc(normal, checks=["file_size"])

    assert "file_size" in report.checks_passed
    assert report.overall_pass


# --- missing filter (skip, not fail) ---------------------------------------

@patch(
    "workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run",
    side_effect=FileNotFoundError("ffmpeg not found"),
)
def test_missing_filter_skips(mock_run):
    report = run_qc(SAMPLE_PATH, checks=["black_frames"])

    assert "black_frames" in report.checks_skipped
    assert "black_frames" not in report.checks_failed
    assert report.overall_pass  # skipped != failed


# --- clean file passes all --------------------------------------------------

@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_clean_file_passes_all(mock_run):
    mock_run.return_value = _mock_subprocess(CLEAN_STDERR)
    mock_loudness = MagicMock(return_value={"input_i": -14.0, "input_tp": -2.0, "input_lra": 6.0})

    with patch(
        "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.measure_loudness",
        mock_loudness,
        create=True,
    ):
        report = run_qc(SAMPLE_PATH)

    assert report.overall_pass
    assert len(report.checks_failed) == 0
    assert len(report.checks_passed) == len(ALL_CHECKS)
```

## Verification Commands

```bash
# Run QC unit tests
uv run pytest tests/unit/test_qc_check.py -v

# Verify models importable
uv run python -c "from workshop_video_brain.core.models import QCReport, TimeRange; print('OK')"

# Run full suite to confirm no regressions
uv run pytest tests/ -v

# Manual: QC check on a known-good render
uv run python -c "
from pathlib import Path
from workshop_video_brain.edit_mcp.pipelines.qc_check import run_qc
report = run_qc(Path('tests/fixtures/media/sample.mp4'))
print(f'Overall pass: {report.overall_pass}')
print(f'Passed: {report.checks_passed}')
print(f'Failed: {report.checks_failed}')
print(f'Skipped: {report.checks_skipped}')
"
```

## Acceptance Criteria

- [ ] `QCReport` and `TimeRange` models created in `core/models/qc.py`
- [ ] Models re-exported in `core/models/__init__.py` `__all__`
- [ ] `run_qc()` pipeline runs all 5 checks by default
- [ ] `run_qc()` accepts a subset of checks via `checks` parameter
- [ ] `black_frames` check parses `blackdetect` stderr for `black_start`/`black_end`
- [ ] `silence` check parses `silencedetect` stderr for `silence_start`/`silence_end`
- [ ] `loudness` check calls `measure_loudness()` from Sub-Spec 1, fails if LUFS < -24 or true peak > -1 dBTP
- [ ] `clipping` check parses `astats` stderr for clipping indicators
- [ ] `file_size` check fails if < 1KB or > 10GB
- [ ] If an FFmpeg filter is unavailable (subprocess error), check is added to `checks_skipped`, not `checks_failed`
- [ ] `overall_pass` is `True` only when `checks_failed` is empty
- [ ] MCP tool `qc_check` parses comma-separated checks string, returns `_ok(report.model_dump())`
- [ ] All tests pass: black frames detected/clean, silence detected/clean, loudness good/bad, clipping detected/clean, file size too small/reasonable, missing filter skips, clean file passes all
- [ ] Existing test suite still passes
