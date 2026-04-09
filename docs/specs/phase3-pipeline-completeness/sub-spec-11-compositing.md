---
type: phase-spec
master_spec: "docs/specs/2026-04-09-phase3-pipeline-completeness.md"
sub_spec: 11
title: "Compositing Tools"
dependencies: "2"
date: 2026-04-09
---

# Sub-Spec 11: Compositing Tools

## Shared Context
PiP (picture-in-picture) and wipe/dissolve compositions for Kdenlive projects. Uses the AddComposition intent from Sub-Spec 2 (Kdenlive Filter Engine) to insert composition entries into the project timeline.

## Interface Contract
**Provides:**
- `PipPreset` enum, `PipLayout` model
- `get_pip_layout(preset, frame_width, frame_height, pip_scale?) -> PipLayout`
- `apply_pip(project, overlay_track, base_track, start_frame, end_frame, layout) -> KdenliveProject`
- `apply_wipe(project, track_a, track_b, start_frame, end_frame, wipe_type?) -> KdenliveProject`
- MCP tool `composite_pip`
- MCP tool `composite_wipe`

**Requires:**
- `AddComposition` intent + `patch_project()` from Sub-Spec 2
- `KdenliveProject` model

## Implementation Steps

### Step 1: Create compositing models

File: `workshop-video-brain/src/workshop_video_brain/core/models/compositing.py`

```python
"""Compositing models -- PiP presets and layout geometry."""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel


class PipPreset(str, Enum):
    top_left = "top_left"
    top_right = "top_right"
    bottom_left = "bottom_left"
    bottom_right = "bottom_right"
    center = "center"
    custom = "custom"


class PipLayout(BaseModel):
    x: int
    y: int
    width: int
    height: int
```

Update `workshop-video-brain/src/workshop_video_brain/core/models/__init__.py` to re-export:
```python
from .compositing import PipPreset, PipLayout
```

### Step 2: Write tests

File: `tests/unit/test_compositing.py`

```python
"""Tests for compositing pipeline -- PiP and wipe tools."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from workshop_video_brain.core.models.compositing import PipPreset, PipLayout
from workshop_video_brain.edit_mcp.pipelines.compositing import (
    get_pip_layout,
    apply_pip,
    apply_wipe,
)

FRAME_W = 1920
FRAME_H = 1080
MARGIN = 20


class TestGetPipLayout:
    def test_bottom_right(self):
        layout = get_pip_layout(PipPreset.bottom_right, FRAME_W, FRAME_H, pip_scale=0.25)
        assert layout.width == 480
        assert layout.height == 270
        assert layout.x == FRAME_W - 480 - MARGIN  # 1420
        assert layout.y == FRAME_H - 270 - MARGIN  # 790

    def test_top_left(self):
        layout = get_pip_layout(PipPreset.top_left, FRAME_W, FRAME_H, pip_scale=0.25)
        assert layout.width == 480
        assert layout.height == 270
        assert layout.x == MARGIN
        assert layout.y == MARGIN

    def test_top_right(self):
        layout = get_pip_layout(PipPreset.top_right, FRAME_W, FRAME_H, pip_scale=0.25)
        assert layout.x == FRAME_W - 480 - MARGIN
        assert layout.y == MARGIN

    def test_bottom_left(self):
        layout = get_pip_layout(PipPreset.bottom_left, FRAME_W, FRAME_H, pip_scale=0.25)
        assert layout.x == MARGIN
        assert layout.y == FRAME_H - 270 - MARGIN

    def test_center(self):
        layout = get_pip_layout(PipPreset.center, FRAME_W, FRAME_H, pip_scale=0.25)
        assert layout.x == (FRAME_W - 480) // 2
        assert layout.y == (FRAME_H - 270) // 2

    def test_custom_raises_without_override(self):
        """Custom preset requires caller to build PipLayout manually."""
        with pytest.raises(ValueError, match="custom"):
            get_pip_layout(PipPreset.custom, FRAME_W, FRAME_H)

    def test_scale_half(self):
        layout = get_pip_layout(PipPreset.bottom_right, FRAME_W, FRAME_H, pip_scale=0.5)
        assert layout.width == 960
        assert layout.height == 540

    def test_4k_frame(self):
        layout = get_pip_layout(PipPreset.bottom_right, 3840, 2160, pip_scale=0.25)
        assert layout.width == 960
        assert layout.height == 540


class TestApplyPip:
    def _make_project(self):
        from workshop_video_brain.core.models.kdenlive import KdenliveProject
        return KdenliveProject.model_validate({
            "profile": {"width": 1920, "height": 1080, "frame_rate_num": 30, "frame_rate_den": 1, "colorspace": 709},
            "tracks": [{"id": 0}, {"id": 1}],
            "clips": [],
            "compositions": [],
        })

    @patch("workshop_video_brain.edit_mcp.pipelines.compositing.patch_project")
    def test_apply_pip_calls_patch(self, mock_patch):
        project = self._make_project()
        mock_patch.return_value = deepcopy(project)
        layout = PipLayout(x=1420, y=790, width=480, height=270)

        result = apply_pip(project, overlay_track=1, base_track=0, start_frame=0, end_frame=150, layout=layout)

        mock_patch.assert_called_once()
        intents = mock_patch.call_args[0][1]
        assert len(intents) == 1
        intent = intents[0]
        assert intent.composition_type == "composite"
        assert intent.params["geometry"] == "1420/790:480x270:100"

    @patch("workshop_video_brain.edit_mcp.pipelines.compositing.patch_project")
    def test_apply_pip_deep_copies(self, mock_patch):
        project = self._make_project()
        mock_patch.return_value = deepcopy(project)
        layout = PipLayout(x=0, y=0, width=480, height=270)

        result = apply_pip(project, overlay_track=1, base_track=0, start_frame=0, end_frame=150, layout=layout)
        assert result is not project


class TestApplyWipe:
    def _make_project(self):
        from workshop_video_brain.core.models.kdenlive import KdenliveProject
        return KdenliveProject.model_validate({
            "profile": {"width": 1920, "height": 1080, "frame_rate_num": 30, "frame_rate_den": 1, "colorspace": 709},
            "tracks": [{"id": 0}, {"id": 1}],
            "clips": [],
            "compositions": [],
        })

    @patch("workshop_video_brain.edit_mcp.pipelines.compositing.patch_project")
    def test_dissolve(self, mock_patch):
        project = self._make_project()
        mock_patch.return_value = deepcopy(project)

        result = apply_wipe(project, track_a=0, track_b=1, start_frame=100, end_frame=130, wipe_type="dissolve")

        intent = mock_patch.call_args[0][1][0]
        assert intent.composition_type == "luma"
        assert "resource" not in intent.params or intent.params["resource"] == ""

    @patch("workshop_video_brain.edit_mcp.pipelines.compositing.patch_project")
    def test_wipe_luma(self, mock_patch):
        project = self._make_project()
        mock_patch.return_value = deepcopy(project)

        result = apply_wipe(project, track_a=0, track_b=1, start_frame=100, end_frame=130, wipe_type="wipe")

        intent = mock_patch.call_args[0][1][0]
        assert intent.composition_type == "luma"
        assert intent.params.get("resource") != ""

    @patch("workshop_video_brain.edit_mcp.pipelines.compositing.patch_project")
    def test_invalid_wipe_type(self, mock_patch):
        project = self._make_project()
        with pytest.raises(ValueError, match="wipe_type"):
            apply_wipe(project, track_a=0, track_b=1, start_frame=0, end_frame=30, wipe_type="unknown")
```

### Step 3: Implement pipeline functions

File: `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/compositing.py`

```python
"""Compositing pipeline -- PiP layouts and wipe transitions."""
from __future__ import annotations

from copy import deepcopy

from workshop_video_brain.core.models.compositing import PipPreset, PipLayout
from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project, AddComposition

MARGIN = 20
VALID_WIPE_TYPES = {"dissolve", "wipe"}


def get_pip_layout(
    preset: PipPreset,
    frame_width: int,
    frame_height: int,
    pip_scale: float = 0.25,
) -> PipLayout:
    """Calculate PiP geometry from a preset and frame dimensions."""
    if preset == PipPreset.custom:
        raise ValueError("custom preset requires caller to build PipLayout directly")

    w = int(frame_width * pip_scale)
    h = int(frame_height * pip_scale)

    positions = {
        PipPreset.top_left: (MARGIN, MARGIN),
        PipPreset.top_right: (frame_width - w - MARGIN, MARGIN),
        PipPreset.bottom_left: (MARGIN, frame_height - h - MARGIN),
        PipPreset.bottom_right: (frame_width - w - MARGIN, frame_height - h - MARGIN),
        PipPreset.center: ((frame_width - w) // 2, (frame_height - h) // 2),
    }

    x, y = positions[preset]
    return PipLayout(x=x, y=y, width=w, height=h)


def apply_pip(
    project: KdenliveProject,
    overlay_track: int,
    base_track: int,
    start_frame: int,
    end_frame: int,
    layout: PipLayout,
) -> KdenliveProject:
    """Add a PiP composite composition to the project."""
    geometry = f"{layout.x}/{layout.y}:{layout.width}x{layout.height}:100"
    intent = AddComposition(
        composition_type="composite",
        track_a=base_track,
        track_b=overlay_track,
        start_frame=start_frame,
        end_frame=end_frame,
        params={"geometry": geometry},
    )
    return patch_project(deepcopy(project), [intent])


def apply_wipe(
    project: KdenliveProject,
    track_a: int,
    track_b: int,
    start_frame: int,
    end_frame: int,
    wipe_type: str = "dissolve",
) -> KdenliveProject:
    """Add a wipe/dissolve transition between two tracks."""
    if wipe_type not in VALID_WIPE_TYPES:
        raise ValueError(f"Invalid wipe_type '{wipe_type}'; must be one of {VALID_WIPE_TYPES}")

    params: dict[str, str] = {}
    if wipe_type == "dissolve":
        params["resource"] = ""
    else:  # wipe
        params["resource"] = "/usr/share/kdenlive/lumas/HD/luma01.pgm"

    intent = AddComposition(
        composition_type="luma",
        track_a=track_a,
        track_b=track_b,
        start_frame=start_frame,
        end_frame=end_frame,
        params=params,
    )
    return patch_project(deepcopy(project), [intent])
```

### Step 4: Register MCP tools

File: `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (append)

```python
@mcp.tool()
def composite_pip(
    workspace_path: str,
    project_file: str,
    overlay_track: int,
    base_track: int,
    start_frame: int,
    end_frame: int,
    preset: str = "bottom_right",
    scale: float = 0.25,
) -> dict:
    """Add a picture-in-picture composite to the project."""
    from workshop_video_brain.core.models.compositing import PipPreset
    from workshop_video_brain.edit_mcp.pipelines.compositing import get_pip_layout, apply_pip
    ws = Path(workspace_path)
    proj_path = ws / project_file
    try:
        create_snapshot(ws)
        project = parse_project(proj_path)
        layout = get_pip_layout(PipPreset(preset), project.profile.width, project.profile.height, scale)
        updated = apply_pip(project, overlay_track, base_track, start_frame, end_frame, layout)
        serialize_project(updated, proj_path)
        return _ok({"preset": preset, "layout": layout.model_dump(), "frames": [start_frame, end_frame]})
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def composite_wipe(
    workspace_path: str,
    project_file: str,
    track_a: int,
    track_b: int,
    start_frame: int,
    end_frame: int,
    wipe_type: str = "dissolve",
) -> dict:
    """Add a wipe or dissolve transition between two tracks."""
    from workshop_video_brain.edit_mcp.pipelines.compositing import apply_wipe
    ws = Path(workspace_path)
    proj_path = ws / project_file
    try:
        create_snapshot(ws)
        project = parse_project(proj_path)
        updated = apply_wipe(project, track_a, track_b, start_frame, end_frame, wipe_type)
        serialize_project(updated, proj_path)
        return _ok({"wipe_type": wipe_type, "frames": [start_frame, end_frame]})
    except Exception as e:
        return _err(str(e))
```

## Verification

```bash
uv run pytest tests/unit/test_compositing.py -v
```

**Pass criteria:** All PiP layout presets compute correct geometry. apply_pip and apply_wipe produce correct AddComposition intents. Invalid wipe type raises ValueError. Deep copy is enforced.
