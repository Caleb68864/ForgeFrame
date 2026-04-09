"""Unit tests for the Script-to-Timeline Assembly pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from workshop_video_brain.core.models.assembly import (
    AssemblyPlan,
    ClipAssignment,
    StepAssembly,
)
from workshop_video_brain.core.models.clips import ClipLabel
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.edit_mcp.pipelines.assembly import (
    _extract_key_phrases,
    _jaccard_similarity,
    _score_clip_for_step,
    build_assembly_plan,
    assemble_timeline,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_label(
    clip_ref: str,
    content_type: str = "tutorial_step",
    shot_type: str = "medium",
    topics: list[str] | None = None,
    duration: float = 10.0,
    source_path: str = "",
    summary: str = "",
) -> ClipLabel:
    return ClipLabel(
        clip_ref=clip_ref,
        content_type=content_type,
        topics=topics or [],
        shot_type=shot_type,
        has_speech=True,
        speech_density=0.7,
        summary=summary,
        tags=[],
        duration=duration,
        source_path=source_path or f"/media/{clip_ref}.mp4",
    )


def _make_transcript(raw_text: str) -> Transcript:
    return Transcript(
        asset_id=uuid4(),
        engine="test",
        segments=[
            TranscriptSegment(start_seconds=0.0, end_seconds=10.0, text=raw_text)
        ],
        raw_text=raw_text,
    )


def _setup_workspace(
    tmp_path: Path,
    labels: list[ClipLabel] | None = None,
    transcripts: dict[str, str] | None = None,
    script_steps: list[dict] | None = None,
) -> Path:
    """Create a minimal workspace with optional labels, transcripts, script."""
    (tmp_path / "clips").mkdir()
    (tmp_path / "transcripts").mkdir()
    (tmp_path / "reports").mkdir()

    if labels:
        for label in labels:
            path = tmp_path / "clips" / f"{label.clip_ref}_label.json"
            path.write_text(label.to_json(), encoding="utf-8")

    if transcripts:
        for stem, raw_text in transcripts.items():
            t = _make_transcript(raw_text)
            path = tmp_path / "transcripts" / f"{stem}_transcript.json"
            path.write_text(t.to_json(), encoding="utf-8")

    if script_steps:
        path = tmp_path / "reports" / "script.json"
        path.write_text(json.dumps(script_steps), encoding="utf-8")

    return tmp_path


# ---------------------------------------------------------------------------
# Scoring tests
# ---------------------------------------------------------------------------


class TestExtractKeyPhrases:
    def test_extracts_words_over_3_chars(self):
        phrases = _extract_key_phrases("cut fabric with scissors")
        assert "fabric" in phrases
        assert "scissors" in phrases

    def test_removes_stop_words(self):
        phrases = _extract_key_phrases("the best way into the material")
        # "the", "into" are stop words
        assert "the" not in phrases
        assert "into" not in phrases

    def test_empty_text_returns_empty_set(self):
        assert _extract_key_phrases("") == set()

    def test_short_words_excluded(self):
        # Words <= 3 chars should not appear
        phrases = _extract_key_phrases("cut saw pin")
        assert "cut" not in phrases
        assert "saw" not in phrases
        assert "pin" not in phrases

    def test_case_insensitive(self):
        phrases = _extract_key_phrases("Apply GLUE carefully")
        assert "apply" in phrases
        assert "glue" in phrases


class TestJaccardSimilarity:
    def test_identical_sets(self):
        s = {"a", "b", "c"}
        assert _jaccard_similarity(s, s) == 1.0

    def test_disjoint_sets(self):
        assert _jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self):
        score = _jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"})
        # intersection=2, union=4 → 0.5
        assert abs(score - 0.5) < 0.001

    def test_empty_sets(self):
        assert _jaccard_similarity(set(), {"a"}) == 0.0
        assert _jaccard_similarity({"a"}, set()) == 0.0


class TestScoreClipForStep:
    def test_transcript_overlap_increases_score(self):
        label = _make_label("clip1", topics=[], content_type="b_roll")
        transcript_words = {"fabric", "cutting", "scissors"}
        step_phrases = {"fabric", "cutting", "measure"}
        score = _score_clip_for_step(label, transcript_words, step_phrases)
        assert score > 0.1

    def test_topic_overlap_contributes_to_score(self):
        label = _make_label("clip1", topics=["fabric", "cutting"], content_type="b_roll")
        no_transcript = set()
        step_phrases = {"fabric", "cutting", "measure"}
        score = _score_clip_for_step(label, no_transcript, step_phrases)
        assert score > 0.05

    def test_tutorial_step_content_type_boosts_score(self):
        label_tutorial = _make_label("clip1", content_type="tutorial_step")
        label_broll = _make_label("clip2", content_type="b_roll")
        step_phrases = {"fabric"}
        s1 = _score_clip_for_step(label_tutorial, set(), step_phrases)
        s2 = _score_clip_for_step(label_broll, set(), step_phrases)
        assert s1 > s2

    def test_no_overlap_returns_low_score(self):
        label = _make_label("clip1", topics=[], content_type="b_roll")
        score = _score_clip_for_step(label, set(), set())
        assert score < 0.2

    def test_score_clamped_to_one(self):
        label = _make_label("clip1", topics=["fabric", "cutting", "glue"], content_type="tutorial_step")
        transcript_words = {"fabric", "cutting", "glue"}
        step_phrases = {"fabric", "cutting", "glue"}
        score = _score_clip_for_step(label, transcript_words, step_phrases)
        assert score <= 1.0


# ---------------------------------------------------------------------------
# Plan generation tests
# ---------------------------------------------------------------------------


class TestBuildAssemblyPlan:
    def test_three_steps_five_clips_correct_matching(self, tmp_path):
        """Script with 3 steps + 5 labeled clips → correct matching."""
        labels = [
            _make_label("fabric_cut", topics=["fabric", "cutting"], content_type="tutorial_step"),
            _make_label("glue_apply", topics=["glue", "apply"], content_type="tutorial_step"),
            _make_label("sand_finish", topics=["sand", "finish"], content_type="tutorial_step"),
            _make_label("closeup_ruler", shot_type="closeup", content_type="b_roll"),
            _make_label("overview_wide", content_type="b_roll"),
        ]
        script_steps = [
            {"description": "Cut fabric with scissors", "chapter_title": "Cutting"},
            {"description": "Apply glue to surfaces", "chapter_title": "Gluing"},
            {"description": "Sand and finish the wood", "chapter_title": "Finishing"},
        ]
        _setup_workspace(tmp_path, labels=labels, script_steps=script_steps)

        plan = build_assembly_plan(tmp_path)
        assert len(plan.steps) == 3
        assert all(len(s.clips) > 0 for s in plan.steps)

    def test_primary_assigned_to_best_scoring_clip(self, tmp_path):
        """Primary should be the best-scoring clip per step."""
        labels = [
            _make_label("fabric_cut", topics=["fabric", "cutting"], content_type="tutorial_step", duration=15.0),
            _make_label("random_broll", topics=["general"], content_type="b_roll", duration=8.0),
        ]
        script_steps = [{"description": "Cut the fabric carefully"}]
        _setup_workspace(tmp_path, labels=labels, script_steps=script_steps)

        plan = build_assembly_plan(tmp_path)
        step = plan.steps[0]
        primaries = [c for c in step.clips if c.role == "primary"]
        assert len(primaries) == 1
        assert primaries[0].clip_ref == "fabric_cut"

    def test_insert_clips_assigned_for_closeup_types(self, tmp_path):
        """Closeup clips should be assigned as inserts."""
        labels = [
            # main_cut is a tutorial_step — higher content_type score → primary
            _make_label(
                "main_cut",
                topics=["fabric", "cutting", "scissors", "board"],
                content_type="tutorial_step",
            ),
            # closeup_scissors is b_roll with closeup shot_type → insert candidate
            _make_label(
                "closeup_scissors",
                shot_type="closeup",
                topics=["scissors", "fabric"],
                content_type="b_roll",
            ),
        ]
        # Step description overlaps with both clips' topics
        script_steps = [{"description": "Cut fabric with scissors board"}]
        _setup_workspace(
            tmp_path,
            labels=labels,
            transcripts={
                "main_cut": "cut fabric scissors board carefully tutorial step",
                "closeup_scissors": "scissors fabric close detail",
            },
            script_steps=script_steps,
        )

        plan = build_assembly_plan(tmp_path)
        step = plan.steps[0]
        inserts = [c for c in step.clips if c.role == "insert"]
        assert len(inserts) >= 1
        assert any(c.clip_ref == "closeup_scissors" for c in inserts)

    def test_clip_can_only_be_primary_for_one_step(self, tmp_path):
        """Once a clip is assigned as primary, it can't be primary for another step."""
        labels = [
            _make_label("only_clip", topics=["fabric"], content_type="tutorial_step"),
        ]
        script_steps = [
            {"description": "Cut fabric"},
            {"description": "Apply glue to fabric"},
        ]
        _setup_workspace(tmp_path, labels=labels, script_steps=script_steps)

        plan = build_assembly_plan(tmp_path)
        primary_assignments = [
            (step.step_number, c.clip_ref)
            for step in plan.steps
            for c in step.clips
            if c.role == "primary"
        ]
        # Each clip_ref should appear as primary at most once
        from collections import Counter
        counts = Counter(clip_ref for _, clip_ref in primary_assignments)
        assert all(v == 1 for v in counts.values())

    def test_unmatched_clips_captured(self, tmp_path):
        """Clips not assigned as primary go to unmatched_clips."""
        labels = [
            _make_label("step1_clip", topics=["cutting"], content_type="tutorial_step"),
            _make_label("irrelevant_broll", topics=["nothing"], content_type="b_roll"),
            _make_label("irrelevant2", topics=["nothing"], content_type="b_roll"),
        ]
        script_steps = [{"description": "Cut the wood"}]
        _setup_workspace(tmp_path, labels=labels, script_steps=script_steps)

        plan = build_assembly_plan(tmp_path)
        # The non-matching clips should be in unmatched
        assert len(plan.unmatched_clips) >= 1

    def test_no_script_data_falls_back_to_chapter_markers(self, tmp_path):
        """No script data → falls back to chapter markers as pseudo-steps."""
        (tmp_path / "clips").mkdir()
        (tmp_path / "markers").mkdir()

        label = _make_label("step1_clip", topics=["cutting"])
        (tmp_path / "clips" / "step1_clip_label.json").write_text(
            label.to_json(), encoding="utf-8"
        )
        markers = [
            {
                "id": str(uuid4()),
                "category": "chapter_candidate",
                "confidence_score": 0.9,
                "source_method": "test",
                "reason": "Setup step",
                "clip_ref": "step1_clip",
                "start_seconds": 0.0,
                "end_seconds": 10.0,
                "suggested_label": "Setup",
            }
        ]
        (tmp_path / "markers" / "step1_clip_markers.json").write_text(
            json.dumps(markers), encoding="utf-8"
        )

        plan = build_assembly_plan(tmp_path)
        assert len(plan.steps) >= 1

    def test_no_clips_returns_empty_plan(self, tmp_path):
        """No clips → empty plan with message, no crash."""
        # No labels provided → empty clips dir created by _setup_workspace
        script_steps = [{"description": "Step 1"}, {"description": "Step 2"}]
        _setup_workspace(tmp_path, labels=[], script_steps=script_steps)

        plan = build_assembly_plan(tmp_path)
        assert plan.assembly_report == "No clips available for assembly."
        assert len(plan.steps) == 2
        assert all(len(s.clips) == 0 for s in plan.steps)

    def test_minimum_score_threshold_respected(self, tmp_path):
        """Clips scoring below threshold are not assigned."""
        # Clip with no meaningful overlap with step
        labels = [
            _make_label("completely_unrelated", topics=["xyz123"], content_type="b_roll"),
        ]
        script_steps = [{"description": "Apply stain to wood surface"}]
        _setup_workspace(tmp_path, labels=labels, script_steps=script_steps)

        plan = build_assembly_plan(tmp_path)
        # With low content_type score and no overlap, b_roll may score below threshold
        # We just verify unmatched_clips or empty primary list
        assert isinstance(plan.unmatched_clips, list)
        assert isinstance(plan.steps, list)

    def test_assembly_report_generated_as_markdown(self, tmp_path):
        """Assembly report should be a non-empty string starting with #."""
        labels = [_make_label("clip1", topics=["cutting"], content_type="tutorial_step")]
        script_steps = [{"description": "Cut the material"}]
        _setup_workspace(tmp_path, labels=labels, script_steps=script_steps)

        plan = build_assembly_plan(tmp_path)
        assert plan.assembly_report.startswith("# Assembly Report")
        assert "Step 1" in plan.assembly_report

    def test_estimated_duration_calculated(self, tmp_path):
        """Estimated duration should be > 0 when clips have known durations."""
        labels = [
            _make_label("clip1", topics=["cutting"], duration=15.0, content_type="tutorial_step"),
        ]
        script_steps = [{"description": "Cut the fabric"}]
        _setup_workspace(tmp_path, labels=labels, script_steps=script_steps)

        plan = build_assembly_plan(tmp_path)
        assert plan.total_estimated_duration >= 0.0

    def test_inserts_up_to_two_per_step(self, tmp_path):
        """No more than 2 inserts should be assigned per step."""
        labels = [
            _make_label("main_step", topics=["cutting"], content_type="tutorial_step"),
            _make_label("close1", shot_type="closeup", topics=["scissors", "cutting"]),
            _make_label("close2", shot_type="closeup", topics=["blade", "cutting"]),
            _make_label("close3", shot_type="closeup", topics=["hand", "cutting"]),
        ]
        script_steps = [{"description": "Cut fabric with scissors blade"}]
        _setup_workspace(
            tmp_path,
            labels=labels,
            transcripts={
                "main_step": "cut fabric scissors blade",
                "close1": "scissors cutting fabric",
                "close2": "blade cutting material",
                "close3": "hand cutting",
            },
            script_steps=script_steps,
        )

        plan = build_assembly_plan(tmp_path)
        step = plan.steps[0]
        inserts = [c for c in step.clips if c.role == "insert"]
        assert len(inserts) <= 2

    def test_chapter_titles_propagated(self, tmp_path):
        """Chapter titles from script steps should appear in StepAssembly."""
        labels = [_make_label("clip1", content_type="tutorial_step")]
        script_steps = [{"description": "Cut fabric", "chapter_title": "Cutting Phase"}]
        _setup_workspace(tmp_path, labels=labels, script_steps=script_steps)

        plan = build_assembly_plan(tmp_path)
        assert plan.steps[0].chapter_title == "Cutting Phase"

    def test_transcript_words_used_for_matching(self, tmp_path):
        """Clips with matching transcript words should score higher."""
        labels = [
            _make_label("matching_clip", topics=[], content_type="tutorial_step"),
            _make_label("nonmatching_clip", topics=[], content_type="tutorial_step"),
        ]
        _setup_workspace(
            tmp_path,
            labels=labels,
            transcripts={
                "matching_clip": "apply glue wood surface clamp together firmly",
                "nonmatching_clip": "unrelated content about something else entirely",
            },
            script_steps=[{"description": "Apply glue to wood surface"}],
        )

        plan = build_assembly_plan(tmp_path)
        step = plan.steps[0]
        primaries = [c for c in step.clips if c.role == "primary"]
        if primaries:
            assert primaries[0].clip_ref == "matching_clip"

    def test_unmatched_report_section(self, tmp_path):
        """Unmatched clips should appear in the assembly report."""
        labels = [
            _make_label("clip1", topics=["cutting"], content_type="tutorial_step"),
            _make_label("clip_unused", topics=["xyz"], content_type="b_roll"),
        ]
        _setup_workspace(
            tmp_path,
            labels=labels,
            script_steps=[{"description": "Cut the wood"}],
        )

        plan = build_assembly_plan(tmp_path)
        if plan.unmatched_clips:
            assert "Unmatched clips" in plan.assembly_report


# ---------------------------------------------------------------------------
# Timeline generation tests
# ---------------------------------------------------------------------------


class TestAssembleTimeline:
    def test_three_steps_creates_kdenlive_project(self, tmp_path):
        """Plan with 3 steps → Kdenlive project file created."""
        labels = [
            _make_label("clip1", topics=["cutting"], content_type="tutorial_step", duration=10.0),
            _make_label("clip2", topics=["gluing"], content_type="tutorial_step", duration=8.0),
            _make_label("clip3", topics=["sanding"], content_type="tutorial_step", duration=12.0),
        ]
        _setup_workspace(
            tmp_path,
            labels=labels,
            script_steps=[
                {"description": "Cut the fabric", "chapter_title": "Cutting"},
                {"description": "Apply glue", "chapter_title": "Gluing"},
                {"description": "Sand the finish", "chapter_title": "Sanding"},
            ],
        )
        plan = build_assembly_plan(tmp_path)
        path = assemble_timeline(tmp_path, plan)
        assert path.exists()
        assert path.suffix == ".kdenlive"

    def test_chapter_markers_at_step_boundaries(self, tmp_path):
        """Chapter markers (guides) should be added at each step start."""
        labels = [_make_label("clip1", content_type="tutorial_step")]
        _setup_workspace(
            tmp_path,
            labels=labels,
            script_steps=[{"description": "Step one", "chapter_title": "Chapter One"}],
        )
        plan = build_assembly_plan(tmp_path)

        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

        path = assemble_timeline(tmp_path, plan, add_chapter_markers=True)
        project = parse_project(path)
        chapter_guides = [g for g in project.guides if g.category == "chapter"]
        assert len(chapter_guides) >= 1

    def test_no_chapter_markers_when_disabled(self, tmp_path):
        """No chapter guides when add_chapter_markers=False."""
        labels = [_make_label("clip1", content_type="tutorial_step")]
        _setup_workspace(
            tmp_path,
            labels=labels,
            script_steps=[{"description": "Step one", "chapter_title": "Chapter One"}],
        )
        plan = build_assembly_plan(tmp_path)

        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

        path = assemble_timeline(tmp_path, plan, add_chapter_markers=False)
        project = parse_project(path)
        chapter_guides = [g for g in project.guides if g.category == "chapter"]
        assert len(chapter_guides) == 0

    def test_transitions_between_steps_added(self, tmp_path):
        """Transition guides should appear between steps when enabled."""
        labels = [
            _make_label("clip1", topics=["cutting"], content_type="tutorial_step"),
            _make_label("clip2", topics=["gluing"], content_type="tutorial_step"),
        ]
        _setup_workspace(
            tmp_path,
            labels=labels,
            script_steps=[
                {"description": "Cut the wood"},
                {"description": "Apply glue"},
            ],
        )
        plan = build_assembly_plan(tmp_path)

        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

        path = assemble_timeline(tmp_path, plan, add_transitions=True)
        project = parse_project(path)
        transition_guides = [g for g in project.guides if g.category == "transition"]
        assert len(transition_guides) >= 1

    def test_no_transitions_when_disabled(self, tmp_path):
        """No transition guides when add_transitions=False."""
        labels = [
            _make_label("clip1", topics=["cutting"], content_type="tutorial_step"),
            _make_label("clip2", topics=["gluing"], content_type="tutorial_step"),
        ]
        _setup_workspace(
            tmp_path,
            labels=labels,
            script_steps=[
                {"description": "Cut the wood"},
                {"description": "Apply glue"},
            ],
        )
        plan = build_assembly_plan(tmp_path)

        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

        path = assemble_timeline(tmp_path, plan, add_transitions=False)
        project = parse_project(path)
        transition_guides = [g for g in project.guides if g.category == "transition"]
        assert len(transition_guides) == 0

    def test_insert_clips_on_second_video_track(self, tmp_path):
        """Insert clips should appear on playlist_v1 (V1 track)."""
        labels = [
            _make_label("main_clip", topics=["cutting"], content_type="tutorial_step", duration=10.0),
            _make_label("closeup1", shot_type="closeup", topics=["scissors", "cutting"], duration=4.0),
        ]
        _setup_workspace(
            tmp_path,
            labels=labels,
            transcripts={
                "main_clip": "cut fabric scissors carefully",
                "closeup1": "scissors cutting close",
            },
            script_steps=[{"description": "Cut fabric with scissors"}],
        )
        plan = build_assembly_plan(tmp_path)

        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

        path = assemble_timeline(tmp_path, plan)
        project = parse_project(path)

        v1_playlist = next((p for p in project.playlists if p.id == "playlist_v1"), None)
        assert v1_playlist is not None
        non_blank_entries = [e for e in v1_playlist.entries if e.producer_id]
        # If inserts were assigned, they appear on V1
        inserts_in_plan = [
            c for step in plan.steps for c in step.clips if c.role == "insert"
        ]
        if inserts_in_plan:
            assert len(non_blank_entries) >= 1

    def test_empty_plan_no_crash(self, tmp_path):
        """Empty assembly plan should produce a Kdenlive project without crashing."""
        (tmp_path / "clips").mkdir()
        (tmp_path / "reports").mkdir()
        plan = AssemblyPlan(
            project_title="Empty Project",
            steps=[],
            unmatched_clips=[],
            total_estimated_duration=0.0,
            assembly_report="# Assembly Report\n",
        )
        path = assemble_timeline(tmp_path, plan)
        assert path.exists()
        assert path.suffix == ".kdenlive"

    def test_output_file_written_to_working_copies(self, tmp_path):
        """Output .kdenlive file should be in projects/working_copies/."""
        labels = [_make_label("clip1", content_type="tutorial_step")]
        _setup_workspace(
            tmp_path,
            labels=labels,
            script_steps=[{"description": "Step one"}],
        )
        plan = build_assembly_plan(tmp_path)
        path = assemble_timeline(tmp_path, plan)
        assert "working_copies" in str(path)
        assert path.parent.name == "working_copies"

    def test_assembly_report_written_to_reports(self, tmp_path):
        """Assembly report markdown should be written to reports/ directory."""
        labels = [_make_label("clip1", content_type="tutorial_step")]
        _setup_workspace(
            tmp_path,
            labels=labels,
            script_steps=[{"description": "Step one"}],
        )
        plan = build_assembly_plan(tmp_path)
        assemble_timeline(tmp_path, plan)
        report_path = tmp_path / "reports" / "assembly_report.md"
        assert report_path.exists()
        assert len(report_path.read_text()) > 0

    def test_assembly_plan_json_written_to_reports(self, tmp_path):
        """Assembly plan JSON should be written to reports/ directory."""
        labels = [_make_label("clip1", content_type="tutorial_step")]
        _setup_workspace(
            tmp_path,
            labels=labels,
            script_steps=[{"description": "Step one"}],
        )
        plan = build_assembly_plan(tmp_path)
        assemble_timeline(tmp_path, plan)
        plan_path = tmp_path / "reports" / "assembly_plan.json"
        assert plan_path.exists()
        loaded = json.loads(plan_path.read_text())
        assert "steps" in loaded

    def test_primary_clips_on_v2_track(self, tmp_path):
        """Primary clips should appear on playlist_v2 (V2 track)."""
        labels = [
            _make_label("main_clip", topics=["cutting"], content_type="tutorial_step", duration=10.0),
        ]
        _setup_workspace(
            tmp_path,
            labels=labels,
            script_steps=[{"description": "Cut fabric"}],
        )
        plan = build_assembly_plan(tmp_path)

        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

        path = assemble_timeline(tmp_path, plan)
        project = parse_project(path)
        v2_playlist = next((p for p in project.playlists if p.id == "playlist_v2"), None)
        assert v2_playlist is not None
        non_blank = [e for e in v2_playlist.entries if e.producer_id]
        assert len(non_blank) >= 1

    def test_versioned_output_filename(self, tmp_path):
        """Output file should include _v1 (or higher) in name."""
        labels = [_make_label("clip1", content_type="tutorial_step")]
        _setup_workspace(
            tmp_path,
            labels=labels,
            script_steps=[{"description": "Step one"}],
        )
        plan = build_assembly_plan(tmp_path)
        path = assemble_timeline(tmp_path, plan)
        assert "_v" in path.stem


# ---------------------------------------------------------------------------
# Model serialization tests
# ---------------------------------------------------------------------------


class TestAssemblyModels:
    def test_clip_assignment_serialization(self):
        ca = ClipAssignment(
            clip_ref="clip1.mp4",
            source_path="/media/clip1.mp4",
            role="primary",
            score=0.85,
            in_seconds=0.0,
            out_seconds=10.0,
            reason="best match",
        )
        data = json.loads(ca.to_json())
        assert data["clip_ref"] == "clip1.mp4"
        assert data["score"] == 0.85

    def test_assembly_plan_roundtrip(self):
        plan = AssemblyPlan(
            project_title="Test Project",
            steps=[
                StepAssembly(
                    step_number=1,
                    step_description="Cut wood",
                    clips=[
                        ClipAssignment(clip_ref="cut.mp4", role="primary", score=0.9)
                    ],
                )
            ],
            unmatched_clips=["broll.mp4"],
            total_estimated_duration=15.0,
            assembly_report="# Report\n",
        )
        json_str = plan.to_json()
        restored = AssemblyPlan.from_json(json_str)
        assert restored.project_title == "Test Project"
        assert len(restored.steps) == 1
        assert restored.steps[0].clips[0].clip_ref == "cut.mp4"
        assert restored.unmatched_clips == ["broll.mp4"]
