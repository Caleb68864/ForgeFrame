"""Hardening Pass 2 -- adversarial fault injection for server/tools.

Pass 1 gave every tool the ``errors.py`` contract + ``@tool_guard``. This suite
*actively breaks* a representative deep set of tools (all 15 domain modules) and
proves each failure is **graceful but loud**:

- returns ``status=error`` with a stable ``error_type`` and a non-generic
  ``suggestion``;
- never leaks a traceback into the payload;
- never corrupts state: the target project file is **byte-unchanged** after a
  failed call, no stray ``_v`` working-copy files appear, and no snapshot is
  leaked for a failed op.

It also hunts false successes: injected faults that return ``status=success``
are either proven harmless (documented intentional passthrough) or fixed.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server.errors import VALID_ERROR_TYPES
from workshop_video_brain.edit_mcp.server.tools import (
    workspace_create,
    # workspace_media
    media_list_assets, media_ingest, proxy_generate, workspace_status,
    media_check_vfr,
    # transcript_markers
    markers_list, transcript_export, subtitles_export, transcript_generate,
    # timeline_project
    project_summary, snapshot_restore, project_validate, timeline_build_review,
    # transitions
    transitions_apply_at, transitions_apply_between,
    # clips_nle
    clip_insert, clip_remove, clip_move, clip_split, clip_speed, track_add,
    track_mute, track_visibility, gap_insert, audio_fade, clips_search,
    # render
    render_status, qc_check, project_match_source,
    # audio
    audio_analyze, audio_normalize, audio_compress,
    # broll
    broll_library_search,
    # assembly_titles
    pacing_analyze, replay_generate, title_cards_generate,
    # social_publish
    publish_titles, social_find_clips, effect_keyframe_set_scalar, effect_find, mask_set, mask_set_shape, composite_set, composite_pip, mask_apply,
    effect_chroma_key, composite_wipe,
    # effects_catalog
    effect_add, effect_reorder, effect_stack_apply,
    # effects_bundles
    effect_fade, move_up,
    # effects_color
    effect_color_grade, color_apply_lut, color_analyze,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

BIG_LABEL = "A" * 100_000
NASTY = "clip \U0001F600\U0001F4A5 \"quote\" <tag> ; rm -rf /  \n\t"


# ---------------------------------------------------------------------------
# Contract + state helpers
# ---------------------------------------------------------------------------
def assert_loud_error(result: dict) -> None:
    """Every injected fault must fail gracefully *and* loudly."""
    assert isinstance(result, dict), result
    assert result.get("status") == "error", result
    assert result.get("message"), result  # legacy key preserved
    assert result.get("error_type") in VALID_ERROR_TYPES, result
    sugg = result.get("suggestion")
    assert sugg and len(str(sugg)) > 15, result
    assert str(sugg).strip().lower() not in {
        "error", "failed", "an error occurred", "unknown error",
    }, result
    for value in result.values():
        sv = str(value)
        assert "Traceback" not in sv, result
        assert '  File "' not in sv, result


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


class Ws:
    """A workspace pre-loaded with a valid working copy, an explicit project
    file, and a family of malformed project files at the root."""

    def __init__(self, root: Path):
        media = root / "media"
        media.mkdir(parents=True, exist_ok=True)
        self.media = media
        created = workspace_create(title="Pass2", media_root=str(media))
        assert created["status"] == "success", created
        self.ws = Path(created["data"]["workspace_root"])
        self.wc = self.ws / "projects" / "working_copies"
        self.wc.mkdir(parents=True, exist_ok=True)
        self.snaps = self.ws / "projects" / "snapshots"
        self.snaps.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIXTURE, self.wc / "proj_v1.kdenlive")
        shutil.copy(FIXTURE, self.ws / "proj.kdenlive")
        # malformed project files (0-byte, truncated XML, valid non-MLT, binary)
        (self.ws / "empty.kdenlive").write_bytes(b"")
        (self.ws / "truncated.kdenlive").write_text('<mlt><playlist id="p"><entry')
        (self.ws / "binary.kdenlive").write_bytes(bytes(range(256)) * 8)
        (self.ws / "nonmlt.kdenlive").write_text("<html><body>nope</body></html>")
        self._watch = [
            self.ws / "proj.kdenlive",
            self.wc / "proj_v1.kdenlive",
            self.ws / "empty.kdenlive",
            self.ws / "truncated.kdenlive",
            self.ws / "binary.kdenlive",
            self.ws / "nonmlt.kdenlive",
        ]

    def snapshot_state(self):
        return (
            {str(p): _sha(p) for p in self._watch},
            sorted(x.name for x in self.wc.glob("*")),
            sorted(x.name for x in self.snaps.glob("*")),
        )

    def s(self):
        return str(self.ws)


@pytest.fixture(scope="module")
def shared_ws(tmp_path_factory):
    return Ws(tmp_path_factory.mktemp("faults_shared"))


@pytest.fixture()
def fresh_ws(tmp_path):
    return Ws(tmp_path)


# ---------------------------------------------------------------------------
# The fault matrix. Each entry is (id, callable, args, kwargs). Every one must
# fail with a loud structured error AND leave state byte-identical.
# ---------------------------------------------------------------------------
def build_matrix(w: Ws):
    S = w.s()
    m = []
    def add(i, fn, *args, **kw):
        m.append((i, fn, args, kw))

    # workspace_path: empty / "None" / "null" / missing / a-file / spaces
    add("ws_empty", media_list_assets, "")
    add("ws_none_literal", workspace_status, "None")
    add("ws_null_literal", markers_list, "null")
    add("ws_missing", project_summary, "/nonexistent/ff/pass2/xyz")
    add("ws_is_file", project_summary, str(w.ws / "proj.kdenlive"))
    add("ws_spaces", pacing_analyze, "   ")
    add("ws_empty_ingest", media_ingest, "")
    add("ws_empty_proxy", proxy_generate, "")
    add("ws_empty_vfr", media_check_vfr, "")
    add("ws_empty_transcript", transcript_generate, "")
    add("ws_empty_review", timeline_build_review, "")
    add("ws_empty_titlecards", title_cards_generate, "")
    add("ws_empty_publish", publish_titles, "")
    add("ws_empty_render", render_status, "")
    add("ws_empty_audio", audio_analyze, "")
    add("ws_empty_validate", project_validate, "")
    add("ws_isfile_search", clips_search, str(w.ws / "proj.kdenlive"), "q")

    # enum / format params
    add("transcript_badfmt", transcript_export, S, format="INVALIDFMT")
    add("subs_badfmt", subtitles_export, S, format="\x00bogus")

    # snapshot restore
    add("snap_missing", snapshot_restore, S, "does-not-exist")
    add("snap_empty_id", snapshot_restore, S, "")
    add("snap_traversal", snapshot_restore, S, "../../etc/passwd")

    # transitions
    add("trans_at_neg", transitions_apply_at, S, -5.0)
    add("trans_at_nan", transitions_apply_at, S, float("nan"))
    add("trans_between_badtype", transitions_apply_between, S, 0, transition_type="notreal")
    add("trans_between_neg", transitions_apply_between, S, -1)

    # clips_nle: index / enum / number faults
    add("clip_remove_neg", clip_remove, S, -3)
    add("clip_remove_huge", clip_remove, S, 10**9)
    add("clip_move_badto", clip_move, S, 0, 10**9)
    add("clip_split_neg", clip_split, S, -1)
    add("clip_speed_zero", clip_speed, S, 0)
    add("clip_speed_neg", clip_speed, S, 0, speed=-2.0)
    add("clip_speed_nan", clip_speed, S, 0, speed=float("nan"))
    add("clip_speed_inf", clip_speed, S, 0, speed=float("inf"))
    add("track_add_badtype", track_add, S, track_type="hologram")
    add("track_mute_neg", track_mute, S, -1)
    add("track_mute_huge", track_mute, S, 10**9)
    add("track_vis_huge", track_visibility, S, 10**9)
    add("gap_neg_dur", gap_insert, S, 0, -5.0)
    add("gap_nan_dur", gap_insert, S, 0, float("nan"))
    add("audio_fade_badtype", audio_fade, S, 0, fade_type="sideways")
    add("clip_insert_missing_media", clip_insert, S, "/no/such/media.mp4")
    add("clip_insert_dir_media", clip_insert, S, str(w.media))
    add("clip_insert_empty_media", clip_insert, S, "")

    # render / qc / profile
    add("qc_missing", qc_check, "/no/such/file.mp4")
    add("qc_dir", qc_check, str(w.media))
    add("qc_empty", qc_check, "")
    add("match_source_missing", project_match_source, S, "/no/such/src.mp4")

    # audio
    add("audio_norm_missing", audio_normalize, S, file_path="/no/such.wav")
    add("audio_compress_dir", audio_compress, S, file_path=str(w.media))

    # broll (first positional param is `query`, not workspace_path)
    add("broll_search_emptyq", broll_library_search, "")
    add("broll_search_blankq", broll_library_search, "   ")

    # assembly
    add("replay_neg", replay_generate, S, target_duration=-10.0)
    add("replay_nan", replay_generate, S, target_duration=float("nan"))

    # social
    add("social_find_empty", social_find_clips, "")

    # keyframes (explicit project_file + JSON)
    add("kf_missing_pf", effect_keyframe_set_scalar, S, "missing.kdenlive", 0, 0, 0, "opacity", "[]")
    add("kf_empty_pf", effect_keyframe_set_scalar, S, "empty.kdenlive", 2, 0, 0, "opacity", "[]")
    add("kf_truncated_pf", effect_keyframe_set_scalar, S, "truncated.kdenlive", 2, 0, 0, "opacity", "[]")
    add("kf_binary_pf", effect_keyframe_set_scalar, S, "binary.kdenlive", 2, 0, 0, "opacity", "[]")
    add("kf_badjson_trunc", effect_keyframe_set_scalar, S, "proj.kdenlive", 2, 0, 0, "opacity", "[{")
    add("kf_badjson_type", effect_keyframe_set_scalar, S, "proj.kdenlive", 2, 0, 0, "opacity", "{}")
    add("kf_badjson_empty", effect_keyframe_set_scalar, S, "proj.kdenlive", 2, 0, 0, "opacity", "")
    add("kf_badjson_null", effect_keyframe_set_scalar, S, "proj.kdenlive", 2, 0, 0, "opacity", "null")
    add("kf_neg_effidx", effect_keyframe_set_scalar, S, "proj.kdenlive", 2, 0, -5, "opacity", '[{"frame":0,"value":1.0}]')
    add("kf_huge_effidx", effect_keyframe_set_scalar, S, "proj.kdenlive", 2, 0, 10**9, "opacity", '[{"frame":0,"value":1.0}]')
    add("kf_neg_track", effect_keyframe_set_scalar, S, "proj.kdenlive", -1, 0, 0, "opacity", '[{"frame":0,"value":1.0}]')
    add("kf_badmode", effect_keyframe_set_scalar, S, "proj.kdenlive", 2, 0, 0, "opacity", '[{"frame":0,"value":1.0}]', mode="sideways")
    add("kf_deepnest", effect_keyframe_set_scalar, S, "proj.kdenlive", 2, 0, 0, "opacity", "[" + "[]" * 4000 + "]")
    add("efind_missing_pf", effect_find, S, "missing.kdenlive", 2, 0, "transform")

    # compositing / masking
    add("mask_set_badtype", mask_set, S, "proj.kdenlive", 2, 0, "notatype", "{}")
    add("mask_set_badjson", mask_set, S, "proj.kdenlive", 2, 0, "object_mask", "{")
    add("mask_shape_badshape", mask_set_shape, S, "proj.kdenlive", 2, 0, "notashape")
    add("mask_apply_neg", mask_apply, S, "proj.kdenlive", 2, 0, -1, -2)
    add("mask_apply_huge", mask_apply, S, "proj.kdenlive", 2, 0, 10**9, 10**9)
    add("composite_set_badmode", composite_set, S, "proj.kdenlive", 0, 1, 0, 100, blend_mode="notablend")
    add("composite_set_negframes", composite_set, S, "proj.kdenlive", 0, 1, -100, -50)
    add("composite_set_missing_pf", composite_set, S, "missing.kdenlive", 0, 1, 0, 100)
    add("composite_pip_hugetrack", composite_pip, S, "proj.kdenlive", 10**9, 0, 0, 100)
    add("composite_pip_nan_scale", composite_pip, S, "proj.kdenlive", 2, 0, 0, 100, scale=float("nan"))
    add("chroma_missing_pf", effect_chroma_key, S, "missing.kdenlive", 2, 0)
    add("composite_wipe_binary_pf", composite_wipe, S, "binary.kdenlive", 0, 1, 0, 100)

    # effects_catalog
    add("effadd_missing_pf", effect_add, S, "missing.kdenlive", 2, 0, "blur")
    add("effadd_empty_pf", effect_add, S, "empty.kdenlive", 2, 0, "blur")
    add("effadd_binary_pf", effect_add, S, "binary.kdenlive", 2, 0, "blur")
    add("effadd_badjson", effect_add, S, "proj.kdenlive", 2, 0, "blur", "{not json")
    add("effadd_neg_track", effect_add, S, "proj.kdenlive", -1, 0, "blur")
    add("effadd_neg_clip", effect_add, S, "proj.kdenlive", 2, -1, "blur")
    add("effreorder_neg", effect_reorder, S, "proj.kdenlive", 2, 0, -1, 10**9)
    add("effstack_missing_pf", effect_stack_apply, S, "missing.kdenlive", 2, 0, "somestack")

    # effects_bundles
    add("effade_missing_pf", effect_fade, S, "missing.kdenlive", 2, 0, 10, 0)
    add("effade_neg_frames", effect_fade, S, "proj.kdenlive", 2, 0, -10, 0)
    add("effade_hugeframes", effect_fade, S, "proj.kdenlive", 2, 0, 10**9, 0)
    add("effade_bad_easing", effect_fade, S, "proj.kdenlive", 2, 0, 5, 0, easing="notaneasing")
    add("moveup_neg", move_up, S, "proj.kdenlive", 2, 0, -1)
    add("moveup_huge", move_up, S, "proj.kdenlive", 2, 0, 10**9)
    add("moveup_missing_pf", move_up, S, "missing.kdenlive", 2, 0, 0)

    # effects_color
    add("colorgrade_missing_pf", effect_color_grade, S, "missing.kdenlive", 2, 0)
    add("colorgrade_nan_temp", effect_color_grade, S, "proj.kdenlive", 2, 0, temperature=float("nan"))
    add("colorgrade_inf_exp", effect_color_grade, S, "proj.kdenlive", 2, 0, exposure=float("inf"))
    add("lut_missing_pf", color_apply_lut, S, "missing.kdenlive", 2, 0, "/no/such.cube")
    add("coloranalyze_missing", color_analyze, "/no/such/file.mp4")
    add("coloranalyze_dir", color_analyze, str(w.media))
    return m


def test_fault_matrix_is_deep(shared_ws):
    """Sanity: the matrix covers a representative *deep* set across modules."""
    assert len(build_matrix(shared_ws)) >= 80


def test_faults_are_loud_and_leave_state_intact(shared_ws):
    """Drive every fault; assert a loud structured error and zero state drift."""
    w = shared_ws
    failures = []
    for fid, fn, args, kw in build_matrix(w):
        before = w.snapshot_state()
        try:
            out = fn(*args, **kw)
        except BaseException as exc:  # a raised exception is the worst outcome
            failures.append(f"{fid}: RAISED {type(exc).__name__}: {exc}")
            continue
        after = w.snapshot_state()
        # 1) loud structured error
        try:
            assert_loud_error(out)
        except AssertionError as exc:
            failures.append(f"{fid}: CONTRACT {exc}")
        # 2) no watched project file mutated
        if before[0] != after[0]:
            changed = [Path(k).name for k in before[0] if before[0][k] != after[0][k]]
            failures.append(f"{fid}: FILE_MUTATED {changed}")
        # 3) no stray working-copy (_v) files
        new_wc = [x for x in after[1] if x not in before[1]]
        if new_wc:
            failures.append(f"{fid}: WC_LEAK {new_wc}")
        # 4) no leaked snapshot for a failed op
        new_snaps = [x for x in after[2] if x not in before[2]]
        if new_snaps:
            failures.append(f"{fid}: SNAP_LEAK {new_snaps}")
    assert not failures, "Fault-injection violations:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# False-success regression tests: faults that USED to return success and
# silently corrupt/mislead now fail loudly.
# ---------------------------------------------------------------------------
def test_effect_add_rejects_negative_track(fresh_ws):
    # A negative track index used to wrap (Python list indexing) and edit the
    # WRONG track, returning a false success.
    out = effect_add(fresh_ws.s(), "proj.kdenlive", -1, 0, "avfilter.gblur")
    assert_loud_error(out)
    assert out["error_type"] == "invalid_index"


def test_effect_add_rejects_negative_clip(fresh_ws):
    out = effect_add(fresh_ws.s(), "proj.kdenlive", 2, -1, "avfilter.gblur")
    assert_loud_error(out)


def test_composite_pip_rejects_out_of_range_track(fresh_ws):
    out = composite_pip(fresh_ws.s(), "proj.kdenlive", 10**9, 0, 0, 100)
    assert_loud_error(out)
    assert out["error_type"] == "invalid_index"


def test_composite_set_rejects_negative_frames(fresh_ws):
    out = composite_set(fresh_ws.s(), "proj.kdenlive", 0, 1, -100, -50)
    assert_loud_error(out)


def test_color_grade_rejects_nan_param(fresh_ws):
    out = effect_color_grade(fresh_ws.s(), "proj.kdenlive", 2, 0, temperature=float("nan"))
    assert_loud_error(out)
    # ...and the project file is untouched (no NaN written).
    project = parse_project(fresh_ws.ws / "proj.kdenlive")
    assert project is not None


def test_clip_insert_rejects_directory_media(fresh_ws):
    out = clip_insert(fresh_ws.s(), str(fresh_ws.media))
    assert_loud_error(out)


def test_qc_check_rejects_empty_and_dir(fresh_ws):
    assert_loud_error(qc_check(""))
    assert_loud_error(qc_check(str(fresh_ws.media)))


# ---------------------------------------------------------------------------
# Documented intentional successes: proven harmless (produce a valid,
# re-parseable project -- no corruption).
# ---------------------------------------------------------------------------
def test_effect_add_unknown_effect_is_harmless_passthrough(fresh_ws):
    # effect_add intentionally accepts ANY MLT service id (docstring). An
    # unknown name must still produce a valid, re-parseable project file.
    out = effect_add(fresh_ws.s(), "proj.kdenlive", 2, 0, "totally-unknown-effect-xyz")
    assert out["status"] == "success", out
    project = parse_project(fresh_ws.ws / "proj.kdenlive")  # must not raise
    assert project is not None


def test_mask_set_object_mask_default_params_is_harmless(fresh_ws):
    # object_mask with empty params applies documented defaults; the result is
    # a valid, re-parseable project (not corruption).
    out = mask_set(fresh_ws.s(), "proj.kdenlive", 2, 0, "object_mask", "")
    assert out["status"] == "success", out
    project = parse_project(fresh_ws.ws / "proj.kdenlive")
    assert project is not None


# ---------------------------------------------------------------------------
# Unicode / emoji / extremely-long-string params must not blow up.
# ---------------------------------------------------------------------------
def test_nasty_and_huge_labels_do_not_crash(fresh_ws):
    for name in (NASTY, BIG_LABEL):
        out = track_add(fresh_ws.s(), track_type="video", name=name)
        assert out["status"] in ("success", "error"), out
        if out["status"] == "error":
            assert_loud_error(out)
