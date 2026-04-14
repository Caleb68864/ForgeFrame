---
scenario_id: "SR-12"
title: "Generated __init__.py exposes all wrapped tool names"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - generator
sequential: false
---

# Scenario SR-12: `__init__.py` exposes all wrapped tool names

## Steps
1. Regenerate package to tmp path.
2. Read `__init__.py`.
3. Assert every `effect_<kdenlive_id>` corresponding to a selected effect is re-exported (either in `__all__` or imported at module top).
4. Assert no stale names (from previously-generated runs) remain.

## Expected Results
- Exhaustive, stable export list.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_wrapper_gen.py::test_init_exports -v`

## Pass / Fail Criteria
- **Pass:** `__all__` matches selected effect set.
- **Fail:** missing or extraneous names.
