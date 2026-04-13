---
scenario_id: "EP-15"
title: "apply_wipe body still produces luma composition only"
tool: "bash"
type: test-scenario
covers: ["[STRUCTURAL] apply_wipe unchanged"]
tags: [test-scenario, pipeline, structural, regression]
---

# Scenario EP-15: apply_wipe untouched

## Description
Spec Requirement 5 + Sub-Spec 2: `apply_wipe` is explicitly out of scope; it must still emit `composition_type="luma"` with `resource` param and accept only `VALID_WIPE_TYPES`.

## Steps
1. Import `apply_wipe` and `VALID_WIPE_TYPES`.
2. Assert `VALID_WIPE_TYPES == {"dissolve", "wipe"}` (unchanged).
3. Call `apply_wipe(project, 1, 2, 0, 60, wipe_type="dissolve")`.
4. Inspect resulting composition: `composition_type == "luma"`, `params["resource"] == ""`.
5. Call with `wipe_type="wipe"`; assert `params["resource"] == "/usr/share/kdenlive/lumas/HD/luma01.pgm"`.
6. Call with `wipe_type="banana"`; assert `ValueError`.

## Expected Results
- `apply_wipe` behavior and signature unchanged.

## Execution Tool
bash -- `uv run pytest tests/unit/test_compositing.py::test_apply_wipe_unchanged -v`

## Pass / Fail Criteria
- **Pass:** All three sub-checks pass.
- **Fail:** Any change in wipe types, composition_type, or resource values.
