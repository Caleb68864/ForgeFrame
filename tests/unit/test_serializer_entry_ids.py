"""Timeline entry identities are serialized from model and native bin clips."""
import xml.etree.ElementTree as ET

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject, OpaqueElement, Playlist, PlaylistEntry, Producer,
    ProjectProfile, Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project


def _props(element):
    return {child.get("name"): child.text or "" for child in element.findall("property")}


def test_each_timeline_entry_starts_with_its_bin_id_and_filters_follow(tmp_path):
    project = KdenliveProject(
        title="Entry IDs",
        profile=ProjectProfile(fps=25),
        producers=[
            Producer(id="first", resource="/media/first.mp4", properties={"length": "100"}),
            Producer(id="second", resource="/media/second.mp4", properties={"length": "100"}),
        ],
        tracks=[
            Track(id="video", track_type="video"),
            Track(id="audio", track_type="audio"),
        ],
        playlists=[
            Playlist(id="video", entries=[
                PlaylistEntry(producer_id="first", in_point=0, out_point=9),
                PlaylistEntry(producer_id="", in_point=0, out_point=4),
                PlaylistEntry(producer_id="second", in_point=0, out_point=9),
            ]),
            Playlist(id="audio", entries=[
                PlaylistEntry(producer_id="first", in_point=0, out_point=9),
            ]),
        ],
        opaque_elements=[OpaqueElement(
            tag="filter",
            position_hint=None,
            xml_string='<filter id="fx" track="0" clip_index="0"><property name="mlt_service">volume</property></filter>',
        )],
    )
    path = tmp_path / "entry_ids.kdenlive"
    serialize_project(project, path)
    root = ET.parse(path).getroot()
    video = root.find("playlist[@id='video']")
    audio = root.find("playlist[@id='audio']")
    first_entry, second_entry = video.findall("entry")
    audio_entry = audio.find("entry")
    assert first_entry[0].get("name") == "kdenlive:id"
    assert _props(first_entry)["kdenlive:id"] == "4"
    assert first_entry[1].tag == "filter"
    assert _props(second_entry)["kdenlive:id"] == "5"
    assert _props(audio_entry)["kdenlive:id"] == "4"
    assert video.find("blank") is not None
    assert not list(video.find("blank"))


def test_opaque_native_chain_entry_uses_its_bin_id(tmp_path):
    project = KdenliveProject(
        title="Opaque Entry ID",
        tracks=[Track(id="video", track_type="video")],
        playlists=[Playlist(id="video", entries=[
            PlaylistEntry(producer_id="native_chain", in_point=0, out_point=9),
        ])],
        opaque_elements=[OpaqueElement(
            tag="chain",
            xml_string=(
                '<chain id="native_chain" out="99">'
                '<property name="resource">/media/native.mp4</property>'
                '<property name="length">100</property>'
                '<property name="mlt_service">avformat-novalidate</property>'
                '<property name="kdenlive:id">7</property>'
                '</chain>'
            ),
        )],
    )
    path = tmp_path / "opaque_entry_id.kdenlive"
    serialize_project(project, path)
    root = ET.parse(path).getroot()
    entry = root.find("playlist[@id='video']/entry")
    assert _props(entry)["kdenlive:id"] == "7"
    assert entry[0].get("name") == "kdenlive:id"
