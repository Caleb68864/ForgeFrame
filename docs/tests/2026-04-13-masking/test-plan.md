---
title: "Masking Tools for Kdenlive MCP Test Plan"
project: "ForgeFrame"
date: 2026-04-13
type: test-plan
tags:
  - test-plan
  - forgeframe
  - masking
---

# Test Plan: Masking Tools for Kdenlive MCP

## Meta
- Project: ForgeFrame (Workshop Video Brain)
- Date: 2026-04-13
- Author: Forge
- Spec Source: docs/specs/2026-04-13-masking.md
- Scope: Mask pipeline, alpha routing, and MCP tool surface (Sub-Specs 1-3)

## Prerequisites
- Python 3.12+
- `uv sync` completed successfully (Pydantic v2, pytest, fastmcp installed)
- Reference Kdenlive rotoscoping filter XML available at `/usr/share/kdenlive/effects/rotoscoping.xml` (for some builder tests)
- Fixture `tests/unit/fixtures/masking_reference.kdenlive` exists (a hand-authored project containing a rotoscoping mask), used by alpha-routing inspection scenarios
- A clean MLT/Kdenlive workspace fixture (reused from existing `tests/integration` harness) exposing `workspace_path`, `project_file`, `track`, `clip` for MCP end-to-end scenarios
- Tests are self-contained: each scenario sets up its own workspace/project under a tmp path and tears down via test fixtures. Write operations auto-snapshot; tests assert snapshot files exist on disk

## Scenarios

| ID | Title | Area | Priority | Sequential |
|----|-------|------|----------|------------|
| SR-01 | Masking pipeline module exports correct surface | Pipeline / Structure | High | No |
| SR-02 | `MaskShape` and `MaskParams` Pydantic fields and defaults | Pipeline / Structure | High | No |
| SR-03 | `shape_to_points` — rect returns 4 clockwise corners | Pipeline / Shape | High | No |
| SR-04 | `shape_to_points` — ellipse returns `sample_count` points starting at 3 o'clock | Pipeline / Shape | High | No |
| SR-05 | `shape_to_points` — polygon passes through unchanged | Pipeline / Shape | High | No |
| SR-06 | `shape_to_points` — polygon with <3 points raises `ValueError` | Pipeline / Shape | High | No |
| SR-07 | `shape_to_points` — out-of-range coordinate raises `ValueError` naming offender | Pipeline / Shape | High | No |
| SR-08 | `build_rotoscoping_xml` emits correct MLT structure and properties | Pipeline / XML | High | No |
| SR-09 | `build_object_mask_xml` emits valid object_mask MLT XML | Pipeline / XML | High | No |
| SR-10 | `build_chroma_key_xml` emits basic chroma key MLT XML with correct service | Pipeline / XML | High | No |
| SR-11 | `build_chroma_key_advanced_xml` emits advanced chroma key MLT XML | Pipeline / XML | High | No |
| SR-12 | `color_to_mlt_hex` conversion matrix (RRGGBB / RRGGBBAA / int / invalid) | Pipeline / Color | High | No |
| SR-13 | `apply_mask_to_effect` export signature and return shape | Routing / Structure | High | No |
| SR-14 | No-op when mask already precedes target (`mask_idx < target_idx`) | Routing | High | No |
| SR-15 | Reorder when `mask_idx >= target_idx` | Routing | High | No |
| SR-16 | Out-of-range index raises `IndexError` naming stack length | Routing | High | No |
| SR-17 | Non-mask `mlt_service` at mask index raises `ValueError` with service name | Routing | High | No |
| SR-18 | Alpha-routing property decision (target-property OR pure stack-order) | Routing | High | Yes |
| SR-19 | MCP tools module registers all six tools and they are importable callables | MCP / Structure | High | No |
| SR-20 | MCP `mask_set` signature, params JSON, return shape | MCP / Structure | High | No |
| SR-21 | MCP `mask_set_shape` signature and return shape | MCP / Structure | High | No |
| SR-22 | MCP `mask_apply` signature and return shape | MCP / Structure | High | No |
| SR-23 | MCP `effect_chroma_key` signature and return shape | MCP / Structure | High | No |
| SR-24 | MCP `effect_chroma_key_advanced` signature and return shape | MCP / Structure | High | No |
| SR-25 | MCP `effect_object_mask` signature and return shape | MCP / Structure | High | No |
| SR-26 | End-to-end: `mask_set_shape(rect)` persists rotoscoping filter on disk | MCP / E2E | High | Yes |
| SR-27 | End-to-end: `mask_set_shape(ellipse)` produces 32-point spline | MCP / E2E | High | Yes |
| SR-28 | End-to-end: `mask_set_shape(polygon)` writes exactly the supplied points | MCP / E2E | High | Yes |
| SR-29 | End-to-end chain: `mask_set_shape` + `effect_add(glow)` + `mask_apply` | MCP / E2E | High | Yes |
| SR-30 | `mask_apply` reorders when mask index > target index and returns `reordered=true` | MCP / Routing | High | Yes |
| SR-31 | `effect_chroma_key("#00FF00")` persists with MLT-encoded color `0x00ff00ff` | MCP / Color | High | Yes |
| SR-32 | `effect_chroma_key` with invalid color returns `_err` listing accepted formats | MCP / Errors | High | No |
| SR-33 | `effect_chroma_key_advanced` with tolerance_near > tolerance_far returns `_err` with ordering rule | MCP / Errors | High | No |
| SR-34 | Every write-mutating MCP call returns a `snapshot_id` that exists on disk | MCP / Snapshots | High | Yes |
| SR-35 | `mask_set` with unknown `type` returns `_err` listing the three valid types | MCP / Errors | High | No |
| SR-36 | `mask_set_shape` with unknown `shape` returns `_err` listing the three valid shapes | MCP / Errors | High | No |
| SR-37 | Multi-mask: three `mask_set_shape` calls on one clip produce three rotoscoping filters | MCP / E2E | Medium | Yes |
| SR-38 | `uv run pytest tests/unit/test_masking_pipeline.py -v` passes | Mechanical | High | No |
| SR-39 | `uv run pytest tests/unit/test_masking_alpha_routing.py -v` passes | Mechanical | High | No |
| SR-40 | `uv run pytest tests/integration/test_masking_mcp_tools.py -v` passes | Mechanical | High | No |
| SR-41 | `uv run pytest tests/ -v` full suite passes with zero regressions | Mechanical | High | No |

See individual scenario files in this directory for full steps and expected results.

## Coverage Summary
- Total scenarios: 41
- Sub-Spec 1 (Mask Pipeline): SR-01 through SR-12, SR-38 — 13 scenarios covering all 3 STRUCTURAL, 8 BEHAVIORAL, 1 MECHANICAL tags
- Sub-Spec 2 (Alpha Routing): SR-13 through SR-18, SR-39 — 7 scenarios covering 1 STRUCTURAL, 6 BEHAVIORAL, 1 MECHANICAL tag
- Sub-Spec 3 (MCP Tool Surface): SR-19 through SR-37, SR-40, SR-41 — 21 scenarios covering 7 STRUCTURAL, 10 BEHAVIORAL, 1 INTEGRATION, 2 MECHANICAL tags
- Sequential scenarios: 11 (those mutating shared workspace/project on disk)

## Tag-to-Scenario Map

### Sub-Spec 1
- [STRUCTURAL] Module exports → SR-01
- [STRUCTURAL] `MaskParams` fields → SR-02
- [STRUCTURAL] `MaskShape` fields → SR-02
- [BEHAVIORAL] rect → 4 corners CW → SR-03
- [BEHAVIORAL] ellipse → 32 points, first at 3 o'clock → SR-04
- [BEHAVIORAL] polygon passthrough → SR-05
- [BEHAVIORAL] polygon <3 points → `ValueError` → SR-06
- [BEHAVIORAL] Out-of-range coord → `ValueError` naming value → SR-07
- [BEHAVIORAL] `build_rotoscoping_xml` content → SR-08
- [BEHAVIORAL] `build_object_mask_xml` → SR-09
- [BEHAVIORAL] `build_chroma_key_xml` → SR-10
- [BEHAVIORAL] `build_chroma_key_advanced_xml` → SR-11
- [BEHAVIORAL] `color_to_mlt_hex` matrix → SR-12
- [MECHANICAL] unit test module passes → SR-38

### Sub-Spec 2
- [STRUCTURAL] `apply_mask_to_effect` export → SR-13
- [BEHAVIORAL] No-op when already ordered → SR-14
- [BEHAVIORAL] Reorder when out of order → SR-15
- [BEHAVIORAL] Out-of-range index → `IndexError` → SR-16
- [BEHAVIORAL] Non-mask service → `ValueError` → SR-17
- [BEHAVIORAL] Sets target property if Kdenlive requires → SR-18
- [BEHAVIORAL] Otherwise pure stack-order + docstring → SR-18
- [MECHANICAL] alpha routing tests pass → SR-39

### Sub-Spec 3
- [STRUCTURAL] six tools registered → SR-19
- [STRUCTURAL] `mask_set` signature → SR-20
- [STRUCTURAL] `mask_set_shape` signature → SR-21
- [STRUCTURAL] `mask_apply` signature → SR-22
- [STRUCTURAL] `effect_chroma_key` signature → SR-23
- [STRUCTURAL] `effect_chroma_key_advanced` signature → SR-24
- [STRUCTURAL] `effect_object_mask` signature → SR-25
- [INTEGRATION] all six importable → SR-19
- [BEHAVIORAL] rect E2E → SR-26
- [BEHAVIORAL] ellipse → 32 spline points → SR-27
- [BEHAVIORAL] polygon → exact 3 points → SR-28
- [BEHAVIORAL] Full chain mask+effect+apply → SR-29
- [BEHAVIORAL] mask_apply reorder → SR-30
- [BEHAVIORAL] chroma key color encoding → SR-31
- [BEHAVIORAL] chroma key invalid color → SR-32
- [BEHAVIORAL] chroma_key_advanced ordering rule → SR-33
- [BEHAVIORAL] snapshot_id exists on disk → SR-34
- [BEHAVIORAL] `mask_set` unknown type → SR-35
- [BEHAVIORAL] `mask_set_shape` unknown shape → SR-36
- [MECHANICAL] integration test module passes → SR-40
- [MECHANICAL] full suite zero regressions → SR-41

(Multi-mask on one clip — covered by SR-37 as additional priority scenario requested by caller.)
