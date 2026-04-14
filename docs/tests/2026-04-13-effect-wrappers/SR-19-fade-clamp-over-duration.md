---
scenario_id: "SR-19"
title: "effect_fade clamps when fade_in + fade_out > clip duration"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - presets
  - fade
  - edge
sequential: true
---

# Scenario SR-19: Fade clamps at clip boundaries

## Preconditions
- Clip total duration 60 frames.

## Steps
1. Call `effect_fade(..., fade_in_frames=50, fade_out_frames=50)` on a 60-frame clip.
2. Assert call succeeds (no error — spec says "allowed; keyframes clamp naturally").
3. Re-parse project. Assert keyframe times do not exceed clip duration frame range.
4. Assert opacity at clip start ~0.0 and at clip end ~0.0 (both fades present, just overlap).

## Expected Results
- Clamped keyframes produce valid MLT string.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_presets.py::test_fade_clamp -v`

## Pass / Fail Criteria
- **Pass:** succeeds with clamped times.
- **Fail:** error raised or keyframes out of range.
