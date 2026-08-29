"""Hard rule 6: resource paths use forward slashes even on Windows.

Producers reach the serializer with whatever ``str(Path)`` produced at the
tool boundary -- on Windows that is a backslash path such as
``C:\\ws\\media\\raw\\clip.mp4``, which confuses Kdenlive's bin loader
("Clip ... not found in project bin"). Linux CI never sees a backslash, so
this test feeds one in explicitly and checks the single serializer write site
normalises it. The check is platform-independent: the input is a literal.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from tests.unit.test_serializer_bin import _make_project
from workshop_video_brain.core.models.kdenlive import Producer
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

_WIN = "C:\\ws\\media\\raw\\clip.mp4"


def _resource_values(xml: str) -> set[str]:
    root = ET.fromstring(xml)
    return {
        prop.text or ""
        for prop in root.iter("property")
        if prop.get("name") == "resource"
    }


def test_windows_backslash_resource_is_emitted_with_forward_slashes(tmp_path):
    project = _make_project(
        producers=[
            Producer(
                id="prod0",
                resource=_WIN,
                properties={"resource": _WIN, "mlt_service": "avformat"},
            )
        ]
    )
    out = tmp_path / "p.kdenlive"
    serialize_project(project, out)
    values = _resource_values(out.read_text(encoding="utf-8"))

    assert "C:/ws/media/raw/clip.mp4" in values
    assert not any("\\" in v for v in values), values


def test_non_path_resources_are_untouched(tmp_path):
    project = _make_project(
        producers=[
            Producer(
                id="prod0",
                resource="0xff0000ff",
                properties={"resource": "0xff0000ff", "mlt_service": "color"},
            )
        ]
    )
    out = tmp_path / "p.kdenlive"
    serialize_project(project, out)
    assert "0xff0000ff" in _resource_values(out.read_text(encoding="utf-8"))
