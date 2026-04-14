"""Unit tests for the effect wrapper generator (Sub-Spec 1).

Covers SR-01..SR-12 from the effect-wrappers test plan.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from workshop_video_brain.edit_mcp.pipelines.effect_catalog import (
    CATALOG,
    EffectDef,
    ParamDef,
    ParamType,
)
from workshop_video_brain.edit_mcp.pipelines.effect_wrapper_gen import (
    SELECTION_HEURISTIC_DOCSTRING,
    emit_wrappers_package,
    render_wrapper_module,
    select_wrappable_effects,
)


# ---------------------------------------------------------------------------
# Selection heuristic (SR-01..SR-04)
# ---------------------------------------------------------------------------

def test_sr01_select_wrappable_effects_yields_at_least_20():
    effs = select_wrappable_effects(CATALOG)
    assert len(effs) >= 20


def test_sr02_select_skips_audio_category():
    effs = select_wrappable_effects(CATALOG)
    for e in effs:
        assert e.category == "video"


def test_sr03_select_skips_params_gt_8():
    # Construct a fake catalog with one oversized effect.
    big_params = tuple(
        ParamDef(
            name=f"p{i}",
            display_name=f"P{i}",
            type=ParamType.INTEGER,
            default="0",
            min=None,
            max=None,
            decimals=None,
            values=(),
            value_labels=(),
            keyframable=False,
        )
        for i in range(9)
    )
    bad = EffectDef(
        kdenlive_id="too_big",
        mlt_service="foo",
        display_name="Too Big",
        description="",
        category="video",
        params=big_params,
    )
    fake = {"too_big": bad}
    assert select_wrappable_effects(fake) == []


def test_sr04_select_skips_bad_kdenlive_id():
    ok_params = (
        ParamDef(
            name="p",
            display_name="P",
            type=ParamType.INTEGER,
            default="0",
            min=None,
            max=None,
            decimals=None,
            values=(),
            value_labels=(),
            keyframable=False,
        ),
    )
    bad = EffectDef(
        kdenlive_id="weird.id$",
        mlt_service="foo",
        display_name="Bad",
        description="",
        category="video",
        params=ok_params,
    )
    assert select_wrappable_effects({"x": bad}) == []


# ---------------------------------------------------------------------------
# Renderer (SR-05..SR-08)
# ---------------------------------------------------------------------------

def _sample_effect() -> EffectDef:
    # Deterministic pick: first wrappable effect sorted by kdenlive_id.
    effs = select_wrappable_effects(CATALOG)
    assert effs, "catalog produced no wrappable effects"
    return effs[0]


def test_sr05_render_wrapper_module_is_valid_python():
    src = render_wrapper_module(_sample_effect())
    tree = ast.parse(src)
    func_defs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert any(fd.name.startswith("effect_") for fd in func_defs)


def test_sr06_render_adds_keyframes_for_animated_params():
    # Synthesize an effect with an animated param.
    animated = EffectDef(
        kdenlive_id="fake_anim",
        mlt_service="fake",
        display_name="Fake Animated",
        description="",
        category="video",
        params=(
            ParamDef(
                name="rect",
                display_name="Rect",
                type=ParamType.GEOMETRY,
                default="",
                min=None,
                max=None,
                decimals=None,
                values=(),
                value_labels=(),
                keyframable=True,
            ),
        ),
    )
    src = render_wrapper_module(animated)
    assert 'keyframes: str = ""' in src


def test_sr07_render_skips_hidden_params():
    hidden = EffectDef(
        kdenlive_id="fake_hidden",
        mlt_service="fake",
        display_name="Fake Hidden",
        description="",
        category="video",
        params=(
            ParamDef(
                name="hidden_p",
                display_name="Hidden",
                type=ParamType.HIDDEN,
                default="0",
                min=None,
                max=None,
                decimals=None,
                values=(),
                value_labels=(),
                keyframable=False,
            ),
            ParamDef(
                name="vis",
                display_name="Vis",
                type=ParamType.INTEGER,
                default="1",
                min=None,
                max=None,
                decimals=None,
                values=(),
                value_labels=(),
                keyframable=False,
            ),
        ),
    )
    src = render_wrapper_module(hidden)
    assert "hidden_p" not in src
    assert "vis" in src


def test_sr08_rendered_module_contains_generated_marker():
    src = render_wrapper_module(_sample_effect())
    assert "GENERATED" in src
    # Heuristic docstring string is exported for callers/documentation.
    assert "video" in SELECTION_HEURISTIC_DOCSTRING


# ---------------------------------------------------------------------------
# Emitter (SR-09..SR-11)
# ---------------------------------------------------------------------------

def test_sr09_emit_writes_one_file_per_effect(tmp_path):
    effs = select_wrappable_effects(CATALOG)
    emit_wrappers_package(effs, tmp_path, force=True)
    py_files = sorted(p.name for p in tmp_path.glob("*.py"))
    # 1 __init__.py + N effect modules
    assert "__init__.py" in py_files
    assert len(py_files) == len(effs) + 1

    init_src = (tmp_path / "__init__.py").read_text(encoding="utf-8")
    for e in effs:
        assert f"effect_{e.kdenlive_id.replace('-', '_')}" in init_src \
            or f"effect_{e.kdenlive_id}" in init_src


def test_sr10_emit_is_byte_identical_across_runs(tmp_path):
    effs = select_wrappable_effects(CATALOG)
    a = tmp_path / "a"
    b = tmp_path / "b"
    emit_wrappers_package(effs, a, force=True)
    emit_wrappers_package(effs, b, force=True)
    a_files = sorted(p.name for p in a.glob("*.py"))
    b_files = sorted(p.name for p in b.glob("*.py"))
    assert a_files == b_files
    for name in a_files:
        assert (a / name).read_bytes() == (b / name).read_bytes()


def test_sr11_emit_refuses_non_empty_without_force(tmp_path):
    (tmp_path / "handwritten.py").write_text("# hand-edited", encoding="utf-8")
    effs = select_wrappable_effects(CATALOG)
    with pytest.raises(FileExistsError):
        emit_wrappers_package(effs, tmp_path, force=False)


# ---------------------------------------------------------------------------
# CLI / script (SR-12)
# ---------------------------------------------------------------------------

def test_sr12_cli_catalog_regenerate_wrappers_writes_package(tmp_path):
    from workshop_video_brain.app.cli import main

    runner = CliRunner()
    out = tmp_path / "wrappers_out"
    result = runner.invoke(
        main,
        ["catalog", "regenerate-wrappers", "--output", str(out), "--force"],
    )
    assert result.exit_code == 0, result.output
    assert (out / "__init__.py").exists()
    py_files = list(out.glob("effect_*.py"))
    assert len(py_files) >= 20


def test_script_generate_effect_wrappers_writes_package(tmp_path):
    out = tmp_path / "wrappers_script_out"
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "generate_effect_wrappers.py"
    assert script.exists(), f"missing script: {script}"
    result = subprocess.run(
        [sys.executable, str(script), "--output", str(out), "--force"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (out / "__init__.py").exists()
    assert len(list(out.glob("effect_*.py"))) >= 20


# ---------------------------------------------------------------------------
# Integration: server wiring
# ---------------------------------------------------------------------------

def test_effect_wrappers_registered_on_mcp():
    # Importing server triggers the effect_wrappers package import,
    # which fires `register_effect_wrapper` on each module.
    import workshop_video_brain.server  # noqa: F401
    from workshop_video_brain.edit_mcp.server.tools_helpers import (
        __wrapped_effects__,
    )
    assert len(__wrapped_effects__) >= 20
