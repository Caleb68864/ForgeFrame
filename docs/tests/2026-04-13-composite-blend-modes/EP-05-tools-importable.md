---
scenario_id: "EP-05"
title: "All three compositing tools importable as callables"
tool: "bash"
type: test-scenario
covers: ["[INTEGRATION] callable imports"]
tags: [test-scenario, mcp, integration]
---

# Scenario EP-05: All three compositing tools importable

## Description
Spec Sub-Spec 2 INTEGRATION: `composite_set`, `composite_pip`, `composite_wipe` importable as callables from `workshop_video_brain.edit_mcp.server.tools`.

## Preconditions
- Sub-Spec 2 merged.

## Steps
1. Execute: `from workshop_video_brain.edit_mcp.server.tools import composite_set, composite_pip, composite_wipe`.
2. Assert all three are callable (`callable(x) is True`).

## Expected Results
- All three import cleanly and are callable.

## Execution Tool
bash -- `uv run pytest tests/integration/test_composite_set_mcp_tool.py::test_tools_importable -v`

## Pass / Fail Criteria
- **Pass:** Imports succeed, all callable.
- **Fail:** ImportError or non-callable.
