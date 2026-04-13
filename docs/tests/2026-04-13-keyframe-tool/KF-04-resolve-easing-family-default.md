---
scenario_id: "KF-04"
title: "resolve_easing applies ease_family default for ease_in/ease_out/ease_in_out"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - behavioral
---

# Scenario KF-04: resolve_easing applies ease_family default

## Description
Verifies [BEHAVIORAL] Sub-Spec 2 -- the bare abstract aliases `ease_in`, `ease_out`, `ease_in_out` resolve using the supplied `ease_family_default`. Default when unset is `cubic`.

## Preconditions
- `pipelines/keyframes.py` importable.

## Steps
1. Assert `resolve_easing("ease_in", ease_family_default="expo") == "p"`.
2. Assert `resolve_easing("ease_in")` (no default arg) equals the cubic-in operator char.
3. Assert `resolve_easing("ease_out", ease_family_default="sine")` resolves to the sine-out char.
4. Assert `resolve_easing("ease_in_out", ease_family_default="bounce")` resolves to the bounce-in-out char.

## Expected Results
- Bare aliases honor the `ease_family_default` parameter.
- Omitted default falls back to `cubic`.

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_resolve_easing_family_default -v`

## Pass / Fail Criteria
- **Pass:** Every alias resolves per the supplied family.
- **Fail:** Hardcoded family override or incorrect mapping.
