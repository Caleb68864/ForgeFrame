---
scenario_id: "UI-01"
title: "apply_pip byte-identical regression (pre vs post rewire)"
tool: "bash"
type: test-scenario
covers: ["[BEHAVIORAL] byte-identical before/after rewire"]
tags: [test-scenario, regression, behavioral, critical]
---

# Scenario UI-01: apply_pip byte-identical regression

## Description
Spec Requirement 11 + Sub-Spec 2 BEHAVIORAL: before and after rewiring `apply_pip` through `apply_composite`, calling `apply_pip` with the same args produces byte-identical serialized `.kdenlive` output.

## Preconditions
- A committed golden fixture exists at e.g. `tests/unit/fixtures/apply_pip_golden.kdenlive` (captured from the implementation BEFORE the rewire; see "Golden Capture" note below).
- A deterministic fixture project (`apply_pip_input.kdenlive`) to feed in.

### Golden Capture (one-time)
Before merging the rewire PR, run a captured-at-HEAD script to emit the pre-rewire serializer output for the exact call below and commit it as `apply_pip_golden.kdenlive`. The test then treats that as immutable truth.

## Steps
1. Load the input fixture via `parse_project`.
2. Build a `PipLayout` deterministically (e.g. `get_pip_layout(PipPreset.bottom_right, 1920, 1080, 0.25)`).
3. Call `apply_pip(project, overlay_track=2, base_track=1, start_frame=0, end_frame=120, layout=layout)`.
4. Serialize the result via `serialize_project` to a string (or write to `tmp_path` and read bytes).
5. Read the committed golden file.
6. Assert the two byte sequences are identical (`==`).

## Expected Results
- Serialized output is byte-for-byte equal to the pre-rewire golden.

## Execution Tool
bash -- `uv run pytest tests/unit/test_apply_pip_regression.py::test_apply_pip_byte_identical -v`

## Pass / Fail Criteria
- **Pass:** Byte-equal.
- **Fail:** Any diff. Diff must be investigated and either reconciled (by fixing the rewire) or the golden updated only with explicit human review + ADR-style note.
