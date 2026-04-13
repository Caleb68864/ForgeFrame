---
scenario_id: "SS2-09"
title: "fetch_upstream_effects returns None on network failure"
tool: "bash"
type: test-scenario
tags: [test-scenario, generator, behavioral, fallback]
---

# Scenario SS2-09: fetch_upstream_effects returns None on network failure

## Description
Verifies `[BEHAVIORAL]` graceful fallback (Intent escalation trigger): when upstream fetch fails (network error, 404, auth), the function returns `None` and does not raise.

## Preconditions
- Generator module importable.
- Use `monkeypatch` (pytest) or `unittest.mock` to patch the underlying HTTP client (`urllib.request.urlopen` or `requests.get`) to raise `OSError("network down")`.

## Steps
1. Patch the network call to raise.
2. `result = fetch_upstream_effects()`.
3. Assert `result is None`.
4. Assert no exception escaped.
5. Re-patch to raise `HTTPError(404)`; assert same `None` result.
6. Optionally assert a warning was logged.

## Expected Results
- Always returns None on any failure path; never raises.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_catalog_generator.py::test_fetch_upstream_failure -v`

## Pass / Fail Criteria
- **Pass:** Both failure modes return None silently.
- **Fail:** Raises or returns non-None.
