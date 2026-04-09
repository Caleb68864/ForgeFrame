"""Tests for project archive pipeline."""
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path
import pytest
import yaml

from workshop_video_brain.core.models.archive import ArchiveManifest
from workshop_video_brain.edit_mcp.pipelines.archive import create_archive


@pytest.fixture
def workspace(tmp_path):
    """Create a minimal workspace directory tree."""
    ws = tmp_path / "my-project"
    ws.mkdir()

    # workspace.yaml
    (ws / "workspace.yaml").write_text(yaml.dump({"title": "Test Project"}))

    # Kdenlive project file
    (ws / "project.kdenlive").write_text("<mlt></mlt>")

    # Reports
    (ws / "reports").mkdir()
    (ws / "reports" / "qc.json").write_text("{}")

    # Transcripts
    (ws / "transcripts").mkdir()
    (ws / "transcripts" / "intro.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")

    # Renders
    (ws / "renders").mkdir()
    (ws / "renders" / "final.mp4").write_bytes(b"\x00" * 1024)

    # Raw media
    (ws / "media").mkdir()
    (ws / "media" / "raw").mkdir()
    (ws / "media" / "raw" / "clip01.mp4").write_bytes(b"\x00" * 4096)

    return ws


class TestCreateArchiveTarGz:
    def test_basic_archive(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output, include_renders=True, include_raw=False)

        assert isinstance(manifest, ArchiveManifest)
        assert manifest.workspace_title == "Test Project"
        assert manifest.includes_renders is True
        assert manifest.includes_raw_media is False
        assert manifest.files_included > 0
        assert Path(manifest.archive_path).exists()
        assert manifest.archive_path.endswith(".tar.gz")

    def test_archive_contains_expected_files(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output, include_renders=True, include_raw=False)

        with tarfile.open(manifest.archive_path, "r:gz") as tar:
            names = tar.getnames()
        # Should contain kdenlive, workspace.yaml, reports, transcripts, renders
        assert any("project.kdenlive" in n for n in names)
        assert any("workspace.yaml" in n for n in names)
        assert any("qc.json" in n for n in names)
        assert any("intro.srt" in n for n in names)
        assert any("final.mp4" in n for n in names)
        # Should NOT contain raw media
        assert not any("clip01.mp4" in n for n in names)

    def test_archive_without_renders(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output, include_renders=False, include_raw=False)

        with tarfile.open(manifest.archive_path, "r:gz") as tar:
            names = tar.getnames()
        assert not any("final.mp4" in n for n in names)
        assert manifest.includes_renders is False

    def test_archive_with_raw(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output, include_renders=False, include_raw=True)

        with tarfile.open(manifest.archive_path, "r:gz") as tar:
            names = tar.getnames()
        assert any("clip01.mp4" in n for n in names)
        assert manifest.includes_raw_media is True


class TestCreateArchiveZip:
    def test_zip_format(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output, format="zip")

        assert manifest.archive_path.endswith(".zip")
        assert Path(manifest.archive_path).exists()

        with zipfile.ZipFile(manifest.archive_path, "r") as zf:
            names = zf.namelist()
        assert any("project.kdenlive" in n for n in names)

    def test_invalid_format_raises(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        with pytest.raises(ValueError, match="format"):
            create_archive(workspace, output, format="rar")


class TestManifestAccuracy:
    def test_file_count(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output, include_renders=True, include_raw=True)
        # workspace.yaml + project.kdenlive + qc.json + intro.srt + final.mp4 + clip01.mp4 = 6
        assert manifest.files_included == 6

    def test_total_size(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output, include_renders=True, include_raw=True)
        assert manifest.total_size_bytes > 0

    def test_created_at_is_iso(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output)
        # Should parse as ISO 8601
        datetime.fromisoformat(manifest.created_at)

    def test_archive_name_includes_title(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output)
        assert "Test_Project" in Path(manifest.archive_path).name or "Test-Project" in Path(manifest.archive_path).name


class TestEmptyWorkspace:
    def test_minimal_workspace(self, tmp_path):
        ws = tmp_path / "empty-ws"
        ws.mkdir()
        (ws / "workspace.yaml").write_text(yaml.dump({"title": "Empty"}))
        output = tmp_path / "output"
        output.mkdir()

        manifest = create_archive(ws, output)
        assert manifest.files_included == 1  # just workspace.yaml
        assert manifest.workspace_title == "Empty"
