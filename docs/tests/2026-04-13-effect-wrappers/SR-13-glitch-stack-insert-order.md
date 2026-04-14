---
scenario_id: "SR-13"
title: "effect_glitch_stack inserts 5 filters in specified order with single snapshot"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - presets
  - glitch
sequential: true
---

# Scenario SR-13: `effect_glitch_stack` inserts 5 filters in order with single snapshot

## Preconditions
- Workspace project with track=2 clip=0 present.
- Catalog contains all 5 required frei0r services.

## Steps
1. Snapshot list initial count `snap_before`.
2. Call `effect_glitch_stack(workspace, project, track=2, clip=0, intensity=0.5)`.
3. Re-parse project, read the filter stack on target clip.
4. Assert filter order (by service id) is exactly: `frei0r.pixeliz0r`, `frei0r.glitch0r`, `frei0r.rgbsplit0r`, `frei0r.scanline0r`, `frei0r.exposer`.
5. Assert return payload contains `first_effect_index`, `filter_count == 5`, `snapshot_id`.
6. Assert snapshots list grew by exactly 1 (single snapshot, not per-filter).

## Expected Results
- Five filters inserted in spec order.
- Single new snapshot on disk.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_presets.py::test_glitch_stack_insert_order -v`

## Pass / Fail Criteria
- **Pass:** order, count, snapshot delta all correct.
- **Fail:** wrong order or multiple snapshots.
