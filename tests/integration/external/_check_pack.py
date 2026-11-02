"""Shared builder for the cumulative Kdenlive differential check pack."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from tests._testkit import make_test_clip
from workshop_video_brain.edit_mcp.server.tools import (
    clips_nle, effects_catalog, timeline_project, transitions, workspace_media,
)
from workshop_video_brain.edit_mcp.server.bundles import titles
from workshop_video_brain.edit_mcp.server.tools_helpers import latest_project as _newest


@dataclass(frozen=True)
class PackStep:
    index: int
    slug: str
    path: Path
    expect: str


def latest_project(ws: Path) -> Path:
    found = _newest((ws / "projects" / "working_copies").glob("*.kdenlive"))
    if found is None:
        raise RuntimeError(f"No project in {ws}/projects/working_copies")
    return found


def _fn(tool):
    return getattr(tool, "fn", tool)


def _check(label: str, result: dict) -> dict:
    status = result.get("status", "?")
    print(f"[{status:>7}] {label:<34} {json.dumps(result.get('data') or result.get('message'), default=str)[:110]}")
    if status != "success":
        raise RuntimeError(f"FAILED at {label}: {result}")
    return result.get("data") or {}


def build_check_pack(out: Path) -> list[PackStep]:
    out = Path(out).resolve()
    media = out / "media"
    media.mkdir(parents=True)
    clip_a = make_test_clip(media / "a_bars.mp4", duration=4, fps=25, size=(640, 360), with_audio=True)
    clip_b = make_test_clip(media / "b_blue.mp4", duration=4, fps=25, size=(640, 360),
                            kind="color", color="blue", with_audio=True, freq=660)
    ws = str(_check("workspace_create", _fn(workspace_media.workspace_create)(
        title="Kdenlive check pack", media_root=str(media))) ["workspace_root"])
    _check("project_create_working_copy", _fn(timeline_project.project_create_working_copy)(ws))
    steps: list[PackStep] = []

    def snapshot(slug: str, expect: str) -> None:
        index = len(steps) + 1
        project = latest_project(Path(ws))
        dest = out / f"{index:02d}_{slug}.kdenlive"
        shutil.copy2(project, dest)
        steps.append(PackStep(index, slug, dest, expect))

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
    project = latest_project(Path(ws))
    _check("effect_add", _fn(effects_catalog.effect_add)(
        ws, str(project), 0, 0, "avfilter.gblur", '{"av.sigma": "12"}'))
    snapshot("effect_blur", "Bars clip is visibly blurred; effect listed in the effect stack.")
    project = latest_project(Path(ws))
    _check("title_card_add", _fn(titles.title_card_add)(
        str(project), "ForgeFrame check", subtitle="Kdenlive round trip", at_seconds=0.5))
    snapshot("title", "Lower-third title at 0.5 s; double-click opens it in the Titler.")
    return steps


def write_checklist(out: Path, steps: list[PackStep]) -> Path:
    out = Path(out)
    lines = ["# Kdenlive check pack", "",
             "Open each project in order in Kdenlive. Record any dialog verbatim.", "",
             "| Project | Expect | Result |", "| --- | --- | --- |"]
    lines += [f"| `{step.path.name}` | {step.expect} | |" for step in steps]
    path = out / "CHECKLIST.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
