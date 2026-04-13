---
scenario_id: "SR-17"
title: "Non-mask mlt_service at mask index raises ValueError with service name"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-2
---

# Scenario SR-17: Non-mask mlt_service at mask index raises ValueError with service name

## Description
Verifies [BEHAVIORAL] that if `mask_effect_index` points to a filter whose `mlt_service` is not `rotoscoping` or `object_mask`, `apply_mask_to_effect` raises `ValueError` whose message contains the actual (incorrect) service name.

## Preconditions
- Fixture clip with a non-mask filter (e.g., `frei0r.glow`) at index 0 and a target filter at index 1.

## Steps
1. Call `apply_mask_to_effect(project, clip_ref, mask_effect_index=0, target_effect_index=1)`.
2. Assert `ValueError` raised.
3. Assert message contains the actual service string at that index (e.g., `frei0r.glow`).
4. Also test: mask index points to a chroma-key filter — should still be rejected (not a mask filter for routing purposes).

## Expected Results
- `ValueError` raised.
- Message contains actual service name.

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_alpha_routing.py::test_non_mask_service_rejected -v`

## Pass / Fail Criteria
- **Pass:** error raised with service name included.
- **Fail:** silently accepts or error lacks service name.
