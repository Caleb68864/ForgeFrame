---
scenario_id: "SR-09"
title: "Generator refuses to overwrite hand-written files without --force"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - generator
  - safety
sequential: false
---

# Scenario SR-09: Generator refuses to overwrite non-generated modules without `--force`

## Steps
1. Create `/tmp/wrappers_existing/` with a hand-written `.py` file lacking the `GENERATED` marker.
2. Run `emit_wrappers_package(effects, /tmp/wrappers_existing)` without `force=True`.
3. Assert it raises (or returns error) referencing the file name.
4. Assert the hand-written file is unchanged (hash compare).
5. Re-run with `force=True` -- succeeds, file overwritten.

## Expected Results
- Error without force; overwrite with force.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_wrapper_gen.py::test_refuse_overwrite -v`

## Pass / Fail Criteria
- **Pass:** refusal without force, overwrite with force.
- **Fail:** silent overwrite, or force flag broken.
