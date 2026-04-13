---
scenario_id: "SR-08"
title: "build_rotoscoping_xml emits correct MLT structure and properties"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-1
---

# Scenario SR-08: build_rotoscoping_xml emits correct MLT structure and properties

## Description
Verifies [BEHAVIORAL] that `build_rotoscoping_xml((2,0), MaskParams(points=((0,0),(1,0),(1,1),(0,1)), feather=5, alpha_operation="subtract"))` produces MLT XML with the correct root element, attributes, and property children matching Kdenlive's `/usr/share/kdenlive/effects/rotoscoping.xml` convention.

## Preconditions
- Module importable.
- `/usr/share/kdenlive/effects/rotoscoping.xml` available for reference (read once during test setup to derive the exact spline/points property name).

## Steps
1. Read `/usr/share/kdenlive/effects/rotoscoping.xml` to determine the canonical property name used by Kdenlive for the spline/points list (e.g., `spline` or `shape`).
2. Call `build_rotoscoping_xml((2, 0), MaskParams(points=((0,0),(1,0),(1,1),(0,1)), feather=5, alpha_operation="subtract"))`.
3. Parse the returned XML string with `xml.etree.ElementTree`.
4. Assert root element is `<filter>` with attributes `mlt_service="rotoscoping"`, `track="2"`, `clip_index="0"`.
5. Assert `<property name="spline_is_open">` child exists.
6. Assert `<property name="feather">` child with text `5`.
7. Assert `<property name="alpha_operation">` child with text `subtract`.
8. Assert the points-list property is emitted under the exact name used by Kdenlive (step 1), with the 4 points serialized.

## Expected Results
- All attribute and property assertions pass.
- XML is well-formed (parses without error).
- Property name for the spline points matches Kdenlive's reference XML (not invented).

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_pipeline.py::test_build_rotoscoping_xml -v`

## Pass / Fail Criteria
- **Pass:** all assertions pass and point-list property name matches Kdenlive reference.
- **Fail:** any attribute/property wrong or point-list property name diverges from Kdenlive.
