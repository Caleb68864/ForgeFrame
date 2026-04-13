---
scenario_id: "SS3-04"
title: "CLI catalog regenerate subcommand exists with flags"
tool: "bash"
type: test-scenario
tags: [test-scenario, cli, structural]
---

# Scenario SS3-04: CLI catalog regenerate subcommand exists with flags

## Description
Verifies `[STRUCTURAL]` CLI surface: `workshop-video-brain catalog regenerate` accepts `--no-upstream-check` and `--output PATH`.

## Preconditions
- CLI installed via `uv sync`.

## Steps
1. Run `uv run workshop-video-brain catalog regenerate --help`.
2. Assert exit 0.
3. Assert stdout contains `--no-upstream-check`.
4. Assert stdout contains `--output`.
5. Run `uv run workshop-video-brain catalog --help`; assert `regenerate` listed as a subcommand.

## Expected Results
- Subcommand discoverable with both flags.

## Execution Tool
bash -- `uv run workshop-video-brain catalog regenerate --help` (assertions in pytest)

## Pass / Fail Criteria
- **Pass:** Both flags + subcommand visible.
- **Fail:** Missing flag, subcommand, or non-zero exit.
