---
scenario_id: "SR-38"
title: "uv run pytest tests/unit/test_masking_pipeline.py -v passes"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mechanical
  - sub-spec-1
---

# Scenario SR-38: uv run pytest tests/unit/test_masking_pipeline.py -v passes

## Description
Verifies [MECHANICAL] Sub-Spec 1 acceptance: the dedicated unit test module for the masking pipeline runs clean.

## Preconditions
- `uv sync` complete.
- All Sub-Spec 1 code and tests written.

## Steps
1. From repo root, run `uv run pytest tests/unit/test_masking_pipeline.py -v`.
2. Capture exit code and output.

## Expected Results
- Exit code `0`.
- All tests in the file pass (no failures, no errors).
- No skipped tests hide required coverage.

## Execution Tool
bash — run the command above from repo root.

## Pass / Fail Criteria
- **Pass:** exit 0, all tests passed.
- **Fail:** any non-zero exit or failed/errored test.
