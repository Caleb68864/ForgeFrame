---
scenario_id: "SR-32"
title: "effect_chroma_key with invalid color returns _err listing accepted formats"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-3
---

# Scenario SR-32: effect_chroma_key with invalid color returns _err listing accepted formats

## Description
Verifies [BEHAVIORAL] that calling `effect_chroma_key` with `color="notcolor"` returns an `_err` response whose message lists accepted formats (`#RRGGBB`, `#RRGGBBAA`, int hex).

## Preconditions
- Workspace fixture ready.

## Steps
1. Call `effect_chroma_key(..., color="notcolor")`.
2. Assert return indicates error (status == "error" or `_err` key present, per project convention).
3. Assert the message references each of the three accepted formats (or a clear exhaustive list).
4. Assert no filter was persisted to the project file.

## Expected Results
- Error response with helpful format list.
- Project file unchanged.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_chroma_key_invalid_color_err -v`

## Pass / Fail Criteria
- **Pass:** error returned and project untouched.
- **Fail:** success returned, silent failure, or project mutated.
