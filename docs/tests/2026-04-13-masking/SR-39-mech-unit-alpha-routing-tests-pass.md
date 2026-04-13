---
scenario_id: "SR-39"
title: "uv run pytest tests/unit/test_masking_alpha_routing.py -v passes"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mechanical
  - sub-spec-2
---

# Scenario SR-39: uv run pytest tests/unit/test_masking_alpha_routing.py -v passes

## Description
Verifies [MECHANICAL] Sub-Spec 2 acceptance: dedicated alpha-routing unit tests pass.

## Preconditions
- `uv sync` complete.
- Fixture `tests/unit/fixtures/masking_reference.kdenlive` in place.

## Steps
1. Run `uv run pytest tests/unit/test_masking_alpha_routing.py -v`.
2. Capture exit code.

## Expected Results
- Exit code `0`.
- All tests pass.

## Execution Tool
bash — run the command above from repo root.

## Pass / Fail Criteria
- **Pass:** exit 0.
- **Fail:** any failure or error.
