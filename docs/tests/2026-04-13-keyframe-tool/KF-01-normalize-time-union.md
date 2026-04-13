---
scenario_id: "KF-01"
title: "normalize_time accepts frame/seconds/timestamp union"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - keyframes
  - behavioral
---

# Scenario KF-01: normalize_time accepts frame/seconds/timestamp union

## Description
Verifies [BEHAVIORAL] Sub-Spec 2 -- `normalize_time` converts each of the three union forms to the MLT `HH:MM:SS.mmm` string.

## Preconditions
- `pipelines/keyframes.py` importable.

## Steps
1. Assert `normalize_time({"frame": 60}, 30.0) == "00:00:02.000"`.
2. Assert `normalize_time({"seconds": 2.0}, 30.0) == "00:00:02.000"`.
3. Assert `normalize_time({"timestamp": "00:00:02.000"}, 30.0) == "00:00:02.000"`.
4. Add parametrized cases: frame=0 -> `00:00:00.000`; seconds=1.5 @ 30fps -> `00:00:01.500`; timestamp passthrough with trailing zeros preserved.

## Expected Results
- All three inputs yield the canonical MLT timestamp form.
- Millisecond precision preserved to 3 digits.

## Execution Tool
bash -- `uv run pytest tests/unit/test_keyframes_pipeline.py::test_normalize_time_union -v`

## Pass / Fail Criteria
- **Pass:** All cases produce exact expected strings.
- **Fail:** Any off-by-one, precision drift, or format deviation.
