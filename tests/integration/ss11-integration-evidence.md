# SS-11 Integration Evidence — CLI research/frame/scenes/transcript commands

## Fixtures

- `tests/fixtures/media_generated/greenscreen_reporter_720.mp4` (20.02s, video-only).
- `tests/fixtures/transcripts/sample.json` (segment text includes "reporter"
  and "greenscreen").

## `wvb research --json`

`tests/integration/test_cli_research_smoke.py::TestResearchCommand::test_research_end_to_end_json`
invokes the CLI via `click.testing.CliRunner`:

```
wvb research <fixture> --transcript sample.json --query reporter --output <tmp> --json
```

Observed result: exit code 0, stdout is valid JSON containing `source`,
`regions` (>= 1), and `captures` (>= 1); the output directory exists on
disk with a `manifest.json` written by the underlying `export_package`
step.

## `wvb research --dry-run --json`

`test_research_dry_run_writes_no_images` runs the same command with
`--dry-run`. Result: exit code 0, JSON payload has `dry_run: true` and a
`regions` list where each entry carries `expected_candidate_count`; no
output directory is created (no frames extracted).

## `wvb frame --json`

`TestFrameCommand::test_frame_single_timestamp_json` runs
`wvb frame <fixture> --timestamp 0.5 --json`. Result: exit code 0, JSON is
a single capture object with `timestamp_seconds == 0.5`, and the
`image_path` it references exists on disk with non-zero size.

## `wvb scenes --json`

`TestScenesCommand::test_scenes_json_list` runs `wvb scenes <fixture> --json`.
Result: exit code 0, JSON is a list of `{timestamp_seconds, score}` objects
with at least one entry (scene detection falls back to bounded uniform
sampling on this mostly-static fixture).

## `wvb transcript search` / `wvb transcript context`

`TestTranscriptCommands` runs both subcommands against
`tests/fixtures/transcripts/sample.json` with `--json`, confirming each
prints a JSON list of matching/contextual transcript segments.

## Test command

```
uv run pytest tests/integration/test_cli_research_smoke.py -q
```

## Verification run (SS-11-F14 / SS-11-F15)

```
$ uv run pytest tests/integration/test_cli_research_smoke.py -q
.......                                                                  [100%]
7 passed in 11.17s
```

Exit code: 0. All 7 CLI smoke tests pass.

```
$ uv run pytest tests/ -q
...
FAILED tests/unit/test_publishing.py::TestPackagePublishBundle::test_publish_bundle_json_is_valid
FAILED tests/unit/test_stack_presets_io.py::test_load_missing_raises_with_both_paths
2 failed, 2778 passed, 2 warnings in 131.72s (0:02:11)
```

The 2 failures are pre-existing and unrelated to this sub-spec's in-scope
files (`app/cli.py`, `test_cli_research_smoke.py`):

- `test_publishing.py::test_publish_bundle_json_is_valid` fails on Windows
  because `Path.read_text()` defaults to the `cp1252` codec, which cannot
  decode a UTF-8 multi-byte character (`0x8d`) written by
  `package_publish_bundle`; this is an existing encoding bug in the
  publishing module, not something introduced by the CLI wiring here.
- `test_stack_presets_io.py::test_load_missing_raises_with_both_paths` fails
  on Windows because the error message under test embeds a `\`-separated
  path while the assertion expects the POSIX separator
  `stacks/nope.yaml`; this is an existing path-separator assumption in the
  stack-presets test, unrelated to CLI research/frame/scenes/transcript
  commands.

Total collected test count (2,780) exceeds the spec's baseline of 2,189
because additional sub-specs (SS-06, SS-12, etc.) landed tests since that
baseline was recorded; no regression was introduced by SS-11 — the CLI
smoke suite is fully green and the two unrelated failures are pre-existing
Windows-environment issues outside this sub-spec's scope.
