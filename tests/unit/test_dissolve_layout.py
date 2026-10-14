"""Dissolve layout matches a Kdenlive-saved dissolve (2026-10-14 differential).

Kdenlive 26.08 hid our dissolve: the ``luma`` targeted the black background
(``a_track=0``) and was written after the per-track compositors, so Kdenlive
layered the left clip over it. The left clip was also stretched past its media.
Ground truth: ``tests/fixtures/kdenlive_references/cross_dissolve_native.kdenlive``.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from tests._testkit import VIDEO_TRACK, sequence_project
from workshop_video_brain.core.models.timeline import AddTransition
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

EACH = 25


def _dissolve(proj, frames: int = 12):
    return patcher.patch_project(
        proj,
        [AddTransition(type="dissolve", track_ref=VIDEO_TRACK,
                       left_clip_ref="0", right_clip_ref="1", duration_frames=frames)],
    )


def _props(elem: ET.Element) -> dict[str, str]:
    return {p.get("name"): (p.text or "") for p in elem.findall("property")}


def _sequence_transitions(tmp_path, proj) -> list[dict[str, str]]:
    path = tmp_path / "dissolve.kdenlive"
    serialize_project(proj, path)
    root = ET.parse(path).getroot()
    seq = next(t for t in root.findall("tractor")
               if any(p.get("name") == "kdenlive:producer_type" and p.text == "17"
                      for p in t.findall("property")))
    return [_props(t) for t in seq.findall("transition")]


def _no_handles(proj):
    for p in proj.producers:
        p.properties["length"] = str(EACH)
    return proj


def test_dissolve_targets_left_clip_track_not_background():
    proj = _dissolve(sequence_project(frames_each=EACH))
    luma = [ET.fromstring(o.xml_string) for o in proj.opaque_elements if o.tag == "transition"]
    assert len(luma) == 1
    props = _props(luma[0])
    # playlists: video (slot 1), audio (slot 2), crossfade (slot 3)
    assert props["a_track"] == "1"
    assert props["b_track"] == "3"
    assert props["mlt_service"] == "luma"
    assert props["kdenlive_id"] == "dissolve"


def test_dissolve_is_planted_before_video_compositors(tmp_path):
    trans = _sequence_transitions(tmp_path, _dissolve(sequence_project(frames_each=EACH)))
    order = [t.get("kdenlive_id") for t in trans]
    first_video = next(i for i, t in enumerate(trans) if t.get("mlt_service") == "frei0r.cairoblend")
    assert order.index("dissolve") < first_video
    # The crossfade track gets its own compositor, like every other video track.
    video_b_tracks = {t["b_track"] for t in trans if t.get("mlt_service") == "frei0r.cairoblend"}
    assert video_b_tracks == {"1", "3"}


def test_dissolve_with_handles_centres_on_the_cut():
    # sequence_project producers are EACH + 10 frames long: 10-frame handles.
    proj = _dissolve(sequence_project(frames_each=EACH), frames=12)
    left = proj.playlists[0].entries[0]
    assert left.out_point == EACH - 1 + 6
    top = proj.playlists[-1].entries
    assert top[0].producer_id == "" and top[0].out_point + 1 == EACH - 6
    props = _props(ET.fromstring(proj.opaque_elements[-1].xml_string))
    assert (props["in"], props["out"]) == (str(EACH - 6), str(EACH + 5))


def test_dissolve_never_extends_a_clip_past_its_media():
    proj = _dissolve(_no_handles(sequence_project(frames_each=EACH)), frames=12)
    left = proj.playlists[0].entries[0]
    assert left.out_point == EACH - 1
    top = proj.playlists[-1].entries
    assert top[0].producer_id == "" and top[0].out_point + 1 == EACH - 12
    props = _props(ET.fromstring(proj.opaque_elements[-1].xml_string))
    assert (props["in"], props["out"]) == (str(EACH - 12), str(EACH - 1))


def test_dissolve_unknown_length_treated_as_no_handle():
    proj = sequence_project(frames_each=EACH)
    for p in proj.producers:
        del p.properties["length"]
    proj = _dissolve(proj, frames=12)
    assert proj.playlists[0].entries[0].out_point == EACH - 1


def test_dissolve_duration_clamped_to_shorter_clip():
    proj = _dissolve(_no_handles(sequence_project(frames_each=EACH)), frames=48)
    props = _props(ET.fromstring(proj.opaque_elements[-1].xml_string))
    assert int(props["out"]) - int(props["in"]) + 1 == EACH
