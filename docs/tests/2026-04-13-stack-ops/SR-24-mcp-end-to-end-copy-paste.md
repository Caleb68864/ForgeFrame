---
scenario_id: "SR-24"
title: "End-to-end copy → JSON → paste (append) via MCP layer"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
  - integration
  - sequential
---

# Scenario SR-24: MCP end-to-end copy + paste

## Description
Verifies `[BEHAVIORAL]`/`[INTEGRATION]` -- the round-trip caller pattern: `effects_copy(source)` → `json.dumps(data.stack)` → `effects_paste(target, stack=<json>, mode="append")`. After paste, `list_effects(target)` reflects the appended filters at the end of the prior stack.

## Preconditions
- Fresh temp workspace with fixture.
- Sequential -- mutates state.

## Steps
1. `cp = effects_copy(workspace, project_file, track=2, clip=0)`.
2. `stack_json = json.dumps(cp["data"]["stack"])`.
3. Capture target's pre-paste `list_effects` baseline -- `pre = list_effects(track=3, clip=0)`.
4. `pst = effects_paste(workspace, project_file, track=3, clip=0, stack=stack_json, mode="append")`.
5. Assert `pst["status"] == "ok"` and `pst["data"]["effects_pasted"] == cp["data"]["effect_count"]`.
6. `post = list_effects(track=3, clip=0)`.
7. Assert `len(post) == len(pre) + cp["data"]["effect_count"]`.
8. Assert `post[len(pre):]` ids match source stack ids in order.

## Expected Results
- Append round-trip wires correctly through MCP boundary.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_ops_mcp_tools.py::test_e2e_copy_paste_append -v`

## Pass / Fail Criteria
- **Pass:** Counts and order correct.
- **Fail:** Mismatched counts/order or non-ok status.
