---
scenario_id: "SR-04"
title: "Generated wrappers package imports cleanly (smoke test)"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - generator
  - smoke
sequential: false
---

# Scenario SR-04: Generated wrappers package imports cleanly

## Description
End-to-end smoke test: regenerate the package in-tree, then import it and call an attribute -- no runtime file I/O at import, no ImportError.

## Preconditions
- Catalog loaded.
- Generator shipped.

## Steps
1. Run the CLI: `uv run workshop-video-brain catalog regenerate-wrappers` (writes to default in-tree location).
2. In a subprocess, run `python -c "from workshop_video_brain.edit_mcp.pipelines.effect_wrappers import effect_transform; print(effect_transform.__doc__)"`.
3. Assert subprocess exits 0.
4. Assert stdout is non-empty and contains catalog-derived description text for `transform`.
5. Assert `from workshop_video_brain.edit_mcp.pipelines.effect_wrappers import *` succeeds (no circular import against `tools.py`).

## Expected Results
- Subprocess exit 0.
- Docstring prints.
- No ImportError, no circular import.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_wrapper_gen.py::test_generated_package_imports -v`

## Pass / Fail Criteria
- **Pass:** import succeeds, docstring present.
- **Fail:** any ImportError or empty docstring.
