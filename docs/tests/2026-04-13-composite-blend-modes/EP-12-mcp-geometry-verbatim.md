---
scenario_id: "EP-12"
title: "composite_set writes custom geometry verbatim"
tool: "bash"
type: test-scenario
sequential: true
covers: ["[BEHAVIORAL] geometry verbatim"]
tags: [test-scenario, mcp, behavioral]
---

# Scenario EP-12: MCP writes geometry verbatim

## Steps
1. Set up workspace + fixture.
2. Call `composite_set(..., blend_mode="screen", geometry="100/50:1920x1080:75")`.
3. Re-parse the written `.kdenlive`.
4. Locate the composite transition.
5. Assert its `geometry` property equals the exact input string `"100/50:1920x1080:75"`.

## Expected Results
- Geometry round-trips unchanged.

## Execution Tool
bash -- `uv run pytest tests/integration/test_composite_set_mcp_tool.py::test_geometry_verbatim -v`

## Pass / Fail Criteria
- **Pass:** Geometry round-trips byte-identical.
- **Fail:** Normalization, default substitution, or rejection.
