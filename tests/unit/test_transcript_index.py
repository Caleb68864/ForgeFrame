"""Unit tests for the transcript search index + shot-alignment helpers.

Pure-logic coverage (no FFmpeg / no Whisper): schema build, incremental mtime
logic, BM25 ranking, single-row edit reindex, keyword extraction, and step
parsing. Uses stdlib sqlite3 FTS5 (always available in CPython).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.pipelines import shot_alignment as sa
from workshop_video_brain.edit_mcp.pipelines import transcript_index as idx


def _write_transcript(ws: Path, stem: str, segments: list[tuple[float, float, str]]) -> Path:
    tdir = ws / "transcripts"
    tdir.mkdir(parents=True, exist_ok=True)
    data = {
        "id": "11111111-1111-1111-1111-111111111111",
        "asset_id": "22222222-2222-2222-2222-222222222222",
        "engine": "faster-whisper",
        "model": "small",
        "language": "en",
        "raw_text": " ".join(t for _, _, t in segments),
        "created_at": "2026-04-08T10:00:00",
        "segments": [
            {
                "start_seconds": s,
                "end_seconds": e,
                "text": t,
                "confidence": 0.9,
                "words": [],
            }
            for s, e, t in segments
        ],
    }
    path = tdir / f"{stem}_transcript.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    _write_transcript(
        tmp_path,
        "clip_intro",
        [
            (0.0, 3.0, "Welcome to the workshop today"),
            (3.0, 6.0, "We will glue the panel to the frame"),
        ],
    )
    _write_transcript(tmp_path, "clip_sand", [(0.0, 4.0, "Now sand the edge until it is smooth")])
    _write_transcript(tmp_path, "clip_drill", [(0.0, 4.0, "Time to drill pilot holes for the screws")])
    return tmp_path


# ---------------------------------------------------------------------------
# Schema / build
# ---------------------------------------------------------------------------


class TestSchemaAndBuild:
    def test_build_creates_db_and_tables(self, workspace: Path):
        stats = idx.build_index(workspace)
        db = Path(stats["db_path"])
        assert db.exists()
        assert db == idx.index_db_path(workspace)

        import sqlite3

        conn = sqlite3.connect(str(db))
        try:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table')"
                )
            }
        finally:
            conn.close()
        assert {"clips", "segments", "segments_fts", "tags"} <= tables

    def test_build_counts(self, workspace: Path):
        stats = idx.build_index(workspace)
        assert stats["clips_indexed"] == 3
        assert stats["segments_indexed"] == 4
        assert stats["clips_skipped"] == 0

    def test_clip_ref_from_path(self):
        assert idx.clip_ref_from_path("clip_step1_transcript.json") == "clip_step1"
        assert (
            idx.clip_ref_from_path("/a/b/clip_intro_transcript.json") == "clip_intro"
        )

    def test_build_missing_transcripts_dir_is_empty(self, tmp_path: Path):
        stats = idx.build_index(tmp_path)
        assert stats["clips_indexed"] == 0
        assert stats["segments_indexed"] == 0


# ---------------------------------------------------------------------------
# Incremental logic
# ---------------------------------------------------------------------------


class TestIncremental:
    def test_unchanged_files_skipped(self, workspace: Path):
        idx.build_index(workspace)
        stats = idx.build_index(workspace)
        assert stats["clips_indexed"] == 0
        assert stats["clips_skipped"] == 3

    def test_changed_file_reindexed(self, workspace: Path):
        idx.build_index(workspace)
        # Modify one transcript and bump its mtime.
        path = _write_transcript(
            workspace, "clip_sand", [(0.0, 4.0, "Now sand the corner very gently")]
        )
        future = os.stat(path).st_mtime + 100
        os.utime(path, (future, future))

        stats = idx.build_index(workspace)
        assert stats["clips_indexed"] == 1
        assert stats["clips_skipped"] == 2
        hits = idx.search(workspace, "corner")
        assert hits and hits[0]["clip"] == "clip_sand"
        # Old text no longer indexed.
        assert idx.search(workspace, "edge") == []

    def test_rebuild_reindexes_all(self, workspace: Path):
        idx.build_index(workspace)
        stats = idx.build_index(workspace, rebuild=True)
        assert stats["clips_indexed"] == 3
        assert stats["clips_skipped"] == 0

    def test_deleted_transcript_dropped(self, workspace: Path):
        idx.build_index(workspace)
        (workspace / "transcripts" / "clip_drill_transcript.json").unlink()
        idx.build_index(workspace)
        assert idx.search(workspace, "drill") == []


# ---------------------------------------------------------------------------
# Search + BM25 ranking
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_returns_right_clip_and_timestamp(self, workspace: Path):
        idx.build_index(workspace)
        hits = idx.search(workspace, "glue the panel")
        assert hits[0]["clip"] == "clip_intro"
        assert hits[0]["start_seconds"] == 3.0
        assert hits[0]["end_seconds"] == 6.0

    def test_exact_match_ranked_first(self, workspace: Path):
        idx.build_index(workspace)
        hits = idx.search(workspace, "drill pilot holes")
        assert hits[0]["clip"] == "clip_drill"
        # The exact-match hit outscores any weaker partial hits.
        assert all(hits[0]["score"] >= h["score"] for h in hits)

    def test_clip_filter(self, workspace: Path):
        idx.build_index(workspace)
        hits = idx.search(workspace, "the", clip="clip_sand")
        assert all(h["clip"] == "clip_sand" for h in hits)

    def test_empty_query_returns_empty(self, workspace: Path):
        idx.build_index(workspace)
        assert idx.search(workspace, "   ") == []
        assert idx.search(workspace, "!!!") == []

    def test_missing_index_returns_empty(self, tmp_path: Path):
        assert idx.search(tmp_path, "anything") == []

    def test_punctuation_query_is_safe(self, workspace: Path):
        idx.build_index(workspace)
        # Reserved-ish characters must not raise.
        hits = idx.search(workspace, 'panel AND (frame)"')
        assert isinstance(hits, list)


# ---------------------------------------------------------------------------
# Edit + reindex
# ---------------------------------------------------------------------------


class TestEdit:
    def test_edit_updates_json_source(self, workspace: Path):
        idx.build_index(workspace)
        result = idx.edit_segment(
            workspace, "clip_sand", 0, "Now sand the surface like glass"
        )
        assert result["old_text"] == "Now sand the edge until it is smooth"
        assert result["new_text"] == "Now sand the surface like glass"

        data = json.loads(
            (workspace / "transcripts" / "clip_sand_transcript.json").read_text()
        )
        assert data["segments"][0]["text"] == "Now sand the surface like glass"
        assert "glass" in data["raw_text"]

    def test_edit_reindexes_row(self, workspace: Path):
        idx.build_index(workspace)
        idx.edit_segment(workspace, "clip_sand", 0, "Now sand the surface like glass")
        # New text findable, old text gone -- single-row reindex.
        assert idx.search(workspace, "glass")[0]["clip"] == "clip_sand"
        assert idx.search(workspace, "edge") == []

    def test_edit_bad_clip_raises(self, workspace: Path):
        idx.build_index(workspace)
        with pytest.raises(FileNotFoundError):
            idx.edit_segment(workspace, "nope", 0, "x")

    def test_edit_bad_index_raises(self, workspace: Path):
        idx.build_index(workspace)
        with pytest.raises(IndexError):
            idx.edit_segment(workspace, "clip_sand", 99, "x")


# ---------------------------------------------------------------------------
# Keyword extraction + step parsing (shot alignment)
# ---------------------------------------------------------------------------


class TestKeywords:
    def test_drops_stopwords_and_short_tokens(self):
        kw = sa.extract_keywords("Glue the panel to the frame")
        assert "glue" in kw and "panel" in kw and "frame" in kw
        assert "the" not in kw and "to" not in kw

    def test_dedupes_preserving_order(self):
        kw = sa.extract_keywords("sand sand the edge edge smooth")
        assert kw == ["sand", "edge", "smooth"]

    def test_respects_max(self):
        kw = sa.extract_keywords(
            "alpha bravo charlie delta echo foxtrot golf hotel india", max_keywords=3
        )
        assert len(kw) == 3

    def test_lowercases(self):
        assert sa.extract_keywords("DRILL Pilot HOLES") == ["drill", "pilot", "holes"]


class TestStepParsing:
    def test_numbered_dot_and_paren(self, tmp_path: Path):
        f = tmp_path / "steps.md"
        f.write_text("1. Glue the panel\n2) Sand the edge\n3 - Drill holes\n")
        steps = sa.parse_steps(f)
        assert [s["index"] for s in steps] == [1, 2, 3]
        assert steps[0]["text"] == "Glue the panel"

    def test_step_prefix(self, tmp_path: Path):
        f = tmp_path / "steps.md"
        f.write_text("Step 1: Glue\nStep 2: Sand\n")
        steps = sa.parse_steps(f)
        assert steps[1]["text"] == "Sand"

    def test_fallback_to_lines(self, tmp_path: Path):
        f = tmp_path / "steps.md"
        f.write_text("# Heading\nGlue the panel\n- Sand the edge\n\n")
        steps = sa.parse_steps(f)
        assert [s["text"] for s in steps] == ["Glue the panel", "Sand the edge"]

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            sa.parse_steps(tmp_path / "nope.md")
