---
scenario_id: "KF-05"
title: "resolve_easing raises on unknown name and unknown operator"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - behavioral
  - edge-case
---

# Scenario KF-05: resolve_easing raises on unknown name / unknown operator

## Description
Verifies [BEHAVIORAL] Sub-Spec 2 -- unknown abstract name raises `ValueError` listing the valid set; unknown raw operator char raises `ValueError` referencing the MLT operator table.

## Preconditions
- `pipelines/keyframes.py` importable.

## Steps
1. Call `resolve_easing("curvy_swoosh")` -- assert `ValueError`; message lists valid abstract names (or a substantial subset clearly identifying the valid table).
2. Call `resolve_easing("Z=")` -- assert `ValueError`; message references the MLT operator table.
3. Call `resolve_easing("")` -- assert `ValueError`.
4. Call `resolve_easing("=")` alone (missing operator body) -- assert behavior matches spec (treated as linear equivalent or raises; whichever the implementer chose) and is documented.

## Expected Results
- Unknown names raise with an enumeration of valid options.
- Unknown operators raise with a reference to the authoritative MLT table.

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_resolve_easing_errors -v`

## Pass / Fail Criteria
- **Pass:** All invalid inputs raise `ValueError` with actionable messages.
- **Fail:** Silent fallback or opaque error.
