"""A save must not re-base a project's relative resources.

melt resolves every relative ``resource`` against the ``<mlt root>`` attribute,
falling back to the document's own directory when the attribute is absent or
empty (``adapters/render/media_check.effective_root`` is the one statement of
that rule).  So the *effective root* is a property of the document that was
imported, not of wherever the user happens to save it next.

The decision recorded here: **a save preserves the imported project's effective
root; it never rewrites resource strings.**  Rewriting was rejected because MLT
``resource`` values are not all filesystem paths -- ``color``/``black``,
built-in luma names, ``%``-prefixed ``MLT_DATA`` names and ``%04d``/``glob:``
image sequences all live in the same property, and a rewriter that
misidentifies one corrupts the project silently.  Preserving the root leaves
every resource string byte-identical and leaves every one of them pointing at
the same file it pointed at before, which is what "lossless" has to mean here.

Every assertion below is made against the **re-parsed document on disk**, not
against the model that was handed to the serializer.
"""
from __future__ import annotations

import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    serialize_project,
)
from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    Track,
)

# A document whose media reference is RELATIVE -- the only kind that can be
# re-based.  ``root`` names the directory those relatives resolve against.
_RELATIVE_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <mlt LC_NUMERIC="C" version="7" title="Imported" producer="main_bin" root="{root}">
      <profile width="1920" height="1080" frame_rate_num="25" frame_rate_den="1"/>
      <producer id="prod0" in="0" out="99">
        <property name="mlt_service">avformat</property>
        <property name="resource">footage/clip.mp4</property>
        <property name="length">100</property>
      </producer>
      <playlist id="pl0">
        <entry producer="prod0" in="0" out="99"/>
      </playlist>
      <tractor id="tractor0" in="0" out="99">
        <track producer="pl0"/>
      </tractor>
    </mlt>
""")

_NO_ROOT_ATTR_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <mlt LC_NUMERIC="C" version="7" title="Rootless" producer="main_bin">
      <profile width="1920" height="1080" frame_rate_num="25" frame_rate_den="1"/>
      <producer id="prod0" in="0" out="99">
        <property name="mlt_service">avformat</property>
        <property name="resource">footage/clip.mp4</property>
        <property name="length">100</property>
      </producer>
      <playlist id="pl0">
        <entry producer="prod0" in="0" out="99"/>
      </playlist>
      <tractor id="tractor0" in="0" out="99">
        <track producer="pl0"/>
      </tractor>
    </mlt>
""")


def _written_root(path: Path) -> str:
    """The ``<mlt root>`` of the document actually on disk."""
    return ET.parse(path).getroot().get("root", "")


def _resolved_resources(path: Path) -> list[Path]:
    """Every file-backed (``avformat``) resource in the document on disk,
    resolved the way melt resolves it: relative values joined to the document's
    effective root.

    Synthetic producers -- the ``color``/``black`` background the serializer
    regenerates on every write -- are excluded: their ``resource`` is not a
    path, and including them would compare a parsed document against a written
    one that legitimately carries extra infrastructure.
    """
    root = ET.parse(path).getroot()
    base = Path(root.get("root") or path.parent)
    out: list[Path] = []
    for element in root.iter():
        props = {
            p.get("name"): (p.text or "").strip() for p in element.findall("property")
        }
        if props.get("mlt_service") != "avformat":
            continue
        value = props.get("resource", "")
        if not value:
            continue
        p = Path(value)
        out.append(p if p.is_absolute() else base / p)
    return sorted(out)


# ---------------------------------------------------------------------------
# The bug: importing a project and saving it elsewhere re-points its media
# ---------------------------------------------------------------------------


def test_saving_elsewhere_preserves_the_imported_root(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    src = origin / "imported.kdenlive"
    src.write_text(_RELATIVE_XML.format(root=origin), encoding="utf-8")

    project = parse_project(src)
    out = elsewhere / "saved.kdenlive"
    serialize_project(project, out)

    assert _written_root(out) == str(origin)


def test_saving_elsewhere_keeps_relative_media_pointing_at_the_same_files(
    tmp_path: Path,
) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    src = origin / "imported.kdenlive"
    src.write_text(_RELATIVE_XML.format(root=origin), encoding="utf-8")
    before = _resolved_resources(src)

    project = parse_project(src)
    out = elsewhere / "saved.kdenlive"
    serialize_project(project, out)

    # What the relative resource MEANS is unchanged...
    assert _resolved_resources(out) == before
    assert before == [origin / "footage" / "clip.mp4"]


def test_saving_elsewhere_does_not_rewrite_the_resource_string(
    tmp_path: Path,
) -> None:
    """The chosen fix preserves the root; it must not touch resource text."""
    origin = tmp_path / "origin"
    origin.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    src = origin / "imported.kdenlive"
    src.write_text(_RELATIVE_XML.format(root=origin), encoding="utf-8")

    project = parse_project(src)
    out = elsewhere / "saved.kdenlive"
    serialize_project(project, out)

    written = ET.parse(out).getroot()
    resources = [
        (p.text or "").strip()
        for e in written.iter()
        for p in e.findall("property")
        if p.get("name") == "resource" and (p.text or "").strip()
    ]
    assert "footage/clip.mp4" in resources


def test_a_rootless_document_resolves_against_its_own_directory(
    tmp_path: Path,
) -> None:
    """A document with no ``root`` attribute resolves relatives against its own
    directory -- ``missing_media`` already says so, and a save must agree."""
    origin = tmp_path / "origin"
    origin.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    src = origin / "imported.kdenlive"
    src.write_text(_NO_ROOT_ATTR_XML, encoding="utf-8")
    before = _resolved_resources(src)
    assert before == [origin / "footage" / "clip.mp4"]

    project = parse_project(src)
    out = elsewhere / "saved.kdenlive"
    serialize_project(project, out)

    assert _resolved_resources(out) == before


def test_repeated_round_trips_do_not_drift(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    src = origin / "imported.kdenlive"
    src.write_text(_RELATIVE_XML.format(root=origin), encoding="utf-8")
    before = _resolved_resources(src)

    current = src
    for i in range(3):
        hop = tmp_path / f"hop{i}"
        hop.mkdir()
        out = hop / "saved.kdenlive"
        serialize_project(parse_project(current), out)
        current = out

    assert _written_root(current) == str(origin)
    assert _resolved_resources(current) == before


# ---------------------------------------------------------------------------
# Accept controls -- the other direction.  A guard that preserves everything is
# as wrong as one that preserves nothing.
# ---------------------------------------------------------------------------


def _in_memory_project() -> KdenliveProject:
    return KdenliveProject(
        version="7",
        title="Built here",
        producers=[
            Producer(
                id="prod0",
                resource="/abs/clip.mp4",
                properties={"mlt_service": "avformat", "length": "100"},
            )
        ],
        tracks=[Track(id="pl0", track_type="video")],
        playlists=[
            Playlist(
                id="pl0",
                entries=[PlaylistEntry(producer_id="prod0", in_point=0, out_point=99)],
            )
        ],
    )


def test_in_memory_project_still_roots_at_the_output_directory(
    tmp_path: Path,
) -> None:
    """A project that was never parsed has no imported root to preserve; the
    output file's own directory stays the right answer."""
    out = tmp_path / "built" / "new.kdenlive"
    serialize_project(_in_memory_project(), out)

    assert _written_root(out) == str(out.parent)


def test_an_explicitly_cleared_root_falls_back_to_the_output_directory(
    tmp_path: Path,
) -> None:
    """Accept control: a caller that clears ``root`` opts back in to re-rooting
    at the save location -- that is the relocate escape hatch."""
    origin = tmp_path / "origin"
    origin.mkdir()
    src = origin / "imported.kdenlive"
    src.write_text(_RELATIVE_XML.format(root=origin), encoding="utf-8")

    project = parse_project(src)
    project.root = ""

    out = tmp_path / "elsewhere" / "saved.kdenlive"
    serialize_project(project, out)

    assert _written_root(out) == str(out.parent)


def test_saving_in_place_is_unchanged(tmp_path: Path) -> None:
    """Accept control: the common case -- open, edit, save over the same file --
    must keep writing the same root it always did."""
    origin = tmp_path / "origin"
    origin.mkdir()
    src = origin / "imported.kdenlive"
    src.write_text(_RELATIVE_XML.format(root=origin), encoding="utf-8")

    project = parse_project(src)
    serialize_project(project, src)

    assert _written_root(src) == str(origin)
    assert _resolved_resources(src) == [origin / "footage" / "clip.mp4"]


def test_a_caller_may_retarget_the_root_explicitly(tmp_path: Path) -> None:
    """Accept control: preserving the parsed root must not become a lock.  A
    relocate sets ``project.root`` and the serializer honours that."""
    origin = tmp_path / "origin"
    origin.mkdir()
    relocated = tmp_path / "relocated"
    relocated.mkdir()
    src = origin / "imported.kdenlive"
    src.write_text(_RELATIVE_XML.format(root=origin), encoding="utf-8")

    project = parse_project(src)
    project.root = str(relocated)

    out = tmp_path / "elsewhere" / "saved.kdenlive"
    serialize_project(project, out)

    assert _written_root(out) == str(relocated)
    assert _resolved_resources(out) == [relocated / "footage" / "clip.mp4"]


# ---------------------------------------------------------------------------
# The parser side of the same rule: ``project.root`` is the EFFECTIVE root.
# ---------------------------------------------------------------------------


def test_parser_records_the_root_attribute(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    src = origin / "imported.kdenlive"
    src.write_text(_RELATIVE_XML.format(root=origin), encoding="utf-8")

    assert parse_project(src).root == str(origin)


def test_parser_falls_back_to_the_document_directory(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    src = origin / "imported.kdenlive"
    src.write_text(_NO_ROOT_ATTR_XML, encoding="utf-8")

    assert parse_project(src).root == str(origin)


def test_parser_falls_back_for_an_empty_root_attribute(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    src = origin / "imported.kdenlive"
    src.write_text(_RELATIVE_XML.format(root=""), encoding="utf-8")

    assert parse_project(src).root == str(origin)


def test_the_model_and_xml_front_doors_agree_on_the_effective_root(
    tmp_path: Path,
) -> None:
    """``missing_media`` (XML door) and ``parse_project`` (model door) must
    resolve a relative resource against the same directory, for every shape of
    the ``root`` attribute."""
    from workshop_video_brain.edit_mcp.adapters.render.media_check import (
        missing_media,
    )

    for i, xml in enumerate(
        (
            _RELATIVE_XML.format(root="{origin}"),
            _NO_ROOT_ATTR_XML,
            _RELATIVE_XML.format(root=""),
        )
    ):
        origin = tmp_path / f"case{i}"
        origin.mkdir()
        src = origin / "imported.kdenlive"
        src.write_text(xml.replace("{origin}", str(origin)), encoding="utf-8")

        xml_door = missing_media(src)
        model_door = Path(parse_project(src).root) / "footage" / "clip.mp4"

        assert xml_door == [str(model_door)], f"case {i}"
