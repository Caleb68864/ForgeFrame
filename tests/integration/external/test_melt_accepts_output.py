"""melt-accepts: every project-writing tool family must load in real melt.

Non-self-referential oracle: build a tiny project, apply the real tool code
path (intents through ``patch_project`` / the effect-placement functions),
serialize with the real serializer, then run ``melt ... -consumer null:`` and
assert it loads and processes without a fatal error.

These are acceptance (loadability) checks -- they pass for the current code
even where §1.1 makes a tool a semantic no-op. Whether the effect actually
*renders* is proven separately (test_effect_visible / test_speed_duration).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.timeline import (
    AddClip,
    AddComposition,
    AddGuide,
    AddTransition,
    AudioFade,
    CreateTrack,
    InsertGap,
    SetClipSpeed,
    SetTrackMute,
    SetTrackVisibility,
    SplitClip,
    TrimClip,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

from . import builders
from ._oracle import melt_accepts

pytestmark = pytest.mark.external


def _with_effect(service: str, props=None, track: int = 0, clip: int = 0):
    proj = builders.solid_color_project()
    xml = builders.build_filter_xml(service, track, clip, props or [])
    patcher.insert_effect_xml(proj, (track, clip), xml, position=0)
    return proj


def _with_intents(proj, intents):
    return patcher.patch_project(proj, intents)


# §1.1 known-broken: these tools emit XML that MLT rejects at load time
# (transition/filter without mlt_service, invalid custom "type" attr). Marked
# xfail(strict=True) so the suite is green today and fails loudly the moment
# the correctness wave makes melt accept them.
KNOWN_BROKEN = {
    "transitions_apply": '§1.1 transition pseudo-XML has no mlt_service -- melt fails to load it',
    "clip_speed": '§1.1 <filter type="speed"> has no mlt_service (needs timewarp producer) -- melt fails to load it',
    "audio_fade": '§1.1 <filter type="volume"> uses custom "type" attr, no mlt_service -- melt fails to load it',
}


# Each scenario returns a fully-built KdenliveProject ready to serialize.
SCENARIOS = {
    "clip_insert": lambda: _with_intents(
        builders.solid_color_project(),
        [AddClip(producer_id="producer_0", track_ref=builders.VIDEO_TRACK,
                 in_point=0, out_point=24)],
    ),
    "effect_add_negate": lambda: _with_effect("avfilter.negate"),
    "effect_wrapper_scanline": lambda: _with_effect("frei0r.scanline0r"),
    "effect_brightness_params": lambda: _with_effect(
        "brightness", props=[("level", "0.5")]
    ),
    "composite_set": lambda: _with_intents(
        builders.two_video_track_project(),
        [AddComposition(track_a=0, track_b=1, start_frame=0, end_frame=49,
                        composition_type="frei0r.cairoblend")],
    ),
    "transitions_apply": lambda: _with_intents(
        builders.sequence_project(),
        [AddTransition(type="luma", track_ref=builders.VIDEO_TRACK,
                       left_clip_ref="0", right_clip_ref="1", duration_frames=12)],
    ),
    "clip_speed": lambda: _with_intents(
        builders.sequence_project(),
        [SetClipSpeed(track_ref=builders.VIDEO_TRACK, clip_index=0, speed=2.0)],
    ),
    "track_mute": lambda: _with_intents(
        builders.solid_color_project(),
        [SetTrackMute(track_ref=builders.AUDIO_TRACK, muted=True)],
    ),
    "track_visibility": lambda: _with_intents(
        builders.solid_color_project(),
        [SetTrackVisibility(track_ref=builders.VIDEO_TRACK, visible=False)],
    ),
    "audio_fade": lambda: _with_intents(
        builders.solid_color_project(),
        [AudioFade(track_ref=builders.AUDIO_TRACK, clip_index=0,
                   fade_type="in", duration_frames=24)],
    ),
    "trim_clip": lambda: _with_intents(
        builders.solid_color_project(),
        [TrimClip(clip_ref=f"{builders.VIDEO_TRACK}:0", new_in=5, new_out=40)],
    ),
    "insert_gap": lambda: _with_intents(
        builders.sequence_project(),
        [InsertGap(track_id=builders.VIDEO_TRACK, position=1, duration_frames=10)],
    ),
    "split_clip": lambda: _with_intents(
        builders.sequence_project(frames_each=40),
        [SplitClip(track_ref=builders.VIDEO_TRACK, clip_index=0, split_at_frame=20)],
    ),
    "create_track": lambda: _with_intents(
        builders.solid_color_project(),
        [CreateTrack(track_type="video", name="Overlay")],
    ),
    "add_guide": lambda: _with_intents(
        builders.solid_color_project(),
        [AddGuide(position_frames=10, label="chapter", category="chapter")],
    ),
}


def _params():
    params = []
    for name in sorted(SCENARIOS):
        marks = []
        if name in KNOWN_BROKEN:
            marks.append(pytest.mark.xfail(strict=True, reason=KNOWN_BROKEN[name]))
        params.append(pytest.param(name, marks=marks, id=name))
    return params


@pytest.mark.parametrize("scenario", _params())
def test_tool_output_loads_in_melt(scenario, melt_bin, tmp_path: Path):
    proj = SCENARIOS[scenario]()
    out = tmp_path / f"{scenario}.kdenlive"
    serialize_project(proj, out)

    result = melt_accepts(out, melt_bin=melt_bin, frames=25)
    assert result.ok, (
        f"melt rejected output of '{scenario}' "
        f"(rc={result.returncode}).\nstderr:\n{result.stderr[-2000:]}"
    )
