# Prompt 37: subtitle file operations (convert, shift, merge, split, restyle, burn)

Bare-file subtitle tools for Phase 5:

- `subtitle_convert`: SRT, VTT, ASS and TXT;
- `subtitle_shift`: offset and/or rescale timings;
- `subtitle_merge`: several files into one, each with an offset;
- `subtitle_split`: one file into two at a time point;
- `subtitle_restyle`: rewrap lines and/or emit a styled ASS;
- `media_burn_subtitles`: a bare-file burn-in, since today's
  `subtitles_burn_in` requires a workspace.

These are mostly pure text transforms over `SubtitleCue` lists, so most tests
need no ffmpeg.

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here. **Needs prompts 30 and 36 merged** (`pipelines/media_files.py`,
`server/bundles/_media_shell.py`, and `pipelines/subtitle_files.py` with
`load_cues`, `write_cues`, `export_vtt`). If any is missing, stop and report.

## What exists (reuse)

- `pipelines/subtitle_files.py` (prompt 36): `load_cues(path)` for
  `.srt`/`.vtt`/`.json`, `write_cues(cues, path, fmt)` for srt/vtt/txt.
- `pipelines/subtitle_track.py`:
  - `SubtitleStyle` (line 48), with `from_input(dict | JSON str | None)`, font
    sanitising and `position` to `alignment`;
  - `cues_to_ass(cues, style, width, height)` (line 190);
  - `force_style_string`;
  - `hex_to_ass_color`.
- `server/bundles/subtitle_track.py` `subtitles_burn_in` (around lines
  200-330): its media branch writes an ASS sidecar into a temp dir and runs
  `run_ffmpeg(args=["-vf", f"ass={escape_filter_path(ass_path)}", "-c:a",
  "copy"], ...)`.
  - **Known flaw:** it always builds the ASS at 1920x1080 `PlayRes` whatever
    the real video size is. The bare-file tool must use the probed size.
  - Do not fix the workspace tool here; list the flaw in your report.
- `pipelines/_common.py` `escape_filter_path`: mandatory for the `ass=` path
  (CLAUDE.md filtergraph rule 1).
- `vault/wiki/ass-style-field-injection.md`: why fonts are sanitised.

## Steps

### 1. Pure transforms in `pipelines/subtitle_files.py`

Add these functions; none of them does I/O:

- `shift_cues(cues, offset=0.0, scale=1.0, from_seconds=0.0)`. For each cue
  whose start >= `from_seconds`: `t' = t*scale + offset`. Cues that end <= 0
  are dropped; a start below 0 is clamped to 0. Return new cues, not mutated
  ones. `scale` fixes frame-rate drift (25 vs 23.976 is `scale=25/23.976`).
  Require `0.5 <= scale <= 2.0`.
- `merge_cues(groups: list[tuple[list[SubtitleCue], float]])`. Apply each
  group's offset, concatenate, and sort by (start, end). Overlaps are kept.
  Return the count of overlapping pairs so the shell can warn.
- `split_cues(cues, at_seconds, rebase=True) -> (first, second)`. Cues fully
  before go to the first list and cues fully after to the second. A cue that
  straddles is cut into two halves (same text). With `rebase`, subtract
  `at_seconds` from the second list's times.
- `rewrap_cues(cues, max_line_length=42, max_lines=2)`. Rewrap text. If a cue
  needs more than `max_lines` lines, split it into consecutive cues dividing
  its duration in proportion to character counts.
- `cues_to_text(cues)` for the txt writer, if 36 did not already add it.

### 2. ASS output

Extend `write_cues` with fmt `ass`. It calls `subtitle_track.cues_to_ass(cues,
style=SubtitleStyle.from_input(style), width, height)`; `width` and `height`
are keyword parameters, default 1920x1080. `load_cues` stays without ASS
input; an `.ass` input raises a clear `ValueError` ("ASS input is not
supported; convert from the SRT/VTT source").

### 3. Shells (one module each under `server/bundles/`, or one grouped `server/tools/subtitle_files.py`; grouped is fine here)

Every tool leads with the input path and takes `output_path=""`,
`output_dir=""` and `overwrite=False`. Resolve outputs with
`resolve_output(..., ext=...)`. Return `_ok({output_path, cue_count, ...})`.

- `subtitle_convert(source, format="vtt", style=None, width=1920,
  height=1080, ...)`. format in {srt, vtt, ass, txt}. `style` applies to ass
  only. Same-format conversion is allowed (it normalises the file).
- `subtitle_shift(source, offset_seconds=0.0, scale=1.0, from_seconds=0.0,
  ...)`. Default suffix `_shifted`, same extension. Report `dropped` (cues
  removed).
- `subtitle_merge(sources: str, offsets: str = "", format="srt", ...)`.
  `sources` is a JSON list and `offsets` an optional JSON list of the same
  length (`bad_json_param` on bad JSON, `invalid_input` on a length
  mismatch). Report `overlaps`. Tip for the docstring: after `media_concat`,
  pass offsets equal to the cumulative durations of the earlier files.
- `subtitle_split(source, at_seconds, rebase=True, ...)`. Writes two files,
  `<stem>_part1` and `<stem>_part2`, and returns both paths and counts.
- `subtitle_restyle(source, max_line_length=42, max_lines=2, style=None,
  format="", width=1920, height=1080, ...)`. `format=""` keeps the input
  format. With `style` set and `format` empty, emit ASS (only ASS can carry a
  style); say so in the result as `format: "ass"`.
- `media_burn_subtitles(source, subtitles, style=None, output_path="",
  output_dir="", overwrite=False)`. `source` is a video and `subtitles` an
  srt/vtt/json file.
  - Probe the video for width and height. Write the ASS into a
    `TemporaryDirectory` using the **probed** size.
  - Run `run_ffmpeg(["-vf", f"ass={escape_filter_path(ass)}", *ENCODE_VIDEO_ARGS,
    "-c:a", "copy"], ...)`. Default suffix `_subtitled`, `.mp4`.
  - Cue text goes into the ASS file, not into the filtergraph, so only the
    path needs escaping.

## Tests

Unit (`tests/unit/test_subtitle_file_ops.py`, no ffmpeg):
- shift: +1.5 s moves every cue. With -2.0, a cue at 1.0-1.5 is dropped and a
  cue at 1.0-3.0 becomes 0.0-1.0. With `from_seconds=10`, cues before 10 are
  unchanged. `scale=25/23.976` stretches the times. A scale out of range
  raises.
- merge: two files with offsets 0 and 5 are sorted, and the overlap count is
  correct.
- split at 4.0 with a straddling 3.0-5.0 cue: part1 ends with 3.0-4.0, part2
  starts with 0.0-1.0 (rebased) and has the same text.
- rewrap: a 200-character cue with max 42 x 2 becomes at least 3 cues. The
  total duration is preserved within 1 ms; there are no gaps or overlaps
  between the generated cues; no line is longer than 42 characters.
- convert srt to vtt to srt round-trips `tests/fixtures/transcripts/sample.srt`
  (times within 1 ms; text equal after whitespace normalisation).
- ass output contains `PlayResX: 1280` when width=1280, plus a `Style:` line
  with the requested font.
- An `.ass` input raises `ValueError`, which the shell maps to `invalid_input`.
- The protected-path rule for each shell (one parametrised test).
- `assert_registered` for all six tools.

Integration (`tests/integration/test_media_burn_subtitles.py`,
`requires_ffmpeg_ffprobe`):
- Build a 3 s black 640x360 clip and an SRT with one cue at 0.5-2.5 s, white
  text with a 72 px font, alignment centre (`style={"size": 72,
  "position": "center"}`). Burn it.
  - The output is 640x360 and 3.0 ± 0.1 s.
  - A frame at 1.5 s has white pixels in the middle band and a frame at 2.8 s
    has none. Check with PIL (`pytest.importorskip("PIL")`).
  - This proves the cue rendered, was timed, and the PlayRes matched the real
    size: with a wrong 1920x1080 PlayRes, a 72 px font scales to about 24 px,
    so also assert the white bounding-box height is above 30 px.
- Escaping: put the burn logic in a pipeline function
  `burn_subtitles_file(source, subtitles, output, style=None,
  scratch_dir=None)` (`scratch_dir=None` means a `TemporaryDirectory`). Call
  it directly with `scratch_dir=tmp_path / "it's a dir: x"` so the ASS path
  that goes into the filtergraph contains a space, a `'` and a `:`. The burn
  must succeed and the PIL check must pass. A temp dir alone never contains
  those characters, so without this the escaping is untested.

## Acceptance criteria

- Six tools registered, bare-file, and sharing `pipelines/subtitle_files.py`.
- Burn-in uses the probed size and passes the PIL checks.
- Unit suite, full suite and ruff clean.

## Do NOT

- Do not change `subtitles_burn_in` or `subtitles_attach` (report the
  PlayRes flaw instead).
- Do not interpolate cue text or style values into an ffmpeg filtergraph.
  They go into the ASS file, and `SubtitleStyle` already sanitises fonts.
- Do not introduce a third SRT parser. Use the existing two via `load_cues`.

## When done

1. Mark "subtitle file ops (shift, merge/split, restyle, convert)" done in
   Phase 5 of the expansion plan.
2. Add a "Subtitle files" section to
   `docs/video-editing-guide/12-effects-titles-graphics.md` (or the guide
   chapter that already covers subtitles; grep for `subtitles_burn_in`)
   listing the six tools and the concat-then-merge recipe.
3. Regenerate `docs/capabilities.md`.
4. Report, including the PlayRes flaw in `subtitles_burn_in` as a found bug.
