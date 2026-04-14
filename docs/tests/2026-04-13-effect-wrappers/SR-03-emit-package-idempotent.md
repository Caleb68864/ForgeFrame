---
scenario_id: "SR-03"
title: "emit_wrappers_package is idempotent (byte-identical re-runs)"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - generator
  - idempotency
sequential: false
---

# Scenario SR-03: `emit_wrappers_package` is idempotent

## Description
Verifies the generator produces byte-identical output on two consecutive runs against the same catalog. Required by spec "Regeneration must be idempotent."

## Preconditions
- `emit_wrappers_package` importable.
- `tmp_path` pytest fixture for output dirs.

## Steps
1. Call `emit_wrappers_package(effects, tmp_path / "run1")`.
2. Call `emit_wrappers_package(effects, tmp_path / "run2")`.
3. Walk both directories recursively.
4. Assert filesets match exactly (same filenames).
5. Assert each corresponding file has identical bytes (e.g., hashlib.sha256 compare).
6. Assert `__init__.py` lists tool names in a deterministic (sorted) order.

## Expected Results
- Both runs produce the same set of files.
- Every file is byte-for-byte identical.
- `__init__.py` ordering is stable.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_wrapper_gen.py::test_emit_package_idempotent -v`

## Pass / Fail Criteria
- **Pass:** all files byte-identical.
- **Fail:** any diff or missing/extra file.
