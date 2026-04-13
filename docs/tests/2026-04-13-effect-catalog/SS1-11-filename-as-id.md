---
scenario_id: "SS1-11"
title: "kdenlive_id derived from filename stem"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, behavioral]
---

# Scenario SS1-11: kdenlive_id derived from filename stem

## Description
Verifies `[BEHAVIORAL]` rule: there is no explicit id attribute in the XML; `parse_effect_xml` must use `path.stem` as `kdenlive_id`.

## Preconditions
- Two fixture files with identical XML body but different filenames (e.g. copy `acompressor.xml` to `renamed_compressor.xml`).

## Steps
1. Parse `acompressor.xml`; assert `eff.kdenlive_id == "acompressor"`.
2. Parse `renamed_compressor.xml`; assert `eff.kdenlive_id == "renamed_compressor"`.
3. Assert `mlt_service` is identical between the two (confirming id comes from filename, not body).

## Expected Results
- Different ids, same mlt_service.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py::test_filename_as_id -v`

## Pass / Fail Criteria
- **Pass:** Both asserts succeed.
- **Fail:** id sourced from XML body or matches across files.
