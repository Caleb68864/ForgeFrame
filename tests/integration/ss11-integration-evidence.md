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
