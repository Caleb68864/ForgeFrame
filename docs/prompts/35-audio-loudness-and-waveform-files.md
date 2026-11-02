# Prompt 35: `audio_loudness` (no workspace) and `audio_waveform_image`

Two small bare-file audio tools. `audio_loudness` measures integrated LUFS,
true peak and LRA for a file or a folder. Given a target, it also writes an
accurately normalized copy using the existing two-pass loudnorm pipeline.
`audio_waveform_image` renders a PNG waveform of any file's audio, for
thumbnails, review notes or a quick visual check for silence or clipping. Both
loudness tools that exist today (`audio_loudness_scan`,
`audio_normalize_two_pass`) require a workspace. The logic underneath them
does not, so this prompt mostly **exposes** existing code.

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here. **Needs prompt 30 merged** (`pipelines/media_files.py`,
`server/bundles/_media_shell.py`). Prompt 34 created `pipelines/audio_files.py`.
Add to it if it exists, otherwise create it.

## What exists (reuse, do not rewrite)

- `edit_mcp/adapters/ffmpeg/probe.py`: `measure_loudness(path) ->
  LoudnessResult | None` (line 410). It returns `None` on any failure.
  **Note:** its timeout is a hardcoded `timeout=120`, not a shared constant. A
  long file can time out and come back as `None`. Changing it to
  `ANALYSIS_TIMEOUT_SECONDS` is in scope here (one line; import the constant
  from `runner.py`; check that `tests/unit/test_subprocess_timeouts.py` still
  passes).
- `edit_mcp/pipelines/loudness_scan.py`: `measure_clip(source) -> dict` and
  `scan_loudness(sources) -> {clips_scanned, summary, results}` (lines
  18-94).
- `edit_mcp/pipelines/analysis_common.py`: `iter_media_files(target,
  extensions=None)` (line 33) yields a single file or a recursive sorted
  directory listing.
- `edit_mcp/pipelines/loudnorm_two_pass.py`: `normalize_two_pass_file(input_path,
  output_path, target_i, target_tp, target_lra, linear=True)` (line 204). It
  returns `success`, `measured`, `achieved_i`, `normalization_type`,
  `has_video`, `warning` and `final_output`, and stream-copies video. Use it
  as-is for the normalize path.
- The workspace shells for reference: `server/bundles/loudness_scan.py` and
  `server/bundles/audio_normalize_two_pass.py`.

Measured on this host (`measure_loudness`), for test expectations:

| fixture | I (LUFS) | TP (dBTP) | LRA |
|---|---|---|---|
| `music_cinematic_short.mp3` | -13.3 | -0.12 | 17.4 |
| `test_audio_with_silence.mp4` | -22.05 | -16.31 | 2.3 |
| `test_clip_1080p2997_5s.mp4` | -21.14 | -20.14 | 0.0 |

## Steps

### 1. `audio_loudness`

Shell `server/bundles/audio_loudness.py`: `audio_loudness(source,
target_lufs=0.0, true_peak=-1.5, lra=11.0, output_path="", output_dir="",
overwrite=False)`.

- `source` is a file **or** a directory. Use `iter_media_files`. An empty
  result gives `not_found`.
- `target_lufs == 0.0` means measure only. Return
  `_ok(scan_loudness(files))`. If every row has `ok == False`, return
  `media_unreadable` for the first file.
- `target_lufs < 0`: normalize. This is allowed only for a single file;
  for a directory return `invalid_input` ("normalize one file at a time, or
  pass output_dir and a single source"). Resolve the output with
  `resolve_output(suffix="_normalized")`, then call `normalize_two_pass_file`.
  On failure clean up the partial output and map the result with
  `error_from_pipeline_result` from `server/bundles/_pipeline_errors.py`.
  Return the pipeline's `measured`, `achieved_i`, `normalization_type`,
  `warning` and `output_summary(out)`.
- `target_lufs > 0` gives `invalid_input` (LUFS targets are negative).

### 2. `audio_waveform_image`

Pipeline in `pipelines/audio_files.py`:
`waveform_image(source, output, width=1600, height=300, color="0x3399ff",
split_channels=False, start=0.0, duration=None) -> dict`.

- `require_streams(audio=True)`.
- Command (verified on this host; 1280x240 PNG from the music fixture):
  `ffmpeg [-ss start] [-t dur] -i src -filter_complex
  "showwavespic=s=<w>x<h>:split_channels=<0|1>:colors=<color>"
  -frames:v 1 out.png`. Use `run_ffmpeg(..., timeout=ANALYSIS_TIMEOUT_SECONDS)`.
- Validate `color` against `^0x[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$` or a plain
  ffmpeg colour name `[a-z]+`. Anything else gives `ValueError`, because it is
  interpolated into a filtergraph.
- Width and height in [64, 8000].
- Output extension `.png` (default) or `.jpg`.

Shell `server/bundles/audio_waveform_image.py`: `audio_waveform_image(source,
width=1600, height=300, color="0x3399ff", split_channels=False,
start_seconds=0.0, duration_seconds=-1.0, output_path="", output_dir="",
overwrite=False)`. Default name `<stem>_waveform.png`.

## Tests

Unit (no ffmpeg), `tests/unit/test_audio_loudness_waveform_pure.py`:
- Colour validation accepts `0x3399ff`, `0x3399ffcc` and `red`, and rejects
  `red:x=1`, `0x33`, `'; rm`.
- The waveform argv contains `showwavespic=s=1600x300` and `-frames:v 1`.
- `measure_loudness` now uses `ANALYSIS_TIMEOUT_SECONDS`: monkeypatch
  `subprocess.run` and capture `timeout`.

Integration (`tests/integration/test_audio_ffmpeg_smoke.py` or a new
`tests/integration/test_audio_loudness_waveform.py`,
`requires_ffmpeg_ffprobe`):
- `audio_loudness` measure-only on `music_cinematic_short.mp3`: `lufs` within
  ±0.5 of -13.3.
- Directory mode on a temp dir with two copies of the fixtures:
  `clips_scanned == 2` and a `summary` with `lufs_spread`.
- Normalize `test_audio_with_silence.mp4` to -16: the output exists. Re-measure
  it with `measure_loudness`; `input_i` is within ±1.0 of -16 (two-pass should
  land well inside this; CLAUDE.md warns single-pass misses by 2-4 LU, so a
  ±1 pass proves the two-pass path ran). Measured on this host by calling the
  pipeline directly: `achieved_i` -15.92, re-measured -15.99, linear mode.
  The video stream is still present.
- Normalize with a directory source gives `invalid_input`.
- `audio_waveform_image` on `music_cinematic_short.mp3` at 1280x240: a PNG of
  exactly 1280x240 (probe with `probe_media` or PIL). Not every pixel is the
  same colour (PIL `getextrema()` differs per band); use
  `pytest.importorskip("PIL")`.
- Waveform of `greenscreen_reporter_720.mp4` (no audio): error
  `media_unreadable`, no file.
- `assert_registered("audio_loudness", "audio_waveform_image")`.

## Acceptance criteria

- Both tools are bare-file. Normalization goes through
  `normalize_two_pass_file` and lands within ±1 LU.
- `measure_loudness` uses the shared timeout constant. Unit suite, full suite
  and ruff clean.

## Do NOT

- Do not change `audio_loudness_scan`, `audio_normalize_two_pass` or the
  single-pass `normalize_audio` adapter.
- Do not re-implement the loudnorm JSON parsing.
- Do not interpolate unvalidated strings into the filtergraph.

## When done

1. Mark "file-level loudness without a workspace" and `audio_waveform_image`
   done in Phase 5 of `docs/plans/2026-10-13-media-mcp-expansion.md`.
2. In `docs/video-editing-guide/10-audio-production.md`, add both tools to the
   loudness section, with the measured fixture table above as an example.
3. Regenerate `docs/capabilities.md`.
4. Report with the measured and achieved LUFS values and the waveform size.
