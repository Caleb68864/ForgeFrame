"""End-to-end integration test.

Workflow:
  1. Create workspace with fixture media
  2. Run ingest (skips transcription if ffmpeg/whisper unavailable)
  3. Auto-generate markers (uses fake transcript if ingest couldn't transcribe)
  4. Build review timeline → .kdenlive
  5. Validate project
  6. Verify all expected artifacts exist:
     workspace.yaml, transcripts/, markers/, projects/working_copies/*.kdenlive, reports/

Parts that require FFmpeg are automatically skipped when it's absent.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from workshop_video_brain.app.config import Config
from workshop_video_brain.core.models.markers import Marker, MarkerConfig
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.validator import validate_project
from workshop_video_brain.edit_mcp.pipelines.auto_mark import generate_markers
from workshop_video_brain.edit_mcp.pipelines.ingest import run_ingest
from workshop_video_brain.edit_mcp.pipelines.review_timeline import build_review_timeline
from workshop_video_brain.workspace.manager import WorkspaceManager

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXTURE_VIDEO = Path(__file__).parent.parent / "fixtures" / "media" / "sample.mp4"
ffmpeg_available = shutil.which("ffmpeg") is not None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_transcript(transcripts_dir: Path, stem: str = "sample") -> Path:
    """Write a synthetic transcript JSON for use when ingest cannot transcribe."""
    t = Transcript(
        asset_id=uuid4(),
        engine="synthetic",
        model="test",
        language="en",
        segments=[
            TranscriptSegment(start_seconds=0.0, end_seconds=10.0,
                              text="Welcome to this tutorial. Today we build something."),
            TranscriptSegment(start_seconds=10.0, end_seconds=25.0,
                              text="First you need materials like wood and screws."),
            TranscriptSegment(start_seconds=25.0, end_seconds=40.0,
                              text="Step one: cut the pieces to the right measurement."),
            TranscriptSegment(start_seconds=40.0, end_seconds=55.0,
                              text="Be careful with the saw. Important caution: keep fingers clear."),
            TranscriptSegment(start_seconds=55.0, end_seconds=70.0,
                              text="Now assemble everything and we are done."),
        ],
        raw_text="Welcome to this tutorial. Today we build something step by step.",
    )
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out = transcripts_dir / f"{stem}_transcript.json"
    out.write_text(t.to_json(), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def workspace(tmp_path: Path):
    """Create a workspace. Copy fixture video if available."""
    ws = WorkspaceManager.create(
        title="E2E Tutorial Project",
        media_root=str(tmp_path / "raw_media"),
        workspace_root=tmp_path / "workspace",
    )
    raw_dir = Path(ws.workspace_root) / "media" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if FIXTURE_VIDEO.exists():
        shutil.copy(FIXTURE_VIDEO, raw_dir / "sample.mp4")
    return ws


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_workspace_yaml_exists(self, workspace):
        """workspace.yaml must be created during workspace creation."""
        assert (Path(workspace.workspace_root) / "workspace.yaml").exists()

    def test_workspace_folder_structure(self, workspace):
        """All standard workspace subdirectories must exist."""
        ws = Path(workspace.workspace_root)
        expected = [
            "media/raw",
            "media/proxies",
            "media/derived_audio",
            "transcripts",
            "markers",
            "projects/source",
            "projects/working_copies",
            "projects/snapshots",
            "renders",
            "reports",
            "logs",
        ]
        for folder in expected:
            assert (ws / folder).is_dir(), f"Missing folder: {folder}"

    @pytest.mark.skipif(not ffmpeg_available, reason="ffmpeg not available")
    def test_ingest_scans_fixture_video(self, workspace):
        """When FFmpeg is available, ingest should scan the fixture video."""
        if not FIXTURE_VIDEO.exists():
            pytest.skip("Fixture video not available")
        config = Config(
            vault_path=None,
            workspace_root=None,
            ffmpeg_path="ffmpeg",
            whisper_model="tiny",
            whisper_available=False,
            ffmpeg_available=True,
        )
        report = run_ingest(workspace, config)
        assert report.scanned_count >= 1

    def test_ingest_without_ffmpeg_returns_valid_report(self, workspace):
        """Even without FFmpeg the ingest pipeline must return a valid report."""
        config = Config(
            vault_path=None,
            workspace_root=None,
            ffmpeg_path="ffmpeg",
            whisper_model="tiny",
            whisper_available=False,
            ffmpeg_available=False,
        )
        report = run_ingest(workspace, config)
        assert report is not None
        assert isinstance(report.errors, list)

    def test_auto_markers_from_synthetic_transcript(self, workspace):
        """Marker generation with a synthetic transcript produces at least 1 marker."""
        transcripts_dir = Path(workspace.workspace_root) / "transcripts"
        _make_fake_transcript(transcripts_dir, "sample")
        markers_dir = Path(workspace.workspace_root) / "markers"
        markers_dir.mkdir(parents=True, exist_ok=True)

        config = MarkerConfig()
        transcript = Transcript.from_json(
            (transcripts_dir / "sample_transcript.json").read_text(encoding="utf-8")
        )
        markers = generate_markers(transcript, [], config)
        assert len(markers) >= 1

        # Write marker file
        out = markers_dir / "sample_markers.json"
        out.write_text(json.dumps([m.model_dump(mode="json") for m in markers], indent=2),
                       encoding="utf-8")
        assert out.exists()

    def test_marker_json_has_required_fields(self, workspace):
        """Each marker dict must have category, confidence_score, start/end seconds."""
        transcripts_dir = Path(workspace.workspace_root) / "transcripts"
        _make_fake_transcript(transcripts_dir, "sample")
        markers_dir = Path(workspace.workspace_root) / "markers"
        markers_dir.mkdir(parents=True, exist_ok=True)

        transcript = Transcript.from_json(
            (transcripts_dir / "sample_transcript.json").read_text(encoding="utf-8")
        )
        config = MarkerConfig()
        markers = generate_markers(transcript, [], config)
        out = markers_dir / "sample_markers.json"
        out.write_text(json.dumps([m.model_dump(mode="json") for m in markers], indent=2),
                       encoding="utf-8")

        data = json.loads(out.read_text(encoding="utf-8"))
        for m in data:
            assert "category" in m
            assert "confidence_score" in m
            assert "start_seconds" in m
            assert "end_seconds" in m

    def test_build_review_timeline_creates_kdenlive(self, workspace):
        """build_review_timeline must produce a .kdenlive file."""
        transcripts_dir = Path(workspace.workspace_root) / "transcripts"
        _make_fake_transcript(transcripts_dir, "sample")
        markers_dir = Path(workspace.workspace_root) / "markers"
        markers_dir.mkdir(parents=True, exist_ok=True)

        transcript = Transcript.from_json(
            (transcripts_dir / "sample_transcript.json").read_text(encoding="utf-8")
        )
        config = MarkerConfig()
        markers = generate_markers(transcript, [], config)

        kdenlive_path = build_review_timeline(
            markers=markers,
            assets=[],
            workspace_root=Path(workspace.workspace_root),
        )
        assert kdenlive_path.exists()
        assert kdenlive_path.suffix == ".kdenlive"

    def test_kdenlive_in_working_copies(self, workspace):
        """The .kdenlive file must be written to projects/working_copies/."""
        transcripts_dir = Path(workspace.workspace_root) / "transcripts"
        _make_fake_transcript(transcripts_dir, "sample")
        markers_dir = Path(workspace.workspace_root) / "markers"
        markers_dir.mkdir(parents=True, exist_ok=True)

        transcript = Transcript.from_json(
            (transcripts_dir / "sample_transcript.json").read_text(encoding="utf-8")
        )
        config = MarkerConfig()
        markers = generate_markers(transcript, [], config)
        kdenlive_path = build_review_timeline(markers, [], Path(workspace.workspace_root))

        expected_dir = Path(workspace.workspace_root) / "projects" / "working_copies"
        assert kdenlive_path.parent == expected_dir

    def test_validate_generated_project(self, workspace):
        """The generated .kdenlive project must pass validation (no blocking errors)."""
        transcripts_dir = Path(workspace.workspace_root) / "transcripts"
        _make_fake_transcript(transcripts_dir, "sample")
        markers_dir = Path(workspace.workspace_root) / "markers"
        markers_dir.mkdir(parents=True, exist_ok=True)

        transcript = Transcript.from_json(
            (transcripts_dir / "sample_transcript.json").read_text(encoding="utf-8")
        )
        config = MarkerConfig()
        markers = generate_markers(transcript, [], config)
        kdenlive_path = build_review_timeline(markers, [], Path(workspace.workspace_root))

        project = parse_project(kdenlive_path)
        report = validate_project(project)
        blocking = [i for i in report.items if str(i.severity) == "blocking_error"]
        assert len(blocking) == 0, f"Blocking errors: {blocking}"

    def test_review_report_written(self, workspace):
        """A review report markdown file must be written to reports/."""
        transcripts_dir = Path(workspace.workspace_root) / "transcripts"
        _make_fake_transcript(transcripts_dir, "sample")
        markers_dir = Path(workspace.workspace_root) / "markers"
        markers_dir.mkdir(parents=True, exist_ok=True)

        transcript = Transcript.from_json(
            (transcripts_dir / "sample_transcript.json").read_text(encoding="utf-8")
        )
        config = MarkerConfig()
        markers = generate_markers(transcript, [], config)
        build_review_timeline(markers, [], Path(workspace.workspace_root))

        reports_dir = Path(workspace.workspace_root) / "reports"
        report_files = list(reports_dir.glob("review_report_*.md"))
        assert len(report_files) >= 1

    def test_all_artifacts_present_after_full_pipeline(self, workspace):
        """Full pipeline: verify workspace.yaml, transcripts/, markers/, working_copies/, reports/."""
        ws = Path(workspace.workspace_root)

        # Seed transcript
        transcripts_dir = ws / "transcripts"
        _make_fake_transcript(transcripts_dir, "sample")

        # Auto-mark
        markers_dir = ws / "markers"
        markers_dir.mkdir(parents=True, exist_ok=True)
        transcript = Transcript.from_json(
            (transcripts_dir / "sample_transcript.json").read_text(encoding="utf-8")
        )
        config = MarkerConfig()
        markers = generate_markers(transcript, [], config)
        marker_out = markers_dir / "sample_markers.json"
        marker_out.write_text(
            json.dumps([m.model_dump(mode="json") for m in markers], indent=2), encoding="utf-8"
        )

        # Build timeline
        build_review_timeline(markers, [], ws)

        # Assertions — all required artifacts
        assert (ws / "workspace.yaml").exists(), "workspace.yaml missing"
        assert any(transcripts_dir.glob("*.json")), "No transcript files"
        assert any(markers_dir.glob("*.json")), "No marker files"

        working_copies = ws / "projects" / "working_copies"
        assert any(working_copies.glob("*.kdenlive")), "No .kdenlive working copy"

        reports = ws / "reports"
        assert any(reports.glob("review_report_*.md")), "No review report"
