---
scenario_id: "SR-08"
title: "Script scripts/generate_effect_wrappers.py equivalent to CLI"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - generator
sequential: false
---

# Scenario SR-08: Script equivalent to CLI

## Steps
1. Run `uv run python scripts/generate_effect_wrappers.py --output /tmp/test_wrappers_script`.
2. Run CLI to `/tmp/test_wrappers_cli_cmp`.
3. Diff both dirs -- must be byte-identical.

## Expected Results
- Directories contain identical files with identical contents.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_wrapper_gen.py::test_script_matches_cli -v`

## Pass / Fail Criteria
- **Pass:** no diff.
- **Fail:** any difference.
