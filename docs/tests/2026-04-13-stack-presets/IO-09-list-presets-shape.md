---
scenario_id: "IO-09"
title: "list_presets enumerates both tiers, returns expected dict shape"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - io
  - behavioral
---

# Scenario IO-09: list_presets across tiers

## Description
Verifies `[BEHAVIORAL]` -- `list_presets(workspace_root, vault_root, scope="all")` returns dicts with `{name, scope, tags, effect_count, description, path}` for each found preset, plus a `skipped` companion field.

## Preconditions
- Workspace contains 2 valid presets; vault contains 1 valid preset.

## Steps
1. Call `result = list_presets(ws, vault, scope="all")`.
2. Assert it is dict-like with `presets` and `skipped` keys (or returns `(list, list)` per implementation -- check spec wording: "returns list of dicts ... `{skipped: ...}` in a secondary field").
3. Assert `len(result["presets"]) == 3`.
4. Each preset dict has all keys: `name, scope, tags, effect_count, description, path`.
5. Scope values include both `"workspace"` (2x) and `"vault"` (1x).
6. With `scope="workspace"`: only 2 results, all workspace.
7. With `scope="vault"`: only 1 result, vault scope.

## Expected Results
- Correct counts per scope; required keys present.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_io.py::test_list_presets_shape -v`

## Pass / Fail Criteria
- **Pass:** Counts and keys match.
- **Fail:** Otherwise.
