"""fixture-roundtrip: parse real-Kdenlive projects, re-serialize, and validate.

Oracle = files saved by *actual* Kdenlive plus melt. Asserts (a) the parse is
non-empty (guards against ``parse_project`` swallowing errors into an empty
project -- evidence #6), (b) no gross element loss on round-trip, especially
entry-nested ``<filter>`` elements (§1.2), and (c) the round-tripped file still
loads in melt.

Fixtures live in ``tests/fixtures/projects/real/*.kdenlive`` and must be
produced by hand from real Kdenlive (see ``make_real_fixtures.md``). Until they
exist the module skips cleanly, so the harness lands before the fixtures do.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

from ._oracle import melt_accepts

pytestmark = pytest.mark.external

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "projects" / "real"


def _fixtures() -> list[Path]:
    if not FIXTURE_DIR.exists():
        return []
    return sorted(FIXTURE_DIR.glob("*.kdenlive"))


_FIXTURES = _fixtures()

if not _FIXTURES:
    pytest.skip(
        f"no real-Kdenlive fixtures in {FIXTURE_DIR} -- see make_real_fixtures.md",
        allow_module_level=True,
    )


def _count_tags(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for elem in ET.parse(path).getroot().iter():
        counts[elem.tag] = counts.get(elem.tag, 0) + 1
    return counts


@pytest.mark.parametrize("fixture", _FIXTURES, ids=[f.name for f in _FIXTURES])
def test_roundtrip_preserves_and_loads(fixture: Path, melt_bin, tmp_path: Path):
    project = parse_project(fixture)
    # Guard against a silently-empty parse masquerading as a clean round-trip.
    assert project.producers or project.playlists or project.tracks, (
        f"parse_project returned an empty project for {fixture.name}"
    )

    out = tmp_path / f"roundtrip_{fixture.name}"
    serialize_project(project, out)

    before = _count_tags(fixture)
    after = _count_tags(out)
    # Entry-nested clip effects must survive (§1.2).
    assert after.get("filter", 0) >= before.get("filter", 0), (
        f"lost <filter> elements on round-trip: {before.get('filter', 0)} -> "
        f"{after.get('filter', 0)}"
    )

    result = melt_accepts(out, melt_bin=melt_bin)
    assert result.ok, f"round-tripped {fixture.name} rejected by melt:\n{result.stderr[-1500:]}"
