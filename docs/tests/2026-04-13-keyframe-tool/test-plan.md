---
title: "Keyframe Tool for Kdenlive MCP Test Plan"
project: "ForgeFrame"
date: 2026-04-13
type: test-plan
tags:
  - test-plan
  - forgeframe
  - keyframe-tool
---

# Test Plan: Keyframe Tool for Kdenlive MCP

## Meta
- Project: ForgeFrame (Workshop Video Brain)
- Date: 2026-04-13
- Author: Forge (generated)
- Spec Source: `docs/specs/2026-04-13-keyframe-tool.md`
- Scope: Four sub-specs -- patcher effect-property extensions, keyframes pipeline module, effect_find + workspace config, MCP tool surface + integration.

## Prerequisites

- Python 3.12+ with `uv` installed.
- `uv sync` run to install dev dependencies.
- Pytest available: `uv run pytest`.
- Integration scenarios require the fixture `tests/integration/fixtures/keyframe_project.kdenlive` (minimal project with a `transform` filter on clip at track=2, index=0). The fixture is authored as part of Sub-Spec 4 and must exist before INT scenarios run.
- Tests are self-contained: each pytest unit/integration test sets up and tears down its own in-memory project trees or temp workspace directories.
- No live Kdenlive GUI dependency; MLT version guard is asserted via workspace metadata only.

## Scenarios

| ID      | Title                                                       | Area             | Priority | Sequential |
|---------|-------------------------------------------------------------|------------------|----------|------------|
| PAT-01  | Patcher exports get/set/list_effects with correct signatures| Patcher (unit)   | High     | No         |
| PAT-02  | get_effect_property returns existing rect string            | Patcher (unit)   | High     | No         |
| PAT-03  | set_effect_property mutates tree; round-trips via get       | Patcher (unit)   | High     | No         |
| PAT-04  | list_effects returns filters in stack order with properties | Patcher (unit)   | Medium   | No         |
| PAT-05  | get/set raise clear errors on missing clip/effect/property  | Patcher (unit)   | High     | No         |
| KF-01   | normalize_time accepts frame/seconds/timestamp union        | Keyframes (unit) | High     | No         |
| KF-02   | normalize_time raises ValueError on invalid input           | Keyframes (unit) | High     | No         |
| KF-03   | resolve_easing maps abstract names + raw operators          | Keyframes (unit) | High     | No         |
| KF-04   | resolve_easing applies ease_family default for ease_in etc. | Keyframes (unit) | High     | No         |
| KF-05   | resolve_easing raises on unknown name / unknown operator    | Keyframes (unit) | Medium   | No         |
| KF-06   | build_keyframe_string emits expected rect animation string  | Keyframes (unit) | High     | No         |
| KF-07   | build accepts 4-tuple rect and defaults opacity to 1        | Keyframes (unit) | High     | No         |
| KF-08   | build+parse round-trip for scalar/rect/color                | Keyframes (unit) | High     | No         |
| KF-09   | merge_keyframes overwrites same-frame and preserves order   | Keyframes (unit) | High     | No         |
| KF-10   | merge handles static non-keyframe existing value            | Keyframes (unit) | High     | No         |
| KF-11   | Empty keyframes list raises ValueError                      | Keyframes (unit) | Medium   | No         |
| KF-12   | Duplicate input frames -- later wins + warning              | Keyframes (unit) | Medium   | No         |
| KF-13   | Time-conversion collision errors with both entries          | Keyframes (unit) | Medium   | No         |
| FIND-01 | effect_find resolves by kdenlive_id first                   | Effect-find (u)  | High     | No         |
| FIND-02 | effect_find falls back to mlt_service when no id match      | Effect-find (u)  | High     | No         |
| FIND-03 | effect_find raises LookupError with effect list on no match | Effect-find (u)  | Medium   | No         |
| FIND-04 | effect_find raises ValueError on ambiguous match            | Effect-find (u)  | Medium   | No         |
| WS-01   | Workspace loads keyframe_defaults.ease_family from yaml     | Workspace (unit) | High     | No         |
| WS-02   | Missing keyframe_defaults section yields default 'cubic'    | Workspace (unit) | High     | No         |
| WS-03   | Invalid ease_family raises validation error at load time    | Workspace (unit) | High     | No         |
| INT-01  | Four MCP tools registered + discoverable via introspection  | MCP (integration)| High     | No         |
| INT-02  | MCP tool signatures match spec                              | MCP (integration)| High     | No         |
| INT-03  | effect_keyframe_set_rect end-to-end write + re-parse        | MCP (integration)| High     | Yes        |
| INT-04  | mode="merge" preserves non-overlap + overwrites same-frame  | MCP (integration)| High     | Yes        |
| INT-05  | effect_find MCP tool returns correct index for fixture      | MCP (integration)| Medium   | No         |
| INT-06  | Invalid effect_index raises MCP error listing effects       | MCP (integration)| High     | No         |
| INT-07  | Each MCP call creates an auto-snapshot; id returned         | MCP (integration)| High     | Yes        |
| INT-08  | Full pytest suite passes with no regressions                | MCP (integration)| High     | Yes        |
| EDGE-01 | Single keyframe permitted; emits static value with operator | Edge (unit)      | Medium   | No         |
| EDGE-02 | MLT version guard fires when workspace pins MLT<7.22        | Edge (unit)      | Medium   | No         |
| EDGE-03 | FPS re-read from project on every call (no caching)         | Edge (integration)| Medium  | No         |
| EDGE-04 | Auto-snapshot policy not bypassed by keyframe tools         | Edge (integration)| High    | Yes        |
| EDGE-05 | Serializer output unchanged for non-keyframe properties     | Edge (integration)| High    | Yes        |

See individual scenario files in this directory for full steps and expected results.

## Coverage Summary

- Total scenarios: 35
- Sub-Spec 1 (Patcher) coverage: 5 scenarios covering all 7 acceptance criteria
- Sub-Spec 2 (Keyframes pipeline) coverage: 13 scenarios covering all 14 acceptance criteria
- Sub-Spec 3 (effect_find + workspace) coverage: 7 scenarios covering all 9 acceptance criteria
- Sub-Spec 4 (MCP tool surface + integration) coverage: 8 scenarios covering all 9 acceptance criteria
- Edge case coverage: 5 additional scenarios
- Sequential scenarios: 5 (those that mutate the fixture project or rely on snapshot state)

### Acceptance-Criteria Traceability

Each [MECHANICAL] / [STRUCTURAL] / [BEHAVIORAL] / [INTEGRATION] tag maps to at least one scenario:

**Sub-Spec 1:**
- [STRUCTURAL] exports get/set/list_effects -> PAT-01
- [BEHAVIORAL] get rect -> PAT-02
- [BEHAVIORAL] set rect mutates + round-trip -> PAT-03
- [BEHAVIORAL] list_effects stack order -> PAT-04
- [BEHAVIORAL] missing property/effect/clip errors -> PAT-05
- [MECHANICAL] pytest passes -> INT-08

**Sub-Spec 2:**
- [STRUCTURAL] normalize_time/resolve_easing/build/parse/merge/Keyframe -> KF-01, KF-03, KF-06, KF-08, KF-09 (collectively)
- [BEHAVIORAL] frame/seconds/timestamp -> KF-01
- [BEHAVIORAL] linear/smooth/hold/ease_in_out_expo/ease_in+family/$= -> KF-03, KF-04
- [BEHAVIORAL] build rect animation -> KF-06
- [BEHAVIORAL] 4-tuple -> KF-07
- [BEHAVIORAL] build+parse round-trip scalar/rect/color -> KF-08
- [BEHAVIORAL] merge overwrite + sorted -> KF-09
- [BEHAVIORAL] merge static existing -> KF-10
- [BEHAVIORAL] invalid time -> KF-02
- [BEHAVIORAL] unknown easing name -> KF-05
- [BEHAVIORAL] unknown raw operator -> KF-05
- [MECHANICAL] pytest passes -> INT-08

**Sub-Spec 3:**
- [STRUCTURAL] effect_find.find -> FIND-01
- [STRUCTURAL] workspace.keyframe_defaults with Literal ease_family -> WS-01, WS-03
- [STRUCTURAL] loader reads yaml -> WS-01, WS-02
- [BEHAVIORAL] find by kdenlive_id / mlt_service -> FIND-01, FIND-02
- [BEHAVIORAL] LookupError on no match -> FIND-03
- [BEHAVIORAL] ValueError on ambiguous -> FIND-04
- [BEHAVIORAL] load expo -> WS-01
- [BEHAVIORAL] default cubic -> WS-02
- [BEHAVIORAL] invalid validation error -> WS-03
- [MECHANICAL] pytest passes -> INT-08

**Sub-Spec 4:**
- [STRUCTURAL] four tools registered -> INT-01
- [STRUCTURAL] keyframe tool signatures w/ snapshot id -> INT-02, INT-07
- [STRUCTURAL] effect_find signature -> INT-02
- [INTEGRATION] imported/registered, MCP introspection -> INT-01
- [BEHAVIORAL] end-to-end rect write + re-parse -> INT-03
- [BEHAVIORAL] merge mode -> INT-04
- [BEHAVIORAL] effect_find returns 0 -> INT-05
- [BEHAVIORAL] invalid effect_index error -> INT-06
- [BEHAVIORAL] auto-snapshot id in return -> INT-07
- [MECHANICAL] integration test passes -> INT-08
- [MECHANICAL] full suite passes -> INT-08

**Edge Cases (spec Edge Cases section):**
- Empty keyframes list -> KF-11
- Single keyframe -> EDGE-01
- Duplicate frames in input -> KF-12
- Time-conversion collision -> KF-13
- Static non-keyframe merge -> KF-10
- Missing keyframe_defaults -> WS-02
- Invalid ease_family at load time -> WS-03
- MLT version guard -> EDGE-02
- Ambiguous effect_find -> FIND-04
- FPS re-read per call -> EDGE-03
- Auto-snapshot not bypassed -> EDGE-04
- Serializer untouched for non-keyframe props -> EDGE-05
