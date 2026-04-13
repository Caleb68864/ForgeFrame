---
scenario_id: "EP-02"
title: "composite_set Python signature matches spec"
tool: "bash"
type: test-scenario
covers: ["[STRUCTURAL] signature"]
tags: [test-scenario, mcp, structural, critical]
---

# Scenario EP-02: composite_set signature matches spec

## Description
`inspect.signature` check for the undecorated callable (or decorated, if FastMCP preserves signature).

## Preconditions
- Sub-Spec 2 implemented.

## Steps
1. `from workshop_video_brain.edit_mcp.server.tools import composite_set`.
2. `sig = inspect.signature(composite_set)`.
3. Assert params in order: `workspace_path, project_file, track_a, track_b, start_frame, end_frame, blend_mode, geometry`.
4. Assert types (annotations): `str, str, int, int, int, int, str, str`.
5. Assert defaults: `blend_mode="cairoblend"`, `geometry=""`.
6. Assert return annotation is `dict`.

## Expected Results
- Signature matches spec exactly.

## Execution Tool
bash -- `uv run pytest tests/integration/test_composite_set_mcp_tool.py::test_composite_set_signature -v`

## Pass / Fail Criteria
- **Pass:** All inspect assertions pass.
- **Fail:** Any deviation.
