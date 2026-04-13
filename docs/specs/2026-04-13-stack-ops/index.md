---
type: phase-spec-index
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-stack-ops.md"
date: 2026-04-13
sub_specs: 3
---

# Phase Specs — Effect Stack Operations for Kdenlive MCP

Refined from `docs/specs/2026-04-13-stack-ops.md`.

| Sub-Spec | Title | Dependencies | Phase Spec |
|----------|-------|--------------|------------|
| 1 | Patcher Stack-Mutation Extensions | none | [sub-spec-1-patcher-stack-mutation-extensions.md](sub-spec-1-patcher-stack-mutation-extensions.md) |
| 2 | Stack-Ops Pipeline Module | 1 | [sub-spec-2-stack-ops-pipeline-module.md](sub-spec-2-stack-ops-pipeline-module.md) |
| 3 | MCP Tool Surface + Integration | 1, 2 | [sub-spec-3-mcp-tool-surface-integration.md](sub-spec-3-mcp-tool-surface-integration.md) |

## Execution Notes

- Sub-specs MUST be executed in order (1 → 2 → 3) — Sub-Spec 2 imports patcher functions from Sub-Spec 1; Sub-Spec 3 imports from both.
- Spec 1 (Keyframes) shipped at commit `2bb76d6` — `_iter_clip_filters`, `list_effects`, `get_effect_property`, `set_effect_property` are present and MUST NOT be modified.
- All three sub-specs are additive only.
- The integration fixture `tests/integration/fixtures/keyframe_project.kdenlive` is reused; no new fixtures.

## Interface Contract Summary

| Layer | Provides | Consumed By |
|-------|----------|-------------|
| Patcher (Sub-Spec 1) | `insert_effect_xml`, `remove_effect`, `reorder_effects` | Pipeline (Sub-Spec 2) |
| Pipeline (Sub-Spec 2) | `serialize_stack`, `deserialize_stack`, `apply_paste`, `reorder_stack` | MCP tools (Sub-Spec 3) |
| MCP tools (Sub-Spec 3) | `effects_copy`, `effects_paste`, `effect_reorder` | LLM clients |

## Cross-Cutting Constraints

- Reuse `_iter_clip_filters` for read paths — no duplicate XML traversal.
- Snapshot before every write call (`effects_paste`, `effect_reorder`). `effects_copy` is read-only and does not snapshot.
- Preserve keyframe animation strings byte-exact through copy → paste; verified end-to-end in Sub-Spec 3's integration test.
- All MCP-layer errors flow through `_err` envelopes; no exceptions escape `@mcp.tool()` boundaries.
