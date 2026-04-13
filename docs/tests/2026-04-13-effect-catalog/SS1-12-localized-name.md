---
scenario_id: "SS1-12"
title: "Localized <name lang=\"...\"> variants prefer no-lang"
tool: "bash"
type: test-scenario
tags: [test-scenario, parser, edge-case]
---

# Scenario SS1-12: Localized <name lang="..."> variants prefer no-lang

## Description
Verifies edge-case handling (spec Edge Cases): when an effect has both `<name>Foo</name>` and `<name lang="fr">Bar</name>`, parser must pick the no-`lang` variant. If only localized exist, take first in document order.

## Preconditions
- Fixture `localized-name.xml` with three `<name>` children: `<name lang="fr">Foo-FR</name>`, `<name>Foo</name>`, `<name lang="de">Foo-DE</name>`.
- Fixture `localized-only.xml` with only `<name lang="fr">Foo-FR</name>` and `<name lang="de">Foo-DE</name>`.

## Steps
1. Parse `localized-name.xml`; assert `eff.display_name == "Foo"`.
2. Parse `localized-only.xml`; assert `eff.display_name == "Foo-FR"` (first in document order).
3. Repeat for a parameter `<name>` -- assert same precedence rule applies to `ParamDef.display_name`.

## Expected Results
- No-lang preferred; fallback to first in document order.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_parser.py::test_localized_name_precedence -v`

## Pass / Fail Criteria
- **Pass:** Both fixtures yield the documented winner.
- **Fail:** Wrong locale chosen.
