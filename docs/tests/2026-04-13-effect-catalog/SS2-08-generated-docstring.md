---
scenario_id: "SS2-08"
title: "Generated module top docstring includes regen instructions"
tool: "bash"
type: test-scenario
tags: [test-scenario, generator, behavioral]
---

# Scenario SS2-08: Generated module top docstring includes regen instructions

## Description
Verifies `[BEHAVIORAL]` requirement 12: generated module's top docstring documents regeneration command + `source_version`.

## Preconditions
- Emitted module from SS2-07 (or any successful emit).

## Steps
1. Import emitted module; read `loaded.__doc__`.
2. Assert non-empty.
3. Assert `"regenerate"` (case-insensitive) substring present.
4. Assert the source version string passed to emit appears in the docstring.
5. Assert the docstring mentions either `scripts/generate_effect_catalog.py` or `workshop-video-brain catalog regenerate`.

## Expected Results
- Docstring documents regen path.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_generator.py::test_generated_docstring -v`

## Pass / Fail Criteria
- **Pass:** All substrings present.
- **Fail:** Missing instructions or version.
