"""E-shape structural regression tests (kdenlive-gui-bin-rejection round 2).

Locks the serializer output to the GUI-confirmed *candidate E* document shape
that opens clean in Kdenlive 26.04.2 (no corruption, no Clip Problems dialog):

* media / AV bin producers carry NEITHER ``kdenlive:uuid`` NOR
  ``kdenlive:control_uuid`` (only sequence tractors do) -- otherwise
  ``loadBinPlaylist`` routes them into the sequence branch and skips them
  (projectitemmodel.cpp L1463/L1503);
* exactly one **sequence tractor** carries ``kdenlive:producer_type=17`` +
  ``kdenlive:uuid`` == ``kdenlive:control_uuid``, is registered in ``main_bin``,
  and a ``kdenlive:projectTractor`` tractor references the same uuid;
* ``main_bin`` carries ``xml_retain=1`` and a Sequences folder + open/active
  timeline (= sequence uuid);
* effect ``kdenlive_id``s are dot-form (``avfilter.*`` / ``frei0r.*``) and the
  Transform effect is ``qtblend``; compositing transitions carry a
  ``kdenlive_id``.

The GUI-confirmed candidate E file is the diff-style ground truth.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

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
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

_UUID_RE = re.compile(
    r"^\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}$"
)

_CAND_E = (
    Path(__file__).resolve().parents[2]
    / "smoke-test" / "smoke-test-video" / "projects" / "working_copies"
    / "candidates" / "smoke_test_full_candE_corpus_match.kdenlive"
)


def _props(elem: ET.Element) -> dict[str, str]:
    return {c.get("name", ""): (c.text or "") for c in elem if c.tag == "property"}


def _media_producers(root: ET.Element) -> list[ET.Element]:
    """<producer>/<chain> that are media (not the black background)."""
    out = []
    for tag in ("producer", "chain"):
        for p in root.findall(tag):
            pr = _props(p)
            if p.get("id") in ("black_track", "producer_black"):
                continue
            if pr.get("kdenlive:playlistid") == "black_track":
                continue
            out.append(p)
    return out


def _sequence_tractors(root: ET.Element) -> list[ET.Element]:
    return [
        t for t in root.findall("tractor")
        if _props(t).get("kdenlive:producer_type") == "17"
    ]


def _project_tractors(root: ET.Element) -> list[ET.Element]:
    return [
        t for t in root.findall("tractor")
        if "kdenlive:projectTractor" in _props(t)
    ]


def _effect_kdenlive_ids(root: ET.Element) -> list[str]:
    ids = []
    for f in root.iter("filter"):
        pr = _props(f)
        if "kdenlive_id" in pr:
            ids.append(pr["kdenlive_id"])
    return ids


def assert_e_shape(root: ET.Element) -> None:
    """Assert the E-shape structural invariants on a serialized document root."""
    # (1) media producers carry NO uuid / control_uuid.
    media = _media_producers(root)
    assert media, "expected at least one media producer"
    for p in media:
        pr = _props(p)
        assert "kdenlive:uuid" not in pr, f"uuid leaked on {p.get('id')}"
        assert "kdenlive:control_uuid" not in pr, (
            f"control_uuid leaked on {p.get('id')}"
        )
        assert "kdenlive:id" in pr

    # (2) exactly one sequence tractor, uuid == control_uuid, valid format.
    seqs = _sequence_tractors(root)
    assert len(seqs) == 1, f"expected 1 sequence tractor, got {len(seqs)}"
    sp = _props(seqs[0])
    assert _UUID_RE.match(sp.get("kdenlive:uuid", ""))
    assert sp["kdenlive:uuid"] == sp.get("kdenlive:control_uuid")
    assert seqs[0].get("id") == sp["kdenlive:uuid"]

    # (3) exactly one projectTractor referencing the sequence uuid.
    pts = _project_tractors(root)
    assert len(pts) == 1
    assert pts[0].find("track").get("producer") == sp["kdenlive:uuid"]

    # (4) main_bin: xml_retain + Sequences folder + open/active timeline + entry.
    main_bin = root.find("./playlist[@id='main_bin']")
    assert main_bin is not None
    mb = _props(main_bin)
    assert mb.get("xml_retain") == "1"
    assert mb.get("kdenlive:folder.-1.2") == "Sequences"
    assert mb.get("kdenlive:docproperties.opensequences") == sp["kdenlive:uuid"]
    assert mb.get("kdenlive:docproperties.activetimeline") == sp["kdenlive:uuid"]
    bin_entries = {e.get("producer") for e in main_bin.findall("entry")}
    assert sp["kdenlive:uuid"] in bin_entries

    # (5) compositing transitions carry a kdenlive_id.
    for tr in seqs[0].findall("transition"):
        assert _props(tr).get("kdenlive_id"), "compositor transition without kdenlive_id"


def _project_with_effects() -> KdenliveProject:
    """A smoke_test_full-equivalent: 2 video tracks, a media clip carrying a
    dot-form frei0r effect + a qtblend Transform (entry-nested)."""
    filt = (
        '<filter mlt_service="frei0r.glitch0r" track="0" clip_index="0">'
        '<property name="mlt_service">frei0r.glitch0r</property>'
        '<property name="kdenlive_id">frei0r.glitch0r</property>'
        '<property name="0">0.6</property></filter>'
    )
    xform = (
        '<filter mlt_service="qtblend" track="0" clip_index="0">'
        '<property name="mlt_service">qtblend</property>'
        '<property name="kdenlive_id">qtblend</property>'
        '<property name="rect">00:00:00.000=0 0 1920 1080 1</property></filter>'
    )
    return KdenliveProject(
        version="7",
        title="eshape",
        profile=ProjectProfile(width=1920, height=1080, fps=25.0, colorspace="709"),
        producers=[
            Producer(id="producer0", resource="/media/a.mp4",
                     properties={"resource": "/media/a.mp4", "mlt_service": "avformat"}),
            Producer(id="producer1", resource="/media/b.mp4",
                     properties={"resource": "/media/b.mp4", "mlt_service": "avformat"}),
        ],
        playlists=[
            Playlist(id="playlist0",
                     entries=[PlaylistEntry(producer_id="producer0", in_point=0, out_point=99)]),
            Playlist(id="playlist1",
                     entries=[PlaylistEntry(producer_id="producer1", in_point=0, out_point=99)]),
        ],
        tracks=[Track(id="playlist0", track_type="video"),
                Track(id="playlist1", track_type="video")],
        tractor={"id": "tractor0", "in": "0", "out": "99"},
        opaque_elements=[
            OpaqueElement(tag="filter", xml_string=filt, position_hint="after_tractor"),
            OpaqueElement(tag="filter", xml_string=xform, position_hint="after_tractor"),
        ],
    )


def test_serializer_emits_e_shape(tmp_path):
    out = tmp_path / "eshape.kdenlive"
    serialize_project(_project_with_effects(), out)
    assert_e_shape(ET.parse(out).getroot())


def test_effect_ids_are_dot_form(tmp_path):
    out = tmp_path / "eshape.kdenlive"
    serialize_project(_project_with_effects(), out)
    ids = _effect_kdenlive_ids(ET.parse(out).getroot())
    assert "frei0r.glitch0r" in ids
    assert "qtblend" in ids
    # no underscore-form frei0r/avfilter ids leak.
    for kid in ids:
        assert not re.match(r"^(frei0r|avfilter)_", kid), f"underscore id: {kid}"


@pytest.mark.skipif(not _CAND_E.exists(), reason="candidate E fixture absent")
def test_candidate_e_matches_e_shape_profile():
    """The GUI-confirmed candidate E must satisfy the same invariants our
    serializer emits -- the diff-style ground-truth anchor."""
    assert_e_shape(ET.parse(_CAND_E).getroot())


@pytest.mark.skipif(not _CAND_E.exists(), reason="candidate E fixture absent")
def test_regenerated_matches_candidate_e_structural_profile(tmp_path):
    """Structural-profile diff: our serializer output and candidate E agree on
    the load-bearing element shape (media producers w/o uuid; one sequence
    tractor pt=17; one projectTractor; main_bin xml_retain)."""
    out = tmp_path / "eshape.kdenlive"
    serialize_project(_project_with_effects(), out)
    mine = ET.parse(out).getroot()
    cand = ET.parse(_CAND_E).getroot()

    def profile(root):
        return {
            "media_have_uuid": any(
                "kdenlive:uuid" in _props(p) for p in _media_producers(root)
            ),
            "sequence_tractors": len(_sequence_tractors(root)),
            "project_tractors": len(_project_tractors(root)),
            "main_bin_xml_retain": _props(
                root.find("./playlist[@id='main_bin']")
            ).get("xml_retain"),
        }

    assert profile(mine) == profile(cand)
