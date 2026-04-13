---
type: phase-spec-index
master_spec: "/home/caleb/Projects/ForgeFrame/docs/specs/2026-04-13-stack-presets.md"
date: 2026-04-13
sub_specs: 3
---

# Phase Specs — Effect Stack Presets for Kdenlive MCP

Refined from `docs/specs/2026-04-13-stack-presets.md`.

This feature is pure composition over the shipped Spec 1 (Keyframes), Spec 2 (Stack Ops), and Spec 3 (Effect Catalog). No changes to `patcher.py` or existing pipelines.

| Sub-Spec | Title | Dependencies | Phase Spec |
|----------|-------|--------------|------------|
| 1 | Preset Data Model + Storage I/O | none | [sub-spec-1-preset-data-model-and-storage-io.md](sub-spec-1-preset-data-model-and-storage-io.md) |
| 2 | Preset Operations Pipeline (Serialize, Validate, Apply, Promote) | 1 | [sub-spec-2-preset-operations-pipeline.md](sub-spec-2-preset-operations-pipeline.md) |
| 3 | MCP Tool Surface + Integration | 1, 2 | [sub-spec-3-mcp-tool-surface-integration.md](sub-spec-3-mcp-tool-surface-integration.md) |

## Interface Contracts Summary

- **Sub-Spec 1 → Sub-Spec 2:** `Preset`, `PresetEffect`, `ApplyHints` models + `save_preset`/`load_preset` I/O.
- **Sub-Spec 2 → Sub-Spec 3:** `serialize_clip_to_preset`, `validate_against_catalog`, `apply_preset`, `promote_to_vault` — pure pipeline functions wrapped by MCP tools.
- **External (shipped):** `pipelines.stack_ops.serialize_stack` / `apply_paste` (Sub-Spec 2 reuses); `pipelines.effect_catalog.find_by_service` (Sub-Spec 2 validates with); `workspace.create_snapshot` (Sub-Spec 3 calls on apply only); `workspace.read_manifest` for `vault_note_path` (Sub-Spec 3 reads on promote).

## Verification

- Build: `uv sync`
- Tests: `uv run pytest tests/ -v`
