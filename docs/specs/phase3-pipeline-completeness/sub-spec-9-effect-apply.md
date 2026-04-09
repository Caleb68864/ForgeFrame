---
type: phase-spec
master_spec: "../2026-04-09-phase3-pipeline-completeness.md"
sub_spec: 9
title: "Generic Effect Application Tool"
dependencies: [2]
date: 2026-04-09
---

# Sub-Spec 9: Generic Effect Application Tool

## Scope

MCP tools to add any named Kdenlive/MLT effect to a clip with arbitrary parameters, plus a curated reference list of common effects. Uses the `AddEffect` intent from Sub-Spec 2. Does NOT validate effect names -- Kdenlive effect availability varies by build and installed MLT packages.

## Interface Contracts

### Provides

- **Effect pipeline** in `edit_mcp/pipelines/effect_apply.py`:
  - `apply_effect(project: KdenliveProject, track_index: int, clip_index: int, effect_name: str, params: dict[str, str]) -> KdenliveProject`
  - `list_common_effects() -> list[dict]`

- **MCP tools** in `edit_mcp/server/tools.py`:
  - `effect_add(workspace_path: str, project_file: str, track: int, clip: int, effect_name: str, params: str) -> dict`
  - `effect_list_common() -> dict`

### Requires (from Sub-Spec 2)

- `AddEffect` intent type with fields: `track_index`, `clip_index`, `effect_name`, `params`
- `patch_project(project, intents) -> KdenliveProject`

## Shared Context

- Effect names are MLT service identifiers (e.g., `avfilter.lut3d`, `frei0r.colgate`, `lift_gamma_gain`, `affine`)
- The curated effect list is informational only -- it helps Claude suggest effects to users but is NOT used as a validation gate
- Multiple effects can be added to the same clip; each call appends a new `<filter>` element (never replaces existing effects)
- `apply_effect` uses `patch_project` which deep-copies -- input project is never mutated
- Snapshot must be created before saving modified project files
- `params` in the MCP tool is a JSON string parsed to `dict[str, str]`; empty string `""` or `"{}"` means no params

## Implementation Steps

### Step 1: Create effect pipeline

**Create** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/effect_apply.py`:

```python
"""Generic effect application pipeline."""
from __future__ import annotations

import logging
from typing import Any

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.core.models.timeline import AddEffect
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project

logger = logging.getLogger(__name__)

# Curated reference list -- informational only, NOT a validation gate.
# Kdenlive builds have different effects installed depending on MLT version,
# frei0r availability, and FFmpeg build flags.
_COMMON_EFFECTS: list[dict[str, str]] = [
    {
        "name": "lift_gamma_gain",
        "description": "Color wheels for shadows, midtones, highlights",
    },
    {
        "name": "avfilter.curves",
        "description": "Curve-based color adjustment",
    },
    {
        "name": "frei0r.colgate",
        "description": "White balance correction",
    },
    {
        "name": "avfilter.lut3d",
        "description": "Apply LUT file",
    },
    {
        "name": "avfilter.eq",
        "description": "Brightness, contrast, saturation",
    },
    {
        "name": "frei0r.IIRblur",
        "description": "Gaussian blur",
    },
    {
        "name": "avfilter.chromakey",
        "description": "Chroma key (green screen)",
    },
    {
        "name": "affine",
        "description": "Transform (scale, position, rotate)",
    },
]


def apply_effect(
    project: KdenliveProject,
    track_index: int,
    clip_index: int,
    effect_name: str,
    params: dict[str, str] | None = None,
) -> KdenliveProject:
    """Add a named effect to a clip in a Kdenlive project.

    Creates an AddEffect intent and patches the project via deep-copy.
    Does NOT validate effect_name -- any string is accepted.
    Multiple calls on the same clip append effects (no replacement).

    Parameters
    ----------
    project:
        Parsed Kdenlive project.
    track_index:
        Zero-based track index.
    clip_index:
        Zero-based clip index within the track.
    effect_name:
        MLT service name (e.g., "avfilter.eq", "lift_gamma_gain").
    params:
        Key-value pairs for effect properties. None or empty dict for defaults.

    Returns
    -------
    New KdenliveProject with the effect appended.

    Raises
    ------
    IndexError:
        If track_index or clip_index is out of range.
    ValueError:
        If effect_name is empty.
    """
    if not effect_name or not effect_name.strip():
        raise ValueError("effect_name must be a non-empty string")

    intent = AddEffect(
        track_index=track_index,
        clip_index=clip_index,
        effect_name=effect_name.strip(),
        params=params or {},
    )
    return patch_project(project, [intent])


def list_common_effects() -> list[dict[str, str]]:
    """Return a curated list of common Kdenlive/MLT effects.

    This list is informational only -- it helps users discover effects
    but is NOT used for validation. Any effect name can be passed to
    apply_effect() regardless of whether it appears here.
    """
    return list(_COMMON_EFFECTS)  # return a copy
```

### Step 2: Register MCP tools

**Modify** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py`:

Add the following tool registrations:

```python
@mcp.tool()
def effect_add(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    effect_name: str,
    params: str = "",
) -> dict:
    """Add a named effect to a clip in a Kdenlive project.

    effect_name is any MLT service identifier (e.g. 'avfilter.eq',
    'lift_gamma_gain'). params is a JSON string of key-value pairs
    (e.g. '{"av.brightness": "0.1"}') or empty for effect defaults.
    Snapshot is created before modifying the project.
    """
    import json as _json
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect
    from workshop_video_brain.workspace.manager import WorkspaceManager

    try:
        ws_path, workspace = _require_workspace(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))

    project_path = ws_path / project_file
    if not project_path.exists():
        return _err(f"Project file not found: {project_file}")

    if not effect_name or not effect_name.strip():
        return _err("effect_name must be a non-empty string")

    # Parse params JSON
    param_dict: dict[str, str] = {}
    if params.strip():
        try:
            param_dict = _json.loads(params)
        except _json.JSONDecodeError as exc:
            return _err(f"Invalid params JSON: {exc}")

    # Snapshot before modify
    WorkspaceManager.create_snapshot(ws_path, f"before_effect_{effect_name}")

    project = parse_project(project_path)
    try:
        patched = apply_effect(project, track, clip, effect_name, param_dict)
    except (IndexError, ValueError) as exc:
        return _err(f"Failed to apply effect: {exc}")

    serialize_project(patched, project_path)
    return _ok({
        "project_file": project_file,
        "track": track,
        "clip": clip,
        "effect_name": effect_name,
        "params": param_dict,
    })


@mcp.tool()
def effect_list_common() -> dict:
    """List common Kdenlive/MLT effects with descriptions.

    This is an informational reference -- any effect name can be used
    with effect_add regardless of whether it appears in this list.
    """
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import list_common_effects

    return _ok({"effects": list_common_effects()})
```

### Step 3: Write tests (TDD -- write first, implement to satisfy)

**Create** `tests/unit/test_effect_apply.py`:

```python
"""TDD tests for generic effect application pipeline."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.core.models.timeline import AddEffect


# --- apply_effect -----------------------------------------------------------

@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_single_effect_add(mock_patch):
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

    project = MagicMock()
    patched = MagicMock()
    mock_patch.return_value = patched

    result = apply_effect(
        project,
        track_index=0,
        clip_index=2,
        effect_name="avfilter.eq",
        params={"av.brightness": "0.1", "av.contrast": "1.2"},
    )

    assert result is patched
    mock_patch.assert_called_once()
    intents = mock_patch.call_args[0][1]
    assert len(intents) == 1
    assert isinstance(intents[0], AddEffect)
    assert intents[0].effect_name == "avfilter.eq"
    assert intents[0].track_index == 0
    assert intents[0].clip_index == 2
    assert intents[0].params == {"av.brightness": "0.1", "av.contrast": "1.2"}


@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_multiple_effects_on_same_clip(mock_patch):
    """Each apply_effect call creates a separate AddEffect intent.

    The patcher appends effects; it does not replace existing ones.
    """
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

    project = MagicMock(name="original")
    after_first = MagicMock(name="after_first")
    after_second = MagicMock(name="after_second")
    mock_patch.side_effect = [after_first, after_second]

    # First effect: color correction
    result1 = apply_effect(project, 0, 0, "lift_gamma_gain", {"lift_r": "0.9"})
    assert result1 is after_first

    # Second effect on same clip: blur
    result2 = apply_effect(result1, 0, 0, "frei0r.IIRblur", {"Amount": "0.3"})
    assert result2 is after_second

    # Two separate patch_project calls -- each appends one effect
    assert mock_patch.call_count == 2

    first_intents = mock_patch.call_args_list[0][0][1]
    assert first_intents[0].effect_name == "lift_gamma_gain"

    second_intents = mock_patch.call_args_list[1][0][1]
    assert second_intents[0].effect_name == "frei0r.IIRblur"


@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_invalid_track_index_raises(mock_patch):
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

    mock_patch.side_effect = IndexError("Track index 99 out of range")

    with pytest.raises(IndexError, match="Track index 99"):
        apply_effect(MagicMock(), 99, 0, "avfilter.eq")


@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_invalid_clip_index_raises(mock_patch):
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

    mock_patch.side_effect = IndexError("Clip index 50 out of range")

    with pytest.raises(IndexError, match="Clip index 50"):
        apply_effect(MagicMock(), 0, 50, "avfilter.eq")


def test_empty_effect_name_raises():
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

    with pytest.raises(ValueError, match="effect_name must be a non-empty string"):
        apply_effect(MagicMock(), 0, 0, "", {})

    with pytest.raises(ValueError, match="effect_name must be a non-empty string"):
        apply_effect(MagicMock(), 0, 0, "   ", {})


@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_empty_params(mock_patch):
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

    mock_patch.return_value = MagicMock()

    # None params
    apply_effect(MagicMock(), 0, 0, "affine", None)
    intents = mock_patch.call_args[0][1]
    assert intents[0].params == {}

    # Empty dict params
    apply_effect(MagicMock(), 0, 0, "affine", {})
    intents = mock_patch.call_args[0][1]
    assert intents[0].params == {}


@patch("workshop_video_brain.edit_mcp.adapters.kdenlive.patcher.patch_project")
def test_effect_name_not_validated(mock_patch):
    """Any effect name is accepted -- no hardcoded validation list."""
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

    mock_patch.return_value = MagicMock()

    # Completely custom/unknown effect name should not raise
    apply_effect(MagicMock(), 0, 0, "my_custom_plugin.effect_v2", {"key": "val"})
    intents = mock_patch.call_args[0][1]
    assert intents[0].effect_name == "my_custom_plugin.effect_v2"


# --- list_common_effects ----------------------------------------------------

def test_list_common_effects_returns_expected_items():
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import list_common_effects

    effects = list_common_effects()

    assert isinstance(effects, list)
    assert len(effects) >= 8  # at least the 8 curated effects

    names = [e["name"] for e in effects]
    assert "lift_gamma_gain" in names
    assert "avfilter.lut3d" in names
    assert "avfilter.eq" in names
    assert "avfilter.chromakey" in names
    assert "affine" in names
    assert "frei0r.IIRblur" in names

    # Each entry has name and description
    for effect in effects:
        assert "name" in effect
        assert "description" in effect
        assert isinstance(effect["name"], str)
        assert isinstance(effect["description"], str)
        assert len(effect["name"]) > 0
        assert len(effect["description"]) > 0


def test_list_common_effects_returns_copy():
    """Mutating the returned list should not affect the module-level list."""
    from workshop_video_brain.edit_mcp.pipelines.effect_apply import list_common_effects

    effects1 = list_common_effects()
    effects1.clear()

    effects2 = list_common_effects()
    assert len(effects2) >= 8  # unaffected
```

## Verification Commands

```bash
# Run effect apply unit tests
uv run pytest tests/unit/test_effect_apply.py -v

# Verify pipeline importable
uv run python -c "
from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect, list_common_effects
effects = list_common_effects()
print(f'{len(effects)} common effects available')
for e in effects:
    print(f'  {e[\"name\"]}: {e[\"description\"]}')
"

# Run full suite to confirm no regressions
uv run pytest tests/ -v
```

## Acceptance Criteria

- [ ] `apply_effect()` creates an `AddEffect` intent and calls `patch_project()` -- deep-copies, never mutates input
- [ ] `apply_effect()` accepts any `effect_name` string -- no hardcoded validation
- [ ] `apply_effect()` raises `ValueError` for empty `effect_name`
- [ ] `apply_effect()` passes `params` dict through to `AddEffect` intent; `None` / empty dict both work
- [ ] Multiple `apply_effect()` calls on the same clip append effects (no replacement)
- [ ] Invalid `track_index` / `clip_index` propagates `IndexError` from patcher
- [ ] `list_common_effects()` returns at least 8 curated effects with `name` and `description`
- [ ] `list_common_effects()` returns a copy -- mutations do not affect the source
- [ ] MCP tool `effect_add` parses `params` JSON string to dict, creates snapshot, applies effect, saves project
- [ ] MCP tool `effect_add` returns `_err()` for missing project file, empty effect name, or invalid JSON
- [ ] MCP tool `effect_list_common` returns `_ok({"effects": [...]})` with the curated list
- [ ] All tests pass: single effect, multiple effects on same clip, invalid track/clip, empty effect name, empty params, unchecked effect name, list returns expected items, list returns copy
- [ ] Existing test suite still passes
