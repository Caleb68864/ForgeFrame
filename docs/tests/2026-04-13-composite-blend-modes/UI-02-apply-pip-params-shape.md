---
scenario_id: "UI-02"
title: "apply_pip emits AddComposition with unchanged params dict shape"
tool: "bash"
type: test-scenario
covers: ["Edge: params dict shape preservation"]
tags: [test-scenario, regression, behavioral]
---

# Scenario UI-02: apply_pip params dict shape preserved

## Description
Spec Edge Case: "ensure the `params` dict passed into `AddComposition` has the same key/value shape before and after rewire (e.g., don't introduce a new `compositing` key unless the old default path did so too)."

This is the white-box counterpart to UI-01: even if byte output matches, this test pins the intent-level params dict so a future serializer change doesn't mask a wiring regression.

## Preconditions
- Ability to intercept the `AddComposition` intent (e.g., monkeypatch `patch_project` to capture intents, or refactor to expose intent list for testing).

## Steps
1. Monkeypatch `workshop_video_brain.edit_mcp.pipelines.compositing.patch_project` to record intents then call through.
2. Invoke `apply_pip(...)` with deterministic args.
3. Capture the `AddComposition` intent.
4. Assert `intent.composition_type == "composite"`.
5. Assert `intent.params` has exactly the keys present in the pre-rewire implementation (baseline: `{"geometry"}`). If the rewire requires adding a `compositing` key because `apply_composite` now always sets it, assert that baseline PLUS `{"compositing"}` -- AND cross-check that UI-01 remains byte-identical (if it does not, the serializer already carried that default implicitly; reconcile).
6. Assert `intent.params["geometry"]` equals `"{x}/{y}:{w}x{h}:100"` for the input layout.

## Expected Results
- Params keys match the baseline (plus the documented `compositing` key iff UI-01 still passes byte-identity).

## Execution Tool
bash -- `uv run pytest tests/unit/test_apply_pip_regression.py::test_apply_pip_params_shape -v`

## Pass / Fail Criteria
- **Pass:** Keys/values match the baseline contract.
- **Fail:** Unexpected key appears that is not reflected in UI-01's golden, or values differ.
