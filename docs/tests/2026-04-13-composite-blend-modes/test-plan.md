---
title: "Composite Blend Modes Test Plan"
project: "Workshop Video Brain (ForgeFrame)"
date: 2026-04-13
type: test-plan
tags:
  - test-plan
  - forgeframe
  - compositing
---

# Test Plan: Composite Blend Modes for Kdenlive MCP

## Meta
- Project: Workshop Video Brain (ForgeFrame)
- Date: 2026-04-13
- Author: Forge
- Spec Source: docs/specs/2026-04-13-composite-blend-modes.md
- Scope: Spec 6 -- Composite Blend Modes (`apply_composite`, `composite_set` MCP tool, `apply_pip` rewire)

## Prerequisites

- Python 3.12+, uv environment already installed (`uv sync`).
- Pytest execution via `uv run pytest`.
- Fixture project file: `tests/fixtures/projects/sample_tutorial.kdenlive` (parse/serialize roundtrip capable). Where the spec references `keyframe_project.kdenlive` use the analogous fixture present under `tests/integration/fixtures/` or `tests/fixtures/projects/`.
- Kdenlive effect XML available at `/usr/share/kdenlive/effects/composite.xml` on the dev machine (for Sub-Spec 1 discovery; tests should NOT depend on this file at runtime -- the `BLEND_MODE_TO_MLT` table is hardcoded in the module).
- Tests are self-contained: scenarios set up their own `KdenliveProject` objects or copy fixture files into `tmp_path`.
- Test framework detected: pytest (existing `tests/unit/` and `tests/integration/` structure). Execution tool: `bash` (`uv run pytest <path> -v`).
- No network, GUI, or real Kdenlive process required.

## Scope Mapping to Spec Tags

This plan enumerates one or more scenarios for every acceptance-criterion tag in the spec. Tags are referenced in each scenario's `Covers` field.

Sub-Spec 1 tags (`pipelines/compositing.py` + `tests/unit/test_compositing_blend_modes.py`):
- `[STRUCTURAL]` Worker inspects `/usr/share/kdenlive/effects/composite.xml` (property-name discovery).
- `[STRUCTURAL]` `BLEND_MODES` frozenset of exactly 11 names.
- `[STRUCTURAL]` `BLEND_MODE_TO_MLT` dict covering each mode.
- `[STRUCTURAL]` `apply_composite(...)` exported with specified signature.
- `[BEHAVIORAL]` `apply_composite(blend_mode="screen")` emits `AddComposition` with correct MLT key/value.
- `[BEHAVIORAL]` Default geometry when `geometry=None`.
- `[BEHAVIORAL]` Passed-through geometry preserved.
- `[BEHAVIORAL]` Unknown `blend_mode` -> `ValueError`.
- `[BEHAVIORAL]` `track_a == track_b` -> `ValueError`.
- `[BEHAVIORAL]` `end_frame <= start_frame` -> `ValueError`.
- `[BEHAVIORAL]` `apply_composite` does not mutate caller's project.
- `[MECHANICAL]` unit test file passes.

Sub-Spec 2 tags (`server/tools.py` + integration/regression tests):
- `[STRUCTURAL]` `composite_set` registered via `@mcp.tool()`.
- `[STRUCTURAL]` `composite_set` signature exact.
- `[STRUCTURAL]` `composite_set` return shape exact.
- `[STRUCTURAL]` `apply_pip` signature unchanged, delegates to `apply_composite`.
- `[STRUCTURAL]` `apply_wipe` signature + body unchanged.
- `[STRUCTURAL]` `composite_pip`/`composite_wipe` MCP signatures unchanged.
- `[INTEGRATION]` All three tools importable as callables from `workshop_video_brain.edit_mcp.server.tools`.
- `[BEHAVIORAL]` End-to-end screen blend written + re-parsed.
- `[BEHAVIORAL]` `destination_in` writes correct MLT value from mapping.
- `[BEHAVIORAL]` Unknown mode at MCP level -> `_err` listing 11 modes.
- `[BEHAVIORAL]` `track_a == track_b` at MCP -> `_err`.
- `[BEHAVIORAL]` `end_frame <= start_frame` at MCP -> `_err`.
- `[BEHAVIORAL]` Snapshot created on disk.
- `[BEHAVIORAL]` Custom geometry written verbatim.
- `[BEHAVIORAL]` `apply_pip` byte-identical regression.
- `[MECHANICAL]` Sub-Spec 2 tests pass.
- `[MECHANICAL]` Full suite `uv run pytest tests/ -v` passes.

Also covered: edge cases from spec `## Edge Cases` (case-sensitivity, non-adjacent tracks, zero-length rejection, negative track indices, `params` dict shape preservation for `apply_pip`).

## Scenarios

| ID    | Title                                                     | Area        | Priority | Sequential | Covers (tags)                              |
|-------|-----------------------------------------------------------|-------------|----------|------------|--------------------------------------------|
| SR-01 | `BLEND_MODES` frozenset contains exactly 11 named modes   | Pipeline    | Critical | No         | [STRUCTURAL] BLEND_MODES                   |
| SR-02 | `BLEND_MODE_TO_MLT` maps every mode to a non-empty value  | Pipeline    | Critical | No         | [STRUCTURAL] BLEND_MODE_TO_MLT             |
| SR-03 | `apply_composite` exported with spec signature            | Pipeline    | High     | No         | [STRUCTURAL] apply_composite signature     |
| SR-04 | Composite XML property-name discovery recorded            | Pipeline    | Medium   | No         | [STRUCTURAL] composite.xml inspection      |
| SR-05 | `apply_composite(screen)` emits correct AddComposition    | Pipeline    | Critical | No         | [BEHAVIORAL] screen happy path             |
| SR-06 | `apply_composite(destination_in)` uses mapped MLT value   | Pipeline    | Critical | No         | [BEHAVIORAL] destination_in happy path     |
| SR-07 | Default geometry applied when `geometry=None`             | Pipeline    | High     | No         | [BEHAVIORAL] default geometry              |
| SR-08 | Explicit geometry string passes through unchanged         | Pipeline    | High     | No         | [BEHAVIORAL] geometry passthrough          |
| SR-09 | Unknown `blend_mode` raises `ValueError` listing valid    | Pipeline    | Critical | No         | [BEHAVIORAL] unknown mode error            |
| SR-10 | Case-sensitive rejection (`"Screen"`, `"SCREEN"`)         | Pipeline    | High     | No         | [BEHAVIORAL] + Edge: case sensitivity      |
| SR-11 | `track_a == track_b` raises `ValueError`                  | Pipeline    | Critical | No         | [BEHAVIORAL] same-track error              |
| SR-12 | `end_frame <= start_frame` raises `ValueError`            | Pipeline    | Critical | No         | [BEHAVIORAL] frame ordering / zero-length  |
| SR-13 | `apply_composite` does not mutate input project           | Pipeline    | High     | No         | [BEHAVIORAL] deepcopy immutability         |
| SR-14 | Unit test file passes (`test_compositing_blend_modes.py`) | Pipeline    | High     | No         | [MECHANICAL] Sub-Spec 1                    |
| EP-01 | `composite_set` registered as an MCP tool                 | MCP Tools   | Critical | No         | [STRUCTURAL] tool registration             |
| EP-02 | `composite_set` signature matches spec                    | MCP Tools   | Critical | No         | [STRUCTURAL] signature                     |
| EP-03 | `composite_set` return shape matches spec                 | MCP Tools   | Critical | No         | [STRUCTURAL] return shape                  |
| EP-04 | `composite_pip` / `composite_wipe` signatures unchanged   | MCP Tools   | High     | No         | [STRUCTURAL] back-compat signatures        |
| EP-05 | All three tools importable from `server.tools`            | MCP Tools   | High     | No         | [INTEGRATION] callable imports             |
| EP-06 | End-to-end: screen blend written + re-parsed              | MCP Tools   | Critical | Yes        | [BEHAVIORAL] E2E screen                    |
| EP-07 | End-to-end: `destination_in` writes correct MLT value     | MCP Tools   | Critical | Yes        | [BEHAVIORAL] E2E destination_in mapping    |
| EP-08 | `composite_set` unknown mode -> `_err` lists 11 modes     | MCP Tools   | Critical | No         | [BEHAVIORAL] MCP unknown mode              |
| EP-09 | `composite_set` same-track -> `_err`                      | MCP Tools   | High     | No         | [BEHAVIORAL] MCP same-track                |
| EP-10 | `composite_set` bad frame ordering -> `_err`              | MCP Tools   | High     | No         | [BEHAVIORAL] MCP frame ordering            |
| EP-11 | `composite_set` creates snapshot on disk                  | MCP Tools   | High     | Yes        | [BEHAVIORAL] snapshot verification         |
| EP-12 | `composite_set` writes custom geometry verbatim           | MCP Tools   | High     | Yes        | [BEHAVIORAL] geometry verbatim             |
| EP-13 | `composite_set` negative track indices -> `_err`          | MCP Tools   | Medium   | No         | Edge: negative tracks                      |
| EP-14 | Non-adjacent tracks (1 <-> 4) allowed                     | MCP Tools   | Medium   | Yes        | Edge: non-adjacent tracks                  |
| EP-15 | `apply_wipe` body still produces luma composition only    | Pipeline    | Medium   | No         | [STRUCTURAL] apply_wipe unchanged          |
| UI-01 | `apply_pip` byte-identical regression (pre vs post rewire)| Regression  | Critical | No         | [BEHAVIORAL] byte-identical before/after   |
| UI-02 | `apply_pip` emits `AddComposition` with unchanged `params`| Regression  | High     | No         | Edge: params dict shape preservation       |
| UI-03 | `apply_pip` public signature unchanged (introspection)    | Regression  | High     | No         | [STRUCTURAL] apply_pip signature           |
| DB-01 | Full test suite passes (`uv run pytest tests/ -v`)        | Meta        | Critical | Yes        | [MECHANICAL] zero-regression               |

See individual scenario files in this directory for full steps and expected results.

## Coverage Summary

- Total scenarios: 31
- Pipeline (unit) scenarios: 15 (SR-01..SR-14, EP-15)
- MCP integration scenarios: 13 (EP-01..EP-14 minus EP-15)
- Regression snapshot scenarios: 3 (UI-01..UI-03)
- Meta (full-suite) scenarios: 1 (DB-01)
- Sequential scenarios: 6 (EP-06, EP-07, EP-11, EP-12, EP-14, DB-01 -- these either write `.kdenlive` files or depend on a clean workspace)
- Tag coverage:
  - `[STRUCTURAL]`: SR-01..SR-04, EP-01..EP-05, EP-15, UI-03 (13)
  - `[BEHAVIORAL]`: SR-05..SR-13, EP-06..EP-14, UI-01, UI-02 (20)
  - `[INTEGRATION]`: EP-05 (1)
  - `[MECHANICAL]`: SR-14, DB-01 (2)
  - Edge cases: SR-10, EP-13, EP-14, UI-02

Priority alignment with caller:
- Blend mode set validation (exactly 11): SR-01, SR-02
- `BLEND_MODE_TO_MLT` covers each mode: SR-02, SR-06, EP-07
- `apply_composite` happy paths: SR-05, SR-06 (screen, destination_in)
- `apply_composite` error paths: SR-09, SR-10, SR-11, SR-12
- `apply_pip` regression -- byte-identical: UI-01, UI-02, UI-03
- MCP tool registration + end-to-end written+reparsed: EP-01..EP-03, EP-06, EP-07

## Notes

- Sequential scenarios write to `tmp_path` workspaces -- they must not share state, so "sequential" here means the scenario internally requires ordered steps (snapshot -> mutate -> parse), not cross-scenario ordering.
- DB-01 should be run last; if any earlier scenario fails it may be deferred but must still be green before merge.
- Regression scenarios (UI-01..UI-03) require capturing a pre-rewire serialized `.kdenlive` once and committing it under `tests/unit/fixtures/` as the golden file.
