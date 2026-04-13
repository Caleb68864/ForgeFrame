---
scenario_id: "SS2-10"
title: "Duplicate kdenlive_id warns + last-wins"
tool: "bash"
type: test-scenario
tags: [test-scenario, generator, edge-case]
---

# Scenario SS2-10: Duplicate kdenlive_id warns + last-wins

## Description
Verifies edge-case (spec Edge Cases): two parsed XMLs with the same filename stem (e.g. one in subdir) -- last wins in CATALOG and a warning lists both filenames.

## Preconditions
- Fixture dir with two files producing the same `kdenlive_id` (e.g. `transform.xml` and `subdir/transform.xml`, with different `tag` attributes for verification).

## Steps
1. Capture warnings: `with caplog.at_level(logging.WARNING):` (or `pytest.warns`).
2. Run `effects, _ = build_catalog(dup_dir, check_upstream=False)`.
3. Then `emit_python_module(...)` -> import, inspect `CATALOG["transform"]`.
4. Assert `CATALOG["transform"].mlt_service` matches the second-encountered file's tag.
5. Assert at least one warning record contains both filenames.

## Expected Results
- Last-wins behaviour; warning identifies both source files.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_generator.py::test_duplicate_id_last_wins -v`

## Pass / Fail Criteria
- **Pass:** Last-wins + warning present.
- **Fail:** Crash, first-wins, or no warning.
