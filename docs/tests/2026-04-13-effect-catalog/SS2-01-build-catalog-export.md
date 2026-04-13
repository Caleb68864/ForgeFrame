---
scenario_id: "SS2-01"
title: "build_catalog signature exported"
tool: "bash"
type: test-scenario
tags: [test-scenario, generator, structural]
---

# Scenario SS2-01: build_catalog signature exported

## Description
Verifies `[STRUCTURAL]` `build_catalog(local_dir: Path, check_upstream: bool = True) -> tuple[list[EffectDef], DiffReport]` exists with documented parameters.

## Preconditions
- Sub-Spec 2 implementation merged.

## Steps
1. `from workshop_video_brain.edit_mcp.pipelines.effect_catalog_gen import build_catalog`.
2. `import inspect; sig = inspect.signature(build_catalog)`.
3. Assert parameter names + order: `["local_dir", "check_upstream"]`.
4. Assert `sig.parameters["check_upstream"].default is True`.
5. Assert annotations match (`Path`, `bool`).

## Expected Results
- Signature matches contract.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_generator.py::test_build_catalog_signature -v`

## Pass / Fail Criteria
- **Pass:** Sig matches.
- **Fail:** Missing parameter or wrong default.
