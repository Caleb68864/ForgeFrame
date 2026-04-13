---
scenario_id: "SS2-07"
title: "emit_python_module produces importable round-trip module"
tool: "bash"
type: test-scenario
tags: [test-scenario, generator, behavioral, sequential]
---

# Scenario SS2-07: emit_python_module produces importable round-trip module

## Description
Verifies `[BEHAVIORAL]` round-trip: parse fixture dir -> emit module -> import emitted module -> verify CATALOG matches input.

## Preconditions
- Fixture dir of 3 XMLs.
- `/tmp/emit_test/` writable.

## Steps
1. `effects, report = build_catalog(fixture_dir, check_upstream=False)`.
2. `emit_python_module(effects, Path("/tmp/emit_test/effect_catalog.py"), "test-1.0", report)`.
3. Use `importlib.util.spec_from_file_location` to load the emitted module.
4. Assert module is syntactically valid (no SyntaxError on import).
5. Assert `set(loaded.CATALOG.keys()) == {e.kdenlive_id for e in effects}`.
6. Assert each loaded `EffectDef` equals the in-memory counterpart (or has identical scalar fields).

## Expected Results
- Emitted file valid and importable; CATALOG reproduces input.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_generator.py::test_emit_python_module_roundtrip -v`

## Pass / Fail Criteria
- **Pass:** Round-trip equality holds.
- **Fail:** SyntaxError, ImportError, or mismatch.
