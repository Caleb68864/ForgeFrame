---
scenario_id: "SS2-05"
title: "Generated module exports CATALOG + finders + metadata"
tool: "bash"
type: test-scenario
tags: [test-scenario, generator, structural]
---

# Scenario SS2-05: Generated module exports CATALOG + finders + metadata

## Description
Verifies `[STRUCTURAL]` generated `effect_catalog.py` defines `CATALOG`, `find_by_name`, `find_by_service`, `__generated_at__`, `__source_version__`, `__local_count__`.

## Preconditions
- Generator has produced `workshop_video_brain/edit_mcp/pipelines/effect_catalog.py` (real run, or sub-spec 2 fixture run).

## Steps
1. `from workshop_video_brain.edit_mcp.pipelines import effect_catalog as c`.
2. Assert `isinstance(c.CATALOG, dict)` and `len(c.CATALOG) > 0`.
3. Assert callable: `c.find_by_name`, `c.find_by_service`.
4. Assert presence + types of `__generated_at__` (str), `__source_version__` (str), `__local_count__` (int).

## Expected Results
- Module exposes the documented public surface.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_generator.py::test_generated_module_exports -v`

## Pass / Fail Criteria
- **Pass:** All exports present with right types.
- **Fail:** Missing symbol or wrong type.
