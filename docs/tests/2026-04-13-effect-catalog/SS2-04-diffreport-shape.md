---
scenario_id: "SS2-04"
title: "DiffReport dataclass has documented fields"
tool: "bash"
type: test-scenario
tags: [test-scenario, generator, structural]
---

# Scenario SS2-04: DiffReport dataclass has documented fields

## Description
Verifies `[STRUCTURAL]` `DiffReport` fields: `local_count: int`, `upstream_count: int | None`, `upstream_only_ids: tuple[str,...]`, `local_only_ids: tuple[str,...]`, `upstream_check: Literal["ok","skipped","failed"]`.

## Preconditions
- Generator module importable.

## Steps
1. Import `DiffReport`; assert dataclass.
2. Build expected field set; compare to `{f.name for f in dataclasses.fields(DiffReport)}`.
3. For each field, inspect the annotation matches the documented type (string compare on `f.type`).

## Expected Results
- Exact contract met.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_generator.py::test_diffreport_shape -v`

## Pass / Fail Criteria
- **Pass:** Field set + types match.
- **Fail:** Mismatch.
