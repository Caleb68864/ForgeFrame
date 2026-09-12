"""A model field the caller can set must survive serialize -> re-parse.

The third category of model-field defect, after "declared and unwired" (removed
in ``test_kdenlive_model_has_no_dead_declarations``) and "wired but wrong":
**silently accepted and dropped**.  The model takes the value, the caller sets
it, and the serializer never writes it -- so a named track round-trips to an
unnamed one and nothing anywhere fails.  The name-based rule in
``test_kdenlive_model_has_no_dead_declarations`` cannot see this shape: the field
*is* mentioned in the adapter package (something writes it), which is exactly
what that rule checks for.

So this rule is behavioural, not textual.  For every field of every covered
class it plants a distinctive value, writes the document, **re-parses it from
disk**, and reads the value back off the re-parsed project.  A field either
survives (it is probed) or it is on ``EXEMPT`` with a stated reason.  A new field
on a covered class belongs to neither set and fails ``test_every_covered_field_is
_probed_or_exempt``, which forces the decision the defect was made of: emit it,
or do not accept it.

What this rule caught, none of which the name-based rule could:

* ``Track.name`` -- set by ``patcher_intents`` (``CreateTrack``, the
  ``"Crossfade"`` overlay track) and by a dozen test builders; never emitted.
* ``KdenliveProject.tractor`` -- filled by the parser, mutated by
  ``_sync_tractor_out``, never read by the serializer.  Removed rather than
  emitted; see ``test_the_project_has_no_tractor_field``.
* ``SubtitleTrack.name`` -- the mirror-image asymmetry.  The serializer *does*
  write it, into the ``subtitlesList`` JSON; the parser hard-coded
  ``name="Subtitle"`` instead of reading it back.

The ceiling, stated rather than hidden, three parts:

1. It compares **model values**, so a field that survives through a different
   representation than the one it was set on still passes.  It answers "does the
   caller get their value back?", not "is the XML right?".
2. It covers the four classes whose fields a caller sets directly.  ``Producer``,
   ``Playlist``, ``Link``, ``Guide`` and ``OpaqueElement`` are exercised by the
   probes above but their field *sets* are not checked for completeness; they
   have their own round-trip tests.
3. It cannot tell "written somewhere Kdenlive reads" from "written somewhere
   Kdenlive ignores".  Only melt and Kdenlive can settle that, and only the
   external tier runs them.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from workshop_video_brain.core.models.kdenlive import (
    Guide,
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    SubtitleTrack,
    Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive import serializer as S
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

COVERED_CLASSES = (KdenliveProject, Track, PlaylistEntry, SubtitleTrack)


def _base_project() -> KdenliveProject:
    """A minimal two-track project every probe mutates a copy of."""
    project = KdenliveProject(title="Base")
    project.producers = [
        Producer(
            id="p0",
            resource="/tmp/a.mp4",
            properties={"mlt_service": "avformat", "length": "100"},
        )
    ]
    project.tracks = [
        Track(id="pl_v", track_type="video"),
        Track(id="pl_a", track_type="audio"),
    ]
    project.playlists = [
        Playlist(
            id="pl_v",
            entries=[PlaylistEntry(producer_id="p0", in_point=0, out_point=24)],
        ),
        Playlist(id="pl_a", entries=[]),
    ]
    return project


def round_trip(
    mutate: Callable[[KdenliveProject], Any], tmp_path: Path
) -> KdenliveProject:
    """Serialise a mutated project and return it **re-parsed from disk**.

    Never returns the project that was written: asserting on the model the test
    just populated is how a serializer that writes nothing stays green.
    """
    project = _base_project()
    mutate(project)
    out = tmp_path / "roundtrip.kdenlive"
    S.serialize_project(project, out)
    return parse_project(out)


def _set_track_names(project: KdenliveProject) -> None:
    project.tracks[0].name = "ProbeV"
    project.tracks[1].name = "ProbeA"


#: ``"Class.field"`` -> (mutate the base project, read it off the re-parsed one,
#: the value that must come back).
PROBES: dict[str, tuple[Callable[[KdenliveProject], Any], Callable[[KdenliveProject], Any], Any]] = {
    "KdenliveProject.version": (
        lambda p: setattr(p, "version", "6"),
        lambda p: p.version,
        "6",
    ),
    "KdenliveProject.title": (
        lambda p: setattr(p, "title", "Probe Title"),
        lambda p: p.title,
        "Probe Title",
    ),
    "KdenliveProject.root": (
        lambda p: setattr(p, "root", "/tmp/probe-root"),
        lambda p: p.root,
        "/tmp/probe-root",
    ),
    "KdenliveProject.profile": (
        lambda p: setattr(
            p, "profile", ProjectProfile(width=1280, height=720, fps=30.0, colorspace="709")
        ),
        lambda p: (p.profile.width, p.profile.height, p.profile.fps, p.profile.colorspace),
        (1280, 720, 30.0, "709"),
    ),
    "KdenliveProject.producers": (
        lambda p: None,
        lambda p: sorted(
            (x.id, Path(x.resource).name) for x in p.producers if x.resource.endswith(".mp4")
        ),
        [("p0", "a.mp4")],
    ),
    "KdenliveProject.tracks": (
        lambda p: None,
        lambda p: sorted((t.id, t.track_type) for t in p.tracks),
        [("pl_a", "audio"), ("pl_v", "video")],
    ),
    "KdenliveProject.playlists": (
        lambda p: None,
        lambda p: sorted(pl.id for pl in p.playlists),
        ["pl_a", "pl_v"],
    ),
    "KdenliveProject.guides": (
        lambda p: setattr(
            p, "guides", [Guide(position=12, label="Probe G", category="2", comment="c")]
        ),
        lambda p: [(g.position, g.label) for g in p.guides],
        [(12, "Probe G")],
    ),
    "KdenliveProject.subtitles": (
        lambda p: setattr(
            p, "subtitles", [SubtitleTrack(id=0, name="Probe Sub", file="/tmp/s.ass")]
        ),
        lambda p: [(s.id, s.name) for s in p.subtitles],
        [(0, "Probe Sub")],
    ),
    "KdenliveProject.docproperties": (
        lambda p: setattr(p, "docproperties", {"enableproxy": "1", "probekey": "probeval"}),
        lambda p: {k: v for k, v in p.docproperties.items() if k in ("enableproxy", "probekey")},
        {"enableproxy": "1", "probekey": "probeval"},
    ),
    "KdenliveProject.opaque_elements": (
        lambda p: p.opaque_elements.append(
            OpaqueElement(tag="probe", xml_string='<probe marker="yes" />', position_hint=None)
        ),
        lambda p: sorted(o.tag for o in p.opaque_elements if o.tag == "probe"),
        ["probe"],
    ),
    "Track.id": (
        lambda p: None,
        lambda p: sorted(t.id for t in p.tracks),
        ["pl_a", "pl_v"],
    ),
    "Track.track_type": (
        lambda p: None,
        lambda p: sorted(t.track_type for t in p.tracks),
        ["audio", "video"],
    ),
    "Track.name": (
        _set_track_names,
        lambda p: sorted(t.name or "" for t in p.tracks),
        ["ProbeA", "ProbeV"],
    ),
    "PlaylistEntry.producer_id": (
        lambda p: None,
        lambda p: p.playlists[0].entries[0].producer_id,
        "p0",
    ),
    "PlaylistEntry.in_point": (
        lambda p: setattr(p.playlists[0].entries[0], "in_point", 5),
        lambda p: p.playlists[0].entries[0].in_point,
        5,
    ),
    "PlaylistEntry.out_point": (
        lambda p: setattr(p.playlists[0].entries[0], "out_point", 40),
        lambda p: p.playlists[0].entries[0].out_point,
        40,
    ),
    "SubtitleTrack.id": (
        lambda p: setattr(p, "subtitles", [SubtitleTrack(id=3, name="S", file="/tmp/s.ass")]),
        lambda p: [s.id for s in p.subtitles],
        [3],
    ),
    "SubtitleTrack.name": (
        lambda p: setattr(
            p, "subtitles", [SubtitleTrack(id=0, name="Probe Sub", file="/tmp/s.ass")]
        ),
        lambda p: [s.name for s in p.subtitles],
        ["Probe Sub"],
    ),
    "SubtitleTrack.file": (
        lambda p: setattr(
            p, "subtitles", [SubtitleTrack(id=0, name="S", file="/tmp/probe.ass")]
        ),
        lambda p: [s.file for s in p.subtitles],
        ["/tmp/probe.ass"],
    ),
    "SubtitleTrack.style": (
        lambda p: setattr(
            p,
            "subtitles",
            [SubtitleTrack(id=0, name="S", file="/tmp/s.ass", style="FontSize=42")],
        ),
        lambda p: [s.style for s in p.subtitles],
        ["FontSize=42"],
    ),
}

#: Fields that legitimately do not round-trip, each with the reason.  A field
#: belongs here only when *not* carrying the value is the deliberate behaviour.
EXEMPT: dict[str, str] = {}


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


def _declared_fields() -> set[str]:
    return {
        f"{cls.__name__}.{field}"
        for cls in COVERED_CLASSES
        for field in cls.model_fields
    }


def test_every_covered_field_is_probed_or_exempt() -> None:
    """A new field on a covered class must be given a probe or an exemption.

    This is the half that makes the rule a rule rather than a list of examples:
    adding ``Track.colour`` and wiring nothing fails here, which is the moment
    the "emit it or do not accept it" decision has to be made.
    """
    declared = _declared_fields()
    accounted = set(PROBES) | set(EXEMPT)
    assert declared - accounted == set(), (
        "unaccounted model fields -- add a probe (and make it pass) or an "
        f"EXEMPT entry stating why the value is dropped: {sorted(declared - accounted)}"
    )
    assert accounted - declared == set(), (
        f"PROBES/EXEMPT name fields that no longer exist: {sorted(accounted - declared)}"
    )
    assert set(PROBES) & set(EXEMPT) == set(), "a field cannot be both probed and exempt"


def test_every_exemption_states_a_reason() -> None:
    for field, reason in EXEMPT.items():
        assert reason.strip(), f"{field}: an exemption without a reason is a hidden defect"


@pytest.mark.parametrize("label", sorted(PROBES))
def test_the_value_survives_serialize_and_reparse(label: str, tmp_path: Path) -> None:
    mutate, read, expected = PROBES[label]
    back = round_trip(mutate, tmp_path)
    assert read(back) == expected, (
        f"{label}: the model accepted the value and the written document does "
        f"not carry it back. Emit it, or stop accepting it."
    )


# ---------------------------------------------------------------------------
# Detector controls: the harness must be able to fail, and must not invent values
# ---------------------------------------------------------------------------


def test_the_harness_reports_a_loss_when_the_emission_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control: point the writer at a property name nothing reads, and the same
    probe that passes above must now come back empty.  Without this, a harness
    that silently agreed with itself would look identical."""
    monkeypatch.setattr(S, "TRACK_NAME_PROPERTY", "kdenlive:not_a_real_property")
    back = round_trip(_set_track_names, tmp_path)
    assert [t.name for t in back.tracks] == [None, None]


def test_an_unnamed_track_parses_back_unnamed(tmp_path: Path) -> None:
    """Control in the other direction: the parser must not invent a name for a
    document that carries none, or the probe above would pass on anything."""
    back = round_trip(lambda p: None, tmp_path)
    assert [t.name for t in back.tracks] == [None, None]


# ---------------------------------------------------------------------------
# Track.name: the decision was EMIT, and the document must say so
# ---------------------------------------------------------------------------


def test_the_track_name_lands_on_the_per_track_tractor(tmp_path: Path) -> None:
    """Asserted over the written file, not the model: ``kdenlive:track_name`` on
    the per-track ``<tractor>`` is where Kdenlive 25/26 puts it (ground truth:
    ``tests/fixtures/kdenlive_references/clip_speed_400_native.kdenlive``)."""
    import xml.etree.ElementTree as ET

    project = _base_project()
    _set_track_names(project)
    out = tmp_path / "named.kdenlive"
    S.serialize_project(project, out)

    named: dict[str, str] = {}
    for tractor in ET.parse(out).getroot().findall("tractor"):
        for prop in tractor.findall("property"):
            if prop.get("name") == "kdenlive:track_name":
                named[tractor.get("id", "")] = prop.text or ""
    assert named == {"tractor_pl_v": "ProbeV", "tractor_pl_a": "ProbeA"}


def test_an_unnamed_track_emits_no_track_name_property(tmp_path: Path) -> None:
    """Accept control: ``None`` must write nothing, not an empty property.  An
    empty ``kdenlive:track_name`` is a *named* track called "" in Kdenlive."""
    out = tmp_path / "unnamed.kdenlive"
    S.serialize_project(_base_project(), out)
    assert "kdenlive:track_name" not in out.read_text(encoding="utf-8")


def test_the_track_name_is_not_also_kept_as_an_opaque_property(tmp_path: Path) -> None:
    """Re-writing a native document must not duplicate the label.

    The property is now regenerated from ``Track.name``, so the parser has to
    list it in ``_REGENERATED_SEQUENCE_PROPS``.  Drop it from that set and the
    parser *also* keeps it as an OpaqueElement hinted ``"tractor"``, which the
    serializer appends to the **sequence** tractor -- measured: the sequence
    tractor comes back carrying ``kdenlive:track_name`` twice, ``V1`` and ``A1``,
    on the one element that labels no track at all.  Nothing else notices,
    because the per-track copies are still correct.
    """
    import xml.etree.ElementTree as ET

    reference = (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "kdenlive_references"
        / "clip_speed_400_native.kdenlive"
    )
    out = tmp_path / "rewritten.kdenlive"
    S.serialize_project(parse_project(reference), out)

    stray = [
        tractor.get("id")
        for tractor in ET.parse(out).getroot().findall("tractor")
        if not (tractor.get("id") or "").startswith("tractor_")
        and any(
            p.get("name") == S.TRACK_NAME_PROPERTY for p in tractor.findall("property")
        )
    ]
    assert stray == [], f"{S.TRACK_NAME_PROPERTY} on non per-track tractors: {stray}"


def test_a_real_kdenlive_document_gives_up_its_track_names() -> None:
    """The parser reads the property from a document this project did not write."""
    reference = (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "kdenlive_references"
        / "clip_speed_400_native.kdenlive"
    )
    project = parse_project(reference)
    # Distinct names: a native document's per-track tractor wraps two content
    # playlists (Kdenlive calls them ``playlist0``/``playlist1``, not the
    # ``_kdpair`` suffix this serializer uses), so the parser sees both lanes as
    # tracks and both inherit their tractor's label. That is pre-existing
    # behaviour and not what this test is about.
    assert sorted({t.name or "" for t in project.tracks}) == ["A1", "V1"]


# ---------------------------------------------------------------------------
# KdenliveProject.tractor: the decision was REMOVE
# ---------------------------------------------------------------------------


def test_the_project_has_no_tractor_field() -> None:
    """The serializer regenerates every tractor attribute it writes -- the
    sequence tractor's ``id`` *is* the sequence uuid that
    ``kdenlive:docproperties.uuid``/``opensequences``/``activetimeline`` point
    at, and ``in``/``out`` come from ``_content_out``.  Honouring a stored value
    would produce an invalid document, so there was nothing to emit; the field
    was a sink.  A survey of all 109 ``<tractor>`` elements in
    ``tests/fixtures`` finds only ``id``, ``in`` and ``out``, so nothing is lost.
    """
    assert "tractor" not in KdenliveProject.model_fields


def test_nothing_writes_a_tractor_out_into_the_model() -> None:
    """``_sync_tractor_out`` computed the timeline length and stored it where
    nothing read it -- a second, stale statement of ``serializer._content_out``,
    which computes the same number from the same playlists at write time."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher, patcher_intents

    assert not hasattr(patcher_intents, "_sync_tractor_out")
    assert not hasattr(patcher, "_sync_tractor_out")


def test_the_written_timeline_length_still_tracks_the_content(tmp_path: Path) -> None:
    """Accept control for that removal, over the re-parsed document: the thing
    ``_sync_tractor_out`` claimed to maintain is maintained, by the serializer."""
    import xml.etree.ElementTree as ET

    project = _base_project()
    project.playlists[0].entries[0].out_point = 99
    out = tmp_path / "length.kdenlive"
    S.serialize_project(project, out)

    outs = {
        tractor.get("id"): tractor.get("out")
        for tractor in ET.parse(out).getroot().findall("tractor")
    }
    assert outs, "no tractors written"
    assert set(outs.values()) == {"99"}, outs
