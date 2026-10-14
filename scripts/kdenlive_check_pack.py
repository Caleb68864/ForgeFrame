#!/usr/bin/env python
"""Build a pack of ForgeFrame-generated projects to open in the real Kdenlive.

Each step applies one more MCP tool to a cumulative timeline and copies the
resulting ``.kdenlive`` into the pack as ``NN_<step>.kdenlive``, so a load
problem in Kdenlive can be pinned to the step that introduced it. Media is
synthetic (ffmpeg ``testsrc``/``color`` + sine audio), so the pack builds on
any machine with ffmpeg.

Then, in Kdenlive (the version you target -- currently 26.x):

1. Open each project in order. Note any dialog verbatim (e.g. "Project
   corrupted. Clip ... not found in project bin").
2. Check what the step should show (``CHECKLIST.md`` in the pack).
3. Save the first clean project as ``<name>_native.kdenlive`` -- that is a
   new native reference fixture for ``tests/fixtures/kdenlive_references/``.

Usage:
    uv run python scripts/kdenlive_check_pack.py [OUT_DIR]

OUT_DIR defaults to ``./kdenlive-check-pack`` (git-ignored scratch).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests._testkit import make_test_clip  # noqa: E402
from workshop_video_brain.edit_mcp.server.tools import (  # noqa: E402
    clips_nle,
    effects_catalog,
    timeline_project,
    transitions,
    workspace_media,
)
from workshop_video_brain.edit_mcp.server.bundles import titles  # noqa: E402
from workshop_video_brain.edit_mcp.server.tools_helpers import latest_project as _newest  # noqa: E402


def latest_project(ws: Path) -> Path:
    found = _newest((ws / "projects" / "working_copies").glob("*.kdenlive"))
    if found is None:
        sys.exit(f"No project in {ws}/projects/working_copies")
    return found


def _fn(tool):
    return getattr(tool, "fn", tool)


def _check(label: str, result: dict) -> dict:
    status = result.get("status", "?")
    print(f"[{status:>7}] {label:<34} {json.dumps(result.get('data') or result.get('message'), default=str)[:110]}")
    if status != "success":
        sys.exit(f"FAILED at {label}: {result}")
    return result.get("data") or {}


# (step slug, what to verify in Kdenlive)
CHECKLIST: list[tuple[str, str]] = []


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "kdenlive-check-pack").resolve()
    if out.exists():
        shutil.rmtree(out)
    media = out / "media"
    media.mkdir(parents=True)

    clip_a = make_test_clip(media / "a_bars.mp4", duration=4, fps=25, size=(640, 360), with_audio=True)
    clip_b = make_test_clip(media / "b_blue.mp4", duration=4, fps=25, size=(640, 360),
                            kind="color", color="blue", with_audio=True, freq=660)

    ws = str(_check("workspace_create", _fn(workspace_media.workspace_create)(
        title="Kdenlive check pack", media_root=str(media)))["workspace_root"])
    _check("project_create_working_copy", _fn(timeline_project.project_create_working_copy)(ws))
    step = 0

    def snapshot(slug: str, expect: str) -> None:
        nonlocal step
        step += 1
        proj = latest_project(Path(ws))
        dest = out / f"{step:02d}_{slug}.kdenlive"
        shutil.copy2(proj, dest)
        CHECKLIST.append((dest.name, expect))

    _check("clip_insert a", _fn(clips_nle.clip_insert)(ws, str(clip_a)))
    snapshot("single_clip", "Colour bars, 4 s, with a 440 Hz tone. No load dialog; clip in bin.")

    _check("clip_insert b", _fn(clips_nle.clip_insert)(ws, str(clip_b)))
    snapshot("two_clips", "Bars then solid blue (660 Hz). Both clips in the bin.")

    _check("clip_speed", _fn(clips_nle.clip_speed)(ws, 1, speed=2.0))
    snapshot("speed", "Blue clip plays at 2x (2 s instead of 4 s).")

    _check("transitions_apply_between", _fn(transitions.transitions_apply_between)(ws, 0))
    snapshot("dissolve", "Cross-dissolve bars -> blue around the 4 s cut (blue still 2x).")

    _check("audio_fade", _fn(clips_nle.audio_fade)(ws, 0, fade_type="in", duration_seconds=1.0))
    snapshot("audio_fade", "Tone fades in over the first second.")

    proj = latest_project(Path(ws))
    _check("effect_add", _fn(effects_catalog.effect_add)(
        ws, str(proj), 0, 0, "avfilter.gblur", '{"av.sigma": "12"}'))
    snapshot("effect_blur", "Bars clip is visibly blurred; effect listed in the effect stack.")

    proj = latest_project(Path(ws))
    _check("title_card_add", _fn(titles.title_card_add)(
        str(proj), "ForgeFrame check", subtitle="Kdenlive round trip", at_seconds=0.5))
    snapshot("title", "Lower-third title at 0.5 s; double-click opens it in the Titler.")

    lines = ["# Kdenlive check pack", "",
             "Open each project in order in Kdenlive. Record any dialog verbatim.", "",
             "| Project | Expect | Result |", "| --- | --- | --- |"]
    lines += [f"| `{name}` | {expect} | |" for name, expect in CHECKLIST]
    (out / "CHECKLIST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nPack written to {out} ({len(CHECKLIST)} projects). See CHECKLIST.md.")


if __name__ == "__main__":
    main()
