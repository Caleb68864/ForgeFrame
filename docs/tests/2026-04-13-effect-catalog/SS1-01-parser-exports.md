---
scenario_id: "SS1-01"
title: "Parser module exports data model symbols"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, structural]
---

# Scenario SS1-01: Parser module exports data model symbols

## Description
Verifies the `[STRUCTURAL]` criterion that `effect_catalog_gen.py` exports `EffectDef`, `ParamDef`, `ParamType`, `parse_effect_xml`, `parse_param`.

## Preconditions
- Sub-Spec 1 implementation merged.
- `workshop_video_brain.edit_mcp.pipelines.effect_catalog_gen` importable.

## Steps
1. `from workshop_video_brain.edit_mcp.pipelines import effect_catalog_gen as g`.
2. Assert `hasattr(g, name)` for each of: `EffectDef`, `ParamDef`, `ParamType`, `parse_effect_xml`, `parse_param`.
3. Assert `parse_effect_xml` and `parse_param` are callable.

## Expected Results
- All five symbols present.
- Functions callable.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py::test_module_exports -v`

## Pass / Fail Criteria
- **Pass:** All asserts succeed.
- **Fail:** ImportError or AttributeError.
