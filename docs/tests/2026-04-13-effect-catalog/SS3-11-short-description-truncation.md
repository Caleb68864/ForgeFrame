---
scenario_id: "SS3-11"
title: "Short description truncates at ~80 chars with ellipsis"
tool: "bash"
type: test-scenario
tags: [test-scenario, mcp, behavioral]
---

# Scenario SS3-11: Short description truncates at ~80 chars with ellipsis

## Description
Verifies `[BEHAVIORAL]` truncation rule: if catalog `description` > 80 chars, `effect_list_common` summary's `short_description` is truncated to ~80 chars + ellipsis (`…` or `...`).

## Preconditions
- A catalog entry with a description > 80 chars (or inject one via monkeypatching CATALOG for test isolation).

## Steps
1. Find an entry with `len(description) > 80`. If none, monkeypatch CATALOG to insert one with a 200-char description.
2. Call `effect_list_common()`.
3. Locate the corresponding summary entry by `kdenlive_id`.
4. Assert `len(short_description) <= 83` (80 + ellipsis tolerance).
5. Assert it ends with `"…"` or `"..."`.
6. Find an entry with `len(description) <= 80`; assert its `short_description == description` (no truncation).

## Expected Results
- Truncation only when needed; ellipsis suffix.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py::test_short_description_truncation -v`

## Pass / Fail Criteria
- **Pass:** Both truncated + non-truncated cases behave correctly.
- **Fail:** Always truncates or never truncates.
