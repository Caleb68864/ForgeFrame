# Prompt 38: text-based editing (delete transcript words, get a cut file or `.kdenlive`)

Phase 5's headline feature is editing video by editing its transcript. The
agent reads a numbered word list, says "delete words 40-57, segment 12, and
every 'um'", and gets back one of three outputs:

1. a **cut list** (keep-ranges JSON);
2. a **rendered file** with those parts removed;
3. a **`.kdenlive` project** with one clip per kept range, editable in
   Kdenlive.

It also writes a retimed transcript and SRT that match the edited media. This
prompt adds the pure cut-list logic and two tools; rendering is delegated to
code that earlier prompts already built.

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here.

**Needs:**
- **02** (clip audio placed on an audio track; the A/V contract);
- **12** (the keep-ranges file renderer behind `media_remove_silence`);
- **13** (the keep-ranges to `.kdenlive` builder that uses the source's
  profile, behind `timeline_build_jump_cut`);
- **30** (`media_files.py`, `_media_shell.py`);
- **36** (word-level transcript JSON, `subtitle_files.py`).

Before you start, find the 12/13 functions:
`grep -rn "keep_ranges\|KeepRange\|jump_cut" /home/caleb/Projects/ForgeFrame/workshop-video-brain/src`.
If either the file renderer or the `.kdenlive` builder is missing, **stop and
report**. Do not build a second one.

## What exists

- Transcript JSON written by `transcribe_file` (prompt 36) and by ingest
  (`transcripts/<stem>_transcript.json`): `Transcript` with
  `segments[].words[] = {word, start, end, confidence}` (faster-whisper).
  Segments from openai-whisper or SRT imports have **no words**.
- `adapters/transcript/parsers.py` `parse_transcript(path)` loads
  SRT/VTT/JSON into segments (words are kept only for the Transcript JSON
  shape).
- `pipelines/subtitle_files.py` (36): `transcript_to_cues`, `write_cues`.
- `pipelines/_common.py` `seconds_to_frames` (the one half-up converter).
- `pipelines/transcript_index.py` `edit_segment` only fixes text. It is
  unrelated; do not touch it.
- Fixture `tests/fixtures/transcripts/sample_tutorial.json` has 25
  segments, and every `words` list is empty. Use it for the segment-granularity
  path. `test_clip_1080p2997_5s.mp4` (5.005 s, 29.97 fps,
  stereo 48 kHz) is the media for render tests.

## Steps

### 1. Pure logic, `edit_mcp/pipelines/text_edit.py` (new)

- `@dataclass Word(index, text, start, end, segment_index)`.
  `load_units(transcript_path) -> (units, granularity)`. If any segment has
  words, the units are words, numbered globally from 0, and granularity is
  `"word"`. Otherwise each segment is one unit and granularity is
  `"segment"`. Drop units with `end <= start`.
- `numbered_view(units, start=0, limit=400) -> str`: lines like
  `S3 [41] the [42] zipper [43] goes ...`, one line per segment, so an agent
  can pick indices. Return `next_start` for paging.
- `FILLERS = {"um", "uh", "erm", "er", "ah", "hmm", "mm"}` and
  `normalise(word)`: lowercase, strip punctuation.
- `select_deletions(units, spec: list[dict], remove_fillers=False) ->
  set[int]`. Spec items:
  - `{"words": [a, b]}` (inclusive range);
  - `{"segment": i}`;
  - `{"text": "you know"}` (every occurrence of that normalised word
    sequence);
  - `{"time": [s, e]}` (every unit whose midpoint is inside the range).

  Any other key, or an index out of range, raises `ValueError` naming the
  bad item.
- `keep_ranges(units, deleted, duration, pad=0.05, min_keep=0.2) ->
  list[(start, end)]`. For each maximal run of consecutive deleted units:
  - the cut starts at `prev_kept.end + pad`, or 0.0 if the run starts the
    file;
  - the cut ends at `next_kept.start - pad`, or `duration` if the run ends
    the file;
  - so the silence around the deleted words goes too, but kept words keep
    `pad` seconds of air.

  If `cut_end <= cut_start`, skip that cut. The keep-ranges are the complement
  over `[0, duration]`. Drop fragments shorter than `min_keep`, merge
  touching ranges, and return them sorted.
- `remap_time(t, ranges) -> float | None`: time in the edited output, or
  `None` if `t` was cut.
  `retime_transcript(transcript, ranges, deleted) -> Transcript`: drop the
  deleted words, remap the rest, and rebuild segment start/end/text from the
  surviving words. A segment with nothing left is dropped. For segment
  granularity, remap whole segments.
- `edit_summary(ranges, duration)`: `kept_seconds`, `removed_seconds`,
  `cut_count`.

### 2. Tools, `server/tools/text_edit.py` (grouped domain module, two tools)

- `transcript_words(transcript_path, start_index=0, limit=400)`: returns
  `numbered_view`, `granularity`, `unit_count` and `next_start`. Read-only.
- `media_text_edit(source, transcript_path, delete="[]",
  remove_fillers=False, padding_seconds=0.05, output="file", output_path="",
  output_dir="", overwrite=False)`:
  - `delete` is a JSON list (`bad_json_param("delete", '[{"words":[10,14]},
    {"segment":3}, {"text":"um"}]', given)`). A `ValueError` from
    `select_deletions` gives `invalid_input`.
  - Probe `source` for its duration. If the transcript's last unit ends more
    than 1 s after the media duration, return `invalid_input` (wrong
    transcript for this media).
  - `output="cutlist"`: write `<stem>_cutlist.json` (`{"source", "ranges",
    "deleted_indices", "granularity", ...summary}`).
  - `output="file"`: call prompt 12's
    `pipelines/silence_cut.render_keep_ranges(source, ranges, output_path)`
    to make `<stem>_edited<ext>`.
  - `output="kdenlive"`: call prompt 13's
    `build_ranges_project(source, ranges, profile=None, ...)` builder (it must use the source's
    profile and put audio on an audio track per prompt 02). Return the
    project path. Write it next to the cut list, not into `projects/source/`.
  - All modes also write `<stem>_edited_transcript.json` and
    `<stem>_edited.srt` (from `retime_transcript` + `transcript_to_cues` +
    `write_cues`) and the cut list. Return every path, the summary and
    `granularity`.
  - With segment granularity, add a `warning`: deletions are whole
    sentences; transcribe with `transcribe_file` for word-level cuts.

## Tests

Unit (`tests/unit/test_text_edit.py`, pure, no ffmpeg). Build a synthetic
transcript: 10 words, each 0.4 s long with 0.1 s gaps, starting at 0.0, so
word i spans `[0.5*i, 0.5*i + 0.4]`; duration 5.0.
- Delete words [3, 5] with `pad=0.05`: the cut runs from 1.45 (word 2 ends
  at 1.4, plus 0.05) to 2.95 (word 6 starts at 3.0, minus 0.05). Keep-ranges
  are `[(0, 1.45), (2.95, 5.0)]`, which removes 1.5 s.
- Delete word 0: the first range starts at word 1's start - pad (0.45).
  Delete word 9: the last range ends at word 8 end + pad (4.45).
- `{"text": "um"}` matches `"Um,"` and `"um."`. A two-word phrase matches only
  consecutive words.
- `{"time": [1.0, 2.0]}` selects words whose midpoints fall inside.
- Bad spec items (an unknown key, an out-of-range index) raise `ValueError`.
- `remap_time` for a time inside a cut returns `None`. A time after the cut
  is shifted by the cut length.
- `retime_transcript` drops the deleted words, and segment text is rebuilt.
- Segment granularity (no words) works and reports `"segment"`.
- `min_keep` drops a 0.1 s sliver between two cuts.

Integration (`tests/integration/test_media_text_edit.py`,
`requires_ffmpeg_ffprobe`). Use `test_clip_1080p2997_5s.mp4` with a
hand-written word transcript (the 10-word layout above) and delete words
[3, 5]:
- `output="file"`: duration 5.005 - 1.5 = 3.5 ± 0.1 s, both streams. The
  edited SRT exists and its last cue ends at or before 3.6 s.
- `output="cutlist"`: the JSON ranges equal the unit-test expectation.
- A transcript that runs past the media gives `invalid_input`.

External render proof (`tests/integration/external/test_text_edit_render.py`,
`requires_melt_ffmpeg`, CLAUDE.md checklist item 6; the `.kdenlive` output
is timeline-affecting). Same input, `output="kdenlive"`, then render the
project with `render_video` from `_oracle.py`:
- duration 3.5 ± 0.1 s (frame count about 105 at 29.97);
- `audio_stats` mean above -60 dB (audio was placed, per 02);
- the project profile is 1920x1080 at 30000/1001, not the old hardcoded
  1080p25 (the 13 generalisation).

Any `melt ... -consumer null:` call needs `terminate_on_pause=1`.

## Acceptance criteria

- `transcript_words` and `media_text_edit` registered.
- The cut list, the file and the `.kdenlive` all agree on the 3.5 s result.
- The retimed SRT matches the edited media.
- No second keep-ranges renderer or timeline builder was written.
- Unit suite, full suite and ruff clean.

## Do NOT

- Do not import auto-editor's or any external `.kdenlive` export (see the plan,
  Phase 2).
- Do not write into `projects/source/` or `media/raw/`.
- Do not modify `transcript_edit` / `edit_segment`.
- Do not snap cuts to frames in the pure layer. Frame conversion happens
  once, in the builder, via `seconds_to_frames`.

## When done

1. Mark "text-based editing" done in Phase 5 of
   `docs/plans/2026-10-13-media-mcp-expansion.md`.
2. Add a "Editing by transcript" walkthrough to
   `docs/video-editing-guide/07-your-first-edit.md`: `transcribe_file`, then
   `transcript_words`, then `media_text_edit` (cutlist, then kdenlive or
   file).
3. Regenerate `docs/capabilities.md`.
4. Report with the measured durations, frame count and dB, and which 12/13
   functions you reused (names and paths).
