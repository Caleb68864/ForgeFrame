"""Hardening Pass 3a -- composed-workflow failure propagation.

Passes 1-2 hardened *individual* tools (structured errors, no tracebacks, no
false successes, no leaked snapshots). Real usage, though, *chains* tools:
ingest -> place -> effect -> render -> publish. This suite asks the question those
passes could not: when a fault is injected **mid-pipeline**, does every
*downstream* tool surface the UPSTREAM cause comprehensibly, or does it cascade
into a baffling ``KeyError``-grade message or silently half-work?

Each scenario runs steps ``1..k`` for real, injects one fault, then drives steps
``k+1..n`` and asserts each downstream tool:

* returns the right ``error_type`` (or a job status that is not "success"),
* names the missing/corrupt upstream artifact in its ``message``,
* points at the failed step via its ``suggestion``,
* and never half-mutates the project on the way to discovering the fault.

The money test is scenario 2: a project corrupted mid-workflow is *recovered*
via ``snapshot_restore`` and the next tool then SUCCEEDS end to end.

ffmpeg/melt-gated where a real media/render is required; the pure
error-propagation assertions run everywhere.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server.errors import VALID_ERROR_TYPES
import workshop_video_brain.edit_mcp.server.tools as _tools
from workshop_video_brain.edit_mcp.server.bundles import (
    ai_mask as _ai_mask_bundle,
    clip_place as _clip_place_bundle,
    multicam as _multicam_bundle,
    proxy_wiring as _proxy_bundle,
    shot_alignment as _shot_align_bundle,
    thumbnail_sheet as _thumb_bundle,
    transcript_index as _tindex_bundle,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project


# ---------------------------------------------------------------------------
# Tool handles
# ---------------------------------------------------------------------------
def _fn(obj):
    """Unwrap a FastMCP tool object to its raw callable (identity for plain fns)."""
    return getattr(obj, "fn", obj)


# package tools (already raw callables)
workspace_create = _tools.workspace_create
clip_insert = _tools.clip_insert
transcript_generate = _tools.transcript_generate
render_preview = _tools.render_preview
render_status = _tools.render_status
snapshot_restore = _tools.snapshot_restore
snapshot_list = _tools.snapshot_list
effect_add = _tools.effect_add
composite_set = _tools.composite_set
effect_color_grade = _tools.effect_color_grade

# bundle tools (FastMCP-wrapped)
clip_place = _fn(_clip_place_bundle.clip_place)
media_thumbnail_sheet = _fn(_thumb_bundle.media_thumbnail_sheet)
proxy_attach = _fn(_proxy_bundle.proxy_attach)
proxy_status = _fn(_proxy_bundle.proxy_status)
transcript_index_build = _fn(_tindex_bundle.transcript_index_build)
transcript_search = _fn(_tindex_bundle.transcript_search)
shots_map_to_script = _fn(_shot_align_bundle.shots_map_to_script)
multicam_assemble = _fn(_multicam_bundle.multicam_assemble)
mask_generate_and_apply = _fn(_ai_mask_bundle.mask_generate_and_apply)


FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

_FFMPEG = shutil.which("ffmpeg")
_FFPROBE = shutil.which("ffprobe")
_MELT = shutil.which("melt")

_GENERIC = {"", "an error occurred", "try again", "unknown error", "error", "failed"}


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------
def assert_loud_error(result: dict, *, expected_type=None, names=None) -> None:
    """A downstream failure must be structured, loud, and name the upstream cause."""
    assert isinstance(result, dict), result
    assert result.get("status") == "error", result
    assert result.get("message"), result
    et = result.get("error_type")
    assert et in VALID_ERROR_TYPES, f"bad/absent error_type: {result}"
    if expected_type is not None:
        assert et == expected_type, result
    sug = result.get("suggestion", "")
    assert isinstance(sug, str) and len(sug.strip()) > 12, f"weak suggestion: {result}"
    assert sug.strip().lower() not in _GENERIC, result
    blob = " ".join(str(v) for v in result.values())
    assert "Traceback" not in blob and 'File "' not in blob, result
    if names is not None:
        # The failure must NAME the offending upstream artifact somewhere in the
        # payload (message or an echoed path/given field), not fail generically.
        assert names in blob, f"error does not name {names!r}: {result}"


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _snap_dirs(ws: Path):
    d = ws / "projects" / "snapshots"
    return sorted(p.name for p in d.glob("*")) if d.exists() else []


def _ffmpeg_testsrc(path: Path, duration: float = 1.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"testsrc=size=320x240:rate=25:duration={duration}",
            "-pix_fmt", "yuv420p", str(path),
        ],
        check=True, capture_output=True,
    )


# ---------------------------------------------------------------------------
# Workspace factory
# ---------------------------------------------------------------------------
def _make_ws(tmp_path: Path, *, at_root=True, at_wc=True) -> Path:
    media_root = tmp_path / "media_src"
    media_root.mkdir(parents=True, exist_ok=True)
    created = workspace_create(title="Pass3 Workflow", media_root=str(media_root))
    assert created["status"] == "success", created
    ws = Path(created["data"]["workspace_root"])
    if at_root:
        shutil.copy(FIXTURE, ws / "proj.kdenlive")
    if at_wc:
        wc = ws / "projects" / "working_copies"
        wc.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIXTURE, wc / "proj_v1.kdenlive")
    return ws


@pytest.fixture()
def ws(tmp_path):
    return _make_ws(tmp_path)


# ===========================================================================
# Scenario 1 -- media moved/deleted after ingest
# ===========================================================================
class TestMediaMovedAfterIngest:
    """A media file present at edit time is deleted; every downstream tool that
    touches it must NAME the missing path, not fail generically."""

    def test_clip_insert_names_missing_media(self, ws):
        media = ws / "media" / "raw" / "shot.mp4"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"\x00\x11\x22\x33" * 64)  # a stand-in media file
        media.unlink()  # ...moved/deleted after "ingest"
        out = clip_insert(str(ws), str(media))
        assert_loud_error(out, expected_type="missing_file", names=str(media))

    def test_thumbnail_sheet_names_missing_media(self, ws):
        media = ws / "media" / "raw" / "shot.mp4"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"\x00\x11\x22\x33" * 64)
        media.unlink()
        out = media_thumbnail_sheet(str(ws), source=str(media))
        assert_loud_error(out, expected_type="missing_file", names=str(media))

    def test_clip_place_names_missing_media(self, ws):
        # clip_place used to either silently place a broken clip (out_seconds
        # given) or bail with a confusing "duration unknown" message. It must now
        # name the missing media (propagation fix).
        media = ws / "media" / "raw" / "shot.mp4"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"\x00" * 128)
        before = _sha(ws / "proj.kdenlive")
        snaps_before = _snap_dirs(ws)
        media.unlink()
        out = clip_place(str(ws), "proj.kdenlive", str(media), track=0,
                         at_seconds=0.0, out_seconds=1.0)
        assert_loud_error(out, expected_type="missing_file", names=str(media))
        # Half-mutation guard: project byte-identical, no snapshot leaked.
        assert _sha(ws / "proj.kdenlive") == before
        assert _snap_dirs(ws) == snaps_before

    def test_transcript_generate_does_not_fabricate_for_missing_media(self, ws):
        # transcript_generate is workspace-scoped (it ingests media/raw); a
        # deleted source is simply not scanned. Documented limitation: it cannot
        # "name" a specific missing file because it takes no media argument -- but
        # it must never fabricate a transcript for an absent asset.
        media = ws / "media" / "raw" / "shot.mp4"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"\x00" * 128)
        media.unlink()
        out = transcript_generate(str(ws))
        assert out["status"] in ("success", "error"), out
        # No transcript JSON was invented for the deleted stem.
        tdir = ws / "transcripts"
        stray = list(tdir.glob("shot*_transcript.json")) if tdir.exists() else []
        assert stray == [], f"fabricated transcript for missing media: {stray}"

    @pytest.mark.skipif(not (_FFMPEG and _MELT), reason="ffmpeg+melt required")
    def test_render_after_media_deleted_does_not_report_success(self, tmp_path):
        # Full chain: real testsrc -> clip_place into a project -> delete the
        # media -> render. The render job must NOT come back "succeeded" against
        # footage that no longer exists. Driven through execute_render with a
        # bounded timeout so a stalled melt cannot hang the suite.
        from workshop_video_brain.edit_mcp.adapters.render.executor import execute_render
        from workshop_video_brain.edit_mcp.adapters.render.jobs import create_render_job
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
        from workshop_video_brain.core.models.enums import JobStatus

        ws = _make_ws(tmp_path, at_root=True, at_wc=False)
        media = ws / "media" / "raw" / "shot.mp4"
        _ffmpeg_testsrc(media)
        placed = clip_place(str(ws), "proj.kdenlive", str(media), track=0,
                            at_seconds=0.0, out_seconds=1.0)
        assert placed["status"] == "success", placed
        proj = ws / "proj.kdenlive"
        media.unlink()  # media vanishes after it was wired into the timeline

        job = create_render_job(ws, proj, profile="preview", mode="proxy")
        result = execute_render(job, load_profile("preview"), timeout_seconds=60)
        # melt against missing footage must not report success, and must leave no
        # partial output masquerading as a finished render.
        assert result.status != JobStatus.succeeded, result.status
        assert not Path(job.output_path).exists(), "partial output left behind"


# ===========================================================================
# Scenario 2 -- project corrupted mid-workflow  (THE MONEY TEST)
# ===========================================================================
class TestProjectCorruptedMidWorkflow:
    def _build_two_good_states(self, ws, media):
        """clip_place twice; return the snapshot id capturing the GOOD state that
        already contains the first placement (so restoring it proves real work is
        recovered, not just 'a parseable file')."""
        r1 = clip_place(str(ws), "proj.kdenlive", str(media), track=0,
                        at_seconds=0.0, out_seconds=1.0)
        assert r1["status"] == "success", r1
        # G1 now on disk (track 0 has a clip). The second place snapshots G1.
        r2 = clip_place(str(ws), "proj.kdenlive", str(media), track=1,
                        at_seconds=0.0, out_seconds=1.0)
        assert r2["status"] == "success", r2
        good_snapshot = r2["data"]["snapshot_id"]
        assert good_snapshot
        return good_snapshot

    def test_corrupt_project_is_named_by_every_downstream_tool(self, ws):
        media = ws / "media" / "raw" / "b.mp4"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"\x00" * 128)
        self._build_two_good_states(ws, media)

        proj = ws / "proj.kdenlive"
        # Corrupt: truncate to a torn-open XML fragment.
        proj.write_bytes(b'<mlt><playlist id="playlist0"><entry pro')

        # Every parse-based downstream tool must return corrupt_project naming it
        # -- spanning package tools (effect_add, composite_set, effect_color_grade)
        # AND bundle tools (clip_place), which previously mis-reported a corrupt
        # project as a generic operation_failed (propagation fix).
        for label, call in [
            ("effect_add", lambda: effect_add(str(ws), "proj.kdenlive", 0, 0, "avfilter.gblur")),
            ("composite_set", lambda: composite_set(str(ws), "proj.kdenlive", 0, 1, 0, 100)),
            ("effect_color_grade", lambda: effect_color_grade(str(ws), "proj.kdenlive", 0, 0, exposure=0.5)),
            ("clip_place", lambda: clip_place(str(ws), "proj.kdenlive", "producer0", 0, 0.0, out_seconds=1.0)),
        ]:
            out = call()
            assert out["status"] == "error", (label, out)
            assert_loud_error(out, expected_type="corrupt_project", names="proj.kdenlive")

    def test_mutating_color_tools_leak_no_snapshot_on_corrupt_project(self, ws):
        # Several color tools used to snapshot BEFORE parsing, leaking a snapshot
        # of the (untouched) corrupt file AND mis-reporting operation_failed.
        # They must now fail with corrupt_project and leave zero side effects.
        proj = ws / "proj.kdenlive"
        proj.write_bytes(b'<mlt><playlist id="p"><entry pro')
        before = proj.read_bytes()
        lut = ws / "grade.cube"
        lut.write_text("LUT_3D_SIZE 2\n" + "\n".join(["0 0 0"] * 8) + "\n", encoding="utf-8")
        for label, call in [
            ("color_apply_lut", lambda: _tools.color_apply_lut(str(ws), "proj.kdenlive", 2, 0, str(lut))),
            ("effect_color_wash", lambda: _tools.effect_color_wash(str(ws), "proj.kdenlive", 2, 0)),
            ("effect_scifi_greenscreen", lambda: _tools.effect_scifi_greenscreen(str(ws), "proj.kdenlive", 2, 0)),
        ]:
            snaps_before = _snap_dirs(ws)
            out = call()
            assert out["status"] == "error", (label, out)
            assert_loud_error(out, expected_type="corrupt_project")
            assert _snap_dirs(ws) == snaps_before, f"{label} leaked a snapshot"
            assert proj.read_bytes() == before, f"{label} half-wrote the corrupt file"

    def test_snapshot_restore_recovers_and_next_tool_succeeds(self, ws):
        """THE money test: corrupt -> snapshot_restore -> next tool SUCCEEDS, and
        the restored project retains the real placement work (end-to-end)."""
        media = ws / "media" / "raw" / "b.mp4"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"\x00" * 128)
        good_snapshot = self._build_two_good_states(ws, media)

        proj = ws / "proj.kdenlive"
        proj.write_bytes(b"\x00\x01\x02 not a project at all")

        # Downstream tool confirms corruption (loud, named).
        broken = effect_add(str(ws), "proj.kdenlive", 0, 0, "avfilter.gblur")
        assert_loud_error(broken, expected_type="corrupt_project", names="proj.kdenlive")
        # And it did not half-write over the corrupt file.
        assert proj.read_bytes() == b"\x00\x01\x02 not a project at all"

        # RECOVERY: restore the good snapshot.
        restored = snapshot_restore(str(ws), good_snapshot)
        assert restored["status"] == "success", restored

        # The restored project parses AND retains the first placement (track 0).
        project = parse_project(proj)
        track0 = project.playlists[0]
        assert any(e.producer_id for e in track0.entries), (
            "restored project lost the placed clip on track 0"
        )

        # NEXT TOOL SUCCEEDS on the recovered project -- the whole point.
        out = effect_add(str(ws), "proj.kdenlive", 0, 0, "avfilter.gblur")
        assert out["status"] == "success", out
        # ...and the result is itself a valid, re-parseable project.
        assert parse_project(proj) is not None


# ===========================================================================
# Scenario 3 -- interrupted render
# ===========================================================================
class TestInterruptedRender:
    """A render killed by timeout must report failure, leave no partial output,
    and a subsequent re-render must succeed."""

    def _job(self, ws: Path):
        from workshop_video_brain.edit_mcp.adapters.render.jobs import create_render_job
        proj = ws / "proj.kdenlive"
        return create_render_job(ws, proj, profile="preview", mode="proxy")

    def test_timeout_reports_failed_and_removes_partial_output(self, ws):
        from workshop_video_brain.edit_mcp.adapters.render.executor import execute_render
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
        from workshop_video_brain.core.models.enums import JobStatus

        job = self._job(ws)
        out_file = Path(job.output_path)
        profile = load_profile("preview")
        # A command that writes a *partial* file then hangs past the timeout,
        # standing in for melt being killed mid-encode.
        cmd = ["sh", "-c", f"printf 'PARTIAL' > '{out_file}'; sleep 30"]

        result = execute_render(job, profile, timeout_seconds=1, _command_override=cmd)

        assert result.status == JobStatus.failed, result.status
        assert not out_file.exists(), (
            "interrupted render left a partial output file behind"
        )

    def test_failed_render_leaves_preexisting_output_untouched(self, ws):
        # Safety: cleanup must only remove a file THIS run created, never a
        # pre-existing artifact that happened to share the path.
        from workshop_video_brain.edit_mcp.adapters.render.executor import execute_render
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile

        job = self._job(ws)
        out_file = Path(job.output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(b"PRIOR-GOOD-RENDER")
        profile = load_profile("preview")
        cmd = ["sh", "-c", "false"]  # fails immediately, creates nothing

        execute_render(job, profile, timeout_seconds=5, _command_override=cmd)
        assert out_file.exists() and out_file.read_bytes() == b"PRIOR-GOOD-RENDER"

    def test_render_status_never_reports_a_failed_job_as_success(self, ws):
        from workshop_video_brain.edit_mcp.pipelines.render_pipeline import register_render
        from workshop_video_brain.edit_mcp.adapters.render.jobs import update_job_status
        from workshop_video_brain.core.models.enums import JobStatus

        job = update_job_status(self._job(ws), JobStatus.failed)
        register_render(ws, job)
        listed = render_status(str(ws))
        assert listed["status"] == "success", listed
        jobs = listed["data"]["jobs"]
        assert jobs, listed
        assert all(j["status"] != "succeeded" for j in jobs), jobs
        # The partial output for that failed job is not present.
        assert not Path(job.output_path).exists()

    def test_re_render_after_interruption_succeeds(self, ws):
        from workshop_video_brain.edit_mcp.adapters.render.executor import execute_render
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
        from workshop_video_brain.core.models.enums import JobStatus

        profile = load_profile("preview")

        interrupted = self._job(ws)
        out1 = Path(interrupted.output_path)
        execute_render(
            interrupted, profile, timeout_seconds=1,
            _command_override=["sh", "-c", f"printf x > '{out1}'; sleep 30"],
        )
        assert not out1.exists()

        good = self._job(ws)
        out2 = Path(good.output_path)
        result = execute_render(
            good, profile, timeout_seconds=10,
            _command_override=["sh", "-c", f"printf DONE > '{out2}'"],
        )
        assert result.status == JobStatus.succeeded, result.status
        assert out2.exists() and out2.read_bytes() == b"DONE"


# ===========================================================================
# Scenario 4 -- proxy divergence
# ===========================================================================
class TestProxyDivergence:
    @pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
    def test_proxy_status_reports_missing_after_proxy_deleted(self, tmp_path):
        from workshop_video_brain.core.models import MediaAsset
        from workshop_video_brain.core.models.kdenlive import (
            KdenliveProject, Playlist, PlaylistEntry, Producer, Track,
        )
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import (
            generate_proxy, proxy_path_for,
        )
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

        ws = _make_ws(tmp_path, at_root=False, at_wc=False)
        raw = ws / "media" / "raw"
        original = raw / "testsrc.mp4"
        _ffmpeg_testsrc(original)

        asset = MediaAsset(path=str(original), media_type="video", width=320, height=240)
        proxy_dir = ws / "media" / "proxies"
        generate_proxy(asset, proxy_dir)
        proxy_file = proxy_path_for(asset, proxy_dir)
        assert proxy_file.exists()

        producer = Producer(id="producer0", resource=str(original),
                            properties={"resource": str(original)})
        project = KdenliveProject(
            title="Proxy Divergence",
            producers=[producer],
            playlists=[Playlist(id="playlist0",
                                entries=[PlaylistEntry(producer_id="producer0",
                                                       in_point=0, out_point=24)])],
            tracks=[Track(id="playlist0", track_type="video")],
        )
        proj = ws / "projects" / "working_copies" / "proxy_v1.kdenlive"
        proj.parent.mkdir(parents=True, exist_ok=True)
        serialize_project(project, proj)

        attached = proxy_attach(workspace_path=str(ws), project_file=str(proj))
        assert attached["status"] == "success", attached

        # Divergence: the proxy file disappears from disk.
        proxy_file.unlink()

        status = proxy_status(workspace_path=str(ws), project_file=str(proj))
        assert status["status"] == "success", status
        data = status["data"]
        assert data["missing_proxy_count"] == 1, data
        assert data["producers"][0]["missing_proxy_file"] is True, data

    @pytest.mark.skipif(not (_FFMPEG and _MELT), reason="ffmpeg+melt required")
    def test_render_swaps_to_originals_when_proxy_missing(self, tmp_path):
        from workshop_video_brain.core.models import MediaAsset
        from workshop_video_brain.core.models.kdenlive import (
            KdenliveProject, Playlist, PlaylistEntry, Producer, Track,
        )
        from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import (
            generate_proxy, proxy_path_for,
        )
        from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
        from workshop_video_brain.edit_mcp.pipelines.proxy_wiring import originals_render_copy
        from workshop_video_brain.edit_mcp.adapters.render.executor import execute_render
        from workshop_video_brain.edit_mcp.adapters.render.jobs import create_render_job
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
        from workshop_video_brain.core.models.enums import JobStatus

        ws = _make_ws(tmp_path, at_root=False, at_wc=False)
        original = ws / "media" / "raw" / "testsrc.mp4"
        _ffmpeg_testsrc(original)
        asset = MediaAsset(path=str(original), media_type="video", width=320, height=240)
        proxy_dir = ws / "media" / "proxies"
        generate_proxy(asset, proxy_dir)

        producer = Producer(id="producer0", resource=str(original),
                            properties={"resource": str(original)})
        project = KdenliveProject(
            title="Proxy Render",
            producers=[producer],
            playlists=[Playlist(id="playlist0",
                                entries=[PlaylistEntry(producer_id="producer0",
                                                       in_point=0, out_point=24)])],
            tracks=[Track(id="playlist0", track_type="video")],
        )
        proj = ws / "projects" / "working_copies" / "proxy_v1.kdenlive"
        proj.parent.mkdir(parents=True, exist_ok=True)
        serialize_project(project, proj)
        proxy_attach(workspace_path=str(ws), project_file=str(proj))

        # Proxy diverges (deleted); a standard render must still succeed because
        # run_render swaps producers back to their originals. Reproduce that swap
        # and render with a BOUNDED timeout so a stalled melt can't hang the suite.
        proxy_path_for(asset, proxy_dir).unlink()
        swapped = originals_render_copy(proj, ws / "renders" / ".proxy_originals")
        assert parse_project(swapped).producers[0].resource == str(original)
        job = create_render_job(ws, swapped, profile="preview", mode="standard")
        result = execute_render(job, load_profile("preview"), timeout_seconds=120)
        assert result.status == JobStatus.succeeded, result.status
        assert Path(job.output_path).exists()


# ===========================================================================
# Scenario 5 -- missing dependency mid-chain (mask_generate_and_apply)
# ===========================================================================
class TestMissingDependencyMidChain:
    def test_engine_absent_errors_without_touching_project_or_temp(self, ws, monkeypatch):
        # Force the segmentation engine to be unavailable (deterministic even if
        # rembg is installed).
        import workshop_video_brain.edit_mcp.pipelines.ai_mask as ai_mask
        monkeypatch.setattr(ai_mask, "engine_available", lambda name: False)

        media = ws / "media" / "raw" / "subject.mp4"
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"\x00" * 256)

        proj = ws / "proj.kdenlive"
        before = _sha(proj)
        snaps_before = _snap_dirs(ws)
        temp_before = set(Path(tempfile.gettempdir()).glob("ai_mask_*"))

        out = mask_generate_and_apply(
            str(ws), "proj.kdenlive", track=2, clip=0,
            source=str(media), engine="rembg",
        )
        assert_loud_error(out, expected_type="missing_dependency")
        # names the install path forward.
        assert "install" in out["suggestion"].lower()

        # Project untouched, no snapshot taken, no orphan temp dirs, no matte.
        assert _sha(proj) == before
        assert _snap_dirs(ws) == snaps_before
        temp_after = set(Path(tempfile.gettempdir()).glob("ai_mask_*"))
        assert temp_after == temp_before, "leaked ai_mask temp dir"
        masks = ws / "media" / "derived_masks"
        assert not masks.exists() or list(masks.glob("*")) == []

    @pytest.mark.skipif(not _FFMPEG, reason="ffmpeg required")
    def test_engine_fails_after_frames_extracted_no_orphans(self, tmp_path, monkeypatch):
        # Harder variant: the engine resolves but blows up DURING segmentation
        # (after ffmpeg has already extracted frames). No orphan temp dirs, no
        # partial matte, project untouched.
        import workshop_video_brain.edit_mcp.pipelines.ai_mask as ai_mask

        class _BoomEngine(ai_mask.MaskEngine):
            name = "boom"

            def mask_png_bytes(self, png_bytes):
                raise RuntimeError("segmenter exploded mid-run")

        monkeypatch.setattr(ai_mask, "engine_available", lambda name: True)
        monkeypatch.setattr(ai_mask, "make_engine", lambda *a, **k: _BoomEngine())

        ws = _make_ws(tmp_path)
        media = ws / "media" / "raw" / "subject.mp4"
        _ffmpeg_testsrc(media, duration=0.4)

        proj = ws / "proj.kdenlive"
        before = _sha(proj)
        snaps_before = _snap_dirs(ws)
        temp_before = set(Path(tempfile.gettempdir()).glob("ai_mask_*"))

        out = mask_generate_and_apply(
            str(ws), "proj.kdenlive", track=2, clip=0,
            source=str(media), engine="rembg", max_frames=3,
        )
        assert out["status"] == "error", out
        assert_loud_error(out)
        assert _sha(proj) == before
        assert _snap_dirs(ws) == snaps_before
        temp_after = set(Path(tempfile.gettempdir()).glob("ai_mask_*"))
        assert temp_after == temp_before, "leaked ai_mask temp dir after mid-run failure"


# ===========================================================================
# Scenario 6 -- stale transcript index
# ===========================================================================
class TestStaleTranscriptIndex:
    """PINNED behavior: transcript_search is a derived cache. After a transcript
    JSON is deleted, ``transcript_search`` can return a STALE hit until the index
    is rebuilt; ``transcript_index_build`` (incremental) prunes it; and
    ``shots_map_to_script`` self-heals because it rebuilds incrementally first."""

    def _write_transcript(self, ws: Path, clip: str, text: str) -> None:
        import json
        tdir = ws / "transcripts"
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / f"{clip}_transcript.json").write_text(json.dumps({
            "asset_id": clip,
            "engine": "test",
            "model": "test",
            "language": "en",
            "raw_text": text,
            "segments": [
                {"start_seconds": 0.0, "end_seconds": 2.0, "text": text,
                 "confidence": 1.0},
            ],
        }), encoding="utf-8")

    def test_search_returns_stale_hit_until_reindex_then_clean(self, ws):
        self._write_transcript(ws, "clip_a", "mounting the bracket with screws")
        self._write_transcript(ws, "clip_b", "calibrating the flux capacitor")
        built = transcript_index_build(str(ws), rebuild=True)
        assert built["status"] == "success", built

        hit = transcript_search(str(ws), "flux capacitor")
        assert hit["status"] == "success", hit
        assert any(h["clip"] == "clip_b" for h in hit["data"]["hits"]), hit

        # Delete clip_b's transcript JSON (the source of truth) WITHOUT reindex.
        (ws / "transcripts" / "clip_b_transcript.json").unlink()

        # PINNED: search still returns the stale hit (index not reconciled yet).
        stale = transcript_search(str(ws), "flux capacitor")
        assert stale["status"] == "success", stale
        assert any(h["clip"] == "clip_b" for h in stale["data"]["hits"]), (
            "pinned staleness contract changed: search no longer returns the "
            "stale hit -- update the docstring + this test together"
        )

        # Incremental rebuild reconciles: the disappeared clip is pruned.
        rebuilt = transcript_index_build(str(ws), rebuild=False)
        assert rebuilt["status"] == "success", rebuilt
        clean = transcript_search(str(ws), "flux capacitor")
        assert clean["status"] == "success", clean
        assert not any(h["clip"] == "clip_b" for h in clean["data"]["hits"]), clean

    def test_shots_map_self_heals_no_stale_candidate(self, ws):
        self._write_transcript(ws, "clip_a", "mounting the bracket with screws")
        self._write_transcript(ws, "clip_b", "calibrating the flux capacitor")
        transcript_index_build(str(ws), rebuild=True)

        steps = ws / "steps.md"
        steps.write_text(
            "1. Mount the bracket with screws\n"
            "2. Calibrate the flux capacitor\n",
            encoding="utf-8",
        )
        # Delete clip_b before mapping; shots_map rebuilds incrementally first,
        # so it must NOT offer clip_b as a (stale) candidate.
        (ws / "transcripts" / "clip_b_transcript.json").unlink()

        out = shots_map_to_script(str(ws), str(steps), include_thumbnails=False)
        assert out["status"] == "success", out
        blob = str(out["data"]["table"])
        assert "clip_b" not in blob, (
            "shots_map_to_script surfaced a stale candidate for a deleted "
            f"transcript: {out['data']['table']}"
        )


# ===========================================================================
# Scenario 7 -- chained assembly (multicam TOCTOU)
# ===========================================================================
class TestMulticamToctou:
    def test_source_deleted_before_assemble_is_named(self, ws):
        a = ws / "media" / "raw" / "angle_a.mp4"
        b = ws / "media" / "raw" / "angle_b.mp4"
        a.parent.mkdir(parents=True, exist_ok=True)
        a.write_bytes(b"\x00" * 128)
        b.write_bytes(b"\x00" * 128)
        before = _sha(ws / "proj.kdenlive")
        snaps_before = _snap_dirs(ws)

        # TOCTOU across tools: angle B vanishes after a prior sync/probe step.
        b.unlink()
        import json
        out = multicam_assemble(
            str(ws), "proj.kdenlive",
            sources=json.dumps([str(a), str(b)]), sync="none",
        )
        assert_loud_error(out, expected_type="missing_file", names=str(b))
        # No half-mutation: project byte-identical, no snapshot, no new tracks.
        assert _sha(ws / "proj.kdenlive") == before
        assert _snap_dirs(ws) == snaps_before

    @pytest.mark.skipif(not (_FFMPEG and _FFPROBE), reason="ffmpeg required")
    def test_source_deleted_after_existence_sweep_is_named(self, tmp_path, monkeypatch):
        # Simulate the source vanishing between the initial existence sweep and
        # the per-source duration probe (the true intra-call TOCTOU window).
        ws = _make_ws(tmp_path)
        a = ws / "media" / "raw" / "angle_a.mp4"
        b = ws / "media" / "raw" / "angle_b.mp4"
        _ffmpeg_testsrc(a, duration=0.5)
        _ffmpeg_testsrc(b, duration=0.5)

        import workshop_video_brain.edit_mcp.server.bundles.multicam as mc_bundle
        real_probe = mc_bundle._probe_duration_seconds

        def _probe_then_delete(path):
            # B vanishes while we are probing A -- i.e. after the initial
            # existence sweep but before B's own per-source existence re-check.
            if Path(path) == a and b.exists():
                b.unlink()
            return real_probe(path)

        monkeypatch.setattr(mc_bundle, "_probe_duration_seconds", _probe_then_delete)

        before = _sha(ws / "proj.kdenlive")
        import json
        out = multicam_assemble(
            str(ws), "proj.kdenlive",
            sources=json.dumps([str(a), str(b)]), sync="none",
        )
        assert_loud_error(out, expected_type="missing_file", names=str(b))
        assert _sha(ws / "proj.kdenlive") == before
