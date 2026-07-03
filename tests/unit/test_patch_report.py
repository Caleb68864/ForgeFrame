"""Tests for PatchReport applied/skipped reporting (§1.3 silent no-op fix)."""
from __future__ import annotations

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
)
from workshop_video_brain.core.models.timeline import AddClip, AddGuide
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import (
    PatchReport,
    patch_project,
)


def _project_with_playlist(playlist_id: str = "pl_video") -> KdenliveProject:
    return KdenliveProject(
        producers=[Producer(id="prod0", resource="/tmp/a.mp4")],
        playlists=[
            Playlist(
                id=playlist_id,
                entries=[PlaylistEntry(producer_id="prod0", in_point=0, out_point=10)],
            )
        ],
    )


class TestBackwardCompat:
    def test_default_returns_project_only(self):
        proj = _project_with_playlist()
        result = patch_project(proj, [AddGuide(position_frames=5, label="x")])
        assert isinstance(result, KdenliveProject)
        assert not isinstance(result, tuple)


class TestReportApplied:
    def test_applied_intent_recorded(self):
        proj = _project_with_playlist()
        patched, report = patch_project(
            proj, [AddGuide(position_frames=5, label="hi")], with_report=True
        )
        assert isinstance(report, PatchReport)
        assert report.applied == ["AddGuide"]
        assert report.skipped == []
        assert not report.all_skipped
        assert len(patched.guides) == 1


class TestReportSkipped:
    def test_bad_playlist_ref_is_skipped(self):
        proj = _project_with_playlist()
        intent = AddClip(
            producer_id="p1",
            track_ref="does_not_exist",
            track_id="does_not_exist",
            in_point=0,
            out_point=10,
        )
        patched, report = patch_project(proj, [intent], with_report=True)
        assert report.applied == []
        assert len(report.skipped) == 1
        assert report.skipped[0]["intent"] == "AddClip"
        assert "skip" in report.skipped[0]["reason"].lower()
        assert report.all_skipped
        # Nothing was added to the (only) existing playlist.
        assert len(patched.playlists[0].entries) == 1

    def test_mixed_applied_and_skipped(self):
        proj = _project_with_playlist()
        good = AddGuide(position_frames=1, label="ok")
        bad = AddClip(
            producer_id="p1",
            track_ref="nope",
            track_id="nope",
            in_point=0,
            out_point=5,
        )
        _patched, report = patch_project(proj, [good, bad], with_report=True)
        assert report.applied == ["AddGuide"]
        assert [s["intent"] for s in report.skipped] == ["AddClip"]
        assert not report.all_skipped  # at least one applied
