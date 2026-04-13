---
scenario_id: "KF-03"
title: "resolve_easing maps abstract names and raw operators"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - behavioral
---

# Scenario KF-03: resolve_easing maps abstract names and raw operators

## Description
Verifies [BEHAVIORAL] Sub-Spec 2 -- `resolve_easing` returns the correct single-char MLT operator prefix for every documented abstract name AND raw operator. Covers linear (`""`), smooth (`~`), hold (`|`), `ease_in_out_expo` (`r`), raw `$=` -> `$`, and at least one example per family (sine/quad/cubic/quart/quint/expo/circ/back/elastic/bounce) with in/out/in_out.

## Preconditions
- `pipelines/keyframes.py` importable.

## Steps
1. Assert `resolve_easing("linear") == ""`.
2. Assert `resolve_easing("smooth") == "~"`.
3. Assert `resolve_easing("hold") == "|"`.
4. Assert `resolve_easing("ease_in_out_expo") == "r"`.
5. Assert `resolve_easing("$=") == "$"`.
6. Assert raw operator passthrough for at least `=`, `~=`, `|=`, `-=`, one lowercase (`a=`), and one uppercase (`D=`).
7. Parametrize across every family name in `{sine, quad, cubic, quart, quint, expo, circ, back, elastic, bounce}` x `{ease_in_, ease_out_, ease_in_out_}` plus the `<family>_in` aliases; assert each returns the char documented in the MLT operator table.
8. Also test abstract `smooth_natural` and `smooth_tight`.

## Expected Results
- Every documented abstract name returns the expected char.
- Raw operators pass through stripped of the trailing `=`.

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_resolve_easing_table -v`

## Pass / Fail Criteria
- **Pass:** Full table matches MLT `keyframe_type_map[]` authoritative source.
- **Fail:** Any mapping drift.
