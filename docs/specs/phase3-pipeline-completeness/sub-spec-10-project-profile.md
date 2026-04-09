---
type: phase-spec
master_spec: "docs/specs/2026-04-09-phase3-pipeline-completeness.md"
sub_spec: 10
title: "Project Profile Setup"
dependencies: "1"
date: 2026-04-09
---

# Sub-Spec 10: Project Profile Setup

## Shared Context
Configures the Kdenlive project `<profile>` element (resolution, frame rate, colorspace) either manually or by probing a source file. Depends on Sub-Spec 1 (FFprobe Extended) for source matching.

## Interface Contract
**Provides:**
- `set_project_profile(project, width, height, fps_num, fps_den, colorspace?) -> KdenliveProject`
- `match_profile_to_source(source_path: Path) -> dict`
- MCP tool `project_setup_profile`
- MCP tool `project_match_source`

**Requires:**
- `probe_media(path)` from Sub-Spec 1 (MediaAsset with fps, width, height)
- `KdenliveProject` model with profile attributes (width, height, frame_rate_num, frame_rate_den, colorspace)
- `parse_project()` / `serialize_project()` from Kdenlive parser/serializer
- Snapshot mechanism for safe writes

## Implementation Steps

### Step 1: Write tests

File: `tests/unit/test_project_profile.py`

```python
"""Tests for project profile setup pipeline."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from workshop_video_brain.edit_mcp.pipelines.project_profile import (
    set_project_profile,
    match_profile_to_source,
)


def _make_project(width=1920, height=1080, fps_num=30, fps_den=1, colorspace=709):
    """Create a minimal KdenliveProject-like object with profile attrs."""
    from workshop_video_brain.core.models.kdenlive import KdenliveProject
    project = KdenliveProject.model_validate({
        "profile": {
            "width": width,
            "height": height,
            "frame_rate_num": fps_num,
            "frame_rate_den": fps_den,
            "colorspace": colorspace,
        },
        "tracks": [],
        "clips": [],
        "compositions": [],
    })
    return project


class TestSetProjectProfile:
    def test_sets_resolution(self):
        project = _make_project()
        result = set_project_profile(project, width=3840, height=2160, fps_num=24, fps_den=1)
        assert result.profile.width == 3840
        assert result.profile.height == 2160

    def test_sets_fps(self):
        project = _make_project()
        result = set_project_profile(project, width=1920, height=1080, fps_num=60, fps_den=1)
        assert result.profile.frame_rate_num == 60
        assert result.profile.frame_rate_den == 1

    def test_sets_colorspace(self):
        project = _make_project()
        result = set_project_profile(project, width=1920, height=1080, fps_num=30, fps_den=1, colorspace=601)
        assert result.profile.colorspace == 601

    def test_default_colorspace_709(self):
        project = _make_project(colorspace=601)
        result = set_project_profile(project, width=1920, height=1080, fps_num=30, fps_den=1)
        assert result.profile.colorspace == 709

    def test_deep_copies_project(self):
        project = _make_project()
        result = set_project_profile(project, width=3840, height=2160, fps_num=24, fps_den=1)
        assert result is not project
        assert project.profile.width == 1920  # original unchanged

    def test_invalid_colorspace_raises(self):
        project = _make_project()
        with pytest.raises(ValueError, match="colorspace"):
            set_project_profile(project, width=1920, height=1080, fps_num=30, fps_den=1, colorspace=999)


class TestMatchProfileToSource:
    @patch("workshop_video_brain.edit_mcp.pipelines.project_profile.probe_media")
    def test_match_1080p30(self, mock_probe):
        asset = MagicMock()
        asset.width = 1920
        asset.height = 1080
        asset.fps = 30.0
        mock_probe.return_value = asset

        result = match_profile_to_source(Path("/fake/source.mp4"))
        assert result == {"width": 1920, "height": 1080, "fps_num": 30, "fps_den": 1, "colorspace": 709}

    @patch("workshop_video_brain.edit_mcp.pipelines.project_profile.probe_media")
    def test_match_4k24(self, mock_probe):
        asset = MagicMock()
        asset.width = 3840
        asset.height = 2160
        asset.fps = 24.0
        mock_probe.return_value = asset

        result = match_profile_to_source(Path("/fake/source.mp4"))
        assert result == {"width": 3840, "height": 2160, "fps_num": 24, "fps_den": 1, "colorspace": 709}

    @patch("workshop_video_brain.edit_mcp.pipelines.project_profile.probe_media")
    def test_match_fractional_fps(self, mock_probe):
        """29.97 fps should produce 30000/1001."""
        asset = MagicMock()
        asset.width = 1920
        asset.height = 1080
        asset.fps = 29.97
        mock_probe.return_value = asset

        result = match_profile_to_source(Path("/fake/source.mp4"))
        assert result["fps_num"] == 30000
        assert result["fps_den"] == 1001

    @patch("workshop_video_brain.edit_mcp.pipelines.project_profile.probe_media")
    def test_match_23976(self, mock_probe):
        """23.976 fps should produce 24000/1001."""
        asset = MagicMock()
        asset.width = 1920
        asset.height = 1080
        asset.fps = 23.976
        mock_probe.return_value = asset

        result = match_profile_to_source(Path("/fake/source.mp4"))
        assert result["fps_num"] == 24000
        assert result["fps_den"] == 1001


class TestRoundTrip:
    """Set profile -> serialize -> parse -> verify attributes."""

    @patch("workshop_video_brain.edit_mcp.pipelines.project_profile.probe_media")
    def test_set_serialize_parse_roundtrip(self, mock_probe):
        """Integration-style: set profile, serialize to XML, parse back, verify."""
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
        import tempfile

        project = _make_project()
        updated = set_project_profile(project, width=3840, height=2160, fps_num=24, fps_den=1, colorspace=709)

        with tempfile.NamedTemporaryFile(suffix=".kdenlive", delete=False) as f:
            serialize_project(updated, Path(f.name))
            parsed = parse_project(Path(f.name))

        assert parsed.profile.width == 3840
        assert parsed.profile.height == 2160
        assert parsed.profile.frame_rate_num == 24
        assert parsed.profile.frame_rate_den == 1
        assert parsed.profile.colorspace == 709
```

### Step 2: Implement pipeline functions

File: `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/project_profile.py`

```python
"""Project profile setup pipeline -- resolution, frame rate, colorspace."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from pathlib import Path

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media

VALID_COLORSPACES = {601, 709, 240}

# Known NTSC fractional rates: map float -> (num, den)
_NTSC_RATES = {
    23.976: (24000, 1001),
    23.98: (24000, 1001),
    29.97: (30000, 1001),
    59.94: (60000, 1001),
}


def set_project_profile(
    project: KdenliveProject,
    width: int,
    height: int,
    fps_num: int,
    fps_den: int,
    colorspace: int | None = None,
) -> KdenliveProject:
    """Set project profile attributes. Deep-copies project first."""
    if colorspace is None:
        colorspace = 709
    if colorspace not in VALID_COLORSPACES:
        raise ValueError(f"Invalid colorspace {colorspace}; must be one of {VALID_COLORSPACES}")

    result = deepcopy(project)
    result.profile.width = width
    result.profile.height = height
    result.profile.frame_rate_num = fps_num
    result.profile.frame_rate_den = fps_den
    result.profile.colorspace = colorspace
    return result


def _fps_to_num_den(fps: float) -> tuple[int, int]:
    """Convert float fps to integer num/den pair."""
    # Check known NTSC rates first (within tolerance)
    for known_fps, (num, den) in _NTSC_RATES.items():
        if abs(fps - known_fps) < 0.01:
            return num, den

    # Integer rates
    if abs(fps - round(fps)) < 0.001:
        return int(round(fps)), 1

    # Fallback: use Fraction for exact representation
    frac = Fraction(fps).limit_denominator(1001)
    return frac.numerator, frac.denominator


def match_profile_to_source(source_path: Path) -> dict:
    """Probe source file and return recommended profile settings."""
    asset = probe_media(source_path)
    fps_num, fps_den = _fps_to_num_den(asset.fps)
    return {
        "width": asset.width,
        "height": asset.height,
        "fps_num": fps_num,
        "fps_den": fps_den,
        "colorspace": 709,
    }
```

### Step 3: Register MCP tools

File: `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (append)

```python
@mcp.tool()
def project_setup_profile(
    workspace_path: str,
    project_file: str,
    width: int,
    height: int,
    fps_num: int,
    fps_den: int,
    colorspace: int = 709,
) -> dict:
    """Set up project profile (resolution, fps, colorspace)."""
    from workshop_video_brain.edit_mcp.pipelines.project_profile import set_project_profile
    ws = Path(workspace_path)
    proj_path = ws / project_file
    try:
        create_snapshot(ws)
        project = parse_project(proj_path)
        updated = set_project_profile(project, width, height, fps_num, fps_den, colorspace)
        serialize_project(updated, proj_path)
        return _ok({"width": width, "height": height, "fps_num": fps_num, "fps_den": fps_den, "colorspace": colorspace})
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def project_match_source(workspace_path: str, source_file: str) -> dict:
    """Probe a source file and return recommended project profile settings."""
    from workshop_video_brain.edit_mcp.pipelines.project_profile import match_profile_to_source
    try:
        result = match_profile_to_source(Path(workspace_path) / source_file)
        return _ok(result)
    except Exception as e:
        return _err(str(e))
```

## Verification

```bash
uv run pytest tests/unit/test_project_profile.py -v
```

**Pass criteria:** All tests green. Profile round-trips through serialize/parse unchanged. Fractional NTSC rates (29.97, 23.976) produce correct num/den pairs.
