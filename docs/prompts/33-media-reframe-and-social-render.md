# Prompt 33: `media_reframe` (9:16 / 1:1 / 4:5) and `media_render_social_clips`

Phase 5 adds vertical and square reframing for plain files, plus a way to turn
the `social_generate_package` manifest into real video files. Today
`social_generate_package` writes only `reports/social/clips_manifest.json`
(start/end times, titles, captions) and **renders nothing**. This prompt adds:

- a reframe pipeline with four modes: `crop` (manual focus point), `smart`
  (automatic focus from motion/detail energy, no new dependencies), `pad`
  (letterbox) and `blur` (blurred fill background);
- `media_reframe`, a bare-file tool;
- `media_render_social_clips`, which cuts and reframes every manifest entry
  from a source video.

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here. **Needs prompt 30 merged** (`pipelines/media_files.py`,
`server/bundles/_media_shell.py`, `run_ffmpeg(extra_inputs=...)`). If those
are missing, stop and report.

## What exists

- `edit_mcp/pipelines/social_clips.py`: `generate_social_package` (around
  line 542) writes `reports/social/clips_manifest.json`, a list of
  `ClipExport` dicts (`core/models/social.py` line 22: `clip_id`,
  `start_seconds`, `end_seconds`, `title`, `caption`, `aspect_ratio`,
  `source_video`).
  - **Caveat 1:** `source_video` is set to the `media/raw` *directory*, not a
    file (around line 600).
  - **Caveat 2:** segments from every transcript are concatenated, so with
    several source clips the times are ambiguous.
  - So the new tool takes an explicit `source` file and does not trust
    `source_video`. Do not change `social_clips.py`; list the caveat in your
    report as a known gap.
- `edit_mcp/pipelines/motion_track.py`: a heavy subject tracker (melt
  `opencv.tracker`, optional OpenCV). Do **not** use it here; `smart` mode
  must work with ffmpeg alone.
- `edit_mcp/pipelines/slideshow.py`: `scale_pad_filter(width, height)` (line
  225) and `scale_crop_filter(width, height)` (line 233). Read them and reuse
  them for `pad` mode and the blur background if they fit.

## Steps

### 1. Pipeline `edit_mcp/pipelines/reframe.py` (new)

Pure helpers (unit-testable):

- `ASPECTS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350),
  "16:9": (1920, 1080)}`, plus `target_size(aspect, height=0)`. A custom
  height scales the width proportionally (rounded to even).
- `crop_box(src_w, src_h, aspect_w, aspect_h, focus_x=0.5, focus_y=0.5) ->
  (x, y, w, h)`. Take the largest crop of the target aspect that fits the
  source. Centre it on `(focus_x*src_w, focus_y*src_h)`, clamp it inside the
  frame, and make every value even.
- `best_focus_x(columns_energy: list[float], window: int) -> float`. Slide a
  window of `window` columns over the energy profile and return the centre of
  the maximum-sum window as a fraction of the width. When the profile is flat
  (max - min < 1e-6), return 0.5. On ties, prefer the window closest to
  centre. Write `best_focus_y` the same way for portrait-to-landscape.
- `column_energy(frames: list[bytes], w: int, h: int) -> list[float]`. Each
  frame is 8-bit gray, `w*h` bytes. Per column, sum the absolute
  frame-to-frame difference (motion) plus `0.25 *` the absolute horizontal
  gradient of each frame (detail). Pure Python; numpy is **not** a runtime
  dependency.
- `filter_for(mode, src_w, src_h, out_w, out_h, focus_x, focus_y,
  pad_color="black") -> str`:
  - `crop` / `smart`: `crop=w:h:x:y,scale=out_w:out_h,setsar=1`.
  - `pad`: `scale=out_w:out_h:force_original_aspect_ratio=decrease,pad=out_w:out_h:(ow-iw)/2:(oh-ih)/2:color=<pad_color>,setsar=1`.
  - `blur`: `split=2[a][b];[a]scale=out_w:out_h:force_original_aspect_ratio=increase,crop=out_w:out_h,boxblur=20:5[bg];[b]scale=out_w:out_h:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1`.
    Use `-filter_complex` with labelled output for this mode.

I/O functions:

- `analyse_focus(source, start=0.0, duration=None, samples_fps=2.0,
  analysis_width=160) -> (focus_x, focus_y)`. Run
  `ffmpeg -ss start -t duration -i src -vf fps=2,scale=160:-2,format=gray -f rawvideo pipe:1`.
  Call `subprocess.run(..., capture_output=True, timeout=ANALYSIS_TIMEOUT_SECONDS)`
  with bytes, not text. Split stdout into frames and call `column_energy`;
  do the rows the same way for `focus_y`. Cap at 120 frames. Verified on this
  host: 3 s at fps=4 and 160x90 gives 172800 bytes (12 frames).
- `reframe_file(source, output, aspect="9:16", mode="smart", focus_x=0.5,
  focus_y=0.5, height=0, start=0.0, duration=None, pad_color="black") -> dict`.
  Probe with `require_streams(video=True)`. In `smart` mode, call
  `analyse_focus` over the same window. Build the filter, use
  `pre_input_args=["-ss", ...]` and `-t` when a window is given, re-encode
  video with the house args, and `-c:a aac` (keep audio when present). Return
  `mode`, `focus_x`, `focus_y`, `crop` (x, y, w, h) and `out_size`.

### 2. Shell `server/bundles/media_reframe.py`

`media_reframe(source, aspect="9:16", mode="smart", focus_x=0.5,
focus_y=0.5, height=0, start_seconds=0.0, duration_seconds=-1.0,
pad_color="black", output_path="", output_dir="", overwrite=False)`.
- Validate: `aspect` is in `ASPECTS`; `mode` is in {crop, smart, pad, blur};
  focus is in [0, 1] (use `check_unit_interval` from `pipelines/_common.py`).
- Default name `<stem>_<aspect with ':' replaced by 'x'>.mp4`.
- The docstring tells the agent: for `crop`, look at a frame from
  `media_thumbnail` first and pass `focus_x`.

### 3. Shell `server/bundles/social_render.py`: `media_render_social_clips`

`media_render_social_clips(source, manifest_path, output_dir="",
aspect="", mode="smart", clip_indices="", height=0, overwrite=False)`.
`height` is passed through to `reframe_file` (0 = the aspect's default).
- Load the manifest JSON (bad JSON gives `bad_json_param`; not a list gives
  `invalid_input`). `clip_indices` is an optional JSON list of ints; an out-of-range
  index gives `invalid_index`.
- `aspect=""` uses each entry's `aspect_ratio`.
- Each entry calls `reframe_file(start=start_seconds,
  duration=end-start)`. Name the output `<clip_id>_<stem>.mp4` inside
  `output_dir` (default: `resolve_output` rules applied to the manifest's
  folder). Skip entries whose start is past the source duration and report them
  under `skipped` with a reason.
- Return `_ok({"rendered": [...per-clip output_summary + clip_id + title...],
  "skipped": [...]})`. If any entry fails, clean up that partial file and keep
  going. Report failures per clip under `failed`, and return an error status
  only when every entry failed. An empty manifest is `_ok` with empty lists.

## Tests

Unit (no ffmpeg), `tests/unit/test_reframe_pure.py`:
- `crop_box(1920, 1080, 9, 16)` gives w=606 (1080*9/16=607.5, floored to
  even), h=1080, x=656 (centred 657, rounded down to even). `focus_x=0`
  gives x=0. `focus_x=1` gives x=1314.
- `crop_box` for 1:1 on a portrait 1080x1920 source crops vertically.
- `best_focus_x` on a flat profile returns 0.5; with a spike at column 140 of
  160 and window 54 it returns > 0.7.
- `column_energy` on two synthetic 8x2 frames with a moving bright pixel has
  its peak at the right column.
- `filter_for` strings for all four modes contain the expected filters.

Integration (`tests/integration/test_media_reframe.py`,
`requires_ffmpeg_ffprobe`):
- `media_reframe` on `tests/fixtures/media_generated/test_clip_1080p2997_5s.mp4`,
  `aspect="9:16"`, `mode="pad"`: output 1080x1920, duration 5.0 ± 0.1, has
  audio.
- `mode="blur"`, `aspect="1:1"`: 1080x1080.
- Smart mode: build a 3 s black 640x360 clip with a white box moving near the
  right edge:
  `color=c=black:s=640x360:r=25:d=3,drawbox=x='480+40*sin(t*6)':y=150:w=60:h=60:color=white:t=fill`
  (verified to render on this host). `mode="smart"`, `aspect="9:16"` must
  report `focus_x > 0.6`. Then extract the middle frame and check with PIL
  that the output frame contains white pixels (the box stayed in frame).
- `media_render_social_clips` with a hand-written manifest of two entries
  (0-2 s and 2.5-4.5 s, `aspect_ratio` "9:16") over the 1080p fixture: two
  files, each 1080x1920 and 2.0 ± 0.1 s. A third entry starting at 99 s lands
  in `skipped`.
- A manifest produced by the real `social_generate_package` works too. Copy
  `tests/fixtures/transcripts/sample_tutorial.json` to
  `<tmp>/ws/transcripts/clip_transcript.json` and call the pipeline with
  `max_clips=1`. Measured: with `max_clips=3` its candidates are
  (44.0-87.3), (5.5-43.2) and (90.0-128.5) s, so the source must be at least
  ~90 s. Use a 90 s 320x180 `make_test_clip(with_audio=True)` and
  `height=320` to keep the render fast. The clip's duration must match its
  manifest span within 0.15 s.
- `assert_registered("media_reframe", "media_render_social_clips")`.

## Acceptance criteria

- Both tools registered and bare-file. `smart` uses ffmpeg plus pure Python only.
- Output geometry is exact for every aspect. All crop values are even.
- Unit suite, full suite and ruff clean.

## Do NOT

- Do not add numpy, OpenCV or Pillow as runtime dependencies.
- Do not modify `social_clips.py` or `social_generate_package`; report the
  `source_video` caveat instead.
- Do not do per-frame (animated) crop tracking. Static focus only; mention
  animated tracking as a follow-up in the report.

## When done

1. Mark `media_reframe` (and "render social_clips output") done in Phase 5 of
   `docs/plans/2026-10-13-media-mcp-expansion.md`.
2. Update `docs/video-editing-guide/16-social-media-repurposing.md` with the
   new flow: `social_generate_package`, then `media_render_social_clips`, with
   the four modes explained. Update the `ff-social-clips` skill's process
   section (`workshop-video-brain/skills/ff-social-clips/SKILL.md`) with a
   render step.
3. Regenerate `docs/capabilities.md`.
4. Report with the measured focus_x, the output sizes and the known gaps.
