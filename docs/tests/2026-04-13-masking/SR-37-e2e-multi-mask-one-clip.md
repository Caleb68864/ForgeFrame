---
scenario_id: "SR-37"
title: "Multi-mask: three mask_set_shape calls on one clip produce three rotoscoping filters"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-3
  - sequential
---

# Scenario SR-37: Multi-mask: three mask_set_shape calls on one clip produce three rotoscoping filters

## Description
Verifies Edge Case "Multiple masks on one clip": three sequential `mask_set_shape` calls produce three independent rotoscoping filters on the same clip. Supports caller-specified ordering (no auto-ordering) per Must-Not.

## Preconditions
- Fresh workspace + project fixture, clip with zero filters.

## Steps
1. Call `mask_set_shape(..., shape="rect", bounds="[0,0,0.5,0.5]")` → capture index_1.
2. Call `mask_set_shape(..., shape="ellipse", bounds="[0.2,0.2,0.5,0.5]")` → capture index_2.
3. Call `mask_set_shape(..., shape="polygon", points="[[0.1,0.1],[0.5,0.1],[0.3,0.5]]")` → capture index_3.
4. Re-parse project from disk.
5. Count filters on the target clip with `mlt_service="rotoscoping"`.
6. Assert exactly 3 rotoscoping filters present.
7. Assert ordering on disk matches call sequence (index_1 < index_2 < index_3), confirming no auto-ordering.

## Expected Results
- 3 rotoscoping filters persisted.
- Order preserves insertion sequence.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_multi_mask_one_clip -v`

## Pass / Fail Criteria
- **Pass:** 3 filters in insertion order.
- **Fail:** wrong count, reordered, or missing.
