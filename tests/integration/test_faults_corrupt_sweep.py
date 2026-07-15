"""Hardening Pass 3 closeout -- corrupt-project sweep across the modules whose
``parse_project`` call sites were hardened in the closeout pass.

Contract (per newly-fixed module): feeding a corrupt/truncated ``.kdenlive`` to
a tool that parses it must yield a structured ``corrupt_project`` error --
NEVER the generic ``operation_failed`` from the outer ``tool_guard``, and NEVER
a leaked snapshot of the untouched project. On the corrupt path the tool must:

* return ``status == "error"`` with ``error_type == "corrupt_project"``,
* carry an actionable ``suggestion`` (not filler, no traceback),
* leave the project file byte-identical, and
* leave ``projects/snapshots/`` empty (parse fails BEFORE any snapshot).

These modules previously either let ``ProjectParseError`` escape to the generic
guard (unguarded parse) or snapshotted before parsing (snapshot-before-parse).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server import errors as err_mod
from workshop_video_brain.edit_mcp.server import tools as tools_mod
from workshop_video_brain.edit_mcp.server.bundles import (
    image_overlay,
    masked_wipes,
    overlay_looks,
    proxy_wiring,
    rewind,
    shake_shadow,
    shape_alpha_mask,
    split_screen,
    subtitle_track,
    timeline_audio,
    titles,
    vo_loop,
    guides,
)
from workshop_video_brain.edit_mcp.server.tools import (
    effects_bundles,
    effects_catalog,
    keyframes,
)

_GENERIC = {"", "an error occurred", "try again", "unknown error", "error"}


def _fn(obj):
    """Unwrap a FastMCP tool object to its callable (identity for plain fns)."""
    return getattr(obj, "fn", obj)


@pytest.fixture()
def ws(tmp_path: Path) -> Path:
    media_root = tmp_path / "media_src"
    media_root.mkdir(parents=True, exist_ok=True)
    res = _fn(tools_mod.workspace_create)(
        title="Corrupt Sweep", media_root=str(media_root)
    )
    assert res["status"] == "success", res
    return Path(res["data"]["workspace_root"])


@pytest.fixture()
def corrupt_proj(ws: Path) -> Path:
    """A truncated / unparseable .kdenlive at the workspace root."""
    p = ws / "corrupt.kdenlive"
    p.write_text("<mlt><this is not <<< valid xml & unterminated", encoding="utf-8")
    return p


@pytest.fixture()
def png(tmp_path: Path) -> Path:
    """A file with a .png extension (existence + suffix are all that's checked
    before the project is parsed)."""
    p = tmp_path / "logo.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    return p


@pytest.fixture()
def srt(tmp_path: Path) -> Path:
    p = tmp_path / "subs.srt"
    p.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nHello world\n", encoding="utf-8"
    )
    return p


@pytest.fixture()
def script(tmp_path: Path) -> Path:
    p = tmp_path / "vo.md"
    p.write_text(
        "# Intro\n\nHello world, this is a short voiceover script.\n",
        encoding="utf-8",
    )
    return p


def _snapshot_files(ws: Path) -> list[Path]:
    snap_dir = ws / "projects" / "snapshots"
    if not snap_dir.exists():
        return []
    return [p for p in snap_dir.rglob("*") if p.is_file()]


def _assert_corrupt(result: dict, proj: Path, ws: Path, before: bytes) -> None:
    assert isinstance(result, dict), result
    assert result.get("status") == "error", result
    dumped = json.dumps(result, default=str)
    assert "Traceback" not in dumped, dumped
    assert 'File "' not in dumped, dumped
    assert result.get("error_type") == err_mod.CORRUPT_PROJECT, result
    sug = result.get("suggestion", "")
    assert isinstance(sug, str) and len(sug.strip()) > 12, f"weak suggestion: {result}"
    assert sug.strip().lower() not in _GENERIC, result
    assert result.get("message"), result
    # No mutation, no leaked snapshot of the untouched (corrupt) project.
    assert proj.read_bytes() == before, "project rewritten on corrupt-parse failure"
    assert _snapshot_files(ws) == [], "a snapshot leaked on a corrupt project"


# (module label, builder(ws, proj, fixtures) -> result). One representative
# newly-fixed tool per module.
def _cases():
    return [
        ("image_overlay.watermark_apply",
         lambda ws, proj, fx: _fn(image_overlay.watermark_apply)(
             str(ws), proj.name, image_path=str(fx["png"]))),
        ("overlay_looks.effect_day_to_night",
         lambda ws, proj, fx: _fn(overlay_looks.effect_day_to_night)(
             str(ws), proj.name, 0, 0)),
        ("timeline_audio.track_eq",
         lambda ws, proj, fx: _fn(timeline_audio.track_eq)(
             str(ws), proj.name, 2)),
        ("timeline_audio.audio_duck",
         lambda ws, proj, fx: _fn(timeline_audio.audio_duck)(
             str(ws), proj.name, 1, 2)),
        ("titles.title_card_add",
         lambda ws, proj, fx: _fn(titles.title_card_add)(
             str(proj), text="Title")),
        ("subtitle_track.subtitles_attach",
         lambda ws, proj, fx: _fn(subtitle_track.subtitles_attach)(
             str(ws), str(proj), srt_path=str(fx["srt"]))),
        ("shake_shadow.effect_camera_shake",
         lambda ws, proj, fx: _fn(shake_shadow.effect_camera_shake)(
             str(ws), proj.name, 0, 0, 0, 10)),
        ("shake_shadow.effect_drop_shadow",
         lambda ws, proj, fx: _fn(shake_shadow.effect_drop_shadow)(
             str(ws), proj.name, 0, 0)),
        ("masked_wipes.effect_luma_key",
         lambda ws, proj, fx: _fn(masked_wipes.effect_luma_key)(
             str(ws), proj.name, 0, 0)),
        ("shape_alpha_mask.mask_set_from_file",
         lambda ws, proj, fx: _fn(shape_alpha_mask.mask_set_from_file)(
             str(ws), proj.name, 0, 0, str(fx["png"]))),
        ("vo_loop.vo_plan",
         lambda ws, proj, fx: _fn(vo_loop.vo_plan)(
             str(ws), str(fx["script"]), project_file=proj.name)),
        ("split_screen.composite_split_screen",
         lambda ws, proj, fx: _fn(split_screen.composite_split_screen)(
             str(ws), proj.name, "2h", "0,1", 0, 10)),
        ("proxy_wiring.proxy_status",
         lambda ws, proj, fx: _fn(proxy_wiring.proxy_status)(
             str(ws), str(proj))),
        ("proxy_wiring.proxy_attach",
         lambda ws, proj, fx: _fn(proxy_wiring.proxy_attach)(
             str(ws), str(proj))),
        ("guides.guide_list",
         lambda ws, proj, fx: _fn(guides.guide_list)(str(proj))),
        ("guides.guide_add",
         lambda ws, proj, fx: _fn(guides.guide_add)(str(proj), 1.0, "chapter")),
        ("rewind.effect_rewind",
         lambda ws, proj, fx: _fn(rewind.effect_rewind)(
             str(ws), proj.name, 0, 0, 0.0, 1.0)),
        ("effects_catalog.effects_copy",
         lambda ws, proj, fx: _fn(effects_catalog.effects_copy)(
             str(ws), proj.name, 0, 0)),
        ("effects_catalog.effect_stack_preset",
         lambda ws, proj, fx: _fn(effects_catalog.effect_stack_preset)(
             str(ws), proj.name, 0, 0, "mypreset")),
        ("effects_bundles.effect_glitch_stack",
         lambda ws, proj, fx: _fn(effects_bundles.effect_glitch_stack)(
             str(ws), proj.name, 0, 0)),
        ("effects_bundles.effect_hologram",
         lambda ws, proj, fx: _fn(effects_bundles.effect_hologram)(
             str(ws), proj.name, 0, 0)),
        ("effects_bundles.flash_cut_montage",
         lambda ws, proj, fx: _fn(effects_bundles.flash_cut_montage)(
             str(ws), proj.name, 0, 0)),
        ("effects_bundles.move_to_top",
         lambda ws, proj, fx: _fn(effects_bundles.move_to_top)(
             str(ws), proj.name, 0, 0, 0)),
        ("keyframes.effect_find",
         lambda ws, proj, fx: _fn(keyframes.effect_find)(
             str(ws), proj.name, 0, 0, "brightness")),
    ]


@pytest.mark.parametrize("label,call", _cases(), ids=[c[0] for c in _cases()])
def test_corrupt_project_routes_to_corrupt_project(
    label, call, ws, corrupt_proj, png, srt, script
):
    fx = {"png": png, "srt": srt, "script": script}
    before = corrupt_proj.read_bytes()
    result = call(ws, corrupt_proj, fx)
    _assert_corrupt(result, corrupt_proj, ws, before)
