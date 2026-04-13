---
scenario_id: "IO-10"
title: "list_presets skips malformed files into skipped[] with path+error"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - io
  - behavioral
  - resilience
---

# Scenario IO-10: list_presets handles malformed files

## Description
Verifies `[BEHAVIORAL]` -- malformed preset files (invalid YAML, missing required fields, hand-edited corruption) are NOT raised as errors; they appear in `skipped` with `{path, error}` and the rest of the listing succeeds.

## Preconditions
- Workspace contains 1 valid preset, 1 file with non-YAML garbage, and 1 YAML file missing required `effects` field.

## Steps
1. Write valid `<ws>/stacks/good.yaml`, garbage `<ws>/stacks/bad.yaml` (`":\n[unbalanced"`), and `<ws>/stacks/incomplete.yaml` (valid YAML but `Preset.model_validate` fails).
2. Call `list_presets(ws, vault=None, scope="workspace")`.
3. Assert `presets` has length 1 (only `good`).
4. Assert `skipped` has length 2.
5. Each skipped entry has `path` and `error` keys; `error` is a non-empty string.
6. Function did not raise.

## Expected Results
- Bad files isolated into skipped; listing keeps working.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_io.py::test_list_presets_skips_malformed -v`

## Pass / Fail Criteria
- **Pass:** 1 listed, 2 skipped with error reasons, no raise.
- **Fail:** Function raises or includes malformed entries in `presets`.
