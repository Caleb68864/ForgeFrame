---
scenario_id: "SR-18"
title: "Alpha-routing property decision (target-property OR pure stack-order)"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-2
  - sequential
---

# Scenario SR-18: Alpha-routing property decision (target-property OR pure stack-order)

## Description
Verifies the two [BEHAVIORAL] branches of Kdenlive's alpha-routing mechanism:
1. If Kdenlive requires a property on the target filter (e.g., `use_mask=1`) as confirmed by inspecting `tests/unit/fixtures/masking_reference.kdenlive`, `apply_mask_to_effect` sets that property via `patcher.set_effect_property` on the target.
2. Otherwise, alpha routing is pure stack-order; no property is set; the module docstring explicitly documents this.

## Preconditions
- `tests/unit/fixtures/masking_reference.kdenlive` present (hand-authored with a mask + downstream effect).
- Module docstring accessible via `masking.__doc__` or module-level constant.

## Steps
1. Parse `tests/unit/fixtures/masking_reference.kdenlive`; locate the filter that consumes the rotoscoping mask's alpha.
2. Inspect that filter's MLT properties and compare against a vanilla (non-masked) instance of the same effect. Any property difference is the alpha-routing property.
3. If a difference is found (branch A):
   - Call `apply_mask_to_effect` on a clean clip with mask + target.
   - Assert that `patcher.set_effect_property` was called on the target with the discovered property name and expected value.
4. If no property difference (branch B):
   - Call `apply_mask_to_effect` on a clean clip.
   - Assert that `patcher.set_effect_property` was NOT called on the target.
   - Assert that `masking.__doc__` (or module docstring) contains a documented explanation that alpha routing is pure stack-order.

## Expected Results
- Exactly one branch applies; assertions for that branch pass.
- In branch B, docstring explicitly documents pure-stack-order routing.

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_alpha_routing.py::test_alpha_routing_property_or_stack_order -v`

## Pass / Fail Criteria
- **Pass:** implementation matches reality of the reference fixture.
- **Fail:** property is set when not needed, or not set when required, or missing docstring in branch B.
