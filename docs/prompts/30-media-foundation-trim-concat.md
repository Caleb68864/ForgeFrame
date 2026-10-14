# Prompt 30: bare-file media foundation + `media_trim` / `media_concat`

Phase 5 of `docs/plans/2026-10-13-media-mcp-expansion.md` adds tools that work
on plain files, with no workspace: they lead with `source`, take
`output_path`/`output_dir`, and never write into `media/raw/` or
`projects/source/`. This prompt builds the shared foundation that prompts
31-39 reuse (an output-path resolver, a shell helper, multi-input support in
`run_ffmpeg`) and the first two tools, `media_trim` and `media_concat`.

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here.

## What exists (do not rewrite)

- `edit_mcp/adapters/ffmpeg/runner.py`: `run_ffmpeg(args, input_path,
  output_path, overwrite, dry_run, pre_input_args, timeout)` around line 99.
  It takes **one** `-i` only. It refuses to overwrite an *existing* file in a
  protected tree, but would happily create a *new* file there.
- `core/utils/paths.py`: `assert_not_protected(path, what)` (line 63) raises
  `ProtectedPathError`. `is_protected_path` (line 49).
- `edit_mcp/adapters/ffmpeg/probe.py`: `probe_media(path) -> MediaAsset`
  (fields `duration_seconds`, `width`, `height`, `fps`, `audio_codec`,
  `channels`, `sample_rate`, `video_codec`), `has_video_stream`,
  `count_audio_streams`.
- `server/errors.py`: `tool_guard` already maps `ProtectedPathError` and
  `ValueError` to `invalid_input`, `FileNotFoundError` to `missing_file`,
  `FFmpegNotFound` to `missing_binary`, and `FFmpegTimeout` to a timed-out
  error. Let those propagate from the pipeline; do not re-catch them in shells.
- `server/bundles/_pipeline_errors.py`: `cleanup_partial_output(*paths)`.
- Existing bare-file precedent: `server/tools/research_media.py`
  (`research_probe_video(video_path)`, `research_extract_frame`).
- Workspace-bound media tools (`media_denoise_video`, `media_stabilize`) write
  to `media/processed/`. Do not change them.
- Prompt 12 may have added a keep-ranges renderer for `media_remove_silence`
  (`grep -rn "keep_ranges\|keep-ranges" workshop-video-brain/src`). Do not
  duplicate it. `media_trim` is a single range and stays its own simple
  function.

## Steps

### 1. Multi-input support in `run_ffmpeg`

Add an optional keyword `extra_inputs: list[Path] | None = None`. Each one is
emitted as `-i <path>` right after the main `-i input_path`. So input 0 is
`input_path` and inputs 1..n are `extra_inputs` in order. Default `None`
leaves every existing call byte-identical. Add a unit test in
`tests/unit/test_ffmpeg_runner_extra_inputs.py` using `dry_run=True` that
checks the argv order.

### 2. `edit_mcp/pipelines/media_files.py` (new, shared by 30-39)

Pure helpers, no MCP imports:

- `default_output_dir(source: Path) -> Path`: if the source sits in a
  `media/raw/` tree, return the sibling `media/processed/` of that workspace
  (find the `media` path segment); otherwise `source.parent`.
- `resolve_output(source, output_path="", output_dir="", suffix="_out",
  ext=None, overwrite=False) -> Path`:
  - `output_path` given: use it (relative paths resolve against the
    current directory; document that absolute paths are preferred).
  - else `output_dir or default_output_dir(source)` /
    `f"{source.stem}{suffix}{ext or source.suffix}"`.
  - Always call `assert_not_protected(result, "media output")`, even for new
    files. This is stricter than `run_ffmpeg` on purpose.
  - Raise `ValueError` if the result resolves to the same file as `source`.
  - Raise `ValueError` if it exists and `overwrite` is false (message names
    the `overwrite=true` option).
  - `mkdir(parents=True, exist_ok=True)` the parent.
- `require_streams(asset, *, video=False, audio=False)`: raise `ValueError`
  with a clear message ("source has no audio stream") when a required stream
  is missing (`asset.width == 0` means no video; `asset.channels == 0` and no
  `audio_codec` means no audio).
- `output_summary(path) -> dict`: probe the output with `probe_media` and
  return `output_path`, `duration_seconds`, `width`, `height`, `fps`,
  `has_audio`, `sample_rate`, `channels`, `size_bytes`.
- `ENCODE_VIDEO_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf",
  "20", "-pix_fmt", "yuv420p"]` and `ENCODE_AUDIO_ARGS = ["-c:a", "aac",
  "-b:a", "192k"]` as the house defaults for re-encodes.

### 3. Shell helper `server/bundles/_media_shell.py` (new)

The leading underscore keeps discovery from importing it as a tool module.

- `source_path(source: str, param: str = "source") -> Path | dict`: empty
  string returns `invalid_input(...)`; a missing file returns
  `missing_file(source, param)`; otherwise the resolved `Path`.
- `ffmpeg_ok_or_error(result, output, what) -> dict | None`: on
  `not result.success`, call `cleanup_partial_output(output)` and return
  `operation_failed(f"{what} failed", cause=result.stderr_tail, suggestion=...)`;
  otherwise `None`.

### 4. `media_trim`

Pipeline in `pipelines/media_edit.py` (new; prompts 31 and 32 add to it):
`trim_file(source, output, start, end=None, duration=None, mode="accurate",
dry_run=False) -> FFmpegResult`.

- Validate: `start >= 0`; exactly one of `end`/`duration` (or neither = to
  the end); `end > start`; `start` < source duration (probe once).
- `mode="accurate"`: re-encode. `pre_input_args=["-ss", start]` plus
  `-t duration` after the input, with the house encode args. (Input seeking
  plus re-encode is frame accurate in modern ffmpeg.)
- `mode="copy"`: `-ss` before `-i`, `-t`, `-c copy`,
  `-avoid_negative_ts make_zero`. Document that it snaps to keyframes.
- Video-only and audio-only sources both work (no `-map` that assumes both).

Thin shell in `server/bundles/media_trim.py`:
`media_trim(source, start_seconds, end_seconds=-1.0, duration_seconds=-1.0,
mode="accurate", output_path="", output_dir="", overwrite=False)`.
Use `-1` as "unset" (keep the MCP schema simple). Return
`_ok({**output_summary(out), "source": ..., "mode": ...})`.

### 5. `media_concat`

Pipeline `concat_files(sources: list[Path], output, method="auto",
width=0, height=0, fps=0.0) -> dict` in `pipelines/media_edit.py`.

- `method="copy"`: the concat demuxer. Write the list file into a
  `tempfile.TemporaryDirectory`, one `file '<path>'` line per source, with
  `'` escaped as `'\''`. Run with `pre_input_args=["-f", "concat", "-safe",
  "0"]` and `-c copy`. Only valid when every source has the same video codec,
  size, fps, audio codec, sample rate and channels.
- `method="reencode"`: one filtergraph through `extra_inputs`. Target geometry
  defaults to the first source with video. Verified on this host:

  ```
  [0:v]scale=W:H:force_original_aspect_ratio=decrease,pad=W:H:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=FPS,format=yuv420p[v0];
  [0:a]aresample=48000,aformat=channel_layouts=stereo[a0];
  ... same for each input i ...
  [v0][a0][v1][a1]concat=n=N:v=1:a=1[v][a]
  ```
  with `-map [v] -map [a]` and the house encode args. A source with **no
  audio** (e.g. `greenscreen_reporter_720.mp4`) gets
  `anullsrc=r=48000:cl=stereo,atrim=duration=<its duration>[ai]` instead of
  `[i:a]`. If *no* source has audio, use `a=0` and no audio maps. Audio-only
  sources: reject in `reencode` mode with a clear `ValueError` (say to use
  `audio_concat` later or convert first).
- `method="auto"`: probe all sources; `copy` when the stream parameters all
  match, else `reencode`. Return which method ran.
- Return a dict with `method`, `target` geometry and the `FFmpegResult`.

Shell `server/bundles/media_concat.py`:
`media_concat(sources: str, output_path="", output_dir="", method="auto",
width=0, height=0, fps=0.0, overwrite=False)`. `sources` is a JSON list of
paths. Bad JSON gives `bad_json_param("sources", '["a.mp4", "b.mp4"]', given)`;
fewer than 2 gives `invalid_input`. The default output name is
`<first stem>_concat<ext>` with `.mp4` for reencode.

## Tests

Unit (`tests/unit/test_media_files.py`, `tests/unit/test_media_edit_pure.py`,
no ffmpeg needed):
- `resolve_output`: default name; `output_dir`; a source under
  `<tmp>/ws/media/raw/` defaults to `<tmp>/ws/media/processed/`; an explicit
  output inside `media/raw/` raises `ProtectedPathError` even when the file
  does not exist; same-as-source raises; existing file without `overwrite`
  raises.
- Concat filtergraph builder (factor it as a pure function) for 2 inputs, one
  without audio, produces the `anullsrc` branch.
- The concat list-file escaping of a path containing `'`.

Integration (`tests/integration/test_media_trim_concat.py`,
`requires_ffmpeg_ffprobe`), call the tools with `call_tool`/`unwrap`, probe
outputs with `probe_media`:
- Trim `tests/fixtures/media_generated/test_clip_1080p2997_5s.mp4` from 1.0
  to 3.0 s (accurate): duration 2.0 ± 0.05 s, both streams present,
  1920x1080.
- Trim in `copy` mode. The 1080p fixture has a **single keyframe at t=0**
  (measured), so copy-trimming it 1.0-3.0 gives a 3.09 s file. Do not use it
  for this check. Instead encode a test clip with a keyframe every 5 frames
  (`make_test_clip` output re-encoded in the test with `-c:v libx264 -g 5
  -keyint_min 5 -sc_threshold 0`, 25 fps). The copy trim 1.0-3.0 of that clip
  must be 2.0 ± 0.25 s.
- Trim a video-only `make_test_clip(... with_audio=False)`: no audio stream
  in the output, no error.
- Concat the 1080p clip + `test_audio_with_silence.mp4` (320x180, mono):
  method `reencode`, duration 10.0 ± 0.1 s, 1920x1080, stereo, 48000 Hz.
- Concat the 1080p clip + `greenscreen_reporter_720.mp4` (no audio): output
  has an audio stream and duration ≈ 5.005 + 20.02 s (± 0.15).
- Concat two copies of the same `make_test_clip` file: method `copy`.
- Protected path: `output_dir=<tmp>/ws/media/raw` returns
  `status == "error"` with `error_type == "invalid_input"` and creates no file.
- `assert_registered("media_trim", "media_concat")`.

## Acceptance criteria

- Both tools registered, lead with `source`/`sources`, and never need a
  workspace.
- All numbers above hold. The unit suite, full suite and ruff are clean.
- Every existing `run_ffmpeg` call is unchanged in behaviour.

## Do NOT

- Do not change `media_denoise_video`, `media_stabilize`, or the workspace
  tools' output locations.
- Do not shell out to ffmpeg directly when `run_ffmpeg` can do it.
- Do not use `shell=True` or string-joined commands.
- Do not write scratch files (concat lists) beside the source; use a temp dir.

## When done

1. In `docs/plans/2026-10-13-media-mcp-expansion.md` Phase 5, mark
   `media_trim` and `media_concat` done (date + one line) and mention the
   shared `media_files.py` / `_media_shell.py` / `extra_inputs` foundation.
2. Add a "Working on plain files" section to
   `docs/video-editing-guide/13-formats-codecs-export.md` covering the output
   rules (defaults, `media/raw` -> `media/processed`, protected trees,
   `overwrite`) and the two tools.
3. Regenerate `docs/capabilities.md`:
   `uv run --project /home/caleb/Projects/ForgeFrame wvb capabilities --markdown > /home/caleb/Projects/ForgeFrame/docs/capabilities.md`
4. Report in the `00-README.md` format, including the measured durations.
