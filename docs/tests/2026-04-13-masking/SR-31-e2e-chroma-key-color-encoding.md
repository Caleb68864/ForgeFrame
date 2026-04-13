---
scenario_id: "SR-31"
title: "effect_chroma_key(#00FF00) persists with MLT-encoded color 0x00ff00ff"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-3
  - sequential
---

# Scenario SR-31: effect_chroma_key(#00FF00) persists with MLT-encoded color 0x00ff00ff

## Description
Verifies [BEHAVIORAL] that `effect_chroma_key(color="#00FF00")` inserts a chroma key filter whose color property is encoded in MLT canonical form `0x00ff00ff` (default alpha `ff` appended).

## Preconditions
- Fresh workspace + project fixture.

## Steps
1. Call `effect_chroma_key(..., color="#00FF00")`.
2. Re-read project from disk.
3. Locate the chroma key filter.
4. Assert its color property text equals `0x00ff00ff`.
5. Also test `color="#FF000080"` → expect `0xff000080`.

## Expected Results
- Persisted color is lowercase `0xRRGGBBAA`.
- Default alpha `ff` appended when source lacks alpha.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_e2e_chroma_key_color_encoding -v`

## Pass / Fail Criteria
- **Pass:** both color encodings match expected hex strings.
- **Fail:** any case wrong encoding or alpha missing.
