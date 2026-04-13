---
title: "Effect Stack Presets Test Plan"
project: "ForgeFrame"
date: 2026-04-13
type: test-plan
tags:
  - test-plan
  - forgeframe
  - stack-presets
  - kdenlive-mcp
---

# Test Plan: Effect Stack Presets for Kdenlive MCP

## Meta
- Project: ForgeFrame (Workshop Video Brain)
- Date: 2026-04-13
- Author: Forge
- Spec Source: `docs/specs/2026-04-13-stack-presets.md`
- Scope: Three sub-specs covering Pydantic preset model + two-tier I/O, preset operations pipeline (serialize/validate/apply/promote), and the four MCP tool surfaces (`effect_stack_preset`, `effect_stack_apply`, `effect_stack_promote`, `effect_stack_list`).

## Prerequisites
- Python 3.12+, `uv sync` complete; PyYAML available.
- Specs 1-3 shipped (keyframes, stack ops, effect catalog).
- Fixture present: `tests/integration/fixtures/keyframe_project.kdenlive` (used by Sub-Spec 3).
- `WorkspaceManifest.vault_note_path` field available.
- Tests use ephemeral `tmp_path` workspace + vault roots; no shared state between scenarios except where marked Sequential.
- Test framework: `pytest` via `uv run pytest`.

## Coverage Strategy

Every `[MECHANICAL]`, `[STRUCTURAL]`, `[BEHAVIORAL]`, and `[INTEGRATION]` tagged criterion across the three sub-specs maps to at least one scenario. Coverage emphasis as requested:

- **Preset I/O** (Sub-Spec 1): YAML round-trip, workspace/vault path resolution, vault fallback, malformed-file tolerance during list, markdown frontmatter + body rendering, wikilink embedding.
- **Preset operations** (Sub-Spec 2): `serialize_clip_to_preset` keyframe preservation, strict catalog validation, `apply_preset` with mode override, `promote_to_vault` with/without source video note.
- **MCP** (Sub-Spec 3): tool registration as callables, end-to-end save -> apply, catalog-validation rejection, mode override, vault-root-missing error, snapshot IDs only on apply (not save or promote).

## Scenarios

| ID    | Title                                                                                            | Area     | Priority | Sequential | Tag(s)               |
|-------|--------------------------------------------------------------------------------------------------|----------|----------|------------|----------------------|
| IO-01 | Module exports Preset/PresetEffect/ApplyHints + save/load/list/resolve_vault_root                | I/O      | High     | No         | STRUCTURAL           |
| IO-02 | `Preset` model field shape + defaults                                                            | I/O      | High     | No         | STRUCTURAL           |
| IO-03 | `PresetEffect` model field shape + defaults                                                      | I/O      | High     | No         | STRUCTURAL           |
| IO-04 | `ApplyHints` model field shape + defaults (Literal stack_order)                                  | I/O      | High     | No         | STRUCTURAL           |
| IO-05 | `save_preset(scope="workspace")` writes YAML to `<ws>/stacks/<name>.yaml`, creates dir           | I/O      | High     | No         | BEHAVIORAL           |
| IO-06 | `save_preset(scope="vault")` writes markdown with frontmatter + body to vault path               | I/O      | High     | No         | BEHAVIORAL           |
| IO-07 | `load_preset` workspace-first, falls back to vault                                               | I/O      | High     | No         | BEHAVIORAL           |
| IO-08 | `load_preset` missing in both tiers raises `FileNotFoundError` listing both paths                | I/O      | High     | No         | BEHAVIORAL           |
| IO-09 | `list_presets` enumerates both tiers, returns expected dict shape                                | I/O      | High     | No         | BEHAVIORAL           |
| IO-10 | `list_presets` skips malformed files into `skipped` list with `{path,error}`                     | I/O      | High     | No         | BEHAVIORAL           |
| IO-11 | `resolve_vault_root` precedence: project json -> forge.json -> None                              | I/O      | High     | No         | BEHAVIORAL           |
| IO-12 | YAML round-trip preserves effects.xml byte-identical                                             | I/O      | High     | No         | BEHAVIORAL           |
| IO-13 | Vault markdown body renders header/description/tags/effect-table + wikilink when source provided | I/O      | High     | No         | BEHAVIORAL           |
| IO-14 | `tests/unit/test_stack_presets_io.py` passes                                                     | I/O      | High     | No         | MECHANICAL           |
| OP-01 | Pipeline exports serialize/validate/apply/promote/render_vault_body                              | Ops      | High     | No         | STRUCTURAL           |
| OP-02 | `serialize_clip_to_preset` signature returns a `Preset`                                          | Ops      | High     | No         | STRUCTURAL           |
| OP-03 | `validate_against_catalog(strict=True)` raises; non-strict returns list                          | Ops      | High     | No         | STRUCTURAL           |
| OP-04 | `apply_preset` returns documented dict keys                                                      | Ops      | High     | No         | STRUCTURAL           |
| OP-05 | `promote_to_vault` signature + return path                                                       | Ops      | High     | No         | STRUCTURAL           |
| OP-06 | `serialize_clip_to_preset` 3-filter clip -> 3 PresetEffects, xml byte-equal to source            | Ops      | High     | No         | BEHAVIORAL           |
| OP-07 | `validate_against_catalog` empty list when all services known                                    | Ops      | High     | No         | BEHAVIORAL           |
| OP-08 | `validate_against_catalog(strict=True)` raises ValueError naming bad service                     | Ops      | High     | No         | BEHAVIORAL           |
| OP-09 | `apply_preset` mode_override=None uses preset.apply_hints.stack_order; "replace" overrides       | Ops      | High     | No         | BEHAVIORAL           |
| OP-10 | `apply_preset` writes correct number of filters (verified via list_effects)                      | Ops      | High     | No         | BEHAVIORAL           |
| OP-11 | `apply_preset` preserves keyframe rect property byte-exact across clips                          | Ops      | High     | No         | BEHAVIORAL           |
| OP-12 | `apply_preset` response surfaces blend/track/required hints verbatim                             | Ops      | High     | No         | BEHAVIORAL           |
| OP-13 | `promote_to_vault` with source_video_note_path embeds `[[My Video]]` wikilink                    | Ops      | High     | No         | BEHAVIORAL           |
| OP-14 | `promote_to_vault` with source=None omits "Referenced from" line                                 | Ops      | High     | No         | BEHAVIORAL           |
| OP-15 | `promote_to_vault` missing workspace preset raises `FileNotFoundError`                           | Ops      | High     | No         | BEHAVIORAL           |
| OP-16 | `tests/unit/test_stack_presets_ops.py` passes                                                    | Ops      | High     | No         | MECHANICAL           |
| MCP-01| `server/tools.py` registers all four tools                                                       | MCP      | High     | No         | STRUCTURAL           |
| MCP-02| `effect_stack_preset` signature/envelope shape                                                   | MCP      | High     | No         | STRUCTURAL           |
| MCP-03| `effect_stack_apply` signature/envelope shape                                                    | MCP      | High     | No         | STRUCTURAL           |
| MCP-04| `effect_stack_promote` signature/envelope shape                                                  | MCP      | High     | No         | STRUCTURAL           |
| MCP-05| `effect_stack_list` signature/envelope shape                                                     | MCP      | High     | No         | STRUCTURAL           |
| MCP-06| All four tools importable as callables from `server.tools`                                       | MCP      | High     | No         | INTEGRATION          |
| MCP-07| `effect_stack_preset` against fixture writes valid YAML parsing back to Preset                   | MCP      | High     | Yes        | BEHAVIORAL           |
| MCP-08| `effect_stack_preset` rejects unknown `mlt_service` with `_err` naming the service               | MCP      | High     | No         | BEHAVIORAL           |
| MCP-09| End-to-end preset -> apply -> list_effects matches; reparse preserves keyframes byte-exact       | MCP      | High     | Yes        | BEHAVIORAL/INTEGRATION |
| MCP-10| `effect_stack_apply` with `mode="replace"` overrides preset stack_order                          | MCP      | High     | Yes        | BEHAVIORAL           |
| MCP-11| `effect_stack_apply` name not found in either tier returns `_err` listing both paths             | MCP      | High     | No         | BEHAVIORAL           |
| MCP-12| `effect_stack_apply` response includes blend/track/required hints verbatim                       | MCP      | High     | Yes        | BEHAVIORAL           |
| MCP-13| Snapshot IDs: `apply` only mutates project; `preset` and `promote` produce no snapshot           | MCP      | High     | Yes        | BEHAVIORAL           |
| MCP-14| `effect_stack_promote` embeds `[[My Vid]]` wikilink from manifest `vault_note_path`              | MCP      | High     | No         | BEHAVIORAL           |
| MCP-15| `effect_stack_promote` returns `_err` with documented message when vault root unconfigured       | MCP      | High     | No         | BEHAVIORAL           |
| MCP-16| `effect_stack_list(scope="all")` returns presets from both tiers with scope labels               | MCP      | High     | Yes        | BEHAVIORAL           |
| MCP-17| `tests/integration/test_stack_presets_mcp_tools.py` passes                                      | MCP      | High     | No         | MECHANICAL           |
| MCP-18| Full suite `uv run pytest tests/ -v` passes with no regressions                                  | MCP      | High     | No         | MECHANICAL           |

See individual scenario files in this directory for full steps and expected results.

## Coverage Summary
- Total scenarios: 48
- I/O scenarios (Sub-Spec 1): 14 -- covers 4 STRUCTURAL + 7 BEHAVIORAL + 1 MECHANICAL (consolidated 1 STRUCTURAL `Preset` field check across IO-02..04)
- Operations scenarios (Sub-Spec 2): 16 -- covers 5 STRUCTURAL + 10 BEHAVIORAL + 1 MECHANICAL
- MCP scenarios (Sub-Spec 3): 18 -- covers 5 STRUCTURAL + 1 INTEGRATION + 9 BEHAVIORAL + 2 MECHANICAL (plus integration end-to-end blend on MCP-09)
- Sequential scenarios: 6 (project-mutating MCP flows -- MCP-07, 09, 10, 12, 13, 16)

## Tag Cross-Reference (Sub-Spec -> tagged AC -> scenario)

**Sub-Spec 1 (Preset I/O)**
- STRUCTURAL exports -> IO-01
- STRUCTURAL Preset/PresetEffect/ApplyHints fields -> IO-02, IO-03, IO-04
- BEHAVIORAL save workspace -> IO-05
- BEHAVIORAL save vault -> IO-06
- BEHAVIORAL load fallback -> IO-07
- BEHAVIORAL load missing -> IO-08
- BEHAVIORAL list both tiers -> IO-09
- BEHAVIORAL list malformed skip -> IO-10
- BEHAVIORAL resolve_vault_root -> IO-11
- BEHAVIORAL YAML round-trip -> IO-12
- BEHAVIORAL vault markdown body + wikilink -> IO-13
- MECHANICAL pytest -> IO-14

**Sub-Spec 2 (Preset Ops)**
- STRUCTURAL exports -> OP-01
- STRUCTURAL serialize signature -> OP-02
- STRUCTURAL validate signature -> OP-03
- STRUCTURAL apply signature -> OP-04
- STRUCTURAL promote signature -> OP-05
- BEHAVIORAL serialize 3-filter byte-equal -> OP-06
- BEHAVIORAL validate empty when all known -> OP-07
- BEHAVIORAL validate strict raises -> OP-08
- BEHAVIORAL apply mode override -> OP-09
- BEHAVIORAL apply correct filter count -> OP-10
- BEHAVIORAL apply keyframe preservation -> OP-11
- BEHAVIORAL apply hints surfaced -> OP-12
- BEHAVIORAL promote with source -> OP-13
- BEHAVIORAL promote without source -> OP-14
- BEHAVIORAL promote missing source -> OP-15
- MECHANICAL pytest -> OP-16

**Sub-Spec 3 (MCP)**
- STRUCTURAL register four tools -> MCP-01
- STRUCTURAL preset signature -> MCP-02
- STRUCTURAL apply signature -> MCP-03
- STRUCTURAL promote signature -> MCP-04
- STRUCTURAL list signature -> MCP-05
- INTEGRATION callable imports -> MCP-06
- BEHAVIORAL fixture preset write -> MCP-07
- BEHAVIORAL bad mlt_service rejection -> MCP-08
- BEHAVIORAL end-to-end preset->apply + keyframe byte-exact -> MCP-09
- BEHAVIORAL apply mode override -> MCP-10
- BEHAVIORAL apply name-not-found -> MCP-11
- BEHAVIORAL apply hints surfaced -> MCP-12
- BEHAVIORAL snapshot only on apply -> MCP-13
- BEHAVIORAL promote wikilink from manifest -> MCP-14
- BEHAVIORAL promote vault-root-unconfigured -> MCP-15
- BEHAVIORAL list scope=all both tiers -> MCP-16
- MECHANICAL mcp pytest -> MCP-17
- MECHANICAL full suite no regressions -> MCP-18

## Next Step
Run `/forge-test-run docs/tests/2026-04-13-stack-presets/test-plan.md` to execute all scenarios.
