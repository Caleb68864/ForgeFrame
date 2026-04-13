---
scenario_id: "SS2-06"
title: "build_catalog on fixture dir w/ check_upstream=False"
tool: "bash"
type: test-scenario
tags: [test-scenario, generator, behavioral]
---

# Scenario SS2-06: build_catalog on fixture dir w/ check_upstream=False

## Description
Verifies `[BEHAVIORAL]` `build_catalog(fixture_dir, check_upstream=False)` returns a 3-element list and a DiffReport with `upstream_check="skipped"`.

## Preconditions
- Fixture dir `tests/unit/fixtures/effect_xml/build_three/` containing exactly 3 valid XML fixtures.

## Steps
1. `effects, report = build_catalog(fixture_dir, check_upstream=False)`.
2. Assert `len(effects) == 3`.
3. Assert `isinstance(effects[0], EffectDef)`.
4. Assert `report.upstream_check == "skipped"`.
5. Assert `report.upstream_count is None`.
6. Assert `report.local_count == 3`.

## Expected Results
- Three effects parsed; report reflects skipped upstream.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_generator.py::test_build_catalog_skip_upstream -v`

## Pass / Fail Criteria
- **Pass:** All asserts succeed.
- **Fail:** Wrong count or upstream not skipped.
