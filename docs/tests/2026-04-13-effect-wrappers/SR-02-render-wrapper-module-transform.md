---
scenario_id: "SR-02"
title: "render_wrapper_module produces valid Python for transform"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - generator
  - rendering
sequential: false
---

# Scenario SR-02: `render_wrapper_module` produces valid Python for `transform`

## Description
Verifies the renderer emits syntactically valid Python containing the expected function signature, `@mcp.tool()` decoration, and the GENERATED marker.

## Preconditions
- Catalog entry `transform` exists.
- `render_wrapper_module` importable.

## Steps
1. Load `effect_def = CATALOG["transform"]`.
2. Call `src = render_wrapper_module(effect_def)`.
3. Parse with `ast.parse(src)` — must not raise.
4. Assert `"def effect_transform(" in src`.
5. Assert `"@mcp.tool()" in src` (or equivalent `register_effect_wrapper` decorator).
6. Assert `"GENERATED"` appears in the module docstring.
7. Assert a `keyframes: str = ""` kwarg is present (transform has animated/geometry params).
8. Assert every non-HIDDEN catalog `ParamDef` appears as a typed kwarg with the catalog default.

## Expected Results
- `ast.parse` succeeds.
- Signature and decorator and marker all present.
- Keyframes kwarg present for geometry/animated effects.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_wrapper_gen.py::test_render_wrapper_module_transform -v`

## Pass / Fail Criteria
- **Pass:** all assertions pass.
- **Fail:** `ast.parse` raises, or any expected token missing.
