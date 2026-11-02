# Prompt 34: `audio_mix_music` (ducking on files) and `audio_fade_file`

Two bare-file audio tools. `audio_mix_music` lays a music bed under a voice
recording (an audio file or a video's soundtrack). By default the music
auto-ducks under speech with ffmpeg's `sidechaincompress`, and a video's
picture is stream-copied untouched. `audio_fade_file` fades a file's audio in
and/or out. Today ducking exists only as **timeline** keyframes (`audio_duck`
in `server/bundles/timeline_audio.py`), and `audio_fade` is a **timeline clip**
tool. There is no file-level equivalent of either.

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here. Also follow the CLAUDE.md "Audio adapter rules" and "Testing
requirement" sections. **Needs prompt 30 merged** (`pipelines/media_files.py`,
`server/bundles/_media_shell.py`, `run_ffmpeg(extra_inputs=...)`). If they
are missing, stop and report.

## Naming (important)

`audio_fade` is **already registered**: it is the timeline clip fade in
`server/tools/clips_nle.py` around line 546. The plan's "`audio_fade`" bullet
must not reuse that name. Call the new tool **`audio_fade_file`**. Check that
`audio_mix_music` is not taken:
`grep -rn "def audio_mix_music" /home/caleb/Projects/ForgeFrame/workshop-video-brain/src`.

## What exists

- `edit_mcp/adapters/ffmpeg/audio.py`: single-input filters, each passing
  `-vn`. None of them mixes two inputs.
- `edit_mcp/pipelines/timeline_audio.py`: `voice_activity_to_duck_keyframes`
  (timeline keyframes; not used here, but use the same vocabulary in the
  docstring: `duck_db`, `attack_ms`, `release_ms`).
- `adapters/ffmpeg/probe.py`: `probe_media`, `count_audio_streams`,
  `has_video_stream`.

## Steps

### 1. Pipeline `edit_mcp/pipelines/audio_files.py` (new; prompt 35 adds to it)

`DUCK_PRESETS = {"light": {"ratio": 4, ...}, "medium": {"ratio": 8, ...},
"strong": {"ratio": 20, ...}}`. Each preset sets `threshold` (linear,
default 0.02), `ratio`, `attack` (ms, 20), `release` (ms, 250 to 400).
`strong` must be exactly `threshold=0.02:ratio=20:attack=20:release=250`.
Those are the values behind the measurements below.

Pure builder `build_mix_graph(music_gain_db, duck, preset, loop_music,
music_offset, fade_in, fade_out, out_duration) -> str`. This graph was verified
on this host:

```
[1:a]<aloop>,atrim=start=<music_offset>,asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,volume=<music_gain_db>dB,afade=t=in:d=<fade_in>,afade=t=out:st=<dur-fade_out>:d=<fade_out>[m];
[0:a]aresample=48000,aformat=channel_layouts=stereo,asplit=2[v][sc];
[m][sc]sidechaincompress=threshold=<t>:ratio=<r>:attack=<a>:release=<rel>[d];
[v][d]amix=inputs=2:duration=first:normalize=0[out]
```

- `duck=False`: drop the `asplit` and `sidechaincompress` and mix `[v][m]`
  directly.
- `<aloop>` is `aloop=loop=-1:size=2147483647` **only** when `loop_music` is
  set and the music is shorter than the voice. aloop buffers the whole music
  in memory, so never add it otherwise.
- Omit a fade whose duration is 0.
- `amix ... normalize=0` keeps the voice at its original level. Without it,
  amix halves both inputs.

`mix_music_file(source, music, output, music_gain_db=-18.0, duck=True,
duck_preset="medium", loop_music=True, music_offset=0.0, fade_in=1.0,
fade_out=2.0) -> dict`:
- Probe both. `source` must have audio and `music` must have audio
  (`require_streams`). The output duration is the source's.
- Video source: `-map 0:v -map [out] -c:v copy -c:a aac -b:a 192k`.
  Audio-only source: `-map [out]` and a codec from the output extension
  (`.wav` gives `pcm_s16le`, `.m4a` gives `aac`, `.mp3` gives `libmp3lame`,
  `.flac` gives `flac`).
- Use `run_ffmpeg(["-filter_complex", graph, ...maps...], input_path=source,
  output_path=output, extra_inputs=[music])`.
- Return `success`, `ducked`, `preset`, `music_gain_db`, `graph`,
  `stderr_tail`.

`fade_file(source, output, fade_in=0.0, fade_out=0.0, curve="tri") -> dict`:
- At least one fade > 0, and `fade_in + fade_out <= duration`; otherwise
  `ValueError`.
- `afade=t=in:st=0:d=<in>:curve=<c>,afade=t=out:st=<dur-out>:d=<out>:curve=<c>`.
- `curve` in {tri, qsin, esin, hsin, log, exp}, the ffmpeg names.
- Video source: `-c:v copy` plus the `-af` filter and `-c:a aac`. Audio
  source: `-vn` (audio adapter rule 1) and a codec from the extension.

### 2. Shells

- `server/bundles/audio_mix_music.py`: `audio_mix_music(source, music,
  music_gain_db=-18.0, duck=True, duck_preset="medium", loop_music=True,
  music_offset_seconds=0.0, fade_in_seconds=1.0, fade_out_seconds=2.0,
  output_path="", output_dir="", overwrite=False)`. Default name
  `<stem>_music<source ext>`. A missing `music` file gives
  `missing_file(music, "music")`. An unknown preset gives `invalid_input`
  listing the valid ones.
- `server/bundles/audio_fade_file.py`: `audio_fade_file(source,
  fade_in_seconds=0.0, fade_out_seconds=0.0, curve="tri", output_path="",
  output_dir="", overwrite=False)`. Default suffix `_faded`.

Both return `_ok({**output_summary(out), ...pipeline fields})`.

## Tests

Unit (no ffmpeg), `tests/unit/test_audio_files_pure.py`:
- `build_mix_graph` with `duck=True` contains `sidechaincompress` and
  `normalize=0`; with `duck=False` it contains neither `asplit` nor
  `sidechaincompress`. Without looping there is no `aloop`. With zero fades
  there is no `afade`.
- Fade validation: both zero raises; fades longer than the duration raise.

Integration, in `tests/integration/test_audio_ffmpeg_smoke.py` (CLAUDE.md
names this file) or a new `tests/integration/test_audio_file_tools.py`, with
`requires_ffmpeg_ffprobe`:
- **Ducking is measurable.** In the test, generate with ffmpeg:
  - "voice": a 1000 Hz tone gated 1 s on / 1 s off for 6 s
    (`sine=frequency=1000:duration=6` then
    `-af "volume='if(lt(mod(t,2),1),1,0)':eval=frame"`);
  - "music": a constant 200 Hz tone of 10 s.

  Call `audio_mix_music(..., music_gain_db=-6, duck_preset="strong",
  fade_in_seconds=0, fade_out_seconds=0)` to a `.wav`. Measure the music band
  with `-ss <t> -t 0.5 -af "bandpass=f=200:width_type=q:w=2,volumedetect"`
  at t=0.3 and 2.3 (voice on) versus t=1.5 and 3.5 (voice off). Measured on
  this host: about -39.6 dB while the voice is on and -30.1 dB while it is
  off. **Assert the gap is at least 6 dB.** With `duck=False` the same gap
  must be under 1.5 dB.
- The output duration equals the voice duration (6.0 ± 0.05), 48000 Hz,
  2 channels.
- Video source: `tests/fixtures/media_generated/test_clip_1080p2997_5s.mp4`
  plus `music_cinematic_short.mp3` (160 s, so the music gets trimmed). The
  output keeps video codec h264 at 1920x1080 (stream-copied), duration
  5.0 ± 0.1, and has stereo 48 kHz AAC audio.
- Looping: a 2 s music tone under the 6 s voice with `duck=False`. Measure the
  200 Hz band at t=4.5 and it is not silent (mean > -50 dB).
- `audio_fade_file` on a 5 s 440 Hz tone, 1 s in and 1 s out, `tri`:
  measured -37.9 dB for 0-0.25 s, -21.1 dB for 2-3 s and -37.9 dB for
  4.75-5 s. Assert both ends are at least 10 dB below the middle.
- `audio_fade_file` on the 1080p clip keeps the video stream (h264).
- `greenscreen_reporter_720.mp4` (no audio) as `source`: error
  `media_unreadable`, no file written.
- `assert_registered("audio_mix_music", "audio_fade_file")`.

## Acceptance criteria

- The ducking gap is at least 6 dB with ducking and under 1.5 dB without.
- Video is stream-copied, never re-encoded.
- The `audio_fade` timeline tool is untouched. Unit suite, full suite and
  ruff clean.

## Do NOT

- Do not rename or change the existing `audio_fade` or `audio_duck` tools.
- Do not hardcode `"/dev/null"`; use `os.devnull` for any null sink.
- Do not put the voice and music at different sample rates into
  `sidechaincompress`; resample both first, as the graph above does.

## When done

1. Mark `audio_mix_music` and the file-level fade (as `audio_fade_file`,
   noting the name clash) done in Phase 5 of
   `docs/plans/2026-10-13-media-mcp-expansion.md`.
2. Add a "Music beds on plain files" subsection to
   `docs/video-editing-guide/10-audio-production.md`: presets, the measured
   ducking depth, and when to use the timeline `audio_duck` instead.
3. Regenerate `docs/capabilities.md`.
4. Report with the measured dB values (duck on/off, fade ends and middle).
