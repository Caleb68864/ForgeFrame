---
type: phase-spec-index
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-keyframe-tool.md"
date: 2026-04-13
sub_specs: 4
---

# Phase Specs — Keyframe Tool for Kdenlive MCP

Refined from `docs/specs/2026-04-13-keyframe-tool.md`.

| Sub-Spec | Title | Dependencies | Phase Spec |
|----------|-------|--------------|------------|
| 1 | Patcher Effect-Property Extensions | none | [sub-spec-1-patcher-effect-property-extensions.md](sub-spec-1-patcher-effect-property-extensions.md) |
| 2 | Keyframes Pipeline Module | none | [sub-spec-2-keyframes-pipeline-module.md](sub-spec-2-keyframes-pipeline-module.md) |
| 3 | Effect-Find Module + Workspace Config Extension | none (soft-depends on 1 for `list_effects`, on 2 for `VALID_EASE_FAMILIES`) | [sub-spec-3-effect-find-and-workspace-config.md](sub-spec-3-effect-find-and-workspace-config.md) |
| 4 | MCP Tool Surface + Integration | 1, 2, 3 | [sub-spec-4-mcp-tool-surface-and-integration.md](sub-spec-4-mcp-tool-surface-and-integration.md) |

## Execution notes for workers

- Sub-specs 1 and 2 are fully independent and can run in parallel.
- Sub-spec 3 soft-depends on 1 (reuses `list_effects`) and 2 (reuses `VALID_EASE_FAMILIES`). It can be started in parallel with 1/2 if the worker inlines a TODO fallback for the missing dependency, but merging is simpler after 1 and 2 land.
- Sub-spec 4 hard-depends on 1, 2, and 3 all being merged before implementation.

## Key interface contracts across the phase

- `patcher.list_effects(project, clip_ref) -> list[{index, mlt_service, kdenlive_id, properties}]` — produced by 1, consumed by 3 and 4.
- `patcher.{get,set}_effect_property(project, clip_ref, effect_index, property, [value])` — produced by 1, consumed by 4.
- `keyframes.{build,parse}_keyframe_string`, `merge_keyframes`, `normalize_time`, `Keyframe` — produced by 2, consumed by 4.
- `keyframes.VALID_EASE_FAMILIES` — produced by 2, consumed by 3's `Literal` type.
- `Workspace.keyframe_defaults.ease_family: str` — produced by 3, consumed by 4.
- `effect_find.find(project, clip_ref, name) -> int` — produced by 3, consumed by 4.

## Build / test commands

- Tests: `uv run pytest tests/ -v`
- No separate build step (pure Python, `uv`-managed).
- Python 3.12+ required.
