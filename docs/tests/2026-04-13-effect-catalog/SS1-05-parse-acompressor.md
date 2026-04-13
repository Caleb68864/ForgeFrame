---
scenario_id: "SS1-05"
title: "parse_effect_xml on acompressor fixture returns full EffectDef"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, behavioral]
---

# Scenario SS1-05: parse_effect_xml on acompressor fixture returns full EffectDef

## Description
Verifies `[BEHAVIORAL]` end-to-end parse of `fixtures/effect_xml/acompressor.xml` -- a hand-crafted XML mirroring `/usr/share/kdenlive/effects/acompressor.xml` with 11 parameters.

## Preconditions
- Fixture file `tests/unit/fixtures/effect_xml/acompressor.xml` exists with all 11 `<parameter>` entries from the upstream Kdenlive copy.

## Steps
1. `eff = parse_effect_xml(Path("tests/unit/fixtures/effect_xml/acompressor.xml"))`.
2. Assert `eff.kdenlive_id == "acompressor"`.
3. Assert `eff.mlt_service == "avfilter.acompressor"`.
4. Assert `eff.display_name == "Compressor (avfilter)"`.
5. Assert `eff.category == "audio"`.
6. Assert `len(eff.params) == 11`.
7. Assert `eff.params[0].name == "av.level_in"` and `eff.params[0].type == ParamType.CONSTANT`.
8. Assert `eff.params[0].min == 0.016` and `eff.params[0].max == 64` and `eff.params[0].decimals == 3`.

## Expected Results
- Full EffectDef parsed with correct top-level + first-param fields.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py::test_parse_acompressor -v`

## Pass / Fail Criteria
- **Pass:** All field asserts succeed.
- **Fail:** Any field mismatch or count != 11.
