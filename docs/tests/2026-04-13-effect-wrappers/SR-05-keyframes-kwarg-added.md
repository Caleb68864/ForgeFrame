---
scenario_id: "SR-05"
title: "Keyframe-capable param types add keyframes kwarg"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - generator
sequential: false
---

# Scenario SR-05: Keyframe-capable param types add `keyframes: str = ""` kwarg

## Description
Any effect with a param typed `KEYFRAME`, `ANIMATED`, or `GEOMETRY` must additionally accept a JSON-encoded `keyframes` kwarg.

## Preconditions
- Catalog has at least one effect with each of these param types.

## Steps
1. For each effect in catalog with any param of type `KEYFRAME`/`ANIMATED`/`GEOMETRY`, render its module.
2. Parse rendered source; locate the generated `effect_*` function node.
3. Assert a kwarg named `keyframes` with annotation `str` and default `""` is present.
4. For an effect with none of these types, assert no `keyframes` kwarg is emitted.

## Expected Results
- Kwarg present exactly when required, absent otherwise.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_wrapper_gen.py::test_keyframes_kwarg -v`

## Pass / Fail Criteria
- **Pass:** correct presence/absence across sampled effects.
- **Fail:** any mismatch.
