---
scenario_id: "SR-33"
title: "effect_chroma_key_advanced tolerance_near > tolerance_far returns _err"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-3
---

# Scenario SR-33: effect_chroma_key_advanced tolerance_near > tolerance_far returns _err

## Description
Verifies [BEHAVIORAL] that when `tolerance_near > tolerance_far`, `effect_chroma_key_advanced` returns an `_err` response whose message states the ordering rule (near must be ≤ far).

## Preconditions
- Workspace fixture ready.

## Steps
1. Call `effect_chroma_key_advanced(..., color="#00FF00", tolerance_near=0.4, tolerance_far=0.1)`.
2. Assert error response.
3. Assert the error message contains the phrase "tolerance_near" and "tolerance_far" and communicates the ordering rule.
4. Assert no filter persisted.

## Expected Results
- `_err` with ordering rule explanation.
- Project unchanged.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_chroma_key_advanced_ordering -v`

## Pass / Fail Criteria
- **Pass:** error returned with ordering rule.
- **Fail:** silent acceptance or uninformative error.
