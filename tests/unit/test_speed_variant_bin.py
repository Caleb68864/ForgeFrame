"""Speed and timeremap producers share their source bin identity."""
import xml.etree.ElementTree as ET
from pathlib import Path

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject, Playlist, PlaylistEntry, Producer, ProjectProfile, Track,
)
from workshop_video_brain.core.models.timeline import SetClipSpeed, SpeedRamp
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.validator import validate_serialized_xml


FIXTURES = Path("/home/caleb/Projects/ForgeFrame/tests/fixtures")


def _project():
    return KdenliveProject(
        title="Speed Variant",
        profile=ProjectProfile(width=1920, height=1080, fps=25, colorspace="709"),
        producers=[Producer(
            id="source", resource="/media/source.mp4",
            properties={"mlt_service": "avformat", "length": "100"},
        )],
        tracks=[Track(id="video", track_type="video")],
        playlists=[Playlist(id="video", entries=[
            PlaylistEntry(producer_id="source", in_point=0, out_point=99),
        ])],
    )


def _props(element):
    return {child.get("name"): child.text or "" for child in element.findall("property")}


def _assert_variant_document(project, path, variant_ids):
    serialize_project(project, path)
    root = ET.parse(path).getroot()
    main_bin = root.find("playlist[@id='main_bin']")
    bin_refs = {entry.get("producer") for entry in main_bin.findall("entry")}
    base = root.find("producer[@id='source']")
    base_id = _props(base)["kdenlive:id"]
    assert len(bin_refs) == 2  # source plus sequence, regardless of variant count
    for variant_id in variant_ids:
        variant = root.find(f"producer[@id='{variant_id}']")
        if variant is None:
            variant = root.find(f"chain[@id='{variant_id}']")
        assert _props(variant)["kdenlive:id"] == base_id
        assert variant_id not in bin_refs
        entry = next(
            entry for playlist in root.findall("playlist")
            if playlist is not main_bin
            for entry in playlist.findall("entry")
            if entry.get("producer") == variant_id
        )
        assert _props(entry)["kdenlive:id"] == base_id
    assert validate_serialized_xml(root).items == []
    return root


def test_set_clip_speed_variant_shares_bin_id_and_is_not_registered(tmp_path):
    project = patch_project(_project(), [
        SetClipSpeed(track_ref="video", clip_index=0, speed=2.0),
    ])
    root = _assert_variant_document(project, tmp_path / "speed.kdenlive", ["source_tw2"])
    entry = next(e for p in root.findall("playlist") for e in p.findall("entry")
                 if e.get("producer") == "source_tw2")
    assert _props(entry)["kdenlive:id"] == _props(root.find("producer[@id='source']"))["kdenlive:id"]


def test_speed_ramp_timewarp_slices_share_base_id_including_pitch_variant(tmp_path):
    project = patch_project(_project(), [
        SpeedRamp(
            track_ref="video", clip_index=0,
            segments=[(0, 50, 2.0), (50, 100, 0.5)],
            pitch_compensation=True,
        ),
    ])
    _assert_variant_document(
        project, tmp_path / "speed_ramp.kdenlive", ["source_tw2_pc", "source_tw0.5_pc"]
    )


def test_timeremap_chain_variant_shares_base_id_and_is_not_registered(tmp_path):
    from workshop_video_brain.edit_mcp.server.bundles.speed_ramp import _apply_timeremap_engine
    from workshop_video_brain.edit_mcp.pipelines.speed_ramp import Segment

    project = _project()
    playlist = project.playlists[0]
    entry = playlist.entries[0]
    _apply_timeremap_engine(
        project, playlist, entry,
        [Segment(0, 50, 2.0), Segment(50, 100, 0.5)],
        image_mode="nearest", pitch=False,
    )
    chain_id = entry.producer_id
    root = _assert_variant_document(project, tmp_path / "timeremap.kdenlive", [chain_id])
    chain = root.find(f"chain[@id='{chain_id}']")
    assert chain is not None
    assert chain.find("link[@mlt_service='timeremap']") is not None


def _native_speed_facts(path):
    root = ET.parse(path).getroot()
    props = {element.get("id"): _props(element) for element in root
             if element.tag in {"producer", "chain"}}
    variant_id = next(identity for identity, values in props.items()
                      if values.get("mlt_service") == "timewarp")
    variant_kid = props[variant_id]["kdenlive:id"]
    base_id = next(identity for identity, values in props.items()
                    if values.get("kdenlive:id") == variant_kid
                    and identity != variant_id)
    main_bin = root.find("playlist[@id='main_bin']")
    bin_refs = {entry.get("producer") for entry in main_bin.findall("entry")}
    entry = next(entry for playlist in root.findall("playlist")
                 if playlist is not main_bin for entry in playlist.findall("entry")
                 if entry.get("producer") == variant_id)
    return variant_id, variant_kid, base_id, bin_refs, _props(entry)["kdenlive:id"]


def test_native_golden_and_our_speed_output_share_the_same_invariants(tmp_path):
    native = _native_speed_facts(FIXTURES / "kdenlive_references/clip_speed_400_native.kdenlive")
    assert native[1] == _props(ET.parse(FIXTURES / "kdenlive_references/clip_speed_400_native.kdenlive").getroot().find("chain[@id='clip_kdbin']"))["kdenlive:id"]
    assert native[0] not in native[3]
    assert native[1] == native[4]

    project = patch_project(_project(), [
        SetClipSpeed(track_ref="video", clip_index=0, speed=4.0),
    ])
    path = tmp_path / "ours.kdenlive"
    serialize_project(project, path)
    ours = _native_speed_facts(path)
    ours_root = ET.parse(path).getroot()
    ours_base = ours_root.find(f"producer[@id='{ours[2]}']")
    assert ours[1] == _props(ours_base)["kdenlive:id"]
    assert ours[0] not in ours[3]
    assert ours[1] == ours[4]
