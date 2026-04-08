"""Unit tests for the Kdenlive project serializer."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    Guide,
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    serialize_project,
    serialize_versioned,
)


def _make_minimal_project() -> KdenliveProject:
    return KdenliveProject(
        version="7",
        title="Writer Test",
        profile=ProjectProfile(width=1920, height=1080, fps=25.0, colorspace="709"),
        producers=[
            Producer(
                id="prod0",
                resource="/media/clip.mp4",
                properties={"resource": "/media/clip.mp4", "length": "100"},
            )
        ],
        playlists=[
            Playlist(
                id="pl0",
                entries=[PlaylistEntry(producer_id="prod0", in_point=0, out_point=99)],
            )
        ],
        tracks=[Track(id="pl0", track_type="video", name="Video")],
        tractor={"id": "tractor0", "in": "0", "out": "99"},
        guides=[Guide(position=50, label="Mid point", category="chapter")],
    )


class TestSerializeProject:
    def test_writes_file(self, tmp_path):
        project = _make_minimal_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        assert out.exists()

    def test_well_formed_xml(self, tmp_path):
        project = _make_minimal_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        # Should not raise
        tree = ET.parse(out)
        root = tree.getroot()
        assert root.tag == "mlt"

    def test_title_and_version_in_xml(self, tmp_path):
        project = _make_minimal_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        tree = ET.parse(out)
        root = tree.getroot()
        assert root.get("title") == "Writer Test"
        assert root.get("version") == "7"

    def test_profile_in_xml(self, tmp_path):
        project = _make_minimal_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        tree = ET.parse(out)
        profile = tree.getroot().find("profile")
        assert profile is not None
        assert profile.get("width") == "1920"
        assert profile.get("height") == "1080"

    def test_producer_in_xml(self, tmp_path):
        project = _make_minimal_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        tree = ET.parse(out)
        producers = tree.getroot().findall("producer")
        assert len(producers) == 1
        assert producers[0].get("id") == "prod0"

    def test_guide_in_xml(self, tmp_path):
        project = _make_minimal_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        tree = ET.parse(out)
        guides = tree.getroot().findall("guide")
        assert len(guides) == 1
        assert guides[0].get("position") == "50"
        assert guides[0].get("comment") == "Mid point"

    def test_opaque_element_reinserted(self, tmp_path):
        project = _make_minimal_project()
        project.opaque_elements.append(
            OpaqueElement(
                tag="custom_tag",
                xml_string="<custom_tag>preserved content</custom_tag>",
            )
        )
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        content = out.read_text(encoding="utf-8")
        assert "custom_tag" in content
        assert "preserved content" in content

    def test_snapshot_created_on_overwrite(self, tmp_path):
        # Create workspace structure
        ws = tmp_path / "workspace"
        (ws / "projects" / "working_copies").mkdir(parents=True)
        (ws / "projects" / "snapshots").mkdir(parents=True)
        out = ws / "projects" / "working_copies" / "test_v1.kdenlive"

        project = _make_minimal_project()
        serialize_project(project, out)

        # Write again – should create snapshot
        serialize_project(project, out)

        snapshots = list((ws / "projects" / "snapshots").iterdir())
        assert len(snapshots) >= 1


class TestSerializeVersioned:
    def test_versioned_naming(self, tmp_path):
        ws = tmp_path / "workspace"
        (ws / "projects" / "working_copies").mkdir(parents=True)
        (ws / "projects" / "snapshots").mkdir(parents=True)

        project = _make_minimal_project()
        path = serialize_versioned(project, ws, "my_project")
        assert path.name == "my_project_v1.kdenlive"

    def test_version_increments(self, tmp_path):
        ws = tmp_path / "workspace"
        (ws / "projects" / "working_copies").mkdir(parents=True)
        (ws / "projects" / "snapshots").mkdir(parents=True)

        project = _make_minimal_project()
        path1 = serialize_versioned(project, ws, "my_project")
        path2 = serialize_versioned(project, ws, "my_project")
        assert path1.name == "my_project_v1.kdenlive"
        assert path2.name == "my_project_v2.kdenlive"

    def test_file_is_well_formed(self, tmp_path):
        ws = tmp_path / "workspace"
        (ws / "projects" / "working_copies").mkdir(parents=True)
        (ws / "projects" / "snapshots").mkdir(parents=True)

        project = _make_minimal_project()
        path = serialize_versioned(project, ws, "my_project")
        # Should not raise
        ET.parse(path)
