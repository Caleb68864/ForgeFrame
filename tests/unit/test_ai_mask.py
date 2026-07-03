"""Unit tests for ``edit_mcp/pipelines/ai_mask.py`` (pure decision layer).

Covers engine selection (incl. the missing / second-tier engine error path),
rembg model resolution, box parsing, output-path naming, and the two pure
ffmpeg command builders. No ffmpeg or segmentation engine is invoked here.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.pipelines import ai_mask


# ---------------------------------------------------------------------------
# Engine selection
# ---------------------------------------------------------------------------

def test_resolve_engine_auto_prefers_rembg(monkeypatch):
    monkeypatch.setattr(ai_mask, "engine_available", lambda n: n == "rembg")
    assert ai_mask.resolve_engine("auto") == "rembg"


def test_resolve_engine_auto_none_installed_raises_with_pip_hint(monkeypatch):
    monkeypatch.setattr(ai_mask, "engine_available", lambda n: False)
    with pytest.raises(ai_mask.EngineUnavailable) as exc:
        ai_mask.resolve_engine("auto")
    assert "rembg" in str(exc.value)


def test_resolve_engine_explicit_rembg(monkeypatch):
    monkeypatch.setattr(ai_mask, "engine_available", lambda n: True)
    assert ai_mask.resolve_engine("rembg") == "rembg"


def test_resolve_engine_missing_rembg_raises_pip(monkeypatch):
    monkeypatch.setattr(ai_mask, "engine_available", lambda n: False)
    with pytest.raises(ai_mask.EngineUnavailable) as exc:
        ai_mask.resolve_engine("rembg")
    assert "pip install" in str(exc.value).lower()


def test_resolve_engine_second_tier_sam2_is_unavailable_with_hint():
    with pytest.raises(ai_mask.EngineUnavailable) as exc:
        ai_mask.resolve_engine("sam2")
    msg = str(exc.value)
    assert "ultralytics" in msg  # the documented install target


def test_resolve_engine_second_tier_yolo_is_unavailable():
    with pytest.raises(ai_mask.EngineUnavailable):
        ai_mask.resolve_engine("yolo")


def test_resolve_engine_unknown_name_raises_valueerror():
    with pytest.raises(ValueError):
        ai_mask.resolve_engine("bogus")


def test_engine_available_unknown_is_false():
    assert ai_mask.engine_available("nope") is False


# ---------------------------------------------------------------------------
# rembg model resolution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("subject", ["person", "People", "HUMAN", "portrait"])
def test_resolve_model_person_uses_human_seg(subject):
    assert ai_mask.resolve_model(subject) == "u2net_human_seg"


def test_resolve_model_generic_uses_tiny_default():
    assert ai_mask.resolve_model("guitar") == "u2netp"


def test_resolve_model_explicit_override_wins():
    assert ai_mask.resolve_model("person", model="birefnet-general") == "birefnet-general"


# ---------------------------------------------------------------------------
# Box parsing
# ---------------------------------------------------------------------------

def test_parse_box_valid():
    assert ai_mask.parse_box("10,20,30,40") == (10, 20, 30, 40)


@pytest.mark.parametrize("box", ["", "   ", None])
def test_parse_box_empty_is_none(box):
    assert ai_mask.parse_box(box) is None


@pytest.mark.parametrize("box", ["1,2,3", "1,2,3,4,5", "a,b,c,d", "0,0,-5,10", "0,0,10,0"])
def test_parse_box_invalid_raises(box):
    with pytest.raises(ValueError):
        ai_mask.parse_box(box)


# ---------------------------------------------------------------------------
# Output path naming
# ---------------------------------------------------------------------------

def test_derived_mask_path_default_suffix():
    p = ai_mask.derived_mask_path(Path("/raw/clip.mov"), Path("/ws/masks"))
    assert p == Path("/ws/masks/clip_matte.mp4")


def test_derived_mask_path_custom_name_gets_ext():
    p = ai_mask.derived_mask_path(Path("/raw/clip.mov"), Path("/ws/masks"), "hero")
    assert p == Path("/ws/masks/hero.mp4")


def test_derived_mask_path_custom_name_keeps_ext():
    p = ai_mask.derived_mask_path(Path("/raw/clip.mov"), Path("/ws/masks"), "hero.mov")
    assert p == Path("/ws/masks/hero.mov")


# ---------------------------------------------------------------------------
# ffmpeg command builders (pure)
# ---------------------------------------------------------------------------

def test_build_extract_cmd_all_frames():
    cmd = ai_mask.build_extract_cmd(Path("/s.mp4"), "f_%06d.png")
    assert cmd[0] == "ffmpeg" and "-i" in cmd and "/s.mp4" in cmd
    assert "f_%06d.png" == cmd[-1]
    assert "-frames:v" not in cmd


def test_build_extract_cmd_capped():
    cmd = ai_mask.build_extract_cmd(Path("/s.mp4"), "f_%06d.png", max_frames=5)
    assert "-frames:v" in cmd and cmd[cmd.index("-frames:v") + 1] == "5"


def test_build_encode_cmd_basic_filterchain_order():
    cmd = ai_mask.build_encode_cmd("m_%06d.png", Path("/o.mp4"), 25.0, 320, 240)
    vf = cmd[cmd.index("-vf") + 1]
    # gray -> scale -> yuv420p, no box/invert/feather.
    assert vf == "format=gray,scale=320:240,format=yuv420p"
    assert "-framerate" in cmd and cmd[cmd.index("-framerate") + 1] == "25"
    assert cmd[-1] == "/o.mp4"
    assert "libx264" in cmd


def test_build_encode_cmd_box_invert_feather():
    cmd = ai_mask.build_encode_cmd(
        "m_%06d.png", Path("/o.mp4"), 30.0, 1920, 1080,
        box=(100, 50, 400, 300), invert=True, feather_px=8,
    )
    vf = cmd[cmd.index("-vf") + 1]
    assert "crop=400:300:100:50" in vf
    assert "pad=1920:1080:100:50:color=black" in vf
    assert "negate" in vf
    assert "gblur=sigma=8" in vf
    # ordering: crop before pad before negate before feather before yuv420p.
    assert vf.index("crop") < vf.index("pad") < vf.index("negate") < vf.index("gblur")
    assert vf.endswith("format=yuv420p")


def test_build_encode_cmd_fractional_fps():
    cmd = ai_mask.build_encode_cmd("m_%06d.png", Path("/o.mp4"), 23.976, 640, 360)
    assert cmd[cmd.index("-framerate") + 1] == "23.97600"


def test_build_encode_cmd_zero_fps_falls_back_to_25():
    cmd = ai_mask.build_encode_cmd("m_%06d.png", Path("/o.mp4"), 0.0, 640, 360)
    assert cmd[cmd.index("-framerate") + 1] == "25"


# ---------------------------------------------------------------------------
# plan_matte (decision layer without I/O when probe=False)
# ---------------------------------------------------------------------------

def test_plan_matte_resolves_engine_model_box(monkeypatch):
    monkeypatch.setattr(ai_mask, "engine_available", lambda n: n == "rembg")
    plan = ai_mask.plan_matte(
        Path("/raw/clip.mov"), Path("/ws/masks"),
        subject="person", engine="auto", box="1,2,3,4", probe=False,
    )
    assert plan.engine == "rembg"
    assert plan.model == "u2net_human_seg"
    assert plan.box == (1, 2, 3, 4)
    assert plan.output == Path("/ws/masks/clip_matte.mp4")


def test_plan_matte_missing_engine_raises(monkeypatch):
    monkeypatch.setattr(ai_mask, "engine_available", lambda n: False)
    with pytest.raises(ai_mask.EngineUnavailable):
        ai_mask.plan_matte(Path("/raw/c.mov"), Path("/ws/m"), engine="auto", probe=False)


def test_plan_matte_negative_feather_raises(monkeypatch):
    monkeypatch.setattr(ai_mask, "engine_available", lambda n: True)
    with pytest.raises(ValueError):
        ai_mask.plan_matte(
            Path("/raw/c.mov"), Path("/ws/m"),
            engine="rembg", feather_px=-1, probe=False,
        )
