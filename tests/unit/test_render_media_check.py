"""The pre-render media check, and the two controls that keep it honest.

melt renders footage it cannot open as blank frames and still exits 0, so
``execute_render`` used to report ``succeeded`` for a project whose media had
been deleted. ``adapters/render/media_check`` is the precondition that closes
that; these tests pin both halves of its contract:

* REJECT -- a project referencing a file-backed producer that is not on disk
  fails the render and NAMES the file.
* ACCEPT -- a project whose media is all present still renders. Without this
  control a check that refused every render would look "fixed".

The executor-level tests fake ``subprocess.run`` rather than passing
``_command_override``: the override deliberately bypasses the media check (it
replaces the command outright), so it cannot exercise the accept path.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from workshop_video_brain.core.models.enums import JobStatus
from workshop_video_brain.core.models.project import RenderJob
from workshop_video_brain.edit_mcp.adapters.render.executor import execute_render
from workshop_video_brain.edit_mcp.adapters.render.media_check import (
    missing_media,
    missing_media_message,
)
from workshop_video_brain.edit_mcp.adapters.render.profiles import RenderProfile

EXECUTOR_MOD = "workshop_video_brain.edit_mcp.adapters.render.executor"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project(
    path: Path,
    producers: list[tuple[str, str]],
    *,
    root: str | None = None,
) -> Path:
    """Write a minimal MLT XML with (mlt_service, resource) producers."""
    root_attr = f' root="{root}"' if root else ""
    body = "\n".join(
        f'  <producer id="p{i}">\n'
        f'    <property name="mlt_service">{service}</property>\n'
        f'    <property name="resource">{resource}</property>\n'
        f"  </producer>"
        for i, (service, resource) in enumerate(producers)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<?xml version="1.0"?>\n<mlt version="7"{root_attr}>\n{body}\n</mlt>\n',
        encoding="utf-8",
    )
    return path


def _real_media(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x11\x22\x33" * 64)
    return path


@pytest.fixture()
def profile() -> RenderProfile:
    return RenderProfile(
        name="test", width=1920, height=1080, fps=25.0,
        video_codec="libx264", video_bitrate="8M",
        audio_codec="aac", audio_bitrate="192k",
    )


@pytest.fixture()
def job_for(tmp_path: Path):
    def _make(project: Path) -> RenderJob:
        return RenderJob(
            workspace_id=uuid4(),
            project_path=str(project),
            profile="test",
            output_path=str(tmp_path / "renders" / "out.mp4"),
            log_path=str(tmp_path / "renders" / "out.mp4.log"),
        )
    return _make


# ---------------------------------------------------------------------------
# missing_media -- what counts as a file that must exist
# ---------------------------------------------------------------------------

class TestMissingMedia:
    def test_absent_avformat_resource_is_reported(self, tmp_path):
        gone = tmp_path / "media" / "shot.mp4"
        proj = _project(tmp_path / "p.kdenlive", [("avformat", str(gone))])
        assert missing_media(proj) == [str(gone)]

    def test_present_avformat_resource_is_not_reported(self, tmp_path):
        here = _real_media(tmp_path / "media" / "shot.mp4")
        proj = _project(tmp_path / "p.kdenlive", [("avformat", str(here))])
        assert missing_media(proj) == []

    def test_every_absent_file_is_named_not_just_the_first(self, tmp_path):
        a = tmp_path / "media" / "a.mp4"
        b = tmp_path / "media" / "b.mov"
        proj = _project(
            tmp_path / "p.kdenlive",
            [("avformat", str(a)), ("avformat", str(b))],
        )
        assert missing_media(proj) == sorted([str(a), str(b)])

    @pytest.mark.parametrize(
        "service,resource",
        [
            # The colour producer every Kdenlive timeline carries.
            ("color", "black"),
            ("color", "#00000000"),
            ("colour", "0xff0000ff"),
            # Titles and generated text have no file at all.
            ("kdenlivetitle", ""),
            ("qtext", "Hello"),
            ("dynamictext", "#timecode#"),
            # Generators.
            ("noise", ""),
            ("tone", ""),
            ("count", ""),
            ("frei0r.ising0r", ""),
        ],
    )
    def test_synthetic_producers_are_never_required_to_exist(
        self, tmp_path, service, resource
    ):
        proj = _project(tmp_path / "p.kdenlive", [(service, resource)])
        assert missing_media(proj) == []

    @pytest.mark.parametrize(
        "resource",
        [
            "http://example.invalid/clip.mp4",
            "https://example.invalid/clip.mp4",
            "smb://server/share/clip.mp4",
            "rtsp://cam.invalid/stream",
        ],
    )
    def test_remote_resources_are_skipped(self, tmp_path, resource):
        # A network source cannot be settled by Path.exists(); refusing the
        # render on one would block a legitimate edit.
        proj = _project(tmp_path / "p.kdenlive", [("avformat", resource)])
        assert missing_media(proj) == []

    @pytest.mark.parametrize(
        "resource",
        ["/media/frames/f_%05d.png", "/media/frames/shot.all.png", "glob:/media/*.png"],
    )
    def test_image_sequences_are_skipped(self, tmp_path, resource):
        proj = _project(tmp_path / "p.kdenlive", [("qimage", resource)])
        assert missing_media(proj) == []

    def test_unknown_service_is_skipped_not_guessed(self, tmp_path):
        # The allowlist is the point: an unrecognised service must never cause
        # a render to be refused.
        proj = _project(tmp_path / "p.kdenlive", [("some.future.service", "/nope.bin")])
        assert missing_media(proj) == []

    def test_timewarp_speed_prefix_is_stripped_before_checking(self, tmp_path):
        gone = tmp_path / "media" / "shot.mp4"
        proj = _project(tmp_path / "p.kdenlive", [("timewarp", f"2.0:{gone}")])
        assert missing_media(proj) == [str(gone)]

    def test_timewarp_on_present_media_is_accepted(self, tmp_path):
        here = _real_media(tmp_path / "media" / "shot.mp4")
        proj = _project(tmp_path / "p.kdenlive", [("timewarp", f"0.5:{here}")])
        assert missing_media(proj) == []

    @pytest.mark.parametrize(
        "resource", ["2:color:black", "2:color:0xffffffff", "0.5:black"]
    )
    def test_timewarp_wrapping_a_synthetic_clip_is_skipped(self, tmp_path, resource):
        # patcher_intents builds these when the retimed clip is itself a colour
        # producer; stripping the speed leaves "color:black", not a path.
        proj = _project(tmp_path / "p.kdenlive", [("timewarp", resource)])
        assert missing_media(proj) == []

    def test_timewarp_keeps_a_windows_drive_letter(self, tmp_path):
        # Only the leading speed is stripped -- "4.0:C:/Videos/shot.mp4" must
        # still resolve against the drive-letter path, not lose it to a split.
        proj = _project(
            tmp_path / "p.kdenlive", [("timewarp", "4.000000:C:/Videos/shot.mp4")]
        )
        reported = missing_media(proj)
        assert len(reported) == 1, reported
        # The drive letter survived; only the speed was removed. (On POSIX the
        # remainder is not absolute, so it is resolved against the project dir.)
        assert reported[0].endswith("C:/Videos/shot.mp4"), reported
        assert "4.000000" not in reported[0], reported

    def test_relative_resource_resolves_against_mlt_root(self, tmp_path):
        # Kdenlive writes <mlt root="..."> and melt resolves relative resources
        # against it, so this check must too.
        here = _real_media(tmp_path / "media" / "raw" / "shot.mp4")
        proj = _project(
            tmp_path / "sub" / "p.kdenlive",
            [("avformat", "media/raw/shot.mp4")],
            root=str(tmp_path),
        )
        assert missing_media(proj) == []
        assert here.exists()

    def test_relative_resource_missing_under_root_is_reported_resolved(self, tmp_path):
        proj = _project(
            tmp_path / "sub" / "p.kdenlive",
            [("avformat", "media/raw/gone.mp4")],
            root=str(tmp_path),
        )
        assert missing_media(proj) == [str(tmp_path / "media" / "raw" / "gone.mp4")]

    def test_without_root_attribute_relative_resolves_beside_the_project(self, tmp_path):
        here = _real_media(tmp_path / "sub" / "shot.mp4")
        proj = _project(tmp_path / "sub" / "p.kdenlive", [("avformat", "shot.mp4")])
        assert missing_media(proj) == []
        assert here.exists()

    def test_chain_elements_are_checked_too(self, tmp_path):
        # Speed-ramped clips are serialized as <chain>, not <producer>.
        gone = tmp_path / "media" / "shot.mp4"
        proj = tmp_path / "p.kdenlive"
        proj.write_text(
            '<?xml version="1.0"?>\n<mlt version="7">\n'
            '  <chain id="c0">\n'
            '    <property name="mlt_service">avformat</property>\n'
            f'    <property name="resource">{gone}</property>\n'
            "  </chain>\n</mlt>\n",
            encoding="utf-8",
        )
        assert missing_media(proj) == [str(gone)]

    def test_unreadable_or_corrupt_project_reports_nothing(self, tmp_path):
        # Not this check's job: melt reports a broken project on its own, and
        # guessing here would turn a parse problem into a "missing media" lie.
        corrupt = tmp_path / "bad.kdenlive"
        corrupt.write_text("<mlt><producer", encoding="utf-8")
        assert missing_media(corrupt) == []
        assert missing_media(tmp_path / "does-not-exist.kdenlive") == []

    def test_message_names_every_missing_file(self, tmp_path):
        a, b = "/media/a.mp4", "/media/b.mov"
        msg = missing_media_message(tmp_path / "p.kdenlive", [a, b])
        assert a in msg and b in msg
        assert "p.kdenlive" in msg


# ---------------------------------------------------------------------------
# execute_render -- the reject/accept pair
# ---------------------------------------------------------------------------

class TestExecuteRenderMediaPrecondition:
    def test_reject_missing_media_does_not_report_success(
        self, tmp_path, profile, job_for
    ):
        gone = tmp_path / "media" / "shot.mp4"
        proj = _project(tmp_path / "p.kdenlive", [("avformat", str(gone))])
        job = job_for(proj)

        with patch(f"{EXECUTOR_MOD}.subprocess.run") as run:
            result = execute_render(job, profile)

        assert result.status == JobStatus.failed, result.status
        # The renderer was never started: the project could not produce a
        # correct output, so paying for the render would only hide that.
        run.assert_not_called()

    def test_reject_names_the_missing_file_to_the_caller_and_the_log(
        self, tmp_path, profile, job_for
    ):
        gone = tmp_path / "media" / "shot.mp4"
        proj = _project(tmp_path / "p.kdenlive", [("avformat", str(gone))])
        job = job_for(proj)

        with patch(f"{EXECUTOR_MOD}.subprocess.run"):
            result = execute_render(job, profile)

        assert str(gone) in result.error_message, result.error_message
        assert result.error_type == "missing_file", result.error_type
        assert str(gone) in Path(job.log_path).read_text(encoding="utf-8")

    def test_reject_leaves_no_output_masquerading_as_a_render(
        self, tmp_path, profile, job_for
    ):
        gone = tmp_path / "media" / "shot.mp4"
        proj = _project(tmp_path / "p.kdenlive", [("avformat", str(gone))])
        job = job_for(proj)

        with patch(f"{EXECUTOR_MOD}.subprocess.run"):
            execute_render(job, profile)

        assert not Path(job.output_path).exists()

    def test_accept_render_with_all_media_present_still_succeeds(
        self, tmp_path, profile, job_for
    ):
        """The control: the check must not pass by refusing everything."""
        here = _real_media(tmp_path / "media" / "shot.mp4")
        proj = _project(tmp_path / "p.kdenlive", [("avformat", str(here))])
        job = job_for(proj)

        def _fake_render(cmd, **kwargs):
            Path(job.output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(job.output_path).write_bytes(b"RENDERED")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch(f"{EXECUTOR_MOD}.subprocess.run", side_effect=_fake_render) as run:
            result = execute_render(job, profile)

        assert result.status == JobStatus.succeeded, result.status
        assert result.error_message == ""
        run.assert_called_once()
        assert Path(job.output_path).read_bytes() == b"RENDERED"

    def test_accept_project_of_only_synthetic_producers_still_renders(
        self, tmp_path, profile, job_for
    ):
        """A titles-and-colour timeline has no media on disk and is valid."""
        proj = _project(
            tmp_path / "p.kdenlive",
            [("color", "black"), ("kdenlivetitle", ""), ("qtext", "Chapter 1")],
        )
        job = job_for(proj)

        with patch(f"{EXECUTOR_MOD}.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = execute_render(job, profile)

        assert result.status == JobStatus.succeeded, result.status
        run.assert_called_once()

    def test_command_override_bypasses_the_check(self, tmp_path, profile, job_for):
        # The override replaces the render command outright, so the project is
        # not what runs and the precondition does not apply. Existing executor
        # tests rely on this; documenting it here keeps it deliberate.
        gone = tmp_path / "media" / "shot.mp4"
        proj = _project(tmp_path / "p.kdenlive", [("avformat", str(gone))])
        job = job_for(proj)

        result = execute_render(job, profile, _command_override=["true"])
        assert result.status == JobStatus.succeeded, result.status
