---
type: phase-spec-index
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-effect-wrappers.md"
date: 2026-04-13
sub_specs: 3
---

# Phase Specs — Effect Wrappers + Presets for Kdenlive MCP

Refined from `docs/specs/2026-04-13-effect-wrappers.md`.

| Sub-Spec | Title | Dependencies | Phase Spec |
|----------|-------|--------------|------------|
| 1 | Wrapper Generator + Tool Helpers | none | [sub-spec-1-wrapper-generator-tool-helpers.md](sub-spec-1-wrapper-generator-tool-helpers.md) |
| 2 | Preset Bundles | 1 | [sub-spec-2-preset-bundles.md](sub-spec-2-preset-bundles.md) |
| 3 | Semantic Reorder Wrappers + Integration | 1, 2 | [sub-spec-3-semantic-reorder-wrappers-integration.md](sub-spec-3-semantic-reorder-wrappers-integration.md) |

## Critical Issues Discovered During Prep

1. **`frei0r.exposer` is MISSING from the catalog.** The master spec's glitch-stack 5-service list cannot be satisfied as written. Sub-Spec 2 substitutes `avfilter.exposure` (catalog line 942). Worker must confirm substitution before implementation or escalate. Triggers master-spec escalation on line 32 / 210.

2. **`clip_split` signature is incompatible with `flash_cut_montage` as written in the master spec.** Actual signature `clip_split(workspace_path, clip_index, split_at_seconds)` uses global clip index on playlist 0 only and cannot be called with `(track, clip)` addressing. The MCP tool also reloads/saves the project each call, which is incorrect for batched use inside another tool. Sub-Spec 2 resolves this by dropping to the Python-level `SplitClip` + `patch_project` path that `clip_split` itself uses internally. Triggers master-spec escalation on line 33 / 211.

3. **Refactor safety for Sub-Spec 1 helper extraction** — 60+ existing `@mcp.tool()` functions in `server/tools.py` use the helpers being moved. Sub-Spec 1 mandates a regression-gate run of `uv run pytest tests/ -v` immediately after the extract-and-import refactor, before any generator work proceeds.
