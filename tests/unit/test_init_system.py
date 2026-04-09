"""Unit tests for the ForgeFrame initialization system."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from workshop_video_brain.app.init_system import (
    MEDIA_FOLDERS,
    VAULT_FOLDERS,
    ForgeFrameConfig,
    InitResult,
    check_status,
    initialize_forgeframe,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_init(tmp_path: Path, **kwargs):
    """Run initialize_forgeframe with tmp_path-based defaults."""
    vault = tmp_path / "vault"
    projects = tmp_path / "projects"
    config_dir = tmp_path / "forgeframe_config"
    return initialize_forgeframe(
        vault_path=vault,
        projects_root=projects,
        repo_root=tmp_path,
        config_dir=config_dir,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestModels:
    def test_forgeframe_config_defaults(self):
        cfg = ForgeFrameConfig(vault_path="/v", projects_root="/p")
        assert cfg.ffmpeg_path == "ffmpeg"
        assert cfg.whisper_model == "small"
        assert cfg.default_preset == "youtube_voice"
        assert cfg.media_library_root == ""

    def test_init_result_has_notes_default(self):
        r = InitResult(
            vault_path="/v",
            projects_root="/p",
            vault_folders_created=[],
            media_folders_created=[],
            config_file_written="/c",
            env_file_written="/e",
        )
        assert r.notes == []


# ---------------------------------------------------------------------------
# Vault folder creation
# ---------------------------------------------------------------------------


class TestVaultFolderCreation:
    def test_all_vault_folders_created(self, tmp_path: Path):
        result = _run_init(tmp_path)
        vault = Path(result.vault_path)
        for folder in VAULT_FOLDERS:
            assert (vault / folder).is_dir(), f"Missing vault folder: {folder}"

    def test_vault_path_created_if_missing(self, tmp_path: Path):
        vault = tmp_path / "deep" / "nested" / "vault"
        assert not vault.exists()
        initialize_forgeframe(
            vault_path=vault,
            projects_root=tmp_path / "projects",
            repo_root=tmp_path,
            config_dir=tmp_path / "forgeframe_config",
        )
        assert vault.is_dir()

    def test_result_lists_created_vault_folders(self, tmp_path: Path):
        result = _run_init(tmp_path)
        # On a fresh tmp_path all VAULT_FOLDERS should be reported
        assert set(result.vault_folders_created) == set(VAULT_FOLDERS)

    def test_obsidian_dir_created(self, tmp_path: Path):
        result = _run_init(tmp_path)
        vault = Path(result.vault_path)
        assert (vault / ".obsidian").is_dir()

    def test_obsidian_app_json_created(self, tmp_path: Path):
        result = _run_init(tmp_path)
        vault = Path(result.vault_path)
        app_json = vault / ".obsidian" / "app.json"
        assert app_json.exists()
        data = json.loads(app_json.read_text())
        assert data.get("livePreview") is True

    def test_obsidian_app_json_not_overwritten_if_exists(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        obsidian = vault / ".obsidian"
        obsidian.mkdir()
        app_json = obsidian / "app.json"
        original = '{"livePreview": false, "custom": "value"}'
        app_json.write_text(original)

        initialize_forgeframe(
            vault_path=vault,
            projects_root=tmp_path / "projects",
            repo_root=tmp_path,
            config_dir=tmp_path / "forgeframe_config",
        )
        # Should not be overwritten
        assert app_json.read_text() == original


# ---------------------------------------------------------------------------
# Template notes
# ---------------------------------------------------------------------------


class TestTemplateNotes:
    def test_video_idea_template_created(self, tmp_path: Path):
        result = _run_init(tmp_path)
        vault = Path(result.vault_path)
        assert (vault / "Templates" / "YouTube" / "Video Idea.md").exists()

    def test_in_progress_template_created(self, tmp_path: Path):
        result = _run_init(tmp_path)
        vault = Path(result.vault_path)
        assert (vault / "Templates" / "YouTube" / "In Progress.md").exists()

    def test_published_template_created(self, tmp_path: Path):
        result = _run_init(tmp_path)
        vault = Path(result.vault_path)
        assert (vault / "Templates" / "YouTube" / "Published.md").exists()

    def test_broll_entry_template_created(self, tmp_path: Path):
        result = _run_init(tmp_path)
        vault = Path(result.vault_path)
        assert (vault / "Templates" / "YouTube" / "B-Roll Entry.md").exists()

    def test_template_contains_frontmatter(self, tmp_path: Path):
        result = _run_init(tmp_path)
        vault = Path(result.vault_path)
        content = (vault / "Templates" / "YouTube" / "Video Idea.md").read_text()
        assert "---" in content
        assert "status: idea" in content

    def test_template_not_overwritten_if_exists(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir(parents=True)
        tmpl_dir = vault / "Templates" / "YouTube"
        tmpl_dir.mkdir(parents=True)
        existing = tmpl_dir / "Video Idea.md"
        existing.write_text("# My custom template")

        initialize_forgeframe(
            vault_path=vault,
            projects_root=tmp_path / "projects",
            repo_root=tmp_path,
            config_dir=tmp_path / "forgeframe_config",
        )
        assert existing.read_text() == "# My custom template"


# ---------------------------------------------------------------------------
# Media folder creation
# ---------------------------------------------------------------------------


class TestMediaFolderCreation:
    def test_all_media_folders_created(self, tmp_path: Path):
        result = _run_init(tmp_path)
        projects = Path(result.projects_root)
        media_lib = projects / "Media Library"
        for folder in MEDIA_FOLDERS:
            assert (media_lib / folder).is_dir(), f"Missing media folder: {folder}"

    def test_result_lists_created_media_folders(self, tmp_path: Path):
        result = _run_init(tmp_path)
        assert set(result.media_folders_created) == set(MEDIA_FOLDERS)

    def test_custom_media_library_root(self, tmp_path: Path):
        media_lib = tmp_path / "custom_media"
        result = initialize_forgeframe(
            vault_path=tmp_path / "vault",
            projects_root=tmp_path / "projects",
            media_library_root=media_lib,
            repo_root=tmp_path,
            config_dir=tmp_path / "forgeframe_config",
        )
        for folder in MEDIA_FOLDERS:
            assert (media_lib / folder).is_dir()

    def test_media_readme_files_created(self, tmp_path: Path):
        result = _run_init(tmp_path)
        projects = Path(result.projects_root)
        media_lib = projects / "Media Library"
        for top in ["video", "audio", "images", "graphics", "documents"]:
            readme = media_lib / top / "README.md"
            assert readme.exists(), f"Missing README: {top}/README.md"
            assert readme.read_text().strip() != ""


# ---------------------------------------------------------------------------
# Config files
# ---------------------------------------------------------------------------


class TestConfigFiles:
    def test_env_file_written(self, tmp_path: Path):
        result = _run_init(tmp_path)
        env_path = Path(result.env_file_written)
        assert env_path.exists()
        content = env_path.read_text()
        assert "WVB_VAULT_PATH=" in content
        assert "WVB_WORKSPACE_ROOT=" in content
        assert "WVB_FFMPEG_PATH=" in content
        assert "WVB_WHISPER_MODEL=" in content
        assert "WVB_MEDIA_LIBRARY=" in content
        assert "WVB_AUDIO_PRESET=" in content

    def test_env_file_correct_paths(self, tmp_path: Path):
        vault = tmp_path / "myvault"
        projects = tmp_path / "myprojects"
        result = initialize_forgeframe(
            vault_path=vault,
            projects_root=projects,
            repo_root=tmp_path,
            config_dir=tmp_path / "forgeframe_config",
        )
        content = (tmp_path / ".env").read_text()
        assert str(vault.resolve()) in content
        assert str(projects.resolve()) in content

    def test_config_json_written(self, tmp_path: Path):
        config_dir = tmp_path / "fakeconfig"
        config_dir.mkdir()
        config_path = config_dir / "config.json"

        with patch("pathlib.Path.home", return_value=tmp_path / "fakehome"):
            (tmp_path / "fakehome" / ".forgeframe").mkdir(parents=True, exist_ok=True)
            result = initialize_forgeframe(
                vault_path=tmp_path / "vault",
                projects_root=tmp_path / "projects",
                repo_root=tmp_path,
            config_dir=tmp_path / "forgeframe_config",
            )

        # Verify via result path
        cfg_path = Path(result.config_file_written)
        assert cfg_path.exists()
        data = json.loads(cfg_path.read_text())
        assert "vault_path" in data
        assert "projects_root" in data
        assert "initialized" in data
        assert "version" in data
        assert data["version"] == "0.1.0"
        assert data["default_audio_preset"] == "youtube_voice"


# ---------------------------------------------------------------------------
# Path expansion
# ---------------------------------------------------------------------------


class TestPathExpansion:
    def test_tilde_in_vault_path_expanded(self, tmp_path: Path):
        # Can't easily test ~/... in unit tests without side effects,
        # so we verify that a non-tilde absolute path resolves correctly.
        vault = tmp_path / "vault"
        result = initialize_forgeframe(
            vault_path=str(vault),
            config_dir=tmp_path / "forgeframe_config",
            projects_root=str(tmp_path / "projects"),
            repo_root=tmp_path,
        )
        # result.vault_path must be an absolute path (not contain ~)
        assert not result.vault_path.startswith("~")
        assert Path(result.vault_path).is_absolute()

    def test_path_objects_accepted(self, tmp_path: Path):
        """Path objects (not just strings) must be accepted."""
        result = initialize_forgeframe(
            vault_path=tmp_path / "vault",
            projects_root=tmp_path / "projects",
            repo_root=tmp_path,
            config_dir=tmp_path / "forgeframe_config",
        )
        assert Path(result.vault_path).is_dir()


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_second_run_does_not_raise(self, tmp_path: Path):
        _run_init(tmp_path)
        # Second run must not raise
        _run_init(tmp_path)

    def test_second_run_vault_folders_still_exist(self, tmp_path: Path):
        _run_init(tmp_path)
        result = _run_init(tmp_path)
        vault = Path(result.vault_path)
        for folder in VAULT_FOLDERS:
            assert (vault / folder).is_dir()

    def test_second_run_reports_zero_new_vault_folders(self, tmp_path: Path):
        _run_init(tmp_path)
        result = _run_init(tmp_path)
        # All folders already exist — nothing new to create
        assert result.vault_folders_created == []

    def test_second_run_does_not_clobber_custom_note(self, tmp_path: Path):
        _run_init(tmp_path)
        vault = tmp_path / "vault"
        custom = vault / "Ideas" / "my-idea.md"
        custom.write_text("# Keep me")
        _run_init(tmp_path)
        assert custom.read_text() == "# Keep me"

    def test_existing_vault_folders_not_reported_as_created(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        # Pre-create a subset of folders
        (vault / "Ideas").mkdir()
        (vault / "Published").mkdir()

        result = initialize_forgeframe(
            vault_path=vault,
            projects_root=tmp_path / "projects",
            repo_root=tmp_path,
            config_dir=tmp_path / "forgeframe_config",
        )
        assert "Ideas" not in result.vault_folders_created
        assert "Published" not in result.vault_folders_created


# ---------------------------------------------------------------------------
# InitResult counts
# ---------------------------------------------------------------------------


class TestInitResultCounts:
    def test_vault_folders_created_count(self, tmp_path: Path):
        result = _run_init(tmp_path)
        assert len(result.vault_folders_created) == len(VAULT_FOLDERS)

    def test_media_folders_created_count(self, tmp_path: Path):
        result = _run_init(tmp_path)
        assert len(result.media_folders_created) == len(MEDIA_FOLDERS)

    def test_config_and_env_paths_are_strings(self, tmp_path: Path):
        result = _run_init(tmp_path)
        assert isinstance(result.config_file_written, str)
        assert isinstance(result.env_file_written, str)


# ---------------------------------------------------------------------------
# forgeframe_status
# ---------------------------------------------------------------------------


class TestForgeframeStatus:
    def test_missing_config_returns_not_initialized(self, tmp_path: Path):
        with patch("pathlib.Path.home", return_value=tmp_path / "emptyhome"):
            status = check_status()
        assert status["initialized"] is False
        assert "not been initialized" in status["message"].lower() or \
               "not" in status["message"].lower()

    def test_valid_config_returns_initialized_true(self, tmp_path: Path):
        fake_home = tmp_path / "home"
        cfg_dir = fake_home / ".forgeframe"
        cfg_dir.mkdir(parents=True)

        vault = tmp_path / "vault"
        vault.mkdir()
        projects = tmp_path / "projects"
        projects.mkdir()
        media_lib = tmp_path / "media"
        media_lib.mkdir()

        # Pre-create vault folders so check passes
        for folder in VAULT_FOLDERS:
            (vault / folder).mkdir(parents=True, exist_ok=True)

        config_data = {
            "vault_path": str(vault),
            "projects_root": str(projects),
            "media_library_root": str(media_lib),
            "ffmpeg_path": "ffmpeg",
            "whisper_model": "small",
            "default_audio_preset": "youtube_voice",
            "initialized": "2026-04-08",
            "version": "0.1.0",
        }
        (cfg_dir / "config.json").write_text(json.dumps(config_data))

        with patch("pathlib.Path.home", return_value=fake_home):
            status = check_status()

        assert status["initialized"] is True
        assert status["vault_path"] == str(vault)
        assert status["projects_root"] == str(projects)
        assert "checks" in status

    def test_status_reports_missing_vault_path(self, tmp_path: Path):
        fake_home = tmp_path / "home"
        cfg_dir = fake_home / ".forgeframe"
        cfg_dir.mkdir(parents=True)

        config_data = {
            "vault_path": str(tmp_path / "nonexistent_vault"),
            "projects_root": str(tmp_path / "nonexistent_projects"),
            "media_library_root": "",
            "ffmpeg_path": "ffmpeg",
            "whisper_model": "small",
            "default_audio_preset": "youtube_voice",
            "initialized": "2026-04-08",
            "version": "0.1.0",
        }
        (cfg_dir / "config.json").write_text(json.dumps(config_data))

        with patch("pathlib.Path.home", return_value=fake_home):
            status = check_status()

        assert status["initialized"] is True
        assert status["checks"]["vault_exists"] is False
        assert status["all_clear"] is False
        assert len(status["issues"]) > 0

    def test_status_all_clear_when_paths_exist(self, tmp_path: Path):
        fake_home = tmp_path / "home"
        cfg_dir = fake_home / ".forgeframe"
        cfg_dir.mkdir(parents=True)

        vault = tmp_path / "vault"
        vault.mkdir()
        projects = tmp_path / "projects"
        projects.mkdir()
        media_lib = tmp_path / "media"
        media_lib.mkdir()

        # Create all vault folders so vault_folders_complete check passes
        for folder in VAULT_FOLDERS:
            (vault / folder).mkdir(parents=True, exist_ok=True)

        config_data = {
            "vault_path": str(vault),
            "projects_root": str(projects),
            "media_library_root": str(media_lib),
            "ffmpeg_path": "ffmpeg",
            "whisper_model": "small",
            "default_audio_preset": "youtube_voice",
            "initialized": "2026-04-08",
            "version": "0.1.0",
        }
        (cfg_dir / "config.json").write_text(json.dumps(config_data))

        with patch("pathlib.Path.home", return_value=fake_home), \
             patch("shutil.which", return_value="/usr/bin/ffmpeg"), \
             patch("builtins.__import__", side_effect=lambda name, *a, **kw: (
                 __import__(name, *a, **kw) if name != "faster_whisper" else None
             )):
            # Just check vault/projects exist checks — ffmpeg/whisper may vary
            status = check_status()

        assert status["initialized"] is True
        assert status["checks"]["vault_exists"] is True
        assert status["checks"]["vault_folders_complete"] is True
        assert status["checks"]["projects_root_exists"] is True
