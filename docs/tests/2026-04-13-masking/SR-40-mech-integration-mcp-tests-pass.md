---
scenario_id: "SR-40"
title: "uv run pytest tests/integration/test_masking_mcp_tools.py -v passes"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mechanical
  - sub-spec-3
---

# Scenario SR-40: uv run pytest tests/integration/test_masking_mcp_tools.py -v passes

## Description
Verifies [MECHANICAL] Sub-Spec 3 acceptance: MCP tool integration tests pass end-to-end.

## Preconditions
- `uv sync` complete.
- Workspace/project fixtures available.

## Steps
1. Run `uv run pytest tests/integration/test_masking_mcp_tools.py -v`.
2. Capture exit code and output.

## Expected Results
- Exit code `0`.
- All integration tests pass.

## Execution Tool
bash — run the command above from repo root.

## Pass / Fail Criteria
- **Pass:** exit 0.
- **Fail:** any failure, error, or timeout.
