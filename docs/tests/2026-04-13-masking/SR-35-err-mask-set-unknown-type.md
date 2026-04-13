---
scenario_id: "SR-35"
title: "mask_set with unknown type returns _err listing the three valid types"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-3
---

# Scenario SR-35: mask_set with unknown type returns _err listing the three valid types

## Description
Verifies [BEHAVIORAL] that `mask_set(type="banana", ...)` returns an `_err` response whose message lists the three valid types: `rotoscoping`, `object_mask`, `image_alpha`. Also verifies the Edge Case where `type="image_alpha"` returns a specific "not yet implemented" error.

## Preconditions
- Workspace fixture ready.

## Steps
1. Call `mask_set(..., type="banana", params="{}")`.
2. Assert `_err` response.
3. Assert message contains all three valid type names.
4. Call `mask_set(..., type="image_alpha", params="{}")`.
5. Assert `_err` response with the "not yet implemented — use type='rotoscoping' or 'object_mask'" message (per Edge Cases).
6. Assert no filter persisted for either call.

## Expected Results
- Unknown type: `_err` lists all 3 valid types.
- `image_alpha`: `_err` with the not-yet-implemented pointer.
- Project unchanged.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_mask_set_unknown_type -v`

## Pass / Fail Criteria
- **Pass:** both error paths return correct messages.
- **Fail:** wrong/missing listing or project mutated.
