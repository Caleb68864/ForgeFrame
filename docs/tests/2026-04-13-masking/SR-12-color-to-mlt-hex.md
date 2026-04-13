---
scenario_id: "SR-12"
title: "color_to_mlt_hex conversion matrix"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-1
---

# Scenario SR-12: color_to_mlt_hex conversion matrix

## Description
Verifies [BEHAVIORAL] color parsing/encoding across accepted forms: `#RRGGBB`, `#RRGGBBAA`, `int`, and invalid.

## Preconditions
- Module importable.

## Steps
1. `color_to_mlt_hex("#FF0000")` → assert `"0xff0000ff"`.
2. `color_to_mlt_hex("#FF000080")` → assert `"0xff000080"`.
3. `color_to_mlt_hex(0xff0000ff)` → assert `"0xff0000ff"`.
4. `color_to_mlt_hex("#00FF00")` → assert `"0x00ff00ff"` (default alpha appended).
5. `color_to_mlt_hex("notcolor")` → assert `ValueError` raised, message lists accepted formats.
6. `color_to_mlt_hex("#ZZZZZZ")` → assert `ValueError`.

## Expected Results
- Cases 1-4 produce exact lowercase `0xRRGGBBAA` strings.
- Cases 5-6 raise `ValueError` with a helpful message.

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_pipeline.py::test_color_to_mlt_hex -v`

## Pass / Fail Criteria
- **Pass:** all 6 sub-cases match expected output.
- **Fail:** any case wrong or missing error.
