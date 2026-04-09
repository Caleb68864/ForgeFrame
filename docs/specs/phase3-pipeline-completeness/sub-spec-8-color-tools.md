---
type: phase-spec
master_spec: "../2026-04-09-phase3-pipeline-completeness.md"
sub_spec: 8
title: "Color Analysis and LUT Application"
dependencies: [1, 2]
date: 2026-04-09
---

# Sub-Spec 8: Color Analysis and LUT Application

## Scope

MCP tools to analyze color metadata of media files (color space, primaries, transfer characteristics, HDR detection) and apply LUT files to clips in Kdenlive projects via the `AddEffect` intent from Sub-Spec 2. Generates actionable recommendations for SDR/HDR delivery workflows.

## Interface Contracts

### Provides

- **Color model** in `core/models/color.py`:
  - `ColorAnalysis(file_path, color_space, color_primaries, color_transfer, bit_depth, is_hdr, recommendations)`

- **Color pipeline** in `edit_mcp/pipelines/color_tools.py`:
  - `analyze_color(file_path: Path) -> ColorAnalysis`
  - `apply_lut_to_project(project: KdenliveProject, track_index: int, clip_index: int, lut_path: str, effect_name: str = "avfilter.lut3d") -> KdenliveProject` -- `effect_name` can be `"frei0r.lut3d"` on some Kdenlive builds

- **MCP tools** in `edit_mcp/server/tools.py`:
  - `color_analyze(file_path: str) -> dict`
  - `color_apply_lut(workspace_path: str, project_file: str, track: int, clip: int, lut_path: str) -> dict`

### Requires (from Sub-Spec 1)

- `probe_media(path: Path) -> MediaAsset` with extended fields: `color_space`, `color_primaries`, `color_transfer`

### Requires (from Sub-Spec 2)

- `AddEffect` intent type with fields: `track_index`, `clip_index`, `effect_name`, `params`
- `patch_project(project, intents) -> KdenliveProject`

## Shared Context

- Color metadata comes from ffprobe's video stream fields: `color_space`, `color_primaries`, `color_transfer`
- Common values: `"bt709"` (HD SDR), `"bt2020nc"` / `"bt2020"` (UHD/HDR), `"smpte170m"` (SD/NTSC)
- HDR detection: `color_transfer` contains `"smpte2084"` (PQ/HDR10) or `"arib-std-b67"` (HLG)
- LUT application uses Kdenlive's `avfilter.lut3d` effect with param `av.file` pointing to the .cube/.3dl file
- `apply_lut_to_project` deep-copies via `patch_project` -- never mutates input
- Snapshot must be created before saving modified project files

## Implementation Steps

### Step 1: Create color model

**Create** `workshop-video-brain/src/workshop_video_brain/core/models/color.py`:

```python
"""Color analysis models."""
from __future__ import annotations

from pydantic import BaseModel


class ColorAnalysis(BaseModel):
    """Result of analyze_color() -- color metadata and recommendations."""
    file_path: str
    color_space: str | None = None
    color_primaries: str | None = None
    color_transfer: str | None = None
    bit_depth: int | None = None
    is_hdr: bool = False
    recommendations: list[str] = []
```

### Step 2: Re-export model

**Modify** `workshop-video-brain/src/workshop_video_brain/core/models/__init__.py`:

- Add import: `from .color import ColorAnalysis`
- Add to `__all__`: `"ColorAnalysis"` under a `# color` comment block

### Step 3: Create color pipeline

**Create** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/color_tools.py`:

```python
"""Color analysis and LUT application pipeline."""
from __future__ import annotations

import logging
from pathlib import Path

from workshop_video_brain.core.models.color import ColorAnalysis
from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.core.models.timeline import AddEffect
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

logger = logging.getLogger(__name__)

# Transfer characteristics that indicate HDR content
_HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}


def analyze_color(file_path: Path) -> ColorAnalysis:
    """Probe a media file and return color metadata with recommendations.

    Uses probe_media() from Sub-Spec 1 to read extended color fields.
    """
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media

    asset = probe_media(file_path)

    color_space = getattr(asset, "color_space", None)
    color_primaries = getattr(asset, "color_primaries", None)
    color_transfer = getattr(asset, "color_transfer", None)
    bit_depth = getattr(asset, "bit_depth", None)

    is_hdr = False
    if color_transfer and any(h in color_transfer for h in _HDR_TRANSFERS):
        is_hdr = True

    recommendations = _build_recommendations(
        color_space, color_primaries, color_transfer, is_hdr
    )

    return ColorAnalysis(
        file_path=str(file_path),
        color_space=color_space,
        color_primaries=color_primaries,
        color_transfer=color_transfer,
        bit_depth=bit_depth,
        is_hdr=is_hdr,
        recommendations=recommendations,
    )


def _build_recommendations(
    color_space: str | None,
    color_primaries: str | None,
    color_transfer: str | None,
    is_hdr: bool,
) -> list[str]:
    """Generate actionable color recommendations."""
    recs: list[str] = []

    if is_hdr:
        recs.append(
            "Source is HDR -- consider tone-mapping to BT.709 for SDR delivery"
        )
        if color_transfer and "smpte2084" in color_transfer:
            recs.append("HDR format: PQ (HDR10). Use a PQ-to-SDR LUT for YouTube SDR.")
        elif color_transfer and "arib-std-b67" in color_transfer:
            recs.append("HDR format: HLG. Use an HLG-to-SDR LUT for YouTube SDR.")
        return recs

    if color_space is None and color_primaries is None:
        recs.append(
            "No color metadata found -- assuming BT.709"
        )
        return recs

    if color_primaries and "bt2020" in color_primaries:
        recs.append(
            "Source is BT.2020 -- consider BT.709 conversion for SDR delivery"
        )
    elif color_primaries and "bt709" in color_primaries:
        recs.append(
            "Source is BT.709 SDR -- no conversion needed for YouTube"
        )
    elif color_primaries and "smpte170m" in color_primaries:
        recs.append(
            "Source is BT.601 (SD) -- upconvert color space if targeting HD delivery"
        )

    if color_space and "bt709" in color_space:
        recs.append("Color matrix: BT.709 -- standard for HD content")
    elif color_space and "bt2020" in color_space:
        recs.append("Color matrix: BT.2020 -- wide gamut, verify display compatibility")

    return recs


def apply_lut_to_project(
    project: KdenliveProject,
    track_index: int,
    clip_index: int,
    lut_path: str,
    effect_name: str = "avfilter.lut3d",
) -> KdenliveProject:
    """Apply a LUT file to a clip in a Kdenlive project.

    Creates an AddEffect intent with the given effect_name and
    patches the project. Returns a new KdenliveProject (deep-copy).

    Parameters
    ----------
    project:
        Parsed Kdenlive project.
    track_index:
        Zero-based track index.
    clip_index:
        Zero-based clip index within the track.
    lut_path:
        Absolute path to the .cube / .3dl LUT file.
    effect_name:
        MLT service name for the LUT effect. Default is "avfilter.lut3d".
        Some Kdenlive builds use "frei0r.lut3d" instead.
    """
    intent = AddEffect(
        track_index=track_index,
        clip_index=clip_index,
        effect_name=effect_name,
        params={"av.file": lut_path},
    )
    return patch_project(project, [intent])
```

### Step 4: Register MCP tools

**Modify** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`:

Add the following tool registrations:

```python
@mcp.tool()
def color_analyze(file_path: str) -> dict:
    """Analyze color metadata of a media file.

    Returns color space, primaries, transfer characteristics, HDR detection,
    and actionable recommendations for delivery workflows.
    """
    from workshop_video_brain.edit_mcp.pipelines.color_tools import analyze_color

    p = Path(file_path)
    if not p.exists():
        return _err(f"File not found: {file_path}")

    analysis = analyze_color(p)
    return _ok(analysis.model_dump())


@mcp.tool()
def color_apply_lut(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    lut_path: str,
) -> dict:
    """Apply a LUT file to a clip in a Kdenlive project.

    Creates a snapshot before modifying the project. The LUT is applied via
    the avfilter.lut3d effect and appended to any existing effects on the clip.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines.color_tools import apply_lut_to_project
    from workshop_video_brain.workspace.manager import WorkspaceManager

    try:
        ws_path, workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))

    project_path = ws_path / project_file
    if not project_path.exists():
        return _err(f"Project file not found: {project_file}")

    lut = Path(lut_path)
    if not lut.exists():
        return _err(f"LUT file not found: {lut_path}")

    # Snapshot before modify
    WorkspaceManager.create_snapshot(ws_path, f"before_lut_{lut.stem}")

    project = parse_project(project_path)
    try:
        patched = apply_lut_to_project(project, track, clip, str(lut))
    except (IndexError, ValueError) as exc:
        return _err(f"Failed to apply LUT: {exc}")

    serialize_project(patched, project_path)
    return _ok({
        "project_file": project_file,
        "track": track,
        "clip": clip,
        "lut_applied": str(lut),
    })
```

### Step 5: Write tests (TDD -- write first, implement to satisfy)

**Create** `tests/unit/test_color_tools.py`:

```python
"""TDD tests for color analysis and LUT application."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.core.models.color import ColorAnalysis


# --- fixtures ---------------------------------------------------------------

def _make_asset(**kwargs):
    """Create a mock MediaAsset with color fields."""
    asset = MagicMock()
    asset.color_space = kwargs.get("color_space", None)
    asset.color_primaries = kwargs.get("color_primaries", None)
    asset.color_transfer = kwargs.get("color_transfer", None)
    asset.bit_depth = kwargs.get("bit_depth", None)
    return asset


# --- analyze_color ----------------------------------------------------------

@patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.probe_media")
def test_bt709_source(mock_probe):
    from workshop_video_brain.edit_mcp.pipelines.color_tools import analyze_color

    mock_probe.return_value = _make_asset(
        color_space="bt709",
        color_primaries="bt709",
        color_transfer="bt709",
        bit_depth=8,
    )
    result = analyze_color(Path("/tmp/clip.mp4"))

    assert result.color_space == "bt709"
    assert result.color_primaries == "bt709"
    assert result.is_hdr is False
    assert any("BT.709 SDR" in r for r in result.recommendations)


@patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.probe_media")
def test_bt2020_source(mock_probe):
    from workshop_video_brain.edit_mcp.pipelines.color_tools import analyze_color

    mock_probe.return_value = _make_asset(
        color_space="bt2020nc",
        color_primaries="bt2020",
        color_transfer="bt709",
        bit_depth=10,
    )
    result = analyze_color(Path("/tmp/clip.mp4"))

    assert result.color_primaries == "bt2020"
    assert result.is_hdr is False
    assert any("BT.2020" in r for r in result.recommendations)


@patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.probe_media")
def test_missing_metadata(mock_probe):
    from workshop_video_brain.edit_mcp.pipelines.color_tools import analyze_color

    mock_probe.return_value = _make_asset()  # all None
    result = analyze_color(Path("/tmp/clip.mp4"))

    assert result.color_space is None
    assert result.is_hdr is False
    assert any("No color metadata found" in r for r in result.recommendations)


@patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.probe_media")
def test_hdr_pq_detection(mock_probe):
    from workshop_video_brain.edit_mcp.pipelines.color_tools import analyze_color

    mock_probe.return_value = _make_asset(
        color_space="bt2020nc",
        color_primaries="bt2020",
        color_transfer="smpte2084",
        bit_depth=10,
    )
    result = analyze_color(Path("/tmp/clip.mp4"))

    assert result.is_hdr is True
    assert any("HDR" in r for r in result.recommendations)
    assert any("PQ" in r for r in result.recommendations)


@patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.probe_media")
def test_hdr_hlg_detection(mock_probe):
    from workshop_video_brain.edit_mcp.pipelines.color_tools import analyze_color

    mock_probe.return_value = _make_asset(
        color_space="bt2020nc",
        color_primaries="bt2020",
        color_transfer="arib-std-b67",
        bit_depth=10,
    )
    result = analyze_color(Path("/tmp/clip.mp4"))

    assert result.is_hdr is True
    assert any("HLG" in r for r in result.recommendations)


# --- apply_lut_to_project ---------------------------------------------------

@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_lut_application_creates_add_effect(mock_patch):
    from workshop_video_brain.edit_mcp.pipelines.color_tools import apply_lut_to_project
    from workshop_video_brain.core.models.timeline import AddEffect

    mock_project = MagicMock()
    mock_patch.return_value = MagicMock()

    result = apply_lut_to_project(
        mock_project, track_index=0, clip_index=1, lut_path="/luts/film_look.cube"
    )

    mock_patch.assert_called_once()
    call_args = mock_patch.call_args
    intents = call_args[0][1]  # second positional arg
    assert len(intents) == 1
    assert isinstance(intents[0], AddEffect)
    assert intents[0].effect_name == "avfilter.lut3d"
    assert intents[0].params == {"av.file": "/luts/film_look.cube"}
    assert intents[0].track_index == 0
    assert intents[0].clip_index == 1


@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_lut_round_trip(mock_patch):
    """Verify that applying a LUT returns the patched project, not the original."""
    from workshop_video_brain.edit_mcp.pipelines.color_tools import apply_lut_to_project

    original = MagicMock(name="original")
    patched = MagicMock(name="patched")
    mock_patch.return_value = patched

    result = apply_lut_to_project(original, 0, 0, "/luts/rec709.cube")

    assert result is patched
    assert result is not original


@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_lut_invalid_track_propagates(mock_patch):
    """If patcher raises IndexError for bad track, it should propagate."""
    from workshop_video_brain.edit_mcp.pipelines.color_tools import apply_lut_to_project

    mock_patch.side_effect = IndexError("Track index 99 out of range")

    with pytest.raises(IndexError, match="Track index 99"):
        apply_lut_to_project(MagicMock(), 99, 0, "/luts/test.cube")
```

## Verification Commands

```bash
# Run color tools unit tests
uv run pytest tests/unit/test_color_tools.py -v

# Verify model importable
uv run python -c "from workshop_video_brain.core.models import ColorAnalysis; print('OK')"

# Run full suite to confirm no regressions
uv run pytest tests/ -v

# Manual: analyze color on a sample file
uv run python -c "
from pathlib import Path
from workshop_video_brain.edit_mcp.pipelines.color_tools import analyze_color
result = analyze_color(Path('tests/fixtures/media/sample.mp4'))
print(f'Color space: {result.color_space}')
print(f'HDR: {result.is_hdr}')
for r in result.recommendations:
    print(f'  - {r}')
"
```

## Acceptance Criteria

- [ ] `ColorAnalysis` model created in `core/models/color.py`
- [ ] Model re-exported in `core/models/__init__.py` `__all__`
- [ ] `analyze_color()` probes file via `probe_media()` and reads extended color fields
- [ ] BT.709 source produces "no conversion needed for YouTube" recommendation
- [ ] BT.2020 source produces "consider BT.709 conversion" recommendation
- [ ] Missing metadata produces "No color metadata found -- assuming BT.709" recommendation
- [ ] HDR detected when `color_transfer` contains `smpte2084` (PQ) or `arib-std-b67` (HLG)
- [ ] `apply_lut_to_project()` creates `AddEffect` intent with `effect_name` (default `"avfilter.lut3d"`, configurable to `"frei0r.lut3d"`) and `params={"av.file": lut_path}`
- [ ] LUT application uses `patch_project()` -- deep-copies, never mutates input
- [ ] MCP tool `color_analyze` returns `_ok(analysis.model_dump())`
- [ ] MCP tool `color_apply_lut` creates snapshot before modifying project
- [ ] MCP tool `color_apply_lut` returns clear error for missing project/LUT files
- [ ] Invalid track/clip index error propagated cleanly
- [ ] All tests pass: bt709, bt2020, missing metadata, HDR PQ, HDR HLG, LUT intent creation, LUT round-trip, invalid track
- [ ] Existing test suite still passes
