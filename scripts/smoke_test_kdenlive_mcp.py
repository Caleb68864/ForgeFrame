#!/usr/bin/env python
"""End-to-end smoke test exercising all 7 Kdenlive MCP specs.

Creates a fresh working copy of the smoke-test project, chains 10+ MCP
tool calls across every shipped spec, and produces an output .kdenlive
the user can open in Kdenlive 25.x to verify visually.

Usage:
    uv run python scripts/smoke_test_kdenlive_mcp.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "workshop-video-brain" / "src"))

from workshop_video_brain.edit_mcp.server import tools  # noqa: E402

WS = REPO / "smoke-test" / "smoke-test-video"
PROJECT_FILE = "projects/working_copies/test_roundtrip.kdenlive"
SMOKE_OUT = "projects/working_copies/smoke_test_full.kdenlive"


def _print(label: str, result: dict) -> None:
    status = result.get("status", "?")
    data = result.get("data") or result.get("message")
    print(f"[{status:>7}] {label:<40} {json.dumps(data, default=str)[:120]}")
    if status != "success":
        sys.exit(f"FAILED at {label}: {result}")


def main() -> None:
    # Fresh working copy from a clean source project
    src = WS / PROJECT_FILE
    dst = WS / SMOKE_OUT
    if not src.exists():
        sys.exit(f"Source project not found: {src}")
    shutil.copy2(src, dst)
    print(f"Fresh working copy: {dst}\n")

    ws = str(WS)
    pf = SMOKE_OUT
    t, c = 1, 0

    print("=" * 70)
    print("SPEC 3 — Catalog introspection")
    print("=" * 70)
    _print("effect_info('dust')", tools.effect_info(name="dust"))

    print("\n" + "=" * 70)
    print("SPEC 7 — Effect wrappers + presets")
    print("=" * 70)
    _print("effect_glitch_stack", tools.effect_glitch_stack(
        workspace_path=ws, project_file=pf, track=t, clip=c, intensity=0.6
    ))
    _print("effect_fade", tools.effect_fade(
        workspace_path=ws, project_file=pf, track=t, clip=c,
        fade_in_frames=15, fade_out_frames=15, easing="ease_in_out"
    ))

    # Check how many filters are on the clip now
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import list_effects
    proj = parse_project(dst)
    filters = list_effects(proj, (t, c))
    print(f"  → Clip ({t},{c}) now has {len(filters)} filters")

    print("\n" + "=" * 70)
    print("SPEC 2 — Stack ops (copy filters from this clip)")
    print("=" * 70)
    copy_result = tools.effects_copy(
        workspace_path=ws, project_file=pf, track=t, clip=c
    )
    _print("effects_copy", copy_result)

    print("\n" + "=" * 70)
    print("SPEC 4 — Stack presets (BEFORE masking — rotoscoping not in catalog)")
    print("=" * 70)
    _print("effect_stack_preset", tools.effect_stack_preset(
        workspace_path=ws, project_file=pf, track=t, clip=c,
        name="smoke-test-preset",
        description="End-to-end smoke test preset",
        tags=json.dumps(["smoke-test", "demo"]),
    ))
    _print("effect_stack_list", tools.effect_stack_list(
        workspace_path=ws, scope="workspace"
    ))

    print("\n" + "=" * 70)
    print("SPEC 5 — Masking")
    print("=" * 70)
    _print("mask_set_shape(rect)", tools.mask_set_shape(
        workspace_path=ws, project_file=pf, track=t, clip=c,
        shape="rect",
        bounds=json.dumps([0.2, 0.2, 0.6, 0.6]),
        feather=5,
        alpha_operation="add",
    ))

    print("\n" + "=" * 70)
    print("SPEC 7 — Semantic reorder")
    print("=" * 70)
    _print("move_to_top(eff=5)", tools.move_to_top(
        workspace_path=ws, project_file=pf, track=t, clip=c, effect_index=5
    ))

    print("\n" + "=" * 70)
    print("SPEC 1 — Keyframe animation (on the transform filter now at top)")
    print("=" * 70)
    kfs = json.dumps([
        {"frame": 0, "value": [0, 0, 1920, 1080, 1.0], "easing": "linear"},
        {"frame": 30, "value": [200, 100, 1920, 1080, 0.5], "easing": "ease_in_out"},
        {"frame": 60, "value": [0, 0, 1920, 1080, 1.0], "easing": "ease_out"},
    ])
    _print("effect_keyframe_set_rect", tools.effect_keyframe_set_rect(
        workspace_path=ws, project_file=pf, track=t, clip=c,
        effect_index=0, property="rect", keyframes=kfs, mode="replace"
    ))

    print("\n" + "=" * 70)
    print("SPEC 6 — Composite blend modes")
    print("=" * 70)
    _print("composite_set(screen)", tools.composite_set(
        workspace_path=ws, project_file=pf,
        track_a=0, track_b=1, start_frame=0, end_frame=120,
        blend_mode="screen",
    ))

    print("\n" + "=" * 70)
    print("Final verification")
    print("=" * 70)
    proj = parse_project(dst)
    filters = list_effects(proj, (t, c))
    print(f"Final clip ({t},{c}) filter count: {len(filters)}")
    for i, f in enumerate(filters):
        label = f.get("kdenlive_id") or f.get("mlt_service", "?")
        print(f"  [{i}] {label}")

    print(f"\n✅ Smoke test complete. Output: {dst}")
    print(f"   Open in Kdenlive 25.x to verify visually.")


if __name__ == "__main__":
    main()
