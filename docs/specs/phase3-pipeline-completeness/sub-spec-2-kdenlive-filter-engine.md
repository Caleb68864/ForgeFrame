---
type: phase-spec
master_spec: "docs/specs/2026-04-09-phase3-pipeline-completeness.md"
sub_spec: 2
title: "Kdenlive Filter Insertion Engine"
dependencies: none
date: 2026-04-09
---

# Sub-Spec 2: Kdenlive Filter Insertion Engine

## Shared Context
Infrastructure sub-spec. Adds `AddEffect` and `AddComposition` intent types to the Kdenlive patcher, enabling downstream sub-specs to apply MLT filters (e.g., color correction, volume normalization) and compositions (e.g., dissolves, wipes) to timeline clips. Used by sub-specs 8, 9, 11.

## Interface Contract
**Provides:**
- `AddEffect` intent type -- creates `<filter>` as `OpaqueElement` objects appended to `project.opaque_elements` with `position_hint="after_tractor"` (matches existing SetClipSpeed and AudioFade patterns)
- `AddComposition` intent type -- creates `<transition>` as `OpaqueElement` objects appended to `project.opaque_elements` with `position_hint="after_tractor"`
- Both handled by `patch_project()` via existing dispatch pattern

**Requires:** nothing (extends existing patcher.py and timeline.py)

## Implementation Steps

### Step 1: Write failing tests for AddEffect and AddComposition

File: `tests/unit/test_filter_insertion.py`

```python
"""Tests for Kdenlive filter and composition insertion via patcher."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import AddEffect, AddComposition
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_project() -> KdenliveProject:
    """Create a minimal KdenliveProject with one video track and two clips."""
    return KdenliveProject(
        profile=ProjectProfile(width=1920, height=1080, fps=25.0),
        producers=[
            Producer(id="producer0", resource="/media/clip_a.mp4"),
            Producer(id="producer1", resource="/media/clip_b.mp4"),
        ],
        tracks=[
            Track(id="playlist0", track_type="video", name="V1"),
            Track(id="playlist1", track_type="video", name="V2"),
        ],
        playlists=[
            Playlist(
                id="playlist0",
                entries=[
                    PlaylistEntry(producer_id="producer0", in_point=0, out_point=100),
                    PlaylistEntry(producer_id="producer1", in_point=0, out_point=200),
                ],
            ),
            Playlist(
                id="playlist1",
                entries=[
                    PlaylistEntry(producer_id="producer0", in_point=50, out_point=150),
                ],
            ),
        ],
        guides=[],
        opaque_elements=[],
    )


# ---------------------------------------------------------------------------
# AddEffect tests
# ---------------------------------------------------------------------------

class TestAddEffect:
    def test_effect_appended_as_opaque_element(self):
        project = _minimal_project()
        intent = AddEffect(
            track_index=0,
            clip_index=0,
            effect_name="brightness",
            params={"av.brightness": "0.1"},
        )

        result = patch_project(project, [intent])

        # Should have one new opaque element
        assert len(result.opaque_elements) == 1
        elem = result.opaque_elements[0]
        assert elem.tag == "filter"

        # Parse the XML and verify structure
        xml_elem = ET.fromstring(elem.xml_string)
        assert xml_elem.get("mlt_service") == "brightness"

        # Verify params are present as <property> children
        props = {p.get("name"): p.text for p in xml_elem.findall("property")}
        assert props["av.brightness"] == "0.1"

    def test_multiple_effects_appended_not_replaced(self):
        project = _minimal_project()
        intents = [
            AddEffect(
                track_index=0,
                clip_index=0,
                effect_name="brightness",
                params={"av.brightness": "0.1"},
            ),
            AddEffect(
                track_index=0,
                clip_index=0,
                effect_name="volume",
                params={"level": "0.8"},
            ),
        ]

        result = patch_project(project, intents)

        assert len(result.opaque_elements) == 2
        services = []
        for elem in result.opaque_elements:
            xml_elem = ET.fromstring(elem.xml_string)
            services.append(xml_elem.get("mlt_service"))
        assert "brightness" in services
        assert "volume" in services

    def test_effect_references_correct_clip(self):
        project = _minimal_project()
        intent = AddEffect(
            track_index=0,
            clip_index=1,
            effect_name="charcoal",
            params={},
        )

        result = patch_project(project, [intent])

        elem = result.opaque_elements[0]
        xml_elem = ET.fromstring(elem.xml_string)
        # Should reference the correct track and clip index
        assert xml_elem.get("track") == "0"
        assert xml_elem.get("clip_index") == "1"

    def test_effect_invalid_track_index_skipped(self):
        project = _minimal_project()
        intent = AddEffect(
            track_index=99,
            clip_index=0,
            effect_name="brightness",
            params={},
        )

        result = patch_project(project, [intent])

        # No opaque elements should be added
        assert len(result.opaque_elements) == 0

    def test_effect_invalid_clip_index_skipped(self):
        project = _minimal_project()
        intent = AddEffect(
            track_index=0,
            clip_index=99,
            effect_name="brightness",
            params={},
        )

        result = patch_project(project, [intent])

        assert len(result.opaque_elements) == 0

    def test_original_project_not_mutated(self):
        project = _minimal_project()
        original_count = len(project.opaque_elements)
        intent = AddEffect(
            track_index=0,
            clip_index=0,
            effect_name="brightness",
            params={"av.brightness": "0.5"},
        )

        result = patch_project(project, [intent])

        assert len(project.opaque_elements) == original_count
        assert len(result.opaque_elements) == 1


# ---------------------------------------------------------------------------
# AddComposition tests
# ---------------------------------------------------------------------------

class TestAddComposition:
    def test_composition_appended_as_transition(self):
        project = _minimal_project()
        intent = AddComposition(
            track_a=0,
            track_b=1,
            start_frame=50,
            end_frame=100,
            composition_type="luma",
            params={"softness": "0.5"},
        )

        result = patch_project(project, [intent])

        assert len(result.opaque_elements) == 1
        elem = result.opaque_elements[0]
        assert elem.tag == "transition"

        xml_elem = ET.fromstring(elem.xml_string)
        assert xml_elem.get("mlt_service") == "luma"

        # Verify track routing
        props = {p.get("name"): p.text for p in xml_elem.findall("property")}
        assert props["a_track"] == "0"
        assert props["b_track"] == "1"
        assert props["in"] == "50"
        assert props["out"] == "100"
        assert props["softness"] == "0.5"

    def test_composition_preserves_existing_transitions(self):
        project = _minimal_project()
        # Add a pre-existing opaque transition
        existing = OpaqueElement(
            tag="transition",
            xml_string='<transition mlt_service="mix"><property name="a_track">0</property></transition>',
            position_hint="after_tractor",
        )
        project.opaque_elements.append(existing)

        intent = AddComposition(
            track_a=0,
            track_b=1,
            start_frame=0,
            end_frame=25,
            composition_type="composite",
            params={},
        )

        result = patch_project(project, [intent])

        # Both old and new should be present
        assert len(result.opaque_elements) == 2
        tags = [e.tag for e in result.opaque_elements]
        assert tags.count("transition") == 2

    def test_composition_with_no_params(self):
        project = _minimal_project()
        intent = AddComposition(
            track_a=0,
            track_b=1,
            start_frame=0,
            end_frame=50,
            composition_type="dissolve",
            params={},
        )

        result = patch_project(project, [intent])

        elem = result.opaque_elements[0]
        xml_elem = ET.fromstring(elem.xml_string)
        # Should have only the core properties (a_track, b_track, in, out), no extra params
        prop_names = {p.get("name") for p in xml_elem.findall("property")}
        assert "a_track" in prop_names
        assert "b_track" in prop_names
        assert "in" in prop_names
        assert "out" in prop_names

    def test_original_project_not_mutated_composition(self):
        project = _minimal_project()
        original_count = len(project.opaque_elements)
        intent = AddComposition(
            track_a=0,
            track_b=1,
            start_frame=0,
            end_frame=50,
            composition_type="luma",
            params={},
        )

        result = patch_project(project, [intent])

        assert len(project.opaque_elements) == original_count
        assert len(result.opaque_elements) == 1
```

Run: `uv run pytest tests/unit/test_filter_insertion.py -v`
Expected: FAIL (AddEffect, AddComposition not importable from timeline.py; patcher does not handle them)

### Step 2: Add AddEffect and AddComposition intent models

File: `workshop-video-brain/src/workshop_video_brain/core/models/timeline.py`

Add after the existing `SetTrackVisibility` class:
```python
class AddEffect(TimelineIntent):
    """Apply an MLT filter (effect) to a clip on a track.

    The patcher inserts a <filter mlt_service="{effect_name}"> element
    with <property> children for each entry in params.
    """
    track_index: int = 0
    clip_index: int = 0
    effect_name: str = ""
    params: dict[str, str] = Field(default_factory=dict)


class AddComposition(TimelineIntent):
    """Insert an MLT transition (composition) between two tracks.

    The patcher inserts a <transition mlt_service="{composition_type}">
    element with a_track, b_track, in, out properties and any extra params.
    """
    track_a: int = 0
    track_b: int = 0
    start_frame: int = 0
    end_frame: int = 0
    composition_type: str = ""
    params: dict[str, str] = Field(default_factory=dict)
```

### Step 3: Re-export from models __init__.py

File: `workshop-video-brain/src/workshop_video_brain/core/models/__init__.py`

Add `AddEffect` and `AddComposition` to the import from `.timeline` and to `__all__`.

In the timeline import block, add:
```python
AddEffect,
AddComposition,
```

In `__all__`, add to the timeline intents section:
```python
"AddEffect",
"AddComposition",
```

### Step 4: Implement patcher handlers for AddEffect and AddComposition

File: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py`

Add imports at the top (in the timeline import block):
```python
from workshop_video_brain.core.models.timeline import (
    ...,
    AddEffect,
    AddComposition,
)
```

Add dispatch cases in `patch_project()`, inside the for-loop before the `else` branch:
```python
elif isinstance(intent, AddEffect):
    _apply_add_effect(new_project, intent)
elif isinstance(intent, AddComposition):
    _apply_add_composition(new_project, intent)
```

Add handler functions at the end of the file:
```python
def _apply_add_effect(project: KdenliveProject, intent: AddEffect) -> None:
    """Insert an MLT filter element for a clip on a track.

    Builds a <filter mlt_service="..."> XML element with <property> children
    for each param, and appends it as an OpaqueElement.
    """
    # Resolve track by index
    if intent.track_index < 0 or intent.track_index >= len(project.playlists):
        logger.warning(
            "AddEffect: track_index %d out of range (have %d playlists) -- skipped.",
            intent.track_index, len(project.playlists),
        )
        return

    playlist = project.playlists[intent.track_index]
    real_entries = [e for e in playlist.entries if e.producer_id]

    if intent.clip_index < 0 or intent.clip_index >= len(real_entries):
        logger.warning(
            "AddEffect: clip_index %d out of range (playlist '%s' has %d clips) -- skipped.",
            intent.clip_index, playlist.id, len(real_entries),
        )
        return

    entry = real_entries[intent.clip_index]

    # Build filter XML
    # Filters are OpaqueElement objects with position_hint="after_tractor",
    # matching the existing SetClipSpeed and AudioFade patterns in the patcher.
    props_xml = "".join(
        f'<property name="{k}">{v}</property>' for k, v in intent.params.items()
    )
    filter_id = f"effect_{intent.track_index}_{intent.clip_index}_{intent.effect_name}"
    xml = (
        f'<filter id="{filter_id}" '
        f'mlt_service="{intent.effect_name}" '
        f'track="{intent.track_index}" '
        f'clip_index="{intent.clip_index}">'
        f'{props_xml}'
        f'</filter>'
    )

    element = OpaqueElement(
        tag="filter",
        xml_string=xml,
        position_hint="after_tractor",
    )
    project.opaque_elements.append(element)
    logger.info(
        "AddEffect: applied '%s' to clip %d on track '%s'",
        intent.effect_name, intent.clip_index, playlist.id,
    )


def _apply_add_composition(project: KdenliveProject, intent: AddComposition) -> None:
    """Insert an MLT transition element between two tracks.

    Builds a <transition mlt_service="..."> element with a_track, b_track,
    in, out properties plus any extra params, and appends it as an OpaqueElement.
    """
    # Build core properties
    props = {
        "a_track": str(intent.track_a),
        "b_track": str(intent.track_b),
        "in": str(intent.start_frame),
        "out": str(intent.end_frame),
    }
    # Merge extra params (extra params cannot override core keys)
    for k, v in intent.params.items():
        if k not in props:
            props[k] = v

    props_xml = "".join(
        f'<property name="{k}">{v}</property>' for k, v in props.items()
    )
    xml = (
        f'<transition mlt_service="{intent.composition_type}">'
        f'{props_xml}'
        f'</transition>'
    )

    element = OpaqueElement(
        tag="transition",
        xml_string=xml,
        position_hint="after_tractor",
    )
    project.opaque_elements.append(element)
    logger.info(
        "AddComposition: applied '%s' between tracks %d and %d (frames %d-%d)",
        intent.composition_type, intent.track_a, intent.track_b,
        intent.start_frame, intent.end_frame,
    )
```

### Step 5: Run new tests

Run: `uv run pytest tests/unit/test_filter_insertion.py -v`
Expected: all PASS

### Step 6: Run full test suite

Run: `uv run pytest tests/ -v`
Expected: all existing tests pass + new tests pass

### Step 7: Commit

```bash
git add tests/unit/test_filter_insertion.py
git add workshop-video-brain/src/workshop_video_brain/core/models/timeline.py
git add workshop-video-brain/src/workshop_video_brain/core/models/__init__.py
git add workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py
git commit -m "feat: add AddEffect and AddComposition intent types to Kdenlive patcher"
```

## Verification

- `uv run pytest tests/unit/test_filter_insertion.py -v` -- all pass
- `uv run pytest tests/ -v` -- all existing tests still pass
- AddEffect inserts `<filter>` with correct mlt_service and property children
- AddComposition inserts `<transition>` with a_track, b_track, in, out properties
- Multiple effects append (never replace)
- Existing transitions preserved when adding compositions
- Original project never mutated (deep-copy verified)
- Invalid track/clip indices logged and skipped gracefully
