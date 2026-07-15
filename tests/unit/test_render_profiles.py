"""Unit tests for render profiles, jobs, and artifact registry."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# RenderProfile model
# ---------------------------------------------------------------------------

class TestRenderProfileModel:
    def test_creates_with_defaults(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import RenderProfile
        p = RenderProfile(name="test")
        assert p.width == 1920
        assert p.height == 1080
        assert p.fps == 25.0
        assert p.video_codec == "libx264"
        assert isinstance(p.extra_args, list)

    def test_creates_with_custom_values(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import RenderProfile
        p = RenderProfile(
            name="custom",
            width=1280,
            height=720,
            fps=30.0,
            video_codec="libx265",
            video_bitrate="4M",
            audio_codec="aac",
            audio_bitrate="192k",
            extra_args=["-preset", "fast"],
        )
        assert p.width == 1280
        assert p.fps == 30.0
        assert p.video_codec == "libx265"
        assert p.extra_args == ["-preset", "fast"]


class TestLoadProfile:
    def test_loads_preview_profile(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
        profile = load_profile("preview")
        assert profile.name == "preview"
        assert profile.width == 1280
        assert profile.height == 720
        assert "libx264" in profile.video_codec

    def test_loads_draft_youtube_profile(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
        profile = load_profile("draft-youtube")
        assert profile.name == "draft-youtube"
        assert profile.width == 1920
        assert profile.height == 1080

    def test_loads_final_youtube_profile(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
        profile = load_profile("final-youtube")
        assert profile.name == "final-youtube"
        assert profile.width == 1920
        assert profile.fps == 60

    def test_missing_profile_raises_file_not_found(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
        with pytest.raises(FileNotFoundError):
            load_profile("nonexistent-profile")

    def test_load_from_custom_dir(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_data = {
                "name": "test-custom",
                "width": 640,
                "height": 360,
                "fps": 24,
                "video_codec": "libx264",
                "video_bitrate": "1M",
                "audio_codec": "aac",
                "audio_bitrate": "96k",
                "extra_args": [],
            }
            profile_path = Path(tmpdir) / "test-custom.yaml"
            profile_path.write_text(yaml.dump(profile_data))
            profile = load_profile("test-custom", profiles_dir=tmpdir)
            assert profile.name == "test-custom"
            assert profile.width == 640


class TestListProfiles:
    def test_lists_built_in_profiles(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import list_profiles
        profiles = list_profiles()
        assert "preview" in profiles
        assert "draft-youtube" in profiles
        assert "final-youtube" in profiles

    def test_returns_sorted_list(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import list_profiles
        profiles = list_profiles()
        assert profiles == sorted(profiles)

    def test_empty_dir_returns_empty_list(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import list_profiles
        with tempfile.TemporaryDirectory() as tmpdir:
            result = list_profiles(profiles_dir=tmpdir)
            assert result == []

    def test_nonexistent_dir_returns_empty_list(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import list_profiles
        result = list_profiles(profiles_dir="/nonexistent/path/to/profiles")
        assert result == []

    def test_custom_dir_lists_only_yaml_files(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import list_profiles
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create yaml and non-yaml files
            (Path(tmpdir) / "my-profile.yaml").write_text(
                "name: my-profile\nwidth: 1920\nheight: 1080\n"
                "fps: 25\nvideo_codec: libx264\nvideo_bitrate: 4M\n"
                "audio_codec: aac\naudio_bitrate: 128k\nextra_args: []\n"
            )
            (Path(tmpdir) / "notes.txt").write_text("ignore me")
            result = list_profiles(profiles_dir=tmpdir)
            assert "my-profile" in result
            assert "notes" not in result


# ---------------------------------------------------------------------------
# RenderJob creation and status
# ---------------------------------------------------------------------------

class TestRenderJobCreation:
    def test_creates_render_job(self):
        from workshop_video_brain.edit_mcp.adapters.render.jobs import create_render_job
        from workshop_video_brain.core.models.enums import JobStatus
        with tempfile.TemporaryDirectory() as tmpdir:
            project_file = Path(tmpdir) / "my-project.kdenlive"
            project_file.write_text("<mlt/>")
            job = create_render_job(
                workspace_root=tmpdir,
                project_path=project_file,
                profile="preview",
                mode="standard",
            )
            assert job.profile == "preview"
            assert job.mode == "standard"
            assert job.status in (JobStatus.queued, JobStatus.queued.value)
            assert "my-project" in job.output_path
            assert job.log_path

    def test_update_job_status_running(self):
        from workshop_video_brain.edit_mcp.adapters.render.jobs import (
            create_render_job, update_job_status
        )
        from workshop_video_brain.core.models.enums import JobStatus
        with tempfile.TemporaryDirectory() as tmpdir:
            project_file = Path(tmpdir) / "p.kdenlive"
            project_file.write_text("<mlt/>")
            job = create_render_job(tmpdir, project_file, "preview")
            running = update_job_status(job, JobStatus.running)
            assert running.status in (JobStatus.running, JobStatus.running.value)
            assert running.started_at is not None
            # Original unchanged
            assert job.started_at is None

    def test_update_job_status_succeeded_sets_completed_at(self):
        from workshop_video_brain.edit_mcp.adapters.render.jobs import (
            create_render_job, update_job_status
        )
        from workshop_video_brain.core.models.enums import JobStatus
        with tempfile.TemporaryDirectory() as tmpdir:
            project_file = Path(tmpdir) / "p.kdenlive"
            project_file.write_text("<mlt/>")
            job = create_render_job(tmpdir, project_file, "preview")
            done = update_job_status(job, JobStatus.succeeded)
            assert done.completed_at is not None


# ---------------------------------------------------------------------------
# RenderArtifactRegistry
# ---------------------------------------------------------------------------

class TestRenderArtifactRegistry:
    def test_register_and_list(self):
        from workshop_video_brain.edit_mcp.pipelines.render_pipeline import (
            RenderArtifactRegistry,
        )
        from workshop_video_brain.edit_mcp.adapters.render.jobs import create_render_job
        with tempfile.TemporaryDirectory() as tmpdir:
            project_file = Path(tmpdir) / "project.kdenlive"
            project_file.write_text("<mlt/>")
            job = create_render_job(tmpdir, project_file, "preview")

            registry = RenderArtifactRegistry(tmpdir)
            registry.register_render(job)

            renders = registry.list_renders()
            assert len(renders) == 1
            assert str(renders[0].id) == str(job.id)

    def test_registry_persists_to_yaml(self):
        from workshop_video_brain.edit_mcp.pipelines.render_pipeline import (
            RenderArtifactRegistry,
        )
        from workshop_video_brain.edit_mcp.adapters.render.jobs import create_render_job
        with tempfile.TemporaryDirectory() as tmpdir:
            project_file = Path(tmpdir) / "project.kdenlive"
            project_file.write_text("<mlt/>")
            job = create_render_job(tmpdir, project_file, "draft-youtube")

            registry = RenderArtifactRegistry(tmpdir)
            registry.register_render(job)

            registry_file = Path(tmpdir) / "renders" / "render_registry.yaml"
            assert registry_file.exists()
            data = yaml.safe_load(registry_file.read_text())
            assert isinstance(data, list)
            assert len(data) == 1

    def test_register_multiple_jobs(self):
        from workshop_video_brain.edit_mcp.pipelines.render_pipeline import (
            RenderArtifactRegistry,
        )
        from workshop_video_brain.edit_mcp.adapters.render.jobs import create_render_job
        with tempfile.TemporaryDirectory() as tmpdir:
            project_file = Path(tmpdir) / "project.kdenlive"
            project_file.write_text("<mlt/>")

            job1 = create_render_job(tmpdir, project_file, "preview")
            job2 = create_render_job(tmpdir, project_file, "draft-youtube")

            registry = RenderArtifactRegistry(tmpdir)
            registry.register_render(job1)
            registry.register_render(job2)

            renders = registry.list_renders()
            assert len(renders) == 2

    def test_registering_same_job_id_updates_entry(self):
        from workshop_video_brain.edit_mcp.pipelines.render_pipeline import (
            RenderArtifactRegistry,
        )
        from workshop_video_brain.edit_mcp.adapters.render.jobs import (
            create_render_job, update_job_status
        )
        from workshop_video_brain.core.models.enums import JobStatus
        with tempfile.TemporaryDirectory() as tmpdir:
            project_file = Path(tmpdir) / "project.kdenlive"
            project_file.write_text("<mlt/>")

            job = create_render_job(tmpdir, project_file, "preview")
            registry = RenderArtifactRegistry(tmpdir)
            registry.register_render(job)

            # Update status and re-register
            done_job = update_job_status(job, JobStatus.succeeded)
            registry.register_render(done_job)

            renders = registry.list_renders()
            # Should still be 1 entry (updated, not duplicated)
            assert len(renders) == 1
            assert renders[0].status in (JobStatus.succeeded, JobStatus.succeeded.value)

    def test_convenience_functions(self):
        from workshop_video_brain.edit_mcp.pipelines.render_pipeline import (
            register_render, list_renders
        )
        from workshop_video_brain.edit_mcp.adapters.render.jobs import create_render_job
        with tempfile.TemporaryDirectory() as tmpdir:
            project_file = Path(tmpdir) / "project.kdenlive"
            project_file.write_text("<mlt/>")
            job = create_render_job(tmpdir, project_file, "preview")
            register_render(tmpdir, job)
            renders = list_renders(tmpdir)
            assert len(renders) == 1


# ---------------------------------------------------------------------------
# Alpha (transparent-background) render profiles
# ---------------------------------------------------------------------------

class TestAlphaRenderProfiles:
    """Alpha profiles added for the 'Render with Transparent Background'
    tutorial. They must load through the standard profile loader and carry the
    melt-consumer settings (mlt_image_format=rgba + alpha pix_fmt) required to
    preserve the alpha channel."""

    ALPHA_PROFILES = {
        "webm-alpha": ("libvpx-vp9", "yuva420p", "webm"),
        "prores-4444-alpha": ("prores_ks", "yuva444p10le", "mov"),
        "mov-alpha": ("qtrle", "argb", "mov"),
        "ffv1-alpha": ("ffv1", "yuva420p", "mkv"),
    }

    def test_alpha_profiles_are_listed(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import list_profiles
        available = set(list_profiles())
        for name in self.ALPHA_PROFILES:
            assert name in available, f"{name} not discoverable by list_profiles()"

    @pytest.mark.parametrize("name", list(ALPHA_PROFILES))
    def test_alpha_profile_loads_with_alpha_settings(self, name):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
        codec, pix_fmt, container = self.ALPHA_PROFILES[name]
        p = load_profile(name)
        assert p.name == name
        assert p.video_codec == codec
        assert p.pix_fmt == pix_fmt
        assert p.container == container
        assert p.mlt_image_format == "rgba"
        assert p.disable_audio is True

    def test_webm_alpha_forces_webm_container_in_melt_args(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
        p = load_profile("webm-alpha")
        assert "f=webm" in p.melt_args

    def test_melt_command_includes_alpha_flags(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
        from workshop_video_brain.edit_mcp.adapters.render.executor import (
            _build_melt_command,
        )
        p = load_profile("webm-alpha")
        cmd = _build_melt_command(Path("/tmp/x.kdenlive"), "/tmp/o.webm", p)
        assert cmd[0] == "melt"
        assert "mlt_image_format=rgba" in cmd
        assert "pix_fmt=yuva420p" in cmd
        assert "vcodec=libvpx-vp9" in cmd
        assert "an=1" in cmd
        assert "f=webm" in cmd
        assert not any(c.startswith("acodec=") for c in cmd)

    def test_melt_command_omits_alpha_flags_for_plain_profile(self):
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
        from workshop_video_brain.edit_mcp.adapters.render.executor import (
            _build_melt_command,
        )
        p = load_profile("preview")
        cmd = _build_melt_command(Path("/tmp/x.kdenlive"), "/tmp/o.mp4", p)
        assert not any(c.startswith("mlt_image_format=") for c in cmd)
        assert not any(c.startswith("pix_fmt=") for c in cmd)
        assert any(c.startswith("acodec=") for c in cmd)

    def test_alpha_profile_drives_render_job_extension(self):
        from workshop_video_brain.edit_mcp.adapters.render.jobs import create_render_job
        with tempfile.TemporaryDirectory() as tmpdir:
            job = create_render_job(
                tmpdir, Path(tmpdir) / "edit.kdenlive", "webm-alpha"
            )
            assert job.output_path.endswith(".webm")
