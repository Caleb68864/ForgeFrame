"""Item 5: BRollEntry.loudness_lufs field + optional loudness->library write.

The b-roll model previously dropped an unknown ``loudness_lufs`` key, so
``audio_loudness_scan`` could not persist measured LUFS into the index. These
tests lock the new field and the minimal ``write_loudness_to_library`` wiring.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.core.models.broll_library import BRollEntry, BRollLibrary
from workshop_video_brain.edit_mcp.pipelines import broll_library as lib
from workshop_video_brain.edit_mcp.pipelines.loudness_scan import (
    write_loudness_to_library,
)


def test_broll_entry_has_optional_loudness_field():
    e = BRollEntry(clip_ref="a.mov")
    assert e.loudness_lufs is None
    e2 = BRollEntry(clip_ref="a.mov", loudness_lufs=-16.4)
    assert e2.loudness_lufs == -16.4
    # Round-trips through JSON serialization.
    assert BRollEntry.from_json(e2.to_json()).loudness_lufs == -16.4


def _seed_library(vault: Path, paths: list[str]) -> None:
    library = BRollLibrary(
        entries=[BRollEntry(clip_ref=Path(p).name, source_path=p) for p in paths]
    )
    lib.save_library(vault, library)


def test_write_loudness_updates_matching_entries(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    _seed_library(vault, ["/media/a.mov", "/media/b.mov"])

    rows = [
        {"clip": "/media/a.mov", "ok": True, "lufs": -16.2, "true_peak": -1.0, "lra": 5.0},
        {"clip": "/media/b.mov", "ok": True, "lufs": -14.0, "true_peak": -1.0, "lra": 5.0},
        {"clip": "/media/missing.mov", "ok": True, "lufs": -20.0},  # no entry
        {"clip": "/media/a.mov", "ok": False, "lufs": None},        # skipped
    ]
    result = write_loudness_to_library(vault, rows)
    assert result["updated"] == 2
    assert result["matched"] == 2

    reloaded = lib.load_library(vault)
    by_path = {e.source_path: e for e in reloaded.entries}
    assert by_path["/media/a.mov"].loudness_lufs == -16.2
    assert by_path["/media/b.mov"].loudness_lufs == -14.0


def test_write_loudness_noop_when_no_matches(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    _seed_library(vault, ["/media/a.mov"])
    result = write_loudness_to_library(
        vault, [{"clip": "/media/other.mov", "ok": True, "lufs": -12.0}]
    )
    assert result == {"matched": 1, "updated": 0}
    assert lib.load_library(vault).entries[0].loudness_lufs is None
