---
scenario_id: "SS3-12"
title: "CLI catalog regenerate writes file when invoked"
tool: "bash"
type: test-scenario
tags: [test-scenario, cli, behavioral, sequential]
---

# Scenario SS3-12: CLI catalog regenerate writes file when invoked

## Description
Verifies `[BEHAVIORAL]` end-to-end CLI invocation: `uv run workshop-video-brain catalog regenerate --no-upstream-check --output /tmp/cli_catalog.py --source-dir tests/unit/fixtures/effect_xml/build_three/` exits 0 and writes the file.

## Preconditions
- CLI installed; fixture dir present; `/tmp/` writable.
- Note: if the CLI uses different flag names than the script (e.g. `--source` instead of `--source-dir`), accept the equivalent per spec criteria.

## Steps
1. Remove any prior `/tmp/cli_catalog.py`.
2. Run the CLI command above.
3. Assert exit code 0.
4. Assert `/tmp/cli_catalog.py` exists and is non-empty.
5. Load via `importlib.util`; assert `len(CATALOG) == 3`.

## Expected Results
- File generated; importable; correct count.

## Execution Tool
bash -- shell command + import check

## Pass / Fail Criteria
- **Pass:** Exit 0, file written, count correct.
- **Fail:** Non-zero exit, missing file, or wrong count.
