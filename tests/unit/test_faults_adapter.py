"""Adversarial fault-injection tests for the Kdenlive adapter (Hardening Pass 2).

Every adversarial input must produce **either** a correct parse **or** a typed
error (``ProjectParseError`` on read, ``ProjectSerializeError`` on write) that
carries element/track/index context -- never a raw ``KeyError`` / ``IndexError``
/ ``AttributeError`` / ``RecursionError`` leaking from deep inside the adapter,
and never a silently-broken output document.

Corpus lives in ``tests/fixtures/projects/adversarial/`` (malformed inputs) and
``tests/fixtures/projects/legacy/`` (real pre-E-shape ForgeFrame projects that
must still parse and upgrade to the E-shape).  Two pathological inputs (a 10k-clip
~large project and a deeply-nested tree) are generated in-test rather than
committed.

Documented behaviours proven here:
* ``xml.etree.ElementTree`` (expat) rejects **external** entities but *expands*
  **internal** entities -- so a ``DOCTYPE`` is an entity-expansion (billion
  laughs) / XXE surface.  The parser therefore rejects any document carrying a
  ``DOCTYPE`` before it reaches expat.  See ``test_doctype_*``.
* the serializer refuses to emit dangling producer references, inverted/negative
  in/out points and non-positive blank lengths.
* the write path is atomic (sibling temp + ``os.replace``) *and* validated
  (well-formedness check) -- a rejected or interrupted serialize never clobbers
  an existing file.
"""
from __future__ import annotations

import shutil
import subprocess
import time
import tracemalloc
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
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import (
    ProjectParseError,
    parse_project,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    ProjectSerializeError,
    serialize_project,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "projects"
ADVERSARIAL = FIXTURES / "adversarial"
LEGACY = FIXTURES / "legacy"
REAL = FIXTURES / "real"


def _adversarial() -> list[Path]:
    return sorted(ADVERSARIAL.glob("*.kdenlive"))


# Fixtures whose *parse* must raise ProjectParseError.
_PARSE_MUST_FAIL = {
    "empty.kdenlive",
    "not_xml.kdenlive",
    "truncated_prolog.kdenlive",
    "truncated_deep.kdenlive",
    "wrong_root_html.kdenlive",
    "wrong_root_fcpxml.kdenlive",
    "xxe_external.kdenlive",
    "billion_laughs.kdenlive",
    "doctype_plain.kdenlive",
}

# Fixtures that parse cleanly but whose *serialize* must raise
# ProjectSerializeError (model too inconsistent to emit a valid document).
_SERIALIZE_MUST_FAIL = {
    "ghost_producer.kdenlive",
    "negative_blank.kdenlive",
    "out_lt_in.kdenlive",
    "negative_in.kdenlive",
}


# ---------------------------------------------------------------------------
# Global contract: no adversarial input ever leaks a non-typed exception.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture", _adversarial(), ids=[p.name for p in _adversarial()]
)
def test_adversarial_input_never_raises_raw_exception(fixture: Path, tmp_path: Path):
    """Parse+serialize any adversarial input: only KdenliveProject or a typed
    error is allowed to escape."""
    try:
        project = parse_project(fixture)
    except ProjectParseError:
        return  # acceptable, typed
    except Exception as exc:  # noqa: BLE001 - the whole point is to catch these
        pytest.fail(
            f"{fixture.name}: parse leaked non-typed {type(exc).__name__}: {exc}"
        )

    assert isinstance(project, KdenliveProject)

    out = tmp_path / f"out_{fixture.name}"
    try:
        serialize_project(project, out)
    except ProjectSerializeError:
        assert not out.exists(), (
            f"{fixture.name}: failed serialize left a partial file behind"
        )
        return  # acceptable, typed
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"{fixture.name}: serialize leaked non-typed {type(exc).__name__}: {exc}"
        )

    # If it serialized, the output must be well-formed XML rooted at <mlt>.
    root = ET.parse(out).getroot()
    assert root.tag == "mlt"


@pytest.mark.parametrize(
    "fixture",
    sorted(_PARSE_MUST_FAIL),
)
def test_parse_failures_raise_projectparseerror(fixture: str):
    path = ADVERSARIAL / fixture
    with pytest.raises(ProjectParseError) as ei:
        parse_project(path)
    # The error must name the offending file.
    assert str(path) in str(ei.value)


@pytest.mark.parametrize("fixture", sorted(_SERIALIZE_MUST_FAIL))
def test_serialize_failures_raise_with_context(fixture: str, tmp_path: Path):
    project = parse_project(ADVERSARIAL / fixture)
    out = tmp_path / "out.kdenlive"
    with pytest.raises(ProjectSerializeError) as ei:
        serialize_project(project, out)
    msg = str(ei.value)
    # Context: message references a playlist and an entry index.
    assert "playlist" in msg and "#" in msg
    assert not out.exists()


# ---------------------------------------------------------------------------
# missing_ok: parse failures degrade to an empty project, never raise.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", sorted(_PARSE_MUST_FAIL))
def test_missing_ok_returns_empty_project(fixture: str):
    project = parse_project(ADVERSARIAL / fixture, missing_ok=True)
    assert isinstance(project, KdenliveProject)
    assert not project.producers
    assert not project.playlists


# ---------------------------------------------------------------------------
# Entity-expansion / XXE guard (documented behaviour).
# ---------------------------------------------------------------------------


def test_doctype_external_entity_rejected():
    """XXE: a DOCTYPE with an external SYSTEM entity is rejected (no file read)."""
    with pytest.raises(ProjectParseError):
        parse_project(ADVERSARIAL / "xxe_external.kdenlive")


def test_doctype_billion_laughs_rejected():
    """DoS: nested internal entities would expand; the DOCTYPE guard blocks it
    before expat ever expands them."""
    with pytest.raises(ProjectParseError):
        parse_project(ADVERSARIAL / "billion_laughs.kdenlive")


def test_plain_doctype_rejected():
    """Even an entity-free DOCTYPE is rejected -- a real .kdenlive never has one."""
    with pytest.raises(ProjectParseError):
        parse_project(ADVERSARIAL / "doctype_plain.kdenlive")


# ---------------------------------------------------------------------------
# Wrong root.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture", ["wrong_root_html.kdenlive", "wrong_root_fcpxml.kdenlive"]
)
def test_wrong_root_rejected(fixture: str):
    with pytest.raises(ProjectParseError) as ei:
        parse_project(ADVERSARIAL / fixture)
    assert "expected <mlt>" in str(ei.value)


# ---------------------------------------------------------------------------
# Structurally-odd-but-parseable inputs parse and serialize to valid XML.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture",
    [
        "zero_tracks.kdenlive",
        "filter_no_service.kdenlive",
        "bad_entry_int.kdenlive",
        "bad_blank_int.kdenlive",
        "bad_chain_out.kdenlive",
    ],
)
def test_odd_but_parseable_roundtrips(fixture: str, tmp_path: Path):
    project = parse_project(ADVERSARIAL / fixture)
    out = tmp_path / "out.kdenlive"
    serialize_project(project, out)
    root = ET.parse(out).getroot()
    assert root.tag == "mlt"


def test_zero_track_project_serializes():
    project = parse_project(ADVERSARIAL / "zero_tracks.kdenlive")
    assert project.tracks == []
    assert project.profile.width == 1920


# ---------------------------------------------------------------------------
# Deep nesting -> ProjectParseError, not RecursionError.
# ---------------------------------------------------------------------------


def test_deeply_nested_document_rejected(tmp_path: Path):
    depth = 5000
    deep = tmp_path / "deep.kdenlive"
    deep.write_text(
        '<mlt version="7">'
        + "<wrap>" * depth
        + "x"
        + "</wrap>" * depth
        + "</mlt>"
    )
    with pytest.raises(ProjectParseError) as ei:
        parse_project(deep)
    assert "nesting too deep" in str(ei.value)


def test_reasonable_nesting_accepted(tmp_path: Path):
    """A document nested well below the cap parses normally."""
    depth = 30
    ok = tmp_path / "ok.kdenlive"
    ok.write_text(
        '<mlt version="7">'
        + "<wrap>" * depth
        + "x"
        + "</wrap>" * depth
        + "</mlt>"
    )
    project = parse_project(ok)
    assert isinstance(project, KdenliveProject)


# ---------------------------------------------------------------------------
# Large project: parse+serialize time and memory sanity (generous bounds).
# ---------------------------------------------------------------------------


def _build_large_xml(n_clips: int) -> str:
    parts = [
        '<mlt version="7">',
        '<profile width="1920" height="1080" frame_rate_num="25" '
        'frame_rate_den="1"/>',
    ]
    for i in range(n_clips):
        parts.append(
            f'<producer id="p{i}" in="0" out="99">'
            f'<property name="resource">/media/library/clip_{i:06d}.mp4</property>'
            f'<property name="length">100</property>'
            f'<property name="mlt_service">avformat</property></producer>'
        )
    parts.append('<playlist id="pl0">')
    for i in range(n_clips):
        parts.append(f'<entry producer="p{i}" in="0" out="99"/>')
    parts.append("</playlist>")
    parts.append('<tractor id="t0"><track producer="pl0"/></tractor></mlt>')
    return "".join(parts)


def test_large_project_parse_serialize_bounds(tmp_path: Path):
    n_clips = 10_000
    big = tmp_path / "big.kdenlive"
    big.write_text(_build_large_xml(n_clips))

    tracemalloc.start()
    t0 = time.perf_counter()
    project = parse_project(big)
    t1 = time.perf_counter()
    out = tmp_path / "big_out.kdenlive"
    serialize_project(project, out)
    t2 = time.perf_counter()
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert len(project.producers) == n_clips
    # Generous bounds -- these run in ~3s / ~100MB locally.
    assert (t1 - t0) < 20, f"parse took {t1 - t0:.1f}s"
    assert (t2 - t1) < 40, f"serialize took {t2 - t1:.1f}s"
    assert peak < 800 * 1024 * 1024, f"peak memory {peak / 1e6:.0f}MB"
    # Output re-parses and preserves every clip.
    reparsed = parse_project(out)
    assert len(reparsed.producers) == n_clips


# ---------------------------------------------------------------------------
# Legacy backward-compat: pre-E-shape ForgeFrame projects parse & upgrade.
# ---------------------------------------------------------------------------


def _legacy() -> list[Path]:
    return sorted(LEGACY.glob("*.kdenlive"))


def _props(elem: ET.Element) -> dict[str, str]:
    return {c.get("name", ""): (c.text or "") for c in elem if c.tag == "property"}


@pytest.mark.parametrize("fixture", _legacy(), ids=[p.name for p in _legacy()])
def test_legacy_project_upgrades_to_eshape(fixture: Path, tmp_path: Path):
    project = parse_project(fixture)
    # Backward compat: the legacy file must PARSE to real content.
    assert project.producers or project.playlists or project.tracks

    out = tmp_path / f"upgraded_{fixture.name}"
    serialize_project(project, out)
    root = ET.parse(out).getroot()

    # E-shape invariants (kdenlive-gui-bin-rejection round 2):
    # 1. no media/AV producer carries kdenlive:uuid.
    for tag in ("producer", "chain"):
        for p in root.findall(tag):
            pr = _props(p)
            if pr.get("kdenlive:playlistid") == "black_track":
                continue
            if p.get("id") in ("producer_black", "black_track"):
                continue
            assert "kdenlive:uuid" not in pr, (
                f"{fixture.name}: media producer {p.get('id')} kept kdenlive:uuid"
            )
    # 2. exactly one sequence tractor (producer_type=17) carrying kdenlive:uuid.
    seq = [
        t for t in root.findall("tractor")
        if _props(t).get("kdenlive:producer_type") == "17"
    ]
    assert len(seq) == 1
    assert "kdenlive:uuid" in _props(seq[0])
    # 3. a projectTractor render root exists.
    projt = [
        t for t in root.findall("tractor")
        if "kdenlive:projectTractor" in _props(t)
    ]
    assert len(projt) == 1
    # 4. main_bin carries xml_retain=1.
    main_bin = root.find("playlist[@id='main_bin']")
    assert main_bin is not None
    assert _props(main_bin).get("xml_retain") == "1"

    # Re-parses cleanly (upgrade is stable).
    assert isinstance(parse_project(out), KdenliveProject)


# ---------------------------------------------------------------------------
# Round-trip idempotence for the real Kdenlive fixtures.
# ---------------------------------------------------------------------------


def _real() -> list[Path]:
    return sorted(REAL.glob("*.kdenlive"))


def _structural_signature(root: ET.Element):
    return [(e.tag, tuple(sorted(e.attrib.items()))) for e in root.iter()]


@pytest.mark.skipif(not _real(), reason="no real fixtures present")
@pytest.mark.parametrize("fixture", _real(), ids=[p.name for p in _real()])
def test_roundtrip_idempotence(fixture: Path, tmp_path: Path):
    """serialize(parse(x)) == serialize(parse(serialize(parse(x)))) structurally."""
    once = tmp_path / "once.kdenlive"
    serialize_project(parse_project(fixture), once)
    twice = tmp_path / "twice.kdenlive"
    serialize_project(parse_project(once), twice)

    sig_once = _structural_signature(ET.parse(once).getroot())
    sig_twice = _structural_signature(ET.parse(twice).getroot())
    assert sig_once == sig_twice, (
        f"{fixture.name}: second round-trip differs structurally"
    )


# ---------------------------------------------------------------------------
# Atomic-or-validated write path: a failed serialize never clobbers a file.
# ---------------------------------------------------------------------------


def _valid_project() -> KdenliveProject:
    return KdenliveProject(
        version="7",
        title="Valid",
        producers=[Producer(id="p0", resource="/media/a.mp4",
                            properties={"length": "100"})],
        tracks=[Track(id="pl0", track_type="video")],
        playlists=[Playlist(id="pl0", entries=[
            PlaylistEntry(producer_id="p0", in_point=0, out_point=99)])],
    )


def _inconsistent_project() -> KdenliveProject:
    return KdenliveProject(
        version="7",
        playlists=[Playlist(id="pl0", entries=[
            PlaylistEntry(producer_id="ghost", in_point=0, out_point=99)])],
    )


def test_failed_serialize_does_not_clobber_existing_file(tmp_path: Path):
    target = tmp_path / "project.kdenlive"
    serialize_project(_valid_project(), target)
    original = target.read_bytes()

    with pytest.raises(ProjectSerializeError):
        serialize_project(_inconsistent_project(), target)

    # File untouched, no temp turd left behind.
    assert target.read_bytes() == original
    assert not (tmp_path / "project.kdenlive.tmp").exists()


def test_failed_serialize_writes_no_new_file(tmp_path: Path):
    target = tmp_path / "fresh.kdenlive"
    with pytest.raises(ProjectSerializeError):
        serialize_project(_inconsistent_project(), target)
    assert not target.exists()
    assert not (tmp_path / "fresh.kdenlive.tmp").exists()


def test_atomic_write_produces_no_leftover_temp(tmp_path: Path):
    target = tmp_path / "ok.kdenlive"
    serialize_project(_valid_project(), target)
    assert target.exists()
    assert not (tmp_path / "ok.kdenlive.tmp").exists()


# ---------------------------------------------------------------------------
# Optional melt acceptance for legacy upgrades (skipped when melt is absent).
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("melt") is None, reason="melt not installed")
@pytest.mark.parametrize("fixture", _legacy(), ids=[p.name for p in _legacy()])
def test_legacy_upgrade_melt_accepts(fixture: Path, tmp_path: Path):
    project = parse_project(fixture)
    out = tmp_path / f"melt_{fixture.name}"
    serialize_project(project, out)
    result = subprocess.run(
        ["melt", str(out), "out=5", "-consumer", "null:"],
        capture_output=True, text=True, timeout=60,
    )
    fatal = [
        line for line in result.stderr.lower().splitlines()
        if any(s in line for s in (
            "no such producer", "invalid producer", "parse error",
            "syntax error", "cannot load", "could not load"))
    ]
    assert not fatal, f"{fixture.name}: melt structural errors: {fatal[:3]}"
