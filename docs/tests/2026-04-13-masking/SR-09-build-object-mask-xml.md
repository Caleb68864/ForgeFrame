---
scenario_id: "SR-09"
title: "build_object_mask_xml emits valid object_mask MLT XML"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-1
---

# Scenario SR-09: build_object_mask_xml emits valid object_mask MLT XML

## Description
Verifies [BEHAVIORAL] that `build_object_mask_xml((2, 0), {"enabled": True, "threshold": 0.5})` produces MLT XML whose service and property names match Kdenlive's `object_mask` effect definition discovered via the catalog.

## Preconditions
- Module importable.
- `effect_catalog` exposes an entry for the object_mask effect.

## Steps
1. Look up the object_mask entry in the catalog: `effect_catalog.find_by_service("object_mask")` (or equivalent).
2. Call `build_object_mask_xml((2, 0), {"enabled": True, "threshold": 0.5})`.
3. Parse XML.
4. Assert `mlt_service` attribute matches the catalog entry's service string exactly.
5. Assert `track="2"` and `clip_index="0"`.
6. Assert properties `enabled` (or Kdenlive-equivalent name) and `threshold` emitted with values `1`/`True` and `0.5` using the catalog's canonical property names.

## Expected Results
- XML well-formed.
- Service name matches catalog (not invented).
- Property names match catalog entry.

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_pipeline.py::test_build_object_mask_xml -v`

## Pass / Fail Criteria
- **Pass:** XML validates and matches catalog-derived names.
- **Fail:** invented service name, missing property, or malformed XML.
