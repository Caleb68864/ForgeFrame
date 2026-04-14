---
scenario_id: "SR-07"
title: "CLI catalog regenerate-wrappers --output writes package"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - generator
  - cli
sequential: false
---

# Scenario SR-07: CLI `catalog regenerate-wrappers --output` writes package

## Steps
1. Run `uv run workshop-video-brain catalog regenerate-wrappers --output /tmp/test_wrappers_cli`.
2. Assert exit code 0.
3. Assert `/tmp/test_wrappers_cli/__init__.py` exists.
4. Assert count of emitted `.py` files equals `len(select_wrappable_effects(CATALOG)) + 1`.
5. Spot-check one module parses with `ast.parse`.

## Expected Results
- CLI succeeds; files written at specified path.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_wrapper_gen.py::test_cli_regenerate -v`

## Pass / Fail Criteria
- **Pass:** all assertions true.
- **Fail:** exit code non-zero or file count mismatch.
