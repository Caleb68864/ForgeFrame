---
type: phase-spec
master_spec: "docs/specs/2026-04-09-phase3-pipeline-completeness.md"
sub_spec: 1
title: "FFprobe Extended"
dependencies: none
date: 2026-04-09
---

# Sub-Spec 1: FFprobe Extended

## Shared Context
Infrastructure sub-spec. Extends probe_media() for VFR detection, color metadata, and loudness measurement. Used by sub-specs 5, 7, 8, 10.

## Interface Contract
**Provides:**
- `MediaAsset.is_vfr: bool` -- True if r_frame_rate vs avg_frame_rate diverge >5%
- `MediaAsset.color_space: str | None` -- e.g., "bt709"
- `MediaAsset.color_primaries: str | None`
- `MediaAsset.color_transfer: str | None`
- `measure_loudness(path: Path) -> LoudnessResult | None` -- returns `LoudnessResult(input_i: float, input_tp: float, input_lra: float)` dataclass, or `None` on failure

**Requires:** nothing (extends existing probe.py)

## Implementation Steps

### Step 1: Write tests for VFR detection, color metadata, and loudness

File: `tests/unit/test_probe_extended.py`

```python
"""Tests for extended FFprobe capabilities: VFR detection, color metadata, loudness."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media, measure_loudness


# Mock ffprobe output for a VFR file (r_frame_rate and avg_frame_rate diverge >5%)
VFR_PROBE_OUTPUT = {
    "format": {
        "filename": "test_vfr.mp4",
        "duration": "10.0",
        "size": "1000000",
        "bit_rate": "800000",
    },
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "30/1",
            "avg_frame_rate": "25/1",
            "color_space": "bt709",
            "color_primaries": "bt709",
            "color_transfer": "bt709",
        }
    ],
}

# Mock ffprobe output for a CFR file (rates match)
CFR_PROBE_OUTPUT = {
    "format": {
        "filename": "test_cfr.mp4",
        "duration": "10.0",
        "size": "1000000",
        "bit_rate": "800000",
    },
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "30/1",
            "avg_frame_rate": "30/1",
            "color_space": "bt709",
            "color_primaries": "bt709",
            "color_transfer": "bt709",
        }
    ],
}

# Mock ffprobe output with missing color metadata
NO_COLOR_PROBE_OUTPUT = {
    "format": {
        "filename": "test_no_color.mp4",
        "duration": "10.0",
        "size": "1000000",
        "bit_rate": "800000",
    },
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "30/1",
            "avg_frame_rate": "30/1",
        }
    ],
}


def _mock_probe(output_dict):
    """Create a mock for subprocess.run that returns ffprobe JSON."""
    mock_result = MagicMock()
    mock_result.stdout = json.dumps(output_dict)
    mock_result.returncode = 0
    return mock_result


class TestVFRDetection:
    @patch("subprocess.run")
    def test_vfr_file_detected(self, mock_run, tmp_path):
        mock_run.return_value = _mock_probe(VFR_PROBE_OUTPUT)
        test_file = tmp_path / "test_vfr.mp4"
        test_file.write_bytes(b"\x00" * 100)

        asset = probe_media(test_file)

        assert asset.is_vfr is True

    @patch("subprocess.run")
    def test_cfr_file_not_flagged(self, mock_run, tmp_path):
        mock_run.return_value = _mock_probe(CFR_PROBE_OUTPUT)
        test_file = tmp_path / "test_cfr.mp4"
        test_file.write_bytes(b"\x00" * 100)

        asset = probe_media(test_file)

        assert asset.is_vfr is False


class TestColorMetadata:
    @patch("subprocess.run")
    def test_color_metadata_extracted(self, mock_run, tmp_path):
        mock_run.return_value = _mock_probe(CFR_PROBE_OUTPUT)
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"\x00" * 100)

        asset = probe_media(test_file)

        assert asset.color_space == "bt709"
        assert asset.color_primaries == "bt709"
        assert asset.color_transfer == "bt709"

    @patch("subprocess.run")
    def test_missing_color_defaults_none(self, mock_run, tmp_path):
        mock_run.return_value = _mock_probe(NO_COLOR_PROBE_OUTPUT)
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"\x00" * 100)

        asset = probe_media(test_file)

        assert asset.color_space is None
        assert asset.color_primaries is None
        assert asset.color_transfer is None


class TestLoudnessMeasurement:
    @patch("subprocess.run")
    def test_measure_loudness_parses_output(self, mock_run, tmp_path):
        loudnorm_output = (
            '[Parsed_loudnorm_0 @ 0x0] \n'
            '{\n'
            '    "input_i" : "-23.5",\n'
            '    "input_tp" : "-1.2",\n'
            '    "input_lra" : "8.3"\n'
            '}\n'
        )
        mock_result = MagicMock()
        mock_result.stderr = loudnorm_output
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"\x00" * 100)

        result = measure_loudness(test_file)

        assert result is not None
        assert result.input_i == pytest.approx(-23.5)
        assert result.input_tp == pytest.approx(-1.2)
        assert result.input_lra == pytest.approx(8.3)

    @patch("subprocess.run")
    def test_measure_loudness_handles_failure(self, mock_run, tmp_path):
        mock_run.side_effect = Exception("ffmpeg not found")
        test_file = tmp_path / "test.wav"
        test_file.write_bytes(b"\x00" * 100)

        result = measure_loudness(test_file)

        assert result is None
```

Run: `uv run pytest tests/unit/test_probe_extended.py -v`
Expected: FAIL (is_vfr, color_space, color_primaries, color_transfer, measure_loudness don't exist yet)

### Step 2: Add fields to MediaAsset model

File: `workshop-video-brain/src/workshop_video_brain/core/models/media.py`

Add to `MediaAsset` class after `analysis_status`:
```python
is_vfr: bool = False
color_space: str | None = None
color_primaries: str | None = None
color_transfer: str | None = None
```

These fields default to safe values so existing code is unaffected.

### Step 3: Implement VFR detection and color extraction in probe_media()

File: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/probe.py`

Add helper function before `probe_media()`:
```python
def _parse_frame_rate(rate_str: str) -> float:
    """Parse 'num/den' frame rate string to float."""
    try:
        num, den = rate_str.split("/")
        return int(num) / int(den) if int(den) != 0 else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0
```

In `probe_media()`, after the existing FPS calculation block (lines 59-66), add VFR detection:
```python
# VFR detection: compare r_frame_rate vs avg_frame_rate
avg_frame_rate = video_stream.get("avg_frame_rate", "0/1")
r_fps = _parse_frame_rate(r_frame_rate)
avg_fps = _parse_frame_rate(avg_frame_rate)
is_vfr = False
if r_fps > 0 and avg_fps > 0:
    divergence = abs(r_fps - avg_fps) / max(r_fps, avg_fps)
    is_vfr = divergence > 0.05

# Color metadata
color_space = video_stream.get("color_space")
color_primaries = video_stream.get("color_primaries")
color_transfer = video_stream.get("color_transfer")
```

Then pass the new fields to the `MediaAsset(...)` constructor:
```python
is_vfr=is_vfr,
color_space=color_space,
color_primaries=color_primaries,
color_transfer=color_transfer,
```

### Step 4: Implement measure_loudness()

File: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/probe.py`

Add at module level (after existing imports):
```python
import re
```

Add dataclass before the function, and the function after `scan_directory()`:
```python
@dataclass
class LoudnessResult:
    """Loudness measurement result."""
    input_i: float    # Integrated loudness (LUFS)
    input_tp: float   # True peak (dBTP)
    input_lra: float  # Loudness range (LU)


def measure_loudness(path: Path) -> LoudnessResult | None:
    """Measure integrated loudness, true peak, and loudness range using FFmpeg loudnorm filter.

    Returns LoudnessResult with input_i (LUFS), input_tp (dBTP), input_lra (LU).
    Returns None on failure.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-i", str(path),
                "-af", "loudnorm=print_format=json",
                "-f", "null", "-"
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        # loudnorm JSON is in stderr
        match = re.search(r'\{[^}]*"input_i"[^}]*\}', result.stderr, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return LoudnessResult(
                input_i=float(data.get("input_i", 0)),
                input_tp=float(data.get("input_tp", 0)),
                input_lra=float(data.get("input_lra", 0)),
            )
        return None
    except Exception:
        logger.warning("Loudness measurement failed for %s", path)
        return None
```

### Step 5: Run new tests

Run: `uv run pytest tests/unit/test_probe_extended.py -v`
Expected: all PASS

### Step 6: Run full test suite

Run: `uv run pytest tests/ -v`
Expected: all existing tests pass + new tests pass

### Step 7: Commit

```bash
git add tests/unit/test_probe_extended.py
git add workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/probe.py
git add workshop-video-brain/src/workshop_video_brain/core/models/media.py
git commit -m "feat: extend FFprobe with VFR detection, color metadata, and loudness measurement"
```

## Verification

- `uv run pytest tests/unit/test_probe_extended.py -v` -- all pass
- `uv run pytest tests/ -v` -- all existing tests still pass
- VFR detection works with divergence >5%
- Color metadata extracted when present, None when absent
- Loudness measurement parses FFmpeg loudnorm output correctly
