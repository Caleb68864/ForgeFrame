---
scenario_id: "EP-04"
title: "composite_pip / composite_wipe signatures unchanged"
tool: "bash"
type: test-scenario
covers: ["[STRUCTURAL] back-compat signatures"]
tags: [test-scenario, mcp, structural, regression]
---

# Scenario EP-04: Existing MCP tool signatures unchanged

## Description
Spec Requirement 7 + Sub-Spec 2: `composite_pip` and `composite_wipe` keep their public signatures. This is the MCP-surface guard against accidental breaking changes during rewire.

## Preconditions
- Sub-Spec 2 merged.

## Steps
1. Import `composite_pip` and `composite_wipe` from `workshop_video_brain.edit_mcp.server.tools`.
2. Compare `inspect.signature(composite_pip)` against the pinned expected:
   `(workspace_path: str, project_file: str, overlay_track: int, base_track: int, start_frame: int, end_frame: int, preset: str = 'bottom_right', scale: float = 0.25) -> dict`.
3. Compare `inspect.signature(composite_wipe)` against the pinned expected:
   `(workspace_path: str, project_file: str, track_a: int, track_b: int, start_frame: int, end_frame: int, wipe_type: str = 'dissolve') -> dict`.

## Expected Results
- Both signatures match pinned expected exactly.

## Execution Tool
bash -- `uv run pytest tests/integration/test_composite_set_mcp_tool.py::test_existing_tool_signatures_unchanged -v`

## Pass / Fail Criteria
- **Pass:** Both signatures byte-identical to pinned strings.
- **Fail:** Any parameter name, default, or annotation change.
