"""Hardening Pass 1 -- structured-error contract coverage for server/tools.

Every MCP tool must fail *gracefully but loudly*: a structured error dict that
carries ``status=error``, a stable ``error_type``, an actionable non-generic
``suggestion``, and never a raw traceback in any payload field.

These tests exercise representative failure modes for each of the 16 domain
modules plus the contract module itself (``server/errors.py``).
"""
from __future__ import annotations

import pytest

from workshop_video_brain.edit_mcp.server import errors
from workshop_video_brain.edit_mcp.server.errors import (
    err,
    tool_guard,
    from_exception,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    bad_json_param,
    corrupt_project,
    media_unreadable,
    not_found,
    invalid_input,
    operation_failed,
    VALID_ERROR_TYPES,
)

# Real tools (imported via the aggregator so registration side effects fire).
from workshop_video_brain.edit_mcp.server.tools import (
    media_list_assets,
    workspace_status,
    markers_list,
    transcript_export,
    project_summary,
    snapshot_restore,
    transitions_apply,
    clip_insert,
    clips_search,
    qc_check,
    render_status,
    audio_analyze,
    broll_suggest,
    pacing_analyze,
    effect_keyframe_set_scalar,
    mask_set,
    composite_set,
    effect_add,
    effect_fade,
    color_analyze,
    effect_color_grade,
)

NONEXISTENT = "/nonexistent/forgeframe/hardening/xyz"


def assert_contract(result: dict, *, allow_types=None) -> None:
    """Assert the structured-error contract holds for *result*."""
    assert isinstance(result, dict), result
    assert result.get("status") == "error", result
    # legacy backward-compat key preserved
    assert result.get("message"), result
    # stable machine key present and known
    assert "error_type" in result, result
    assert result["error_type"] in VALID_ERROR_TYPES, result
    if allow_types is not None:
        assert result["error_type"] in allow_types, result
    # actionable, non-generic suggestion
    sugg = result.get("suggestion")
    assert sugg, result
    assert len(sugg) > 15, result
    assert sugg.strip().lower() not in {"error", "failed", "an error occurred"}, result
    # no traceback text may leak into any payload field
    for value in result.values():
        assert "Traceback" not in str(value), result
        assert "  File \"" not in str(value), result


# ---------------------------------------------------------------------------
# Contract module (errors.py) unit coverage
# ---------------------------------------------------------------------------
class TestContractBuilders:
    def test_err_backward_compatible_base_keys(self):
        out = err("boom")
        assert out == {"status": "error", "message": "boom"}

    def test_err_adds_optional_keys(self):
        out = err("boom", suggestion="do x", cause="ValueError: y",
                  error_type=errors.INVALID_INPUT, path="/p")
        assert out["error_type"] == "invalid_input"
        assert out["suggestion"] == "do x"
        assert out["cause"] == "ValueError: y"
        assert out["path"] == "/p"

    def test_err_drops_none_details(self):
        out = err("boom", path=None)
        assert "path" not in out

    def test_missing_file(self):
        out = missing_file("/x/y.kdenlive", "Project file")
        assert_contract(out, allow_types={"missing_file"})
        assert "does not exist" in out["message"]
        assert out["path"] == "/x/y.kdenlive"

    def test_missing_binary(self):
        out = missing_binary("melt", "apt install melt")
        assert_contract(out, allow_types={"missing_binary"})
        assert "melt" in out["suggestion"]

    def test_missing_dependency(self):
        out = missing_dependency("numpy", "uv add numpy")
        assert_contract(out, allow_types={"missing_dependency"})

    def test_invalid_index_reports_range(self):
        out = invalid_index("track", 9, "0-3")
        assert_contract(out, allow_types={"invalid_index"})
        assert out["given"] == 9
        assert out["valid_range"] == "0-3"
        assert "0-3" in out["message"]

    def test_bad_json_param_shows_example(self):
        out = bad_json_param("params", '{"opacity": 0.5}', "not json")
        assert_contract(out, allow_types={"bad_json_param"})
        assert "opacity" in out["suggestion"]
        assert out["given"] == "not json"

    def test_corrupt_project_from_exception(self):
        out = corrupt_project("/p.kdenlive", ValueError("bad xml"))
        assert_contract(out, allow_types={"corrupt_project"})
        assert out["cause"] == "ValueError: bad xml"

    def test_media_unreadable(self):
        out = media_unreadable("/m.mp4", RuntimeError("decode fail"))
        assert_contract(out, allow_types={"media_unreadable"})

    def test_not_found(self):
        out = not_found("Effect", "wobble")
        assert_contract(out, allow_types={"not_found"})

    def test_invalid_input(self):
        out = invalid_input("bad arg", "pass a valid value")
        assert_contract(out, allow_types={"invalid_input"})

    def test_operation_failed_never_leaks_traceback(self):
        out = operation_failed("boom", cause=ValueError("deep\nmultiline\nerror"))
        assert_contract(out, allow_types={"operation_failed"})
        # cause is a single line, no embedded newlines from the traceback
        assert "\n" not in out["cause"]

    def test_cause_is_one_line_only(self):
        exc = ValueError("first line\nsecond line\nthird")
        out = operation_failed("x", cause=exc)
        assert out["cause"] == "ValueError: first line"


class TestFromException:
    def test_project_parse_error_maps_to_corrupt_project(self):
        from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import (
            ProjectParseError,
        )
        exc = ProjectParseError("/tmp/broken.kdenlive", ValueError("bad xml"))
        out = from_exception(exc)
        assert_contract(out, allow_types={"corrupt_project"})

    def test_file_not_found_maps_to_missing_file(self):
        out = from_exception(FileNotFoundError("no such file: /x"))
        assert_contract(out, allow_types={"missing_file"})

    def test_import_error_maps_to_missing_dependency(self):
        out = from_exception(ModuleNotFoundError("No module named 'foo'", name="foo"))
        assert_contract(out, allow_types={"missing_dependency"})

    def test_value_error_maps_to_invalid_input(self):
        out = from_exception(ValueError("bad value"))
        assert_contract(out, allow_types={"invalid_input"})
        assert out["message"] == "bad value"

    def test_unknown_maps_to_operation_failed(self):
        out = from_exception(RuntimeError("weird"))
        assert_contract(out, allow_types={"operation_failed"})


class TestToolGuard:
    def test_guard_catches_and_structures(self):
        @tool_guard
        def boom():
            raise RuntimeError("kaboom")

        out = boom()
        assert_contract(out, allow_types={"operation_failed"})
        assert "boom failed unexpectedly" in out["message"]
        assert "RuntimeError" in out["cause"]

    def test_guard_preserves_success(self):
        @tool_guard
        def ok():
            return {"status": "success", "data": {"x": 1}}

        assert ok() == {"status": "success", "data": {"x": 1}}

    def test_guard_preserves_name_and_signature(self):
        import inspect

        @tool_guard
        def sample(a: int, b: str = "x") -> dict:
            return {}

        assert sample.__name__ == "sample"
        params = inspect.signature(sample).parameters
        assert list(params) == ["a", "b"]


# ---------------------------------------------------------------------------
# Per-module tool failure modes
# ---------------------------------------------------------------------------
# Each entry: (callable, args, kwargs). Empty workspace_path exercises the
# common invalid-input validation path; a nonexistent path exercises the
# missing-file path; nonexistent media/file paths exercise file/backstop paths.
WORKSPACE_TOOLS_EMPTY = [
    ("workspace_media.media_list_assets", media_list_assets, ("",)),
    ("workspace_media.workspace_status", workspace_status, ("",)),
    ("transcript_markers.markers_list", markers_list, ("",)),
    ("transcript_markers.transcript_export", transcript_export, ("",)),
    ("timeline_project.project_summary", project_summary, ("",)),
    ("timeline_project.snapshot_restore", snapshot_restore, ("", "snap1")),
    ("transitions.transitions_apply", transitions_apply, ("",)),
    ("clips_nle.clip_insert", clip_insert, ("", "/some/media.mp4")),
    ("clips_nle.clips_search", clips_search, ("", "query")),
    ("render.render_status", render_status, ("",)),
    ("audio.audio_analyze", audio_analyze, ("",)),
    ("broll.broll_suggest", broll_suggest, ("",)),
    ("assembly_titles.pacing_analyze", pacing_analyze, ("",)),
    ("keyframes.effect_keyframe_set_scalar", effect_keyframe_set_scalar,
     ("", "p.kdenlive", 0, 0, 0, "opacity", "[]")),
    ("compositing_masking.mask_set", mask_set,
     ("", "p.kdenlive", 0, 0, "object_mask", "{}")),
    ("compositing_masking.composite_set", composite_set,
     ("", "p.kdenlive", 0, 1, 0, 100)),
    ("effects_catalog.effect_add", effect_add,
     ("", "p.kdenlive", 0, 0, "blur")),
    ("effects_bundles.effect_fade", effect_fade,
     ("", "p.kdenlive", 0, 0, 10, 0)),
    ("effects_color.effect_color_grade", effect_color_grade,
     ("", "p.kdenlive", 0, 0)),
]


@pytest.mark.parametrize(
    "name,fn,args",
    WORKSPACE_TOOLS_EMPTY,
    ids=[t[0] for t in WORKSPACE_TOOLS_EMPTY],
)
def test_empty_workspace_returns_structured_error(name, fn, args):
    out = fn(*args)
    assert_contract(out)


WORKSPACE_TOOLS_MISSING = [
    ("workspace_media.media_list_assets", media_list_assets, (NONEXISTENT,)),
    ("timeline_project.project_summary", project_summary, (NONEXISTENT,)),
    ("broll.broll_suggest", broll_suggest, (NONEXISTENT,)),
    ("transitions.transitions_apply", transitions_apply, (NONEXISTENT,)),
]


@pytest.mark.parametrize(
    "name,fn,args",
    WORKSPACE_TOOLS_MISSING,
    ids=[t[0] for t in WORKSPACE_TOOLS_MISSING],
)
def test_nonexistent_workspace_returns_structured_error(name, fn, args):
    out = fn(*args)
    assert_contract(out)


FILE_TOOLS = [
    ("render.qc_check", qc_check, (NONEXISTENT + ".mp4",)),
    ("effects_color.color_analyze", color_analyze, (NONEXISTENT + ".mp4",)),
]


@pytest.mark.parametrize(
    "name,fn,args",
    FILE_TOOLS,
    ids=[t[0] for t in FILE_TOOLS],
)
def test_missing_file_input_returns_structured_error(name, fn, args):
    out = fn(*args)
    assert_contract(out)
