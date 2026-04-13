---
title: "Effect Stack Operations Test Plan"
project: "ForgeFrame"
date: 2026-04-13
type: test-plan
tags:
  - test-plan
  - forgeframe
  - stack-ops
  - kdenlive-mcp
---

# Test Plan: Effect Stack Operations for Kdenlive MCP

## Meta
- Project: ForgeFrame (Workshop Video Brain)
- Date: 2026-04-13
- Author: Forge
- Spec Source: `docs/specs/2026-04-13-stack-ops.md`
- Scope: Three sub-specs covering patcher stack mutations, stack-ops pipeline, and MCP tool surface for `effects_copy` / `effects_paste` / `effect_reorder`.

## Prerequisites
- Python 3.12+, `uv sync` complete.
- Spec 1 (Keyframes) shipped: `patcher.list_effects`, `_iter_clip_filters`.
- Fixture present: `tests/integration/fixtures/keyframe_project.kdenlive`.
- Tests use ephemeral copies of the fixture and self-contained snapshots; no shared state between scenarios.
- Test framework: `pytest` via `uv run pytest`.

## Scenarios

| ID    | Title                                                                          | Area        | Priority | Sequential | Tag(s)                       |
|-------|--------------------------------------------------------------------------------|-------------|----------|------------|------------------------------|
| SR-01 | Patcher exports `insert_effect_xml`, `remove_effect`, `reorder_effects`        | Patcher     | High     | No         | STRUCTURAL                   |
| SR-02 | `insert_effect_xml` at top, bottom, and middle of stack                        | Patcher     | High     | No         | BEHAVIORAL                   |
| SR-03 | `remove_effect` at start, middle, end indices                                  | Patcher     | High     | No         | BEHAVIORAL                   |
| SR-04 | `reorder_effects` moves filter; verifies new order via `list_effects`          | Patcher     | High     | No         | BEHAVIORAL                   |
| SR-05 | Out-of-range indices raise `IndexError` naming current stack length            | Patcher     | High     | No         | BEHAVIORAL                   |
| SR-06 | `reorder_effects` with `from_index == to_index` is a no-op                     | Patcher     | Medium   | No         | BEHAVIORAL                   |
| SR-07 | `tests/unit/test_patcher_stack_ops.py` passes                                  | Patcher     | High     | No         | MECHANICAL                   |
| SR-08 | Pipeline exports `serialize_stack` / `deserialize_stack` / `apply_paste` / `reorder_stack` | Pipeline | High | No | STRUCTURAL              |
| SR-09 | `serialize_stack` returns canonical dict shape with source_clip + effects[]    | Pipeline    | High     | No         | STRUCTURAL/BEHAVIORAL        |
| SR-10 | `serialize_stack` round-trip through `deserialize_stack`                       | Pipeline    | High     | No         | BEHAVIORAL                   |
| SR-11 | `serialize_stack` on empty stack returns `effects: []` (no error)              | Pipeline    | Medium   | No         | BEHAVIORAL                   |
| SR-12 | `deserialize_stack` rejects dict missing `effects` with `ValueError`           | Pipeline    | High     | No         | BEHAVIORAL                   |
| SR-13 | `apply_paste` mode=`append` preserves order, appends to end                    | Pipeline    | High     | No         | BEHAVIORAL                   |
| SR-14 | `apply_paste` mode=`prepend` places incoming filters at top                    | Pipeline    | High     | No         | BEHAVIORAL                   |
| SR-15 | `apply_paste` mode=`replace` clears target then inserts incoming               | Pipeline    | High     | No         | BEHAVIORAL                   |
| SR-16 | `apply_paste` rewrites `track=` and `clip_index=` attrs to target              | Pipeline    | High     | No         | BEHAVIORAL                   |
| SR-17 | `apply_paste` with empty `effects: []` is a no-op                              | Pipeline    | Medium   | No         | BEHAVIORAL                   |
| SR-18 | `apply_paste` invalid mode raises `ValueError` listing valid modes             | Pipeline    | Medium   | No         | BEHAVIORAL                   |
| SR-19 | Keyframe animation strings preserved byte-exact through serialize/paste       | Pipeline    | High     | No         | BEHAVIORAL                   |
| SR-20 | `tests/unit/test_stack_ops_pipeline.py` passes                                 | Pipeline    | High     | No         | MECHANICAL                   |
| SR-21 | `server/tools.py` registers `effects_copy`, `effects_paste`, `effect_reorder`  | MCP         | High     | No         | STRUCTURAL/INTEGRATION       |
| SR-22 | MCP tool return envelopes match documented shape                               | MCP         | High     | No         | STRUCTURAL                   |
| SR-23 | `effects_copy` against fixture returns `effect_count >= 1` with transform id   | MCP         | High     | No         | BEHAVIORAL                   |
| SR-24 | End-to-end copy → JSON-encode → paste (append) → verify via `list_effects`     | MCP         | High     | Yes        | BEHAVIORAL/INTEGRATION       |
| SR-25 | Paste mode=`replace` clears target's pre-existing filters                      | MCP         | High     | Yes        | BEHAVIORAL                   |
| SR-26 | `effect_reorder` out-of-range `from_index` returns `_err` with stack length    | MCP         | High     | No         | BEHAVIORAL                   |
| SR-27 | Each write call returns `snapshot_id` and snapshot dir exists on disk          | MCP         | High     | Yes        | BEHAVIORAL                   |
| SR-28 | Paste rewrites `track=`/`clip_index=` in written `.kdenlive` XML               | MCP         | High     | Yes        | BEHAVIORAL                   |
| SR-29 | Keyframe preservation through MCP layer (animated transform copy/paste)        | MCP         | High     | Yes        | INTEGRATION                  |
| SR-30 | Malformed JSON / invalid input handling on `effects_paste`                     | MCP         | Medium   | No         | BEHAVIORAL                   |
| SR-31 | `tests/integration/test_stack_ops_mcp_tools.py` passes                         | MCP         | High     | No         | MECHANICAL                   |
| SR-32 | Full suite `uv run pytest tests/ -v` passes (no regressions)                   | Regression  | High     | No         | MECHANICAL                   |

See individual scenario files in this directory for full steps and expected results.

## Coverage Summary
- Total scenarios: 32
- Sub-Spec 1 (Patcher stack mutations): 7
- Sub-Spec 2 (Stack-ops pipeline): 13
- Sub-Spec 3 (MCP tool surface + integration): 11
- Regression gate: 1
- Sequential scenarios: 5 (state-mutating MCP integration scenarios)
- Tags: STRUCTURAL=5, BEHAVIORAL=20, MECHANICAL=4, INTEGRATION=3 (some scenarios cover multiple tags)
