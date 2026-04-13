---
scenario_id: "SS1-10"
title: "Unknown param type raises ValueError naming type + filename"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, behavioral, fail-loud]
---

# Scenario SS1-10: Unknown param type raises ValueError naming type + filename

## Description
Verifies `[BEHAVIORAL]` fail-loud requirement (Intent #4 + Requirement 6): an unrecognized `<parameter type="...">` string causes `parse_effect_xml` to raise `ValueError` whose message names both the offending type string and the filename.

## Preconditions
- Fixture `tests/unit/fixtures/effect_xml/unknown-type.xml` with `<parameter type="frobnicate" ...>`.

## Steps
1. `with pytest.raises(ValueError) as exc_info: parse_effect_xml(fixture_path)`.
2. Assert `"frobnicate"` in `str(exc_info.value)`.
3. Assert `"unknown-type.xml"` in `str(exc_info.value)`.

## Expected Results
- Raises ValueError mentioning both the type and the source filename.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py::test_parse_unknown_type_raises -v`

## Pass / Fail Criteria
- **Pass:** ValueError raised with both substrings present.
- **Fail:** No raise, wrong exception, or message missing context.
