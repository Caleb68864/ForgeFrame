"""Track mute / visibility must reach the document on disk.

``track_mute`` and ``track_visibility`` record their result as an
``OpaqueElement`` that ``serializer._hide_directives`` is supposed to turn into
the ``hide`` attribute on the sequence tractor's ``<track>`` ref -- the only
place MLT honours track muting or visibility.

The directive was written as ``<kdenlive:hide track="..." hide="..."/>``: an XML
element carrying a namespace prefix that the fragment never declares. Parsing it
raises ``unbound prefix``, and **both** paths that read it swallow the failure --
``_hide_directives`` catches ``ET.ParseError`` and skips, and the opaque
re-insertion loop logs and drops the element. So the directive was produced,
stored, never applied and never even written out: muting a track changed
nothing in the file, silently, at both ends.

Every assertion below is made against the re-parsed document on disk.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    Track,
)
from workshop_video_brain.core.models.timeline import (
    SetTrackMute,
    SetTrackVisibility,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    serialize_project,
)


def _project(track_type: str) -> KdenliveProject:
    return KdenliveProject(
        version="7",
        title="Hide directive",
        producers=[
            Producer(
                id="prod0",
                resource="/abs/clip.mp4",
                properties={"mlt_service": "avformat", "length": "100"},
            )
        ],
        tracks=[Track(id="lane", track_type=track_type)],
        playlists=[
            Playlist(
                id="lane",
                entries=[PlaylistEntry(producer_id="prod0", in_point=0, out_point=99)],
            )
        ],
    )


def _hide_on_written_track(project: KdenliveProject, out: Path) -> str | None:
    """The ``hide`` attribute of the sequence tractor's ref to our track."""
    serialize_project(project, out)
    root = ET.parse(out).getroot()
    refs = [t for t in root.iter("track") if t.get("producer") == "tractor_lane"]
    assert len(refs) == 1, [t.get("producer") for t in root.iter("track")]
    return refs[0].get("hide")


def _stray_hide_elements(out: Path) -> list[str]:
    """Any leftover directive element the serializer failed to consume."""
    text = out.read_text(encoding="utf-8")
    return [tag for tag in ("kdenlive:hide", "kdenlive-hide") if tag in text]


# ---------------------------------------------------------------------------
# Refuse direction: a mute/hide must actually suppress the track
# ---------------------------------------------------------------------------


def test_muting_a_video_track_writes_hide_audio(tmp_path: Path) -> None:
    patched = patch_project(
        _project("video"), [SetTrackMute(track_ref="lane", muted=True)]
    )
    assert _hide_on_written_track(patched, tmp_path / "p.kdenlive") == "audio"


def test_muting_an_audio_track_writes_hide_both(tmp_path: Path) -> None:
    patched = patch_project(
        _project("audio"), [SetTrackMute(track_ref="lane", muted=True)]
    )
    assert _hide_on_written_track(patched, tmp_path / "p.kdenlive") == "both"


def test_hiding_a_video_track_writes_hide_video(tmp_path: Path) -> None:
    patched = patch_project(
        _project("video"), [SetTrackVisibility(track_ref="lane", visible=False)]
    )
    assert _hide_on_written_track(patched, tmp_path / "p.kdenlive") == "video"


def test_hiding_an_audio_track_writes_hide_both(tmp_path: Path) -> None:
    patched = patch_project(
        _project("audio"), [SetTrackVisibility(track_ref="lane", visible=False)]
    )
    assert _hide_on_written_track(patched, tmp_path / "p.kdenlive") == "both"


# ---------------------------------------------------------------------------
# Accept direction: un-muting must NOT suppress anything, and an untouched
# project must be byte-for-byte free of hide directives
# ---------------------------------------------------------------------------


def test_an_untouched_video_track_carries_no_hide(tmp_path: Path) -> None:
    assert _hide_on_written_track(_project("video"), tmp_path / "p.kdenlive") is None


def test_unmuting_a_video_track_clears_the_hide(tmp_path: Path) -> None:
    patched = patch_project(
        _project("video"),
        [
            SetTrackMute(track_ref="lane", muted=True),
            SetTrackMute(track_ref="lane", muted=False),
        ],
    )
    assert _hide_on_written_track(patched, tmp_path / "p.kdenlive") is None


def test_unmuting_an_audio_track_leaves_only_the_default_video_hide(
    tmp_path: Path,
) -> None:
    """An audio track always hides video; un-muting must return it to exactly
    that, not to "no suppression at all"."""
    patched = patch_project(
        _project("audio"),
        [
            SetTrackMute(track_ref="lane", muted=True),
            SetTrackMute(track_ref="lane", muted=False),
        ],
    )
    assert _hide_on_written_track(patched, tmp_path / "p.kdenlive") == "video"


def test_showing_a_hidden_video_track_clears_the_hide(tmp_path: Path) -> None:
    patched = patch_project(
        _project("video"),
        [
            SetTrackVisibility(track_ref="lane", visible=False),
            SetTrackVisibility(track_ref="lane", visible=True),
        ],
    )
    assert _hide_on_written_track(patched, tmp_path / "p.kdenlive") is None


def test_the_black_background_track_never_gets_a_hide(tmp_path: Path) -> None:
    """Hard rule 8: ``<track producer="black_track">`` carries no ``hide``, or
    Kdenlive considers the sequence unrecoverable."""
    patched = patch_project(
        _project("video"), [SetTrackMute(track_ref="lane", muted=True)]
    )
    out = tmp_path / "p.kdenlive"
    serialize_project(patched, out)
    blacks = [
        t
        for t in ET.parse(out).getroot().iter("track")
        if (t.get("producer") or "").startswith("producer_black")
        or t.get("producer") == "black_track"
    ]
    assert blacks
    assert all(t.get("hide") is None for t in blacks)


# ---------------------------------------------------------------------------
# The directive is an internal representation: it is consumed, never emitted
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("track_type", ["video", "audio"])
def test_the_directive_element_is_consumed_not_written(
    tmp_path: Path, track_type: str
) -> None:
    patched = patch_project(
        _project(track_type), [SetTrackMute(track_ref="lane", muted=True)]
    )
    out = tmp_path / "p.kdenlive"
    serialize_project(patched, out)
    assert _stray_hide_elements(out) == []


def test_the_directive_fragment_is_well_formed_xml() -> None:
    """It is parsed by two separate readers; neither may be handed a fragment
    that raises. An undeclared namespace prefix is not well-formed."""
    patched = patch_project(
        _project("video"), [SetTrackMute(track_ref="lane", muted=True)]
    )
    directives = [
        el for el in patched.opaque_elements if el.tag.endswith("hide")
    ]
    assert directives, [el.tag for el in patched.opaque_elements]
    for el in directives:
        ET.fromstring(el.xml_string)  # must not raise
