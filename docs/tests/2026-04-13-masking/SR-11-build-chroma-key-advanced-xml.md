---
scenario_id: "SR-11"
title: "build_chroma_key_advanced_xml emits advanced chroma key MLT XML"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-1
---

# Scenario SR-11: build_chroma_key_advanced_xml emits advanced chroma key MLT XML

## Description
Verifies [BEHAVIORAL] that `build_chroma_key_advanced_xml` emits valid XML for the advanced MLT chroma key service with the full parameter set (tolerance_near, tolerance_far, edge_smooth, spill_suppression).

## Preconditions
- Module importable.
- Catalog entry for advanced chroma key resolvable.

## Steps
1. Resolve advanced chroma key service name via catalog.
2. Call `build_chroma_key_advanced_xml((2, 0), color="#00FF00", tolerance_near=0.1, tolerance_far=0.3, edge_smooth=0.05, spill_suppression=0.2)`.
3. Parse XML.
4. Assert `mlt_service` matches catalog.
5. Assert all five properties emitted with correct values and catalog-canonical names.
6. Assert color emitted as `0x00ff00ff`.

## Expected Results
- XML well-formed.
- Service and all property names match catalog.
- All numeric values preserved with sufficient precision.

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_pipeline.py::test_build_chroma_key_advanced_xml -v`

## Pass / Fail Criteria
- **Pass:** all assertions hold.
- **Fail:** any property missing or mis-named.
