"""Standard formats get MLT's own profile name (hard rule 4)."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from tests._testkit import sequence_project
from workshop_video_brain.core.models.kdenlive import ProjectProfile
from workshop_video_brain.edit_mcp.adapters.kdenlive.profiles import canonical_profile_name
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project


@pytest.mark.parametrize(
    ("format_", "name"),
    [((1920, 1080, 30000, 1001), "atsc_1080p_2997"),
     ((1920, 1080, 25, 1), "atsc_1080p_25"),
     ((3840, 2160, 24000, 1001), "uhd_2160p_2398"),
     ((1280, 720, 60, 1), "atsc_720p_60"),
     ((2560, 1440, 50, 1), "qhd_1440p_50"),
     ((1080, 1920, 30, 1), "vertical_hd_30")],
)
def test_standard_formats(format_, name):
    assert canonical_profile_name(*format_)[0] == name


def test_unknown_format_has_no_name():
    assert canonical_profile_name(320, 180, 30, 1) is None


def test_interlaced_has_no_name():
    assert canonical_profile_name(1920, 1080, 25, 1, progressive=False) is None


def _doc_profile_name(root: ET.Element) -> str:
    return next(p.text for p in root.iter("property") if p.get("name") == "kdenlive:docproperties.profile")


def test_serializer_writes_the_canonical_name_and_description(tmp_path):
    project = sequence_project()
    project.profile = ProjectProfile(width=1920, height=1080, fps=30000 / 1001, colorspace="709")
    path = tmp_path / "p.kdenlive"
    serialize_project(project, path)
    root = ET.parse(path).getroot()
    assert _doc_profile_name(root) == "atsc_1080p_2997"
    assert root.find("profile").get("description") == "HD 1080p 29.97 fps"


def test_serializer_keeps_the_anonymous_name_for_other_formats(tmp_path):
    project = sequence_project()
    project.profile = ProjectProfile(width=320, height=180, fps=30.0, colorspace="709")
    path = tmp_path / "p.kdenlive"
    serialize_project(project, path)
    root = ET.parse(path).getroot()
    assert _doc_profile_name(root) == "320x180_fps30"
    assert root.find("profile").get("description") is None
