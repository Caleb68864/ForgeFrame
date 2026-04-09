---
scenario_id: "MD-01"
title: "SerializableMixin JSON/YAML round-trip"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario MD-01: SerializableMixin JSON/YAML round-trip

## Description
Verify that `SerializableMixin` (from `core/models/_base.py`) correctly serializes
to and deserializes from both JSON and YAML. The mixin's four methods --
`to_json`, `from_json`, `to_yaml`, `from_yaml` -- must preserve all field values,
produce valid Python types in YAML output (no enum instances), and handle
unicode content without corruption.

## Preconditions
- Source module exists and is importable: `workshop_video_brain.core.models._base`

## Test Cases
- **TestToJson**: `to_json()` returns indented JSON string; parsed dict matches `model_dump()`
- **TestFromJson**: `from_json(json_str)` reconstructs an equal instance
- **TestJsonRoundTrip**: `from_json(instance.to_json()) == instance`
- **TestToYaml**: `to_yaml()` returns a valid YAML string; `yaml.safe_load()` parses without error
- **TestFromYaml**: `from_yaml(yaml_str)` reconstructs an equal instance
- **TestYamlRoundTrip**: `from_yaml(instance.to_yaml()) == instance`
- **TestYamlUnicode**: fields containing unicode (e.g., `"caf\u00e9"`) survive the YAML round-trip
- **TestYamlNoEnumInstances**: YAML output contains only plain Python scalars, not enum repr strings
- **TestFromJsonBytes**: `from_json(b"...")` accepts bytes as well as str
- **TestFromYamlBytes**: `from_yaml(b"...")` accepts bytes as well as str

## Steps
1. Read source module: `workshop_video_brain/core/models/_base.py`
2. Create `tests/unit/test_base_serialization_model.py`
3. Define a minimal concrete subclass: `class _Fixture(SerializableMixin): name: str; value: int = 0`
4. Implement all test cases listed above using `pytest`
5. Run: `uv run pytest tests/unit/test_base_serialization_model.py -v`

## Expected Results
- `to_json()` output is valid JSON with 2-space indent
- `from_json(instance.to_json())` returns an object equal to the original
- `to_yaml()` output parses to a plain dict (no enum instances)
- `from_yaml(instance.to_yaml())` returns an object equal to the original
- Unicode characters are preserved through the YAML round-trip (`allow_unicode=True`)
- Both methods accept `bytes` input without raising

## Pass / Fail Criteria
- Pass: All construction, serialization, and round-trip tests pass
- Fail: Any test fails
