---
scenario_id: "SS2-11"
title: "scripts/generate_effect_catalog.py runs against fixtures"
tool: "bash"
type: test-scenario
tags: [test-scenario, generator, mechanical, sequential]
---

# Scenario SS2-11: scripts/generate_effect_catalog.py runs against fixtures

## Description
Verifies `[MECHANICAL]` script invocation against fixture dir: exits 0 and writes a syntactically valid Python file.

## Preconditions
- `scripts/generate_effect_catalog.py` exists.
- Fixture dir present.
- `/tmp/test_catalog.py` writable.

## Steps
1. Run `python scripts/generate_effect_catalog.py --no-upstream-check --output /tmp/test_catalog.py --source-dir tests/unit/fixtures/effect_xml/build_three/`.
2. Assert exit code 0.
3. Assert `/tmp/test_catalog.py` exists.
4. Run `python -c "import importlib.util; s=importlib.util.spec_from_file_location('c','/tmp/test_catalog.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert len(m.CATALOG) == 3"`.

## Expected Results
- File written, importable, 3 entries.

## Execution Tool
bash -- shell command above

## Pass / Fail Criteria
- **Pass:** Exit 0 + import succeeds + count correct.
- **Fail:** Non-zero exit, SyntaxError, or wrong count.
