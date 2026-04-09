from pathlib import Path

import pytest

from workshop_video_brain.workspace.folders import (
    WORKSPACE_FOLDERS,
    create_workspace_structure,
    validate_workspace_structure,
)


class TestCreateWorkspaceStructure:
    def test_creates_all_standard_folders(self, tmp_path: Path):
        root = tmp_path / "workspace"
        create_workspace_structure(root)
        for folder in WORKSPACE_FOLDERS:
            assert (root / folder).is_dir(), f"Expected folder missing: {folder}"

    def test_creates_nested_subdirectories(self, tmp_path: Path):
        root = tmp_path / "workspace"
        create_workspace_structure(root)
        # Spot-check a few deeply nested paths
        assert (root / "media" / "raw").is_dir()
        assert (root / "projects" / "source").is_dir()
        assert (root / "renders" / "final").is_dir()

    def test_idempotent_when_called_twice(self, tmp_path: Path):
        root = tmp_path / "workspace"
        create_workspace_structure(root)
        # Should not raise on second call
        create_workspace_structure(root)
        for folder in WORKSPACE_FOLDERS:
            assert (root / folder).is_dir()

    def test_root_created_if_absent(self, tmp_path: Path):
        root = tmp_path / "deep" / "nested" / "workspace"
        assert not root.exists()
        create_workspace_structure(root)
        assert root.is_dir()

    def test_accepts_string_path(self, tmp_path: Path):
        root = str(tmp_path / "workspace")
        create_workspace_structure(root)
        assert (Path(root) / "media" / "raw").is_dir()

    def test_folder_count_matches_spec(self, tmp_path: Path):
        root = tmp_path / "workspace"
        create_workspace_structure(root)
        created = [f for f in WORKSPACE_FOLDERS if (root / f).is_dir()]
        assert len(created) == len(WORKSPACE_FOLDERS)

    def test_existing_files_in_root_not_affected(self, tmp_path: Path):
        root = tmp_path / "workspace"
        root.mkdir()
        sentinel = root / "existing_file.txt"
        sentinel.write_text("keep me")
        create_workspace_structure(root)
        assert sentinel.read_text() == "keep me"


class TestValidateWorkspaceStructure:
    def test_returns_empty_list_for_complete_structure(self, tmp_path: Path):
        root = tmp_path / "workspace"
        create_workspace_structure(root)
        missing = validate_workspace_structure(root)
        assert missing == []

    def test_returns_all_missing_for_empty_root(self, tmp_path: Path):
        root = tmp_path / "empty"
        root.mkdir()
        missing = validate_workspace_structure(root)
        assert set(missing) == set(WORKSPACE_FOLDERS)

    def test_returns_specific_missing_folder(self, tmp_path: Path):
        root = tmp_path / "workspace"
        create_workspace_structure(root)
        # Remove one known folder
        import shutil
        shutil.rmtree(root / "clips")
        missing = validate_workspace_structure(root)
        assert "clips" in missing

    def test_does_not_list_extra_unexpected_dirs(self, tmp_path: Path):
        root = tmp_path / "workspace"
        create_workspace_structure(root)
        (root / "extra_custom_dir").mkdir()
        missing = validate_workspace_structure(root)
        # extra dir should not appear in missing list
        assert "extra_custom_dir" not in missing

    def test_accepts_string_path(self, tmp_path: Path):
        root = tmp_path / "workspace"
        create_workspace_structure(root)
        missing = validate_workspace_structure(str(root))
        assert missing == []

    def test_multiple_missing_folders_reported(self, tmp_path: Path):
        root = tmp_path / "workspace"
        create_workspace_structure(root)
        import shutil
        shutil.rmtree(root / "transcripts")
        shutil.rmtree(root / "markers")
        missing = validate_workspace_structure(root)
        assert "transcripts" in missing
        assert "markers" in missing

    def test_returns_list_not_set(self, tmp_path: Path):
        root = tmp_path / "workspace"
        root.mkdir()
        missing = validate_workspace_structure(root)
        assert isinstance(missing, list)


class TestWorkspaceFoldersConstant:
    def test_workspace_folders_contains_media_raw(self):
        assert "media/raw" in WORKSPACE_FOLDERS

    def test_workspace_folders_contains_projects_source(self):
        assert "projects/source" in WORKSPACE_FOLDERS

    def test_workspace_folders_contains_renders(self):
        assert any(f.startswith("renders") for f in WORKSPACE_FOLDERS)

    def test_workspace_folders_has_no_duplicates(self):
        assert len(WORKSPACE_FOLDERS) == len(set(WORKSPACE_FOLDERS))
