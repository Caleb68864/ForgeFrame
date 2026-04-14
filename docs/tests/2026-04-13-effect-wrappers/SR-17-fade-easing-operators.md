---
scenario_id: "SR-17"
title: "effect_fade respects easing via MLT operator char"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - presets
  - fade
  - easing
sequential: true
---

# Scenario SR-17: Fade easing → MLT operator character

## Steps
1. Call `effect_fade(..., easing="linear")`. Parse rect keyframe string. Assert MLT operator char for each keyframe matches linear (`|` or `=` per catalog convention).
2. Call `effect_fade(..., easing="ease_in")`. Assert operator char differs from linear (e.g., `~=` for smooth).
3. Call `effect_fade(..., easing="ease_out")`. Assert operator char set per spec.
4. Call `effect_fade(..., easing="ease_in_out")`. Assert operator char set per spec.
5. Call `build_fade_keyframes(..., easing="bogus")` — assert `_err` or ValueError.

## Expected Results
- Each easing mode encodes a distinct, spec-mapped MLT operator char on each keyframe.
- Unknown easing rejected.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_presets.py::test_fade_easing -v`

## Pass / Fail Criteria
- **Pass:** distinct operator chars per easing.
- **Fail:** all easings produce same operator, or unknown easing silently accepted.
