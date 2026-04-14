---
scenario_id: "SR-15"
title: "effect_glitch_stack errors when frei0r service missing from catalog"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - presets
  - error
sequential: false
---

# Scenario SR-15: Glitch stack missing-service error

## Steps
1. Monkeypatch catalog to remove `frei0r.glitch0r`.
2. Call `effect_glitch_stack(...)`.
3. Assert return is `_err` shape.
4. Assert error message names `frei0r.glitch0r`.
5. Assert no filter was inserted (project unchanged — compare hash before/after).

## Expected Results
- Error returned before any partial insert.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_presets.py::test_glitch_missing_service -v`

## Pass / Fail Criteria
- **Pass:** `_err` names missing service; project unchanged.
- **Fail:** partial insert or silent pass.
