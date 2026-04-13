---
scenario_id: "SR-04"
title: "Composite XML property-name discovery recorded"
tool: "bash"
type: test-scenario
covers: ["[STRUCTURAL] composite.xml inspection"]
tags: [test-scenario, pipeline, structural, discovery]
---

# Scenario SR-04: Composite XML property-name discovery recorded

## Description
Sub-Spec 1 requires the worker to inspect `/usr/share/kdenlive/effects/composite.xml` and record the actual MLT property name carrying blend mode (likely `compositing`). This scenario asserts the discovered property name is captured as a module-level constant so downstream code (and humans) have a single source of truth.

## Preconditions
- Module implemented; property name stored as e.g. `BLEND_MODE_MLT_PROPERTY` or similar constant.

## Steps
1. Import `BLEND_MODE_MLT_PROPERTY` (or equivalent documented constant) from `workshop_video_brain.edit_mcp.pipelines.compositing`.
2. Assert the constant is a non-empty string.
3. Assert it equals the value recorded by the worker (likely `"compositing"`) -- compare against the inline-documented value in the module.
4. Optionally: if the file `/usr/share/kdenlive/effects/composite.xml` exists at test time, parse it and confirm the property name appears there; otherwise skip that assertion (test must NOT fail on missing system file).

## Expected Results
- Constant exists and is non-empty.
- Matches the committed documented value.

## Execution Tool
bash -- `uv run pytest tests/unit/test_compositing_blend_modes.py::test_blend_mode_mlt_property_constant -v`

## Pass / Fail Criteria
- **Pass:** Constant exported, non-empty, matches committed value.
- **Fail:** Constant missing, empty, or disagrees with committed value.
