# Prompt 31: `media_speed`, `media_rotate_flip`, `media_convert`, `media_extract_audio`

Four more bare-file video tools on the Phase 5 foundation from prompt 30:
change playback speed (with pitch-preserving audio), rotate or flip, convert
container/codec, and pull the audio out of a video. Each one is a pipeline
function plus a thin shell, with real-output integration tests.

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here. **Needs prompt 30 merged.** Reuse its
`pipelines/media_files.py` (`resolve_output`, `require_streams`,
`output_summary`, `ENCODE_VIDEO_ARGS`, `ENCODE_AUDIO_ARGS`),
`server/bundles/_media_shell.py` (`source_path`, `ffmpeg_ok_or_error`) and
`pipelines/media_edit.py`. If any of them is missing or named differently,
stop and report.

## What exists (expose, do not rewrite)

`edit_mcp/adapters/ffmpeg/audio.py`:
- `convert_format(input_path, output_path, sample_rate=44100, channels=1, ...)`
  at line 303: `-vn -ar -ac`, codec chosen by the output extension. Note the
  default `channels=1` (mono). Callers must pass the source channel count to
  keep stereo.
- `export_compressed(input_path, output_path, bitrate="192k", ...)` at line
  335: `-vn -b:a`, codec chosen by the extension (mp3, m4a/aac, ogg, opus).

Both are **audio-only**. The plan line "`media_convert` (expose
`convert_format`/`export_compressed`)" means: audio targets delegate to these
two, while video targets need a new function.

Also relevant: `media_transcode_cfr` (workspace tool, `pipelines/vfr_check.py`)
already handles VFR->CFR. Do not duplicate it; mention it in the
`media_convert` docstring.

## Steps

### 1. `media_speed`

Pipeline `speed_file(source, output, factor, keep_pitch=True)` in
`pipelines/media_edit.py`.

- Valid range `0.25 <= factor <= 4.0`, else `ValueError`.
- Video: `setpts=PTS/<factor>`.
- Audio: build the `atempo` chain with a pure helper `atempo_chain(factor) ->
  str`. Each stage stays within `[0.5, 2.0]`. For example 4.0 becomes
  `atempo=2.0,atempo=2.0` and 0.25 becomes `atempo=0.5,atempo=0.5`. With
  `keep_pitch=False` use `asetrate=<sr*factor>,aresample=<sr>` instead (pitch
  shifts, like tape).
- Use `-filter_complex "[0:v]setpts=...[v];[0:a]<chain>[a]" -map [v] -map [a]`.
  Drop the audio branch for video-only sources and the video branch for
  audio-only sources (probe first).
- Verified on this host: 2.0x on the 5.005 s 1080p fixture gives a 2.57 s
  container duration (AAC priming pads slightly).

Shell `server/bundles/media_speed.py`: `media_speed(source, factor,
keep_pitch=True, output_path="", output_dir="", overwrite=False)`. Default
suffix `_x<factor>` (e.g. `_x2`, `_x0.5`).

### 2. `media_rotate_flip`

Pipeline `rotate_flip_file(source, output, rotate=0, flip="")`.

- `rotate` in {0, 90, 180, 270} (clockwise). 90 is `transpose=1`, 270 is
  `transpose=2`, 180 is `hflip,vflip`.
- `flip` in {"", "horizontal", "vertical", "both"}: `hflip` / `vflip`.
- Both empty or zero: `ValueError` ("nothing to do").
- Re-encode video with the house args and `-c:a copy`.
- Add `-metadata:s:v:0 rotate=0` so players do not double-rotate a phone clip
  that carried a rotation tag. ffmpeg auto-rotates tagged input by default;
  write one line about this in the docstring.

Shell `server/bundles/media_rotate_flip.py`: `media_rotate_flip(source,
rotate=0, flip="", output_path="", output_dir="", overwrite=False)`.

### 3. `media_convert`

Pipeline `convert_file(source, output, preset="", crf=None, max_height=0,
audio_bitrate="192k")` in a new `pipelines/media_convert.py`.

- Container from the output extension. Preset table (module constant
  `VIDEO_PRESETS`):
  - `.mp4`, `.mkv`, `.mov`: `libx264` + `aac`, `-movflags +faststart` for
    mp4/mov, crf default 20.
  - `.webm`: `libvpx-vp9 -b:v 0 -crf 32 -row-mt 1` + `libopus`.
  - `preset="prores"` (only `.mov`): `prores_ks -profile:v 3` + `pcm_s16le`.
  - `preset="hevc"` (`.mp4`/`.mkv`): `libx265 -crf 24 -tag:v hvc1` + `aac`.
- Audio-only output extensions (`.wav`, `.flac` -> `convert_format` with the
  source's `sample_rate`/`channels`; `.mp3`, `.m4a`, `.aac`, `.ogg`, `.opus`
  -> `export_compressed`). Delegate to the existing adapter functions; do not
  re-implement.
- `max_height > 0` and source taller: add `scale=-2:<max_height>`.
- Unknown extension: `ValueError` listing the supported ones.

Shell `server/bundles/media_convert.py`: `media_convert(source, format="mp4",
preset="", crf=-1, max_height=0, audio_bitrate="192k", output_path="",
output_dir="", overwrite=False)`. When `output_path` is given its extension
wins over `format`; otherwise `format` picks the extension.

### 4. `media_extract_audio`

Pipeline `extract_audio_file(source, output, sample_rate=0, channels=0,
bitrate="192k")` in `pipelines/media_convert.py`.

- `require_streams(asset, audio=True)` first, so `greenscreen_reporter_720.mp4`
  fails with a clear "no audio stream" error (the shell returns
  `media_unreadable`).
- `sample_rate=0` / `channels=0` mean "keep the source's".
- `.wav`/`.flac` -> `convert_format`; compressed -> `export_compressed`
  (bitrate). `.wav` default.
- Do not reuse `stt/whisper_engine.extract_audio`: that one is hard-wired to
  16 kHz PCM for Whisper.

Shell `server/bundles/media_extract_audio.py`: `media_extract_audio(source,
format="wav", sample_rate=0, channels=0, bitrate="192k", output_path="",
output_dir="", overwrite=False)`.

## Tests

Unit (no ffmpeg), `tests/unit/test_media_speed_convert_pure.py`:
- `atempo_chain` for 0.25, 0.5, 0.8, 1.5, 2.0, 3.0, 4.0: every stage is in
  [0.5, 2.0] and the product equals the factor (to 1e-6).
- The rotate/flip filter builder for every combination; zero/empty raises.
- Preset selection by extension; unknown extension raises.

Integration (`tests/integration/test_media_speed_convert.py`,
`requires_ffmpeg_ffprobe`), probe with `probe_media`:
- Speed 2.0 on `tests/fixtures/media_generated/test_clip_1080p2997_5s.mp4`:
  duration 2.5 ± 0.12 s, both streams. Speed 0.5: 10.0 ± 0.15 s.
- Speed on a video-only `make_test_clip(with_audio=False)`: no error, no audio
  stream.
- Rotate 90 on a 320x240 `make_test_clip`: output 240x320. Flip horizontal on a
  frame whose left half is blue and right half red (build it with lavfi
  `color=red:s=320x240:d=1,drawbox=x=0:y=0:w=160:h=240:color=blue:t=fill`):
  extract a frame (`research_extract_frame` or ffmpeg) and check with PIL
  (`pytest.importorskip("PIL")`) that the left side is now red.
- Convert the 1080p fixture to `.webm`: `video_codec == "vp9"`, audio
  `opus`. Convert with `max_height=720`: height 720, width 1280.
- Convert `music_cinematic_short.mp3` to `.wav`: 44100 Hz, 2 channels (proves
  the mono default was overridden).
- Extract audio from the 1080p fixture as `.wav`: 48000 Hz, 2 channels,
  duration 5.0 ± 0.05. As `.mp3`: codec `mp3`.
- Extract audio from `greenscreen_reporter_720.mp4`: `status == "error"`,
  `error_type == "media_unreadable"`, no file written.
- `assert_registered` for all four tools.

## Acceptance criteria

- Four tools registered, bare-file, using prompt 30's output rules.
- The measured numbers above hold. Unit suite, full suite and ruff clean.
- `convert_format`/`export_compressed` are called, not copied.

## Do NOT

- Do not change the signatures or defaults of `convert_format` or
  `export_compressed` (the workspace `audio_*` tools depend on them).
- Do not duplicate `media_transcode_cfr`.
- Do not pass `-vn` on video outputs (only the audio adapters do that).

## When done

1. Mark the four tools done in Phase 5 of
   `docs/plans/2026-10-13-media-mcp-expansion.md` (date + one line).
2. Extend the "Working on plain files" section of
   `docs/video-editing-guide/13-formats-codecs-export.md` with the preset
   table and the speed range/pitch note.
3. Regenerate `docs/capabilities.md` (`wvb capabilities --markdown`, see 30).
4. Report with the measured durations, sizes and codecs.
