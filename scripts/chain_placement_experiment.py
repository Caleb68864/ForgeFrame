#!/usr/bin/env python
"""Prompt 24 experiment: does Kdenlive need one producer per timeline placement?

Builds scenarios S1-S4 (see tests/integration/external/_chain_layout.py) in the
layout variants V0 (shared, our output), V1 (per track), V2 (per placement),
V1u / V2u (plus a shared kdenlive:control_uuid), renders every file with melt
and with ``kdenlive --render``, measures each placement's colour, the duration
and the audio level, and writes results.json, RESULTS.md and CHECKLIST.md.

Usage:
    uv run python scripts/chain_placement_experiment.py [OUT_DIR]
    uv run python scripts/chain_placement_experiment.py --analyze-resaved [OUT_DIR]

OUT_DIR defaults to ./kdenlive-chain-experiment (git-ignored scratch).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests._testkit import with_display  # noqa: E402
from tests.integration.external import _chain_layout as layout  # noqa: E402
from tests.integration.external._oracle import kdenlive_render, mean_volume_db, probe  # noqa: E402
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import DEFAULT_TIMEOUT_SECONDS  # noqa: E402

_FLAGS = ("missing", "removed", "invalid", "corrupt")
_RENDER_TIMEOUT = min(600, DEFAULT_TIMEOUT_SECONDS)


def _flags(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines()
            if any(word in line.lower() for word in _FLAGS) and "Duplicate" not in line][:10]


def _measure(video: Path, expected, frames: int) -> dict:
    if not video.exists():
        return {"ok": False, "error": "no output"}
    observed = [layout.frame_colour(video, frame) for frame, _ in expected]
    try:
        db = mean_volume_db(video)
    except Exception as exc:  # noqa: BLE001 -- no audio stream counts as silence
        db = None
        print(f"  volumedetect: {exc}")
    duration = probe(video).duration
    colours_ok = observed == [colour for _, colour in expected]
    audio_ok = db is not None and db > -60
    return {"ok": colours_ok and audio_ok, "colours": observed, "duration": duration, "mean_db": db,
            "expected_duration": frames / 25.0}


def _render_melt(project: Path, out: Path) -> tuple[Path, str]:
    proc = subprocess.run(with_display(["melt", str(project), "-consumer", f"avformat:{out}",
                                        "vcodec=libx264", "acodec=aac", "terminate_on_pause=1"]),
                          capture_output=True, text=True, timeout=_RENDER_TIMEOUT)
    (out.with_suffix(".log")).write_text(proc.stderr, encoding="utf-8")
    return out, proc.stderr


def _render_kdenlive(project: Path, out: Path) -> tuple[Path, str]:
    try:
        kdenlive_render(project, out, timeout=_RENDER_TIMEOUT)
        return out, ""
    except RuntimeError as exc:
        (out.with_suffix(".log")).write_text(str(exc), encoding="utf-8")
        return out, str(exc)


def run(out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    media = layout.make_media(out_dir / "media_rgbw.mp4")
    scenarios = layout.build_scenarios(media)
    results = []
    for name, scenario in scenarios.items():
        for variant in layout.VARIANTS:
            stem = f"{name}_{variant}"
            project = out_dir / f"{stem}.kdenlive"
            project.write_text(layout.make_variant(scenario["xml"], variant), encoding="utf-8")
            row = {"file": project.name, "scenario": name, "variant": variant,
                   "expected": [c for _, c in scenario["expected"]]}
            for engine, render in (("melt", _render_melt), ("kdenlive", _render_kdenlive)):
                print(f"{stem}: {engine}")
                try:
                    video, stderr = render(project, out_dir / f"{stem}_{engine}.mp4")
                    row[engine] = {**_measure(video, scenario["expected"], scenario["frames"]),
                                   "flags": _flags(stderr)}
                except Exception as exc:  # noqa: BLE001 -- a failed render is a result
                    row[engine] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
            results.append(row)
            (out_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    _write_reports(out_dir, results)
    print(f"\nWrote {len(results)} rows to {out_dir / 'RESULTS.md'}")


def _cell(result: dict) -> str:
    if "colours" not in result:
        return f"FAIL ({result.get('error', '?')})"
    db = "-" if result["mean_db"] is None else f"{result['mean_db']:.0f} dB"
    verdict = "ok" if result["ok"] else "**FAIL**"
    return f"{verdict}: {', '.join(result['colours'])}; {result['duration']:.2f} s; {db}"


def _write_reports(out_dir: Path, results: list[dict]) -> None:
    lines = ["# Producer layout experiment (prompt 24)", "",
             "| File | Expected | melt | kdenlive --render |", "| --- | --- | --- | --- |"]
    lines += [f"| `{r['file']}` | {', '.join(r['expected'])} | {_cell(r['melt'])} | {_cell(r['kdenlive'])} |"
              for r in results]
    (out_dir / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    check = ["# Kdenlive GUI check (prompt 24)", "",
             "For each file, in Kdenlive 26.08: open it; copy any dialog text verbatim; count the clips on each",
             "track against the expected list; count bin clips (expected: one per media file, duplicates are a",
             "defect); look in Project Notes for \"removed\" warnings; then **Save As** `<name>_resaved.kdenlive`",
             "in this folder. Afterwards run `uv run python scripts/chain_placement_experiment.py --analyze-resaved`.",
             "", "| File | Expected clips (colour per placement) | Dialog | Clips per track | Bin clips | Notes |",
             "| --- | --- | --- | --- | --- | --- |"]
    check += [f"| `{r['file']}` | {', '.join(r['expected'])} | | | | |" for r in results]
    (out_dir / "CHECKLIST.md").write_text("\n".join(check) + "\n", encoding="utf-8")


def analyze_resaved(out_dir: Path) -> None:
    files = sorted(out_dir.glob("*_resaved.kdenlive"))
    if not files:
        print(f"No *_resaved.kdenlive files in {out_dir} yet (see CHECKLIST.md).")
        return
    for path in files:
        counts = layout.count_layout(path.read_text(encoding="utf-8"))
        media = {r: ids for r, ids in counts["elements_per_resource"].items() if r.endswith(".mp4")}
        print(f"{path.name}: elements per media {media}")
        for playlist, producers in counts["producers_per_playlist"].items():
            if producers:
                print(f"    {playlist}: {producers}")


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--analyze-resaved"]
    out = Path(args[0] if args else "kdenlive-chain-experiment").resolve()
    if "--analyze-resaved" in sys.argv:
        analyze_resaved(out)
    else:
        run(out)


if __name__ == "__main__":
    main()
