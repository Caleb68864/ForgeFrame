---
scenario_id: "SS2-03"
title: "fetch_upstream_effects signature exported"
tool: "bash"
type: test-scenario
tags: [test-scenario, generator, structural]
---

# Scenario SS2-03: fetch_upstream_effects signature exported

## Description
Verifies `[STRUCTURAL]` `fetch_upstream_effects() -> list[str] | None`.

## Preconditions
- Generator module importable.

## Steps
1. Import `fetch_upstream_effects`.
2. Inspect signature; assert no required parameters.
3. Assert return annotation is `list[str] | None` (string-match acceptable).

## Expected Results
- Sig matches contract.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_generator.py::test_fetch_upstream_effects_signature -v`

## Pass / Fail Criteria
- **Pass:** Sig matches.
- **Fail:** Missing or differing.
