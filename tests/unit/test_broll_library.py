"""Unit tests for the B-Roll Library cross-project clip index feature."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from workshop_video_brain.core.models.broll_library import BRollEntry, BRollLibrary
from workshop_video_brain.core.models.clips import ClipLabel
from workshop_video_brain.edit_mcp.pipelines.broll_library import (
    generate_library_notes,
    get_library_stats,
    index_all_projects,
    index_project,
    load_library,
    remove_clip,
    save_library,
    search_library,
    tag_clip,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vault(tmp_path: Path) -> Path:
    """Create a minimal vault structure."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "B-Roll Library").mkdir()
    (vault / "B-Roll Library" / "Shots").mkdir()
    return vault


def _make_workspace(tmp_path: Path, title: str = "Test Project") -> Path:
    """Create a minimal workspace with a manifest."""
    ws = tmp_path / title.replace(" ", "-")
    ws.mkdir(parents=True)
    manifest = {
        "workspace_id": "00000000-0000-0000-0000-000000000001",
        "project_title": title,
        "slug": title.lower().replace(" ", "-"),
        "status": "editing",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "content_type": "",
        "vault_note_path": "",
        "media_root": "",
        "proxy_policy": {},
        "stt_engine": "whisper",
        "default_sort_mode": "chronological",
    }
    import yaml
    (ws / "workspace.yaml").write_text(yaml.dump(manifest), encoding="utf-8")
    return ws


def _make_label(
    clip_ref: str = "clip01",
    content_type: str = "b_roll",
    shot_type: str = "medium",
    topics: list[str] | None = None,
    tags: list[str] | None = None,
    summary: str = "",
    duration: float = 10.0,
    source_path: str = "",
) -> ClipLabel:
    return ClipLabel(
        clip_ref=clip_ref,
        content_type=content_type,
        topics=topics or [],
        shot_type=shot_type,
        has_speech=False,
        speech_density=0.0,
        summary=summary,
        tags=tags or [],
        duration=duration,
        source_path=source_path,
    )


def _write_label(workspace: Path, label: ClipLabel) -> None:
    clips_dir = workspace / "clips"
    clips_dir.mkdir(exist_ok=True)
    out = clips_dir / f"{label.clip_ref}_label.json"
    out.write_text(label.to_json(), encoding="utf-8")


def _make_entry(
    clip_ref: str = "clip01.mp4",
    source_project: str = "Test Project",
    source_workspace: str = "/ws/test",
    source_path: str = "/ws/test/media/clip01.mp4",
    content_type: str = "b_roll",
    shot_type: str = "medium",
    topics: list[str] | None = None,
    tags: list[str] | None = None,
    description: str = "",
    duration_seconds: float = 10.0,
    rating: int = 0,
) -> BRollEntry:
    return BRollEntry(
        clip_ref=clip_ref,
        source_project=source_project,
        source_workspace=source_workspace,
        source_path=source_path,
        content_type=content_type,
        shot_type=shot_type,
        topics=topics or [],
        tags=tags or [],
        description=description,
        duration_seconds=duration_seconds,
        rating=rating,
    )


# ---------------------------------------------------------------------------
# Library CRUD
# ---------------------------------------------------------------------------


class TestLoadLibrary:
    def test_load_from_empty_vault_returns_empty(self, tmp_path):
        vault = _make_vault(tmp_path)
        library = load_library(vault)
        assert isinstance(library, BRollLibrary)
        assert library.entries == []

    def test_load_missing_index_file_returns_empty(self, tmp_path):
        # vault exists but no broll-index.json
        vault = tmp_path / "vault"
        vault.mkdir()
        library = load_library(vault)
        assert library.entries == []

    def test_load_malformed_json_returns_empty(self, tmp_path):
        vault = _make_vault(tmp_path)
        index_path = vault / "B-Roll Library" / "broll-index.json"
        index_path.write_text("{invalid json{{{", encoding="utf-8")
        library = load_library(vault)
        assert library.entries == []


class TestSaveAndLoadRoundTrip:
    def test_save_then_load_roundtrip(self, tmp_path):
        vault = _make_vault(tmp_path)
        entry = _make_entry(clip_ref="sewing_01.mp4", source_project="Pouch Build")
        library = BRollLibrary(entries=[entry])
        save_library(vault, library)

        loaded = load_library(vault)
        assert len(loaded.entries) == 1
        assert loaded.entries[0].clip_ref == "sewing_01.mp4"
        assert loaded.entries[0].source_project == "Pouch Build"

    def test_save_updates_total_clips(self, tmp_path):
        vault = _make_vault(tmp_path)
        entries = [_make_entry(source_path=f"/path/clip{i}.mp4") for i in range(3)]
        library = BRollLibrary(entries=entries)
        save_library(vault, library)

        loaded = load_library(vault)
        assert loaded.total_clips == 3

    def test_save_updates_projects_indexed(self, tmp_path):
        vault = _make_vault(tmp_path)
        e1 = _make_entry(source_path="/p1/a.mp4", source_project="Alpha")
        e2 = _make_entry(source_path="/p2/b.mp4", source_project="Beta")
        library = BRollLibrary(entries=[e1, e2])
        save_library(vault, library)

        loaded = load_library(vault)
        assert "Alpha" in loaded.projects_indexed
        assert "Beta" in loaded.projects_indexed

    def test_save_sets_last_updated(self, tmp_path):
        from datetime import date
        vault = _make_vault(tmp_path)
        library = BRollLibrary()
        save_library(vault, library)
        loaded = load_library(vault)
        assert loaded.last_updated == date.today().isoformat()

    def test_roundtrip_preserves_all_fields(self, tmp_path):
        vault = _make_vault(tmp_path)
        entry = BRollEntry(
            clip_ref="stitch.mp4",
            source_project="Bag Build",
            source_workspace="/ws/bag",
            source_path="/ws/bag/media/stitch.mp4",
            content_type="b_roll",
            shot_type="closeup",
            topics=["sewing", "thread"],
            tags=["sewing", "detail"],
            description="Close up of stitching",
            duration_seconds=8.5,
            in_seconds=1.0,
            out_seconds=7.0,
            times_used=2,
            rating=4,
        )
        library = BRollLibrary(entries=[entry])
        save_library(vault, library)
        loaded = load_library(vault)
        e = loaded.entries[0]
        assert e.in_seconds == 1.0
        assert e.out_seconds == 7.0
        assert e.times_used == 2
        assert e.rating == 4
        assert e.description == "Close up of stitching"


class TestIndexProject:
    def test_index_project_adds_clips(self, tmp_path):
        vault = _make_vault(tmp_path)
        ws = _make_workspace(tmp_path, "Pouch Build")
        label = _make_label(
            clip_ref="overhead_01",
            content_type="b_roll",
            shot_type="overhead",
            tags=["sewing", "overhead"],
            source_path="/ws/media/overhead_01.mp4",
        )
        _write_label(ws, label)

        result = index_project(vault, ws)
        assert result["added"] == 1
        assert result["total"] == 1

        library = load_library(vault)
        assert len(library.entries) == 1
        assert library.entries[0].clip_ref == "overhead_01"
        assert library.entries[0].source_project == "Pouch Build"

    def test_index_project_deduplicates_by_source_path(self, tmp_path):
        vault = _make_vault(tmp_path)
        ws = _make_workspace(tmp_path, "Test")
        label = _make_label(
            clip_ref="clip01",
            source_path="/ws/media/clip01.mp4",
        )
        _write_label(ws, label)

        # Index once
        result1 = index_project(vault, ws)
        assert result1["added"] == 1

        # Index again — same source_path should be skipped
        result2 = index_project(vault, ws)
        assert result2["added"] == 0
        assert result2["skipped"] >= 1

        library = load_library(vault)
        assert len(library.entries) == 1

    def test_index_project_empty_clips_dir(self, tmp_path):
        vault = _make_vault(tmp_path)
        ws = _make_workspace(tmp_path, "Empty")
        result = index_project(vault, ws)
        assert result["added"] == 0
        assert result["total"] == 0

    def test_index_project_reads_manifest_title(self, tmp_path):
        vault = _make_vault(tmp_path)
        ws = _make_workspace(tmp_path, "Stove Bag Build")
        label = _make_label(
            clip_ref="footage_01",
            source_path="/ws/footage_01.mp4",
        )
        _write_label(ws, label)

        index_project(vault, ws)
        library = load_library(vault)
        assert library.entries[0].source_project == "Stove Bag Build"

    def test_index_project_skips_malformed_labels(self, tmp_path):
        vault = _make_vault(tmp_path)
        ws = _make_workspace(tmp_path, "Test")
        clips_dir = ws / "clips"
        clips_dir.mkdir()
        # Write a good label
        good = _make_label(clip_ref="good", source_path="/ws/good.mp4")
        _write_label(ws, good)
        # Write a bad label
        (clips_dir / "bad_label.json").write_text("{bad json", encoding="utf-8")

        result = index_project(vault, ws)
        assert result["added"] == 1
        assert result["skipped"] >= 1


class TestIndexAllProjects:
    def test_index_all_scans_multiple_workspaces(self, tmp_path):
        vault = _make_vault(tmp_path)
        projects_root = tmp_path / "projects"
        projects_root.mkdir()

        for i, title in enumerate(["Alpha", "Beta", "Gamma"]):
            ws = projects_root / title
            ws.mkdir()
            label = _make_label(
                clip_ref=f"clip_{i:02d}",
                source_path=f"/ws/{title}/clip_{i:02d}.mp4",
            )
            # Create workspace manifest
            import yaml
            manifest = {
                "workspace_id": f"00000000-0000-0000-0000-00000000000{i+1}",
                "project_title": title,
                "slug": title.lower(),
                "status": "editing",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "content_type": "",
                "vault_note_path": "",
                "media_root": "",
                "proxy_policy": {},
                "stt_engine": "whisper",
                "default_sort_mode": "chronological",
            }
            (ws / "workspace.yaml").write_text(yaml.dump(manifest), encoding="utf-8")
            _write_label(ws, label)

        result = index_all_projects(vault, projects_root)
        assert result["projects_scanned"] == 3
        assert result["total_added"] == 3
        assert result["total_clips"] == 3

    def test_index_all_empty_projects_root(self, tmp_path):
        vault = _make_vault(tmp_path)
        projects_root = tmp_path / "projects"
        projects_root.mkdir()

        result = index_all_projects(vault, projects_root)
        assert result["projects_scanned"] == 0
        assert result["total_clips"] == 0


class TestRemoveClip:
    def test_remove_clip_removes_entry(self, tmp_path):
        vault = _make_vault(tmp_path)
        e1 = _make_entry(source_path="/path/clip1.mp4")
        e2 = _make_entry(source_path="/path/clip2.mp4")
        library = BRollLibrary(entries=[e1, e2])
        save_library(vault, library)

        result = remove_clip(vault, "/path/clip1.mp4")
        assert result is True

        loaded = load_library(vault)
        assert len(loaded.entries) == 1
        assert loaded.entries[0].source_path == "/path/clip2.mp4"

    def test_remove_clip_returns_false_when_not_found(self, tmp_path):
        vault = _make_vault(tmp_path)
        library = BRollLibrary(entries=[_make_entry(source_path="/path/clip.mp4")])
        save_library(vault, library)

        result = remove_clip(vault, "/path/nonexistent.mp4")
        assert result is False

    def test_remove_clip_from_empty_library(self, tmp_path):
        vault = _make_vault(tmp_path)
        result = remove_clip(vault, "/path/anything.mp4")
        assert result is False


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearchLibrary:
    def _setup(self, tmp_path: Path) -> Path:
        vault = _make_vault(tmp_path)
        entries = [
            _make_entry(
                clip_ref="sewing_closeup.mp4",
                source_path="/ws/a/sewing_closeup.mp4",
                tags=["sewing", "thread", "detail"],
                topics=["sewing", "thread"],
                description="Close up of sewing machine stitching",
                content_type="b_roll",
                shot_type="closeup",
                rating=4,
                duration_seconds=8.0,
            ),
            _make_entry(
                clip_ref="machine_wide.mp4",
                source_path="/ws/a/machine_wide.mp4",
                tags=["machine", "sewing", "wide"],
                topics=["machine", "sewing"],
                description="Wide shot of sewing machine",
                content_type="b_roll",
                shot_type="medium",
                rating=2,
                duration_seconds=15.0,
            ),
            _make_entry(
                clip_ref="cutting_mat.mp4",
                source_path="/ws/b/cutting_mat.mp4",
                tags=["cutting", "mat", "fabric"],
                topics=["cutting", "fabric"],
                description="Cutting fabric on mat",
                content_type="b_roll",
                shot_type="overhead",
                rating=3,
                duration_seconds=12.0,
            ),
        ]
        library = BRollLibrary(entries=entries)
        save_library(vault, library)
        return vault

    def test_search_by_exact_tag_returns_match(self, tmp_path):
        vault = self._setup(tmp_path)
        results = search_library(vault, "sewing")
        assert len(results) >= 1
        refs = [e.clip_ref for e in results]
        assert "sewing_closeup.mp4" in refs

    def test_exact_tag_ranked_highest(self, tmp_path):
        vault = self._setup(tmp_path)
        results = search_library(vault, "sewing")
        assert len(results) >= 1
        # Both sewing clips should rank above cutting
        refs = [e.clip_ref for e in results]
        if "cutting_mat.mp4" in refs:
            sewing_idx = min(
                i for i, r in enumerate(refs) if "sewing" in r
            )
            cutting_idx = refs.index("cutting_mat.mp4")
            assert sewing_idx < cutting_idx

    def test_search_by_topic_partial_match(self, tmp_path):
        vault = self._setup(tmp_path)
        results = search_library(vault, "thread")
        assert any(e.clip_ref == "sewing_closeup.mp4" for e in results)

    def test_search_with_content_type_filter(self, tmp_path):
        vault = self._setup(tmp_path)
        results = search_library(vault, "sewing", filters={"content_type": "b_roll"})
        assert all(e.content_type == "b_roll" for e in results)

    def test_search_with_shot_type_filter(self, tmp_path):
        vault = self._setup(tmp_path)
        results = search_library(vault, "sewing", filters={"shot_type": "closeup"})
        assert all(e.shot_type == "closeup" for e in results)

    def test_search_with_min_rating_filter(self, tmp_path):
        vault = self._setup(tmp_path)
        results = search_library(vault, "sewing", filters={"min_rating": 4})
        assert all(e.rating >= 4 for e in results)

    def test_search_with_min_duration_filter(self, tmp_path):
        vault = self._setup(tmp_path)
        results = search_library(vault, "sewing", filters={"min_duration": 14.0})
        assert all(e.duration_seconds >= 14.0 for e in results)

    def test_search_with_max_duration_filter(self, tmp_path):
        vault = self._setup(tmp_path)
        results = search_library(vault, "cutting", filters={"max_duration": 10.0})
        assert all(e.duration_seconds <= 10.0 for e in results)

    def test_search_no_results_returns_empty_list(self, tmp_path):
        vault = self._setup(tmp_path)
        results = search_library(vault, "welding_torch_plasma")
        assert results == []

    def test_search_case_insensitive(self, tmp_path):
        vault = self._setup(tmp_path)
        lower = search_library(vault, "sewing")
        upper = search_library(vault, "SEWING")
        mixed = search_library(vault, "Sewing")
        assert len(lower) == len(upper) == len(mixed)

    def test_search_in_description(self, tmp_path):
        vault = self._setup(tmp_path)
        results = search_library(vault, "stitching")
        assert any(e.clip_ref == "sewing_closeup.mp4" for e in results)

    def test_search_empty_library_returns_empty(self, tmp_path):
        vault = _make_vault(tmp_path)
        results = search_library(vault, "anything")
        assert results == []

    def test_search_project_filter(self, tmp_path):
        vault = _make_vault(tmp_path)
        e1 = _make_entry(
            source_path="/p1/a.mp4",
            source_project="Alpha Project",
            tags=["sewing"],
        )
        e2 = _make_entry(
            source_path="/p2/b.mp4",
            source_project="Beta Project",
            tags=["sewing"],
        )
        save_library(vault, BRollLibrary(entries=[e1, e2]))
        results = search_library(vault, "sewing", filters={"project": "Alpha"})
        assert all("Alpha" in e.source_project for e in results)


# ---------------------------------------------------------------------------
# Tagging
# ---------------------------------------------------------------------------


class TestTagClip:
    def test_tag_clip_adds_new_entry_if_not_in_library(self, tmp_path):
        vault = _make_vault(tmp_path)
        entry = tag_clip(vault, "/new/clip.mp4", tags=["sewing"])
        library = load_library(vault)
        assert len(library.entries) == 1
        assert "sewing" in entry.tags

    def test_tag_clip_updates_existing_entry(self, tmp_path):
        vault = _make_vault(tmp_path)
        existing = _make_entry(source_path="/path/clip.mp4", tags=["old_tag"])
        save_library(vault, BRollLibrary(entries=[existing]))

        tag_clip(vault, "/path/clip.mp4", tags=["new_tag"])
        library = load_library(vault)
        assert len(library.entries) == 1
        assert "new_tag" in library.entries[0].tags

    def test_tag_clip_merges_tags_not_replaces(self, tmp_path):
        vault = _make_vault(tmp_path)
        existing = _make_entry(source_path="/path/clip.mp4", tags=["original"])
        save_library(vault, BRollLibrary(entries=[existing]))

        tag_clip(vault, "/path/clip.mp4", tags=["added"])
        library = load_library(vault)
        entry = library.entries[0]
        assert "original" in entry.tags
        assert "added" in entry.tags

    def test_tag_clip_rating_only_updates_rating(self, tmp_path):
        vault = _make_vault(tmp_path)
        existing = _make_entry(
            source_path="/path/clip.mp4",
            tags=["keep"],
            description="original desc",
        )
        save_library(vault, BRollLibrary(entries=[existing]))

        tag_clip(vault, "/path/clip.mp4", rating=5)
        library = load_library(vault)
        entry = library.entries[0]
        assert entry.rating == 5
        assert "keep" in entry.tags
        assert entry.description == "original desc"

    def test_tag_clip_description_updates(self, tmp_path):
        vault = _make_vault(tmp_path)
        existing = _make_entry(source_path="/path/clip.mp4")
        save_library(vault, BRollLibrary(entries=[existing]))

        tag_clip(vault, "/path/clip.mp4", description="New description")
        library = load_library(vault)
        assert library.entries[0].description == "New description"

    def test_tag_clip_sets_in_out_seconds(self, tmp_path):
        vault = _make_vault(tmp_path)
        existing = _make_entry(source_path="/path/clip.mp4")
        save_library(vault, BRollLibrary(entries=[existing]))

        tag_clip(vault, "/path/clip.mp4", in_seconds=2.5, out_seconds=8.0)
        library = load_library(vault)
        entry = library.entries[0]
        assert entry.in_seconds == 2.5
        assert entry.out_seconds == 8.0

    def test_tag_clip_no_update_when_defaults(self, tmp_path):
        vault = _make_vault(tmp_path)
        existing = _make_entry(source_path="/path/clip.mp4", rating=3, description="keep")
        save_library(vault, BRollLibrary(entries=[existing]))

        # Call with all defaults — nothing should change except possibly tags
        tag_clip(vault, "/path/clip.mp4")
        library = load_library(vault)
        assert library.entries[0].rating == 3
        assert library.entries[0].description == "keep"


# ---------------------------------------------------------------------------
# Obsidian notes
# ---------------------------------------------------------------------------


class TestGenerateLibraryNotes:
    def test_generates_tag_notes(self, tmp_path):
        vault = _make_vault(tmp_path)
        entries = [
            _make_entry(
                source_path="/a.mp4",
                tags=["sewing", "detail"],
                content_type="b_roll",
                shot_type="closeup",
            ),
            _make_entry(
                source_path="/b.mp4",
                tags=["cutting", "fabric"],
                content_type="b_roll",
                shot_type="medium",
            ),
        ]
        library = BRollLibrary(entries=entries)
        notes = generate_library_notes(vault, library)

        assert len(notes) >= 1  # at least tag notes + index

    def test_index_md_generated(self, tmp_path):
        vault = _make_vault(tmp_path)
        entry = _make_entry(source_path="/a.mp4", tags=["sewing"])
        library = BRollLibrary(entries=[entry])
        generate_library_notes(vault, library)

        index_path = vault / "B-Roll Library" / "Index.md"
        assert index_path.exists()

    def test_index_md_has_correct_counts(self, tmp_path):
        vault = _make_vault(tmp_path)
        entries = [
            _make_entry(source_path=f"/a{i}.mp4", source_project="Proj")
            for i in range(3)
        ]
        library = BRollLibrary(entries=entries)
        save_library(vault, library)
        generate_library_notes(vault, library)

        index_content = (vault / "B-Roll Library" / "Index.md").read_text()
        assert "total_clips: 3" in index_content

    def test_tag_note_has_correct_structure(self, tmp_path):
        vault = _make_vault(tmp_path)
        entry = _make_entry(
            clip_ref="stitch.mp4",
            source_path="/ws/stitch.mp4",
            source_project="Bag Project",
            tags=["sewing", "detail"],
            content_type="b_roll",
            shot_type="closeup",
        )
        library = BRollLibrary(entries=[entry])
        generate_library_notes(vault, library)

        # Find a shots note
        shots_dir = vault / "B-Roll Library" / "Shots"
        notes = list(shots_dir.glob("*.md"))
        assert len(notes) >= 1

        content = notes[0].read_text()
        assert "| Clip |" in content
        assert "stitch.mp4" in content

    def test_regenerating_does_not_duplicate(self, tmp_path):
        vault = _make_vault(tmp_path)
        entry = _make_entry(source_path="/a.mp4", tags=["sewing"])
        library = BRollLibrary(entries=[entry])

        generate_library_notes(vault, library)
        generate_library_notes(vault, library)

        shots_dir = vault / "B-Roll Library" / "Shots"
        notes = list(shots_dir.glob("*.md"))
        # Should only have one note per tag
        note_names = [n.name for n in notes]
        assert len(note_names) == len(set(note_names))

    def test_index_note_contains_by_project_section(self, tmp_path):
        vault = _make_vault(tmp_path)
        entry = _make_entry(
            source_path="/ws/a.mp4",
            source_project="Bag Build",
            tags=["sewing"],
        )
        library = BRollLibrary(entries=[entry])
        generate_library_notes(vault, library)

        index_content = (vault / "B-Roll Library" / "Index.md").read_text()
        assert "## By Project" in index_content
        assert "Bag Build" in index_content

    def test_empty_library_generates_index_with_zero(self, tmp_path):
        vault = _make_vault(tmp_path)
        library = BRollLibrary()
        generate_library_notes(vault, library)

        index_path = vault / "B-Roll Library" / "Index.md"
        assert index_path.exists()
        content = index_path.read_text()
        assert "total_clips: 0" in content


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestGetLibraryStats:
    def test_empty_library_returns_zeroes(self, tmp_path):
        vault = _make_vault(tmp_path)
        stats = get_library_stats(vault)
        assert stats["total_clips"] == 0
        assert stats["projects_indexed"] == []
        assert stats["top_tags"] == {}
        assert stats["content_type_breakdown"] == {}

    def test_stats_correct_counts(self, tmp_path):
        vault = _make_vault(tmp_path)
        entries = [
            _make_entry(
                source_path="/a.mp4",
                source_project="Alpha",
                tags=["sewing", "detail"],
                content_type="b_roll",
            ),
            _make_entry(
                source_path="/b.mp4",
                source_project="Beta",
                tags=["sewing", "machine"],
                content_type="b_roll",
            ),
            _make_entry(
                source_path="/c.mp4",
                source_project="Alpha",
                tags=["cutting"],
                content_type="tutorial_step",
            ),
        ]
        library = BRollLibrary(entries=entries)
        save_library(vault, library)

        stats = get_library_stats(vault)
        assert stats["total_clips"] == 3
        assert set(stats["projects_indexed"]) == {"Alpha", "Beta"}
        assert stats["top_tags"]["sewing"] == 2
        assert stats["content_type_breakdown"]["b_roll"] == 2
        assert stats["content_type_breakdown"]["tutorial_step"] == 1

    def test_stats_top_tags_sorted_by_frequency(self, tmp_path):
        vault = _make_vault(tmp_path)
        entries = []
        for i in range(5):
            entries.append(
                _make_entry(source_path=f"/a{i}.mp4", tags=["common"])
            )
        entries.append(_make_entry(source_path="/rare.mp4", tags=["rare"]))
        library = BRollLibrary(entries=entries)
        save_library(vault, library)

        stats = get_library_stats(vault)
        tags = list(stats["top_tags"].keys())
        assert tags[0] == "common"
