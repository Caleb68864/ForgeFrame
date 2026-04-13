---
scenario_id: "SS2-13"
title: "Generated CATALOG importable + count > 300"
tool: "bash"
type: test-scenario
tags: [test-scenario, generator, mechanical, sequential, requires-kdenlive]
---

# Scenario SS2-13: Generated CATALOG importable + count > 300

## Description
Verifies `[MECHANICAL]` smoke check on the checked-in generated module.

## Preconditions
- Generator has been run against real Kdenlive (SS2-12 completed) and the result is checked in.

## Steps
1. Run `python -c "from workshop_video_brain.edit_mcp.pipelines.effect_catalog import CATALOG; print(len(CATALOG))"`.
2. Assert exit 0.
3. Assert printed integer is `> 300`.

## Expected Results
- Count > 300.

## Execution Tool
bash -- shell command above

## Pass / Fail Criteria
- **Pass:** Importable + count > 300.
- **Fail:** ImportError or count <= 300.
