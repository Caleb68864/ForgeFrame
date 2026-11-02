"""Serializer producer lengths cover declarations and all timeline uses."""
import xml.etree.ElementTree as ET

from workshop_video_brain.core.models.kdenlive import (
    Playlist, PlaylistEntry, Producer, Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from tests._testkit import solid_color_project


def _emit_length(tmp_path, *, length=None, entries=None):
    properties = {"mlt_service": "avformat"}
    if length is not None:
        properties["length"] = length
    project = solid_color_project(frames=100, title="lengths")
    project.producers = [Producer(id="clip", resource="clip.mp4", properties=properties)]
    project.playlists = [Playlist(id="video", entries=entries or [
        PlaylistEntry(producer_id="clip", in_point=0, out_point=99),
    ])]
    project.tracks = [Track(id="video", track_type="video")]
    path = tmp_path / "lengths.kdenlive"
    serialize_project(project, path)
    root = ET.parse(path).getroot()
    producer = root.find("producer[@id='clip']")
    main_bin = root.find("playlist[@id='main_bin']")
    entry = main_bin.find("entry[@producer='clip']")
    return producer.find("property[@name='length']").text, entry.get("out")


def test_used_producer_without_declared_length_gets_length_from_out(tmp_path):
    assert _emit_length(tmp_path, entries=[
        PlaylistEntry(producer_id="clip", in_point=0, out_point=99),
    ]) == ("100", "99")


def test_reused_producer_length_covers_largest_out_point(tmp_path):
    assert _emit_length(tmp_path, entries=[
        PlaylistEntry(producer_id="clip", in_point=0, out_point=49),
        PlaylistEntry(producer_id="clip", in_point=150, out_point=199),
    ]) == ("200", "199")


def test_larger_declared_length_is_preserved(tmp_path):
    assert _emit_length(tmp_path, length="300", entries=[
        PlaylistEntry(producer_id="clip", in_point=0, out_point=99),
    ]) == ("300", "299")


def test_timecode_length_falls_back_to_timeline_uses(tmp_path):
    assert _emit_length(tmp_path, length="00:00:05.005", entries=[
        PlaylistEntry(producer_id="clip", in_point=0, out_point=99),
    ]) == ("100", "99")
