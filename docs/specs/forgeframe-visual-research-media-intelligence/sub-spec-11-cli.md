---
sub_spec_id: SS-11
phase: run
depends_on: ['SS-02', 'SS-03', 'SS-04', 'SS-10']
dispatch: factory
wave: 6
---

# SS-11 — CLI commands (research / frame / scenes / transcript) with --json

## Context
Entry-point integration sub-spec. Add four Click groups to the existing `main` group in
`app/cli.py`, following the `@main.group()` + lazy-import-inside-command pattern (see
`workspace_create`). Each supports `--json`. `main` is the `wvb` console script.

## Implementation Steps (TDD)
1. **Failing test** `tests/integration/test_cli_research_smoke.py` (use `click.testing.CliRunner`):
   `research <fixture> --transcript <fixture.json> --query "reporter on camera" --output <tmp>
   --json` exits 0, prints JSON with `source`/`regions`/`captures`, package on disk; `frame
   <fixture> --timestamp 0.5 --json` prints one capture + writes one image; `scenes <fixture>
   --json` prints a JSON list of `{timestamp_seconds, score}`; `research … --dry-run` prints
   resolved regions + expected counts and writes no images; assert existing commands (`version`,
   `workspace`) still resolve.
2. **Run to fail:** `uv run pytest tests/integration/test_cli_research_smoke.py -q`.
3. **Implement** in `app/cli.py`: `@main.group() research/frame/scenes/transcript` with the options
   from the master spec; wire `research` to `research_video`, `frame` to `extract_frame`/
   `extract_centered_burst`, `scenes` to `detect_scene_changes`, `transcript` to
   `TranscriptRepository`/`parse_transcript`. `--json` emits the machine-readable shape. Lazy-import
   heavy modules inside each command. Write `tests/integration/ss11-integration-evidence.md` with a
   captured `--json` run.
4. **Run to pass:** `uv run pytest tests/integration/test_cli_research_smoke.py -q`.
5. **Full regression:** `uv run pytest tests/ -q` (existing 2,189 unaffected).
6. **Commit:** `factory(SS-11): research/frame/scenes/transcript CLI with --json [factory-managed]`

## Interface Contracts
- **Consumer** of `research_video` (SS-10), `extract_frame*` (SS-02), `detect_scene_changes`
  (SS-03), `parse_transcript`/`TranscriptRepository` (SS-04). Implements the CLI wiring; owns no
  contract others consume.

## Verification Commands
- `uv run pytest tests/integration/test_cli_research_smoke.py -q`
- `uv run pytest tests/ -q`

## Checks
| Criterion | Type | Command |
|-----------|------|---------|
| cli registers the four groups | [STRUCTURAL] | `grep -Eq "def research\b" workshop-video-brain/src/workshop_video_brain/app/cli.py && grep -q "def scenes" workshop-video-brain/src/workshop_video_brain/app/cli.py && grep -q "def frame" workshop-video-brain/src/workshop_video_brain/app/cli.py \|\| (echo "FAIL: cli groups missing" && exit 1)` |
| integration evidence written | [STRUCTURAL] | `test -f tests/integration/ss11-integration-evidence.md \|\| (echo "FAIL: ss11 evidence missing" && exit 1)` |
| cli integration smoke passes | [MECHANICAL] | `uv run pytest tests/integration/test_cli_research_smoke.py -q 2>&1 \| tail -1; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: cli smoke" && exit 1)` |
| full suite passes (no regression) | [MECHANICAL] | `uv run pytest tests/ -q 2>&1 \| tail -1; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: full suite" && exit 1)` |
