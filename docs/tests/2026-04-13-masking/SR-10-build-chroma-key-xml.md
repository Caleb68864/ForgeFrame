---
scenario_id: "SR-10"
title: "build_chroma_key_xml emits basic chroma key MLT XML"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-1
---

# Scenario SR-10: build_chroma_key_xml emits basic chroma key MLT XML

## Description
Verifies [BEHAVIORAL] that `build_chroma_key_xml((2, 0), color="#00FF00", tolerance=0.15, blend=0.0)` emits valid MLT XML whose service name comes from the catalog lookup for basic chroma key.

## Preconditions
- Module importable.
- Catalog contains a basic chroma key entry (distinct from advanced).

## Steps
1. Resolve basic chroma key service name via `effect_catalog` lookup.
2. Call `build_chroma_key_xml((2, 0), color="#00FF00", tolerance=0.15, blend=0.0)`.
3. Parse XML.
4. Assert `mlt_service` matches catalog result.
5. Assert color property emitted as `0x00ff00ff` (MLT canonical).
6. Assert `tolerance` property equal to `0.15` and `blend` property equal to `0.0` (or Kdenlive-canonical property names per catalog).

## Expected Results
- XML well-formed.
- Service matches catalog.
- Color emitted in `0xRRGGBBAA` form with default alpha `ff` appended.

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_pipeline.py::test_build_chroma_key_xml -v`

## Pass / Fail Criteria
- **Pass:** all assertions hold.
- **Fail:** service name wrong, color format wrong, or properties missing.
