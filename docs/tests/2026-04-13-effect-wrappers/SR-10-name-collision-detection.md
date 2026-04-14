---
scenario_id: "SR-10"
title: "Wrapper name collision detection errors before writing"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - generator
  - safety
sequential: false
---

# Scenario SR-10: Wrapper name collision detection errors before writing

## Steps
1. Monkeypatch/mock a catalog entry to produce `kdenlive_id` matching an existing `@mcp.tool()` name in `server/tools.py` (e.g., `effect_add`).
2. Call `emit_wrappers_package`.
3. Assert it raises with a message listing the colliding name(s).
4. Assert no files were written to the output directory.

## Expected Results
- Collision surfaced before any file I/O.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_wrapper_gen.py::test_name_collision -v`

## Pass / Fail Criteria
- **Pass:** error raised, directory empty.
- **Fail:** silent overwrite or partial write.
