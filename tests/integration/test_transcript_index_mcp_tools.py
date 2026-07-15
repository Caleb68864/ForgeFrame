"""Integration proofs for the transcript-index + shot-alignment MCP tools.

Builds a synthetic workspace of three transcript JSONs (real schema) mentioning
distinct activities, then drives the *registered MCP tools* (unwrapped via
``.fn``) to prove:

- index build + segment-level search returns the right clip+timestamp per
  phrase, ranking exact matches first;
- ``transcript_edit`` corrects the JSON source and reindexes that row;
- ``shots_map_to_script`` produces a step->clips table and reports a step with
  no footage as unmatched.

No FFmpeg / Whisper needed -- the transcripts are hand-authored and thumbnails
are disabled (no media). Registration is asserted through the FastMCP server.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.server.bundles import shot_alignment as sa_bundle
from workshop_video_brain.edit_mcp.server.bundles import transcript_index as ti_bundle


def _fn(tool):
    """Unwrap a possibly ``FunctionTool``-wrapped MCP tool to its function."""
    return getattr(tool, "fn", tool)


transcript_index_build = _fn(ti_bundle.transcript_index_build)
transcript_search = _fn(ti_bundle.transcript_search)
transcript_edit = _fn(ti_bundle.transcript_edit)
shots_map_to_script = _fn(sa_bundle.shots_map_to_script)


def _write_transcript(ws: Path, stem: str, segments: list[tuple[float, float, str]]) -> None:
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
            {"start_seconds": s, "end_seconds": e, "text": t, "confidence": 0.9, "words": []}
            for s, e, t in segments
        ],
    }
    (tdir / f"{stem}_transcript.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    _write_transcript(
        tmp_path,
        "clip_glue",
        [
            (0.0, 3.0, "Alright let us begin the assembly"),
            (3.0, 7.5, "Now we glue the panel onto the base"),
        ],
    )
    _write_transcript(
        tmp_path,
        "clip_sand",
        [(0.0, 5.0, "Here I sand the edge until it feels perfectly smooth")],
    )
    _write_transcript(
        tmp_path,
        "clip_drill",
        [(0.0, 6.0, "Next we drill pilot holes before driving the screws")],
    )
    return tmp_path


class TestIndexAndSearch:
    def test_build_then_search_each_phrase(self, workspace: Path):
        built = transcript_index_build(str(workspace))
        assert built["status"] == "success", built
        assert built["data"]["clips_indexed"] == 3
        assert built["data"]["segments_indexed"] == 4

        cases = {
            "glue the panel": ("clip_glue", 3.0),
            "sand the edge": ("clip_sand", 0.0),
            "drill pilot holes": ("clip_drill", 0.0),
        }
        for query, (clip, start) in cases.items():
            res = transcript_search(str(workspace), query, limit=3)
            assert res["status"] == "success", res
            hits = res["data"]["hits"]
            assert hits, f"no hits for {query!r}"
            assert hits[0]["clip"] == clip, (query, hits)
            assert hits[0]["start_seconds"] == start
            # Exact match ranks first.
            assert all(hits[0]["score"] >= h["score"] for h in hits)

    def test_search_autobuilds_index(self, workspace: Path):
        # No explicit build call -- search must build the index on demand.
        res = transcript_search(str(workspace), "drill pilot holes")
        assert res["status"] == "success", res
        assert res["data"]["hits"][0]["clip"] == "clip_drill"


class TestEditReindex:
    def test_edit_corrects_source_and_reindexes(self, workspace: Path):
        transcript_index_build(str(workspace))
        res = transcript_edit(
            str(workspace), "clip_sand", 0, "Here I polish the surface until it shines like glass"
        )
        assert res["status"] == "success", res
        assert res["data"]["old_text"].startswith("Here I sand the edge")

        # Source JSON updated.
        data = json.loads(
            (workspace / "transcripts" / "clip_sand_transcript.json").read_text()
        )
        assert "glass" in data["segments"][0]["text"]

        # New term findable, old term gone -- proves single-row reindex.
        glass = transcript_search(str(workspace), "glass")
        assert glass["data"]["hits"][0]["clip"] == "clip_sand"
        gone = transcript_search(str(workspace), "sand")
        assert gone["data"]["hits"] == []


class TestShotMapping:
    def test_step_with_no_footage_reported_unmatched(self, workspace: Path):
        steps = workspace / "build_steps.md"
        steps.write_text(
            "1. Glue the panel onto the base\n"
            "2. Sand the edge until smooth\n"
            "3. Drill pilot holes for the screws\n"
            "4. Apply the specialty holographic lacquer coating\n"
        )
        res = shots_map_to_script(
            str(workspace), str(steps), top_k=3, include_thumbnails=False
        )
        assert res["status"] == "success", res
        data = res["data"]

        assert data["step_count"] == 4
        assert data["matched_count"] == 3

        table = {r["step_index"]: r for r in data["table"]}
        assert table[1]["matched"] and table[1]["candidates"][0]["clip"] == "clip_glue"
        assert table[2]["candidates"][0]["clip"] == "clip_sand"
        assert table[3]["candidates"][0]["clip"] == "clip_drill"

        # Step 4 has no matching footage -> reported unmatched.
        assert table[4]["matched"] is False
        unmatched_idx = [u["step_index"] for u in data["unmatched_steps"]]
        assert unmatched_idx == [4]

        # Reports written.
        assert Path(data["json_path"]).exists()
        md = Path(data["md_path"]).read_text()
        assert "NO FOOTAGE" in md
        assert "Coverage Gaps" in md

    def test_steps_file_resolved_workspace_relative(self, workspace: Path):
        (workspace / "build_steps.md").write_text("1. Glue the panel\n")
        res = shots_map_to_script(
            str(workspace), "build_steps.md", include_thumbnails=False
        )
        assert res["status"] == "success", res
        assert res["data"]["step_count"] == 1

    def test_missing_steps_file_errors(self, workspace: Path):
        res = shots_map_to_script(str(workspace), "nope.md")
        assert res["status"] == "error"


class TestRegistration:
    def test_tools_registered_with_server(self):
        import asyncio
        import inspect

        from workshop_video_brain import server

        getter = getattr(server.mcp, "list_tools", None) or server.mcp.get_tools
        result = getter()
        if inspect.iscoroutine(result):
            result = asyncio.run(result)
        names = (
            list(result.keys())
            if isinstance(result, dict)
            else [t.name for t in result]
        )
        for tool in (
            "transcript_index_build",
            "transcript_search",
            "transcript_edit",
            "shots_map_to_script",
        ):
            assert tool in names, f"{tool} not registered"
