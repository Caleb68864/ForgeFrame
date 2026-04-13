---
scenario_id: "SR-29"
title: "End-to-end chain: mask_set_shape + effect_add(glow) + mask_apply"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-3
  - sequential
---

# Scenario SR-29: End-to-end chain: mask_set_shape + effect_add(glow) + mask_apply

## Description
Verifies [BEHAVIORAL] the full localize flow: mask set, secondary effect added, `mask_apply` binds effect to mask alpha. Inspection after the chain shows mask at index 0, glow at index 1, and (if Kdenlive requires) alpha-routing property set on the glow.

## Preconditions
- Fresh workspace + project fixture with a clip.
- `effect_add` MCP tool (from prior specs) operational.

## Steps
1. Call `mask_set_shape(..., shape="rect", bounds="[0.2,0.2,0.6,0.6]")` → capture `effect_index_mask`.
2. Call `effect_add(..., effect_name="glow")` (or catalog-equivalent) → capture `effect_index_glow`.
3. Call `mask_apply(..., mask_effect_index=effect_index_mask, target_effect_index=effect_index_glow)`.
4. Re-read project file; enumerate clip filters.
5. Assert mask (rotoscoping) at index 0, glow at index 1.
6. If SR-18 determined alpha routing needs a target property, assert it is set on the glow filter.

## Expected Results
- Mask precedes glow in stack.
- `mask_apply.data.reordered` consistent with whether reorder was needed.
- Alpha-routing property present on target if required by Kdenlive.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_e2e_chain_mask_effect_apply -v`

## Pass / Fail Criteria
- **Pass:** stack order correct + optional target property set when required.
- **Fail:** wrong order or missing property.
