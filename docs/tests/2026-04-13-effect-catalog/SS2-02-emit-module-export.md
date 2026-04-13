---
scenario_id: "SS2-02"
title: "emit_python_module signature exported"
tool: "bash"
type: test-scenario
tags: [test-scenario, generator, structural]
---

# Scenario SS2-02: emit_python_module signature exported

## Description
Verifies `[STRUCTURAL]` `emit_python_module(effects, output_path, source_version, diff_report) -> None` exists with named parameters.

## Preconditions
- Generator module importable.

## Steps
1. Import `emit_python_module`.
2. Inspect signature; assert parameter names + order: `["effects", "output_path", "source_version", "diff_report"]`.
3. Assert return annotation is `None`.

## Expected Results
- Signature matches contract.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_generator.py::test_emit_python_module_signature -v`

## Pass / Fail Criteria
- **Pass:** Sig matches.
- **Fail:** Mismatch.
