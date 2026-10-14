# Prompt 36: `transcribe_file` (bare file to SRT / VTT / JSON / TXT)

Phase 5 needs transcription that works on any file without a workspace.
Today transcription runs only inside `media_ingest` / `transcript_generate`
(workspace `transcripts/`). The engine underneath is already
workspace-independent: `adapters/stt/whisper_engine.py` (faster-whisper, with
word timestamps). This prompt adds a shared subtitle-file module
(`pipelines/subtitle_files.py`: load and write SRT/VTT/JSON/TXT, the first
**VTT writer** in the repo) and the `transcribe_file` tool. Prompt 37 builds
the subtitle file operations on the same module. Prompt 38 (text-based
editing) consumes the word-level JSON this tool writes.

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here. **Needs prompt 30 merged** (`pipelines/media_files.py`,
`server/bundles/_media_shell.py`). If they are missing, stop and report.

## What exists (reuse)

- `edit_mcp/adapters/stt/whisper_engine.py`:
  - `is_available()`.
  - `extract_audio(video_path, output_path)`: 16 kHz mono PCM, timeout-guarded,
    refuses protected outputs.
  - `transcribe(audio_path, model="small", language=None, asset_id=None) ->
    Transcript`. faster-whisper runs with `word_timestamps=True`, so
    `TranscriptSegment.words: list[WordTiming(word, start, end, confidence)]`
    is filled. The openai-whisper fallback gives **no** words.
  - `transcript_to_srt` duplicates `subtitle_pipeline.export_srt`; use the
    latter.
- `core/models/transcript.py`: `Transcript`, `TranscriptSegment`,
  `WordTiming`. `Transcript.to_json()` / `from_json()` (the SerializableMixin).
- `edit_mcp/pipelines/subtitle_pipeline.py`: `generate_srt(transcript,
  max_line_length=42, max_duration=5.0)`, `export_srt(cues, max_line_length)`,
  `_parse_srt_content` (keeps line breaks), `_seconds_to_srt_time`.
- `edit_mcp/adapters/transcript/parsers.py`: `parse_srt`, `parse_vtt`,
  `parse_json_transcript`, `parse_transcript(path)` (auto-detect). These join
  multi-line cue text with spaces.
- `core/models/timeline.py`: `SubtitleCue(start_seconds, end_seconds, text)`.
- `faster-whisper` is a **core** dependency (both pyproject files). The
  `tiny` model is cached on this machine at
  `~/.cache/huggingface/hub/models--Systran--faster-whisper-tiny`. CI will
  not have it, and models download on first use.
- There is **no speech fixture** in the repo. `test_audio_with_silence.mp4` is
  tones. Real-engine tests can only check structure, not words.

## Steps

### 1. `edit_mcp/pipelines/subtitle_files.py` (new, shared with 37/38)

- `seconds_to_vtt_time(s) -> "HH:MM:SS.mmm"`, using the same rounding as
  `_seconds_to_srt_time` (round total milliseconds once).
- `export_vtt(cues, max_line_length=42) -> str`: a `WEBVTT` header, a blank
  line, then `start --> end` and the wrapped text per cue (no numeric index
  needed). Reuse the `_wrap_text` logic from `subtitle_pipeline` by importing
  it; do not copy it.
- `transcript_to_cues(transcript, max_line_length=42, max_duration=5.0) ->
  list[SubtitleCue]`. Refactor the cue-building loop out of
  `subtitle_pipeline.generate_srt` into this function, or into
  `subtitle_pipeline` itself, and have `generate_srt` call it so the two cannot
  drift. Its output must stay byte-identical (existing tests guard it).
  - **Improvement when words exist:** split long segments at word timings
    (start a new cue when adding a word would pass `max_duration` or about two
    lines of `max_line_length`). Cue start/end are then the first/last word
    times. Without words, keep the existing proportional split.
- `load_cues(path) -> list[SubtitleCue]` by extension: `.srt` uses
  `_parse_srt_content` (keeps line breaks); `.vtt` uses `parse_vtt`; `.json`
  uses `parse_json_transcript`. Anything else raises `ValueError`.
- `write_cues(cues, path, fmt)` for fmt in {srt, vtt, txt}. `txt` is plain
  text, one cue per line.

### 2. Pipeline `edit_mcp/pipelines/transcribe_file.py` (new)

`transcribe_to_files(source, out_dir, stem, formats=("srt","vtt","json"),
model="small", language=None, max_line_length=42, max_cue_seconds=5.0) ->
dict`:
- `require_streams(asset, audio=True)`.
- Call `extract_audio` into a `tempfile.TemporaryDirectory()` wav (never
  beside the source), then `whisper_engine.transcribe(wav, model, language)`.
- Write `<stem>.srt`, `<stem>.vtt`, `<stem>.txt`, and for json
  `<stem>_transcript.json` (`Transcript.to_json()`, which includes `words`;
  this is the file prompt 38 reads). Before writing anything, run every
  target path through `media_files.resolve_output` (or at least
  `assert_not_protected`) and the overwrite check.
- Return `paths` (fmt to path), `language`, `engine`, `model`,
  `segment_count`, `word_count`, `duration_seconds`, `has_word_timings`.

### 3. Shell `server/bundles/transcribe_file.py`

`transcribe_file(source, formats="srt,vtt,json", model="small",
language="", max_line_length=42, max_cue_seconds=5.0, output_dir="",
overwrite=False)`:
- `formats` is a comma list. Unknown names give `invalid_input` listing
  {srt, vtt, json, txt}. `model` is in {tiny, base, small, medium, large-v3,
  turbo} plus the `*.en` variants; otherwise `invalid_input`.
- `whisper_engine.is_available()` false gives `missing_dependency(
  "faster-whisper", "uv pip install faster-whisper")`.
- A model download or load failure (no network, bad model name) gives
  `operation_failed` with a suggestion: run once with network, or use a cached
  model such as `tiny`.
- Default `output_dir` is `default_output_dir(source)`; default stem is
  `source.stem`.
- In the docstring, say transcription runs in-process and is not
  timeout-bounded, and that long files are better sent through `job_submit`.

## Tests

Unit (`tests/unit/test_subtitle_files.py`, `tests/unit/test_transcribe_file.py`,
no ffmpeg and no model):
- `export_vtt` on two cues starts with `WEBVTT`, uses `.` before milliseconds,
  and round-trips through `parse_vtt` with times equal to 1 ms.
- `seconds_to_vtt_time(3661.2346) == "01:01:01.235"`.
- `generate_srt` output for the existing fixture transcript
  (`tests/fixtures/transcripts/sample_tutorial.json`) is byte-identical
  before and after the refactor. Compute the "before" string in the test from a
  literal you capture **before** you change the code, and save it under
  `tests/fixtures/transcripts/`.
- Word-aware splitting: a 12 s segment with 24 evenly spaced words and
  `max_cue_seconds=5` gives 3 cues. Each cue's start equals one word's start
  and each end equals a word's end; no cue is longer than 5 s.
- `transcribe_file` with `whisper_engine.transcribe` and `extract_audio`
  monkeypatched (fake `Transcript` with words; `extract_audio` just touches the
  wav). This needs `make_test_clip` for a real source, so add
  `requires_ffmpeg_ffprobe`. Check: all 3 files written, JSON round-trips with
  `Transcript.from_json` and keeps `words`, `has_word_timings` is true.
- An output dir under `media/raw/` gives `invalid_input`.
- `is_available` patched to False gives `error_type == "missing_dependency"`.

Integration (`tests/integration/test_transcribe_file_real.py`):
- A local skip mark: skip unless
  `Path.home()/".cache/huggingface/hub/models--Systran--faster-whisper-tiny"`
  exists, plus `requires_ffmpeg_ffprobe`. Do not download models in tests.
- `transcribe_file(test_audio_with_silence.mp4, model="tiny",
  formats="srt,vtt,json,txt")`: success, and every file exists and parses
  (`load_cues` / `Transcript.from_json`). Do **not** assert on words: the
  fixture is tones, and Whisper may return zero segments or hallucinate.

## Acceptance criteria

- `transcribe_file` registered and bare-file. Outputs include word-level JSON.
- The VTT writer exists and round-trips. `generate_srt` output is unchanged.
- Unit suite, full suite and ruff clean.

## Do NOT

- Do not add WhisperX or diarization (out of scope per the plan).
- Do not change `media_ingest` / `transcript_generate` behaviour.
- Do not download a model in any test.
- Do not leave the 16 kHz scratch WAV anywhere but a temp dir.

## When done

1. Mark `transcribe_file` done in Phase 5 of the expansion plan, and note the
   missing speech fixture as a follow-up (a short CC0 spoken clip in
   `tests/fixtures/media_generated/` with a `MEDIA_SOURCES.md` entry).
2. Add a "Transcribing a plain file" section to
   `vault/Research/Local Transcription and Clip Search Index.md` (output
   formats, word-level JSON, model choice and speed).
3. Regenerate `docs/capabilities.md`.
4. Report, including the real-engine test result on this host.
