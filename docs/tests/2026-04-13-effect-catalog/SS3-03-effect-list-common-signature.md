---
scenario_id: "SS3-03"
title: "effect_list_common signature unchanged"
tool: "bash"
type: test-scenario
tags: [test-scenario, mcp, structural, backwards-compat]
---

# Scenario SS3-03: effect_list_common signature unchanged

## Description
Verifies `[STRUCTURAL]` requirement: existing `effect_list_common` keeps its signature; only the body changes.

## Preconditions
- Knowledge of pre-spec signature (no required parameters; returns dict).

## Steps
1. Import `effect_list_common`.
2. Inspect signature; assert no required parameters.
3. Assert return annotation unchanged from baseline (`dict` or whatever was previously declared -- record at test time and freeze).

## Expected Results
- Signature byte-identical to pre-spec form.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py::test_effect_list_common_signature_unchanged -v`

## Pass / Fail Criteria
- **Pass:** Sig matches recorded baseline.
- **Fail:** Any added/removed parameter.
