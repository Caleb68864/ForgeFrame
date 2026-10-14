# Prompt 32: `media_gif` and `media_thumbnail` (bare-file)

Two small bare-file tools. `media_gif` makes a high-quality looping GIF (or
WebP) from any window of a video. `media_thumbnail` grabs one still: either at
a given time, or the most representative frame chosen by ffmpeg's `thumbnail`
filter. Both exist today only in workspace-bound form (`clips_preview_gif`
writes to `reports/previews/` from the clip start; `thumbnail_generate` writes
to `reports/thumbnails/` and draws text). This prompt reuses their command
builders instead of rewriting them.

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here. **Needs prompt 30 merged** (`pipelines/media_files.py`,
`server/bundles/_media_shell.py`). If they are missing, stop and report.

## What exists

- `edit_mcp/pipelines/clip_preview.py`: `palettegen_command`,
  `paletteuse_command`, `mp4_preview_command`, `expected_frame_count`, the
  shared `_vf_chain(fps, width)`. All take `seconds` but **no start offset**:
  they always begin at t=0.
- `edit_mcp/server/bundles/clip_preview.py` (`clips_preview_gif`, around
  lines 44-143): runs the two passes with `subprocess.run(...,
  timeout=_ANALYSIS_TIMEOUT_SECONDS)` and puts the palette in
  `reports/previews/`.
- `edit_mcp/adapters/ffmpeg/probe.py`: `probe_frame_geometry(path)` returns
  `(width, height, counted_frames)`.
- `edit_mcp/adapters/ffmpeg/frames.py`: `extract_frame(video_path,
  timestamp_seconds, output_path=None, quality, fmt, output_dir, asset)`
  (line 58) does a single accurate-seek frame grab with VFR handling, but it
  cannot scale.
- `server/tools/research_media.py` `research_extract_frame` (line 56) shows
  the timestamp clamp to the last valid frame. Copy that logic.

## Steps

### 1. Start offset in the preview builders

Add `start: float = 0.0` as the **last** keyword to `palettegen_command`,
`paletteuse_command` and `mp4_preview_command`. When `start > 0`, emit
`-ss f"{start:.4f}"` before the **first** `-i` (input seek, fast and accurate
when re-encoding). With the default 0 the argv must be byte-identical to
today's, so the existing `clips_preview_gif` tests keep passing untouched.

### 2. `render_gif_file` pipeline

In `pipelines/clip_preview.py` add
`render_gif_file(source, output, start, seconds, fps, width, fmt="gif") -> dict`:
- Validate `seconds > 0`, `1 <= fps <= 50`, `width >= 2`, `start >= 0`. Clamp
  `seconds` so `start + seconds` does not pass the probed duration.
- `fmt="gif"`: run pass 1 and pass 2 with the palette inside a
  `tempfile.TemporaryDirectory()`, never beside the source or output.
- `fmt="webp"`: a single pass:
  `-vf "<_vf_chain>" -c:v libwebp_anim -loop 0 -q:v 70` (add a
  `webp_preview_command` builder next to the others).
- `subprocess.run(..., capture_output=True, text=True, check=False,
  timeout=DEFAULT_TIMEOUT_SECONDS)`. Import the constant from
  `adapters/ffmpeg/runner.py`. Map `FileNotFoundError` to `FFmpegNotFound` so
  `tool_guard` gives `missing_binary`.
- Return `success`, `stderr_tail`, `frame_count` (from
  `probe_frame_geometry`), `expected_frame_count`, `width`, `height`.

Shell `server/bundles/media_gif.py`: `media_gif(source, start_seconds=0.0,
seconds=3.0, fps=12, width=480, format="gif", output_path="",
output_dir="", overwrite=False)`. Default name `<stem>_<start>s.gif`. Use
`resolve_output` with `ext=".gif"` or `".webp"`. Return
`_ok({output_path, size_bytes, width, height, frame_count,
expected_frame_count, start_seconds, seconds, fps})`.

### 3. `media_thumbnail`

Pipeline `pipelines/media_thumbnail.py` (new):
`thumbnail_file(source, output, at_seconds=None, width=1280,
window_seconds=4.0) -> dict`.
- `at_seconds` given: clamp to `[0, duration - 1/fps]` (copy the
  `research_extract_frame` clamp), then `run_ffmpeg(["-frames:v", "1",
  "-vf", f"scale={width}:-2", *quality], pre_input_args=["-ss", t])`.
- `at_seconds is None` ("auto"): seek to `0.1 * duration`, then
  `-vf "thumbnail=n=<round(window_seconds*fps)>,scale=<width>:-2"
  -frames:v 1`. The filter picks the most representative frame in that
  window. Return the chosen window start as `searched_from_seconds`.
- Output format from the extension: `.png`, `.jpg`/`.jpeg` (add `-q:v 2`),
  `.webp` (`-c:v libwebp -quality 85`). Anything else raises `ValueError`.
- `require_streams(asset, video=True)`. An audio-only file is an error.
- `width=0` means native size (no scale filter).

Shell `server/bundles/media_thumbnail.py`: `media_thumbnail(source,
at_seconds=-1.0, width=1280, format="jpg", output_path="", output_dir="",
overwrite=False)`. `-1` means auto. Default name `<stem>_thumb.<ext>`.
Return `_ok({output_path, width, height, size_bytes, mode: "at"|"auto",
at_seconds (the clamped value actually used, or null in auto mode),
searched_from_seconds})`. In the
docstring, point to `thumbnail_generate` for a thumbnail with title text.

Note the CLAUDE.md "Scratch frames never go beside the source" rule: it is
about bursts. A single explicit thumbnail is fine, and `resolve_output`
already moves `media/raw` sources' outputs to `media/processed`.

## Tests

Unit (no ffmpeg), `tests/unit/test_media_gif_thumbnail_pure.py`:
- With `start=0` each builder's argv equals the old argv (keep a literal
  expected list in the test). With `start=2.5`, `-ss 2.5000` comes before the
  first `-i`.
- `webp_preview_command` contains `libwebp_anim` and `-loop 0`.
- Thumbnail argv for auto mode contains `thumbnail=n=` with the expected n.

Integration (`tests/integration/test_media_gif_thumbnail.py`,
`requires_ffmpeg_ffprobe`):
- Build a 4 s clip that is red for 2 s and then blue for 2 s. Two lavfi
  `color` sources plus `concat=n=2:v=1:a=0`, written in the test with
  `subprocess.run(..., timeout=60)`.
- `media_gif(start_seconds=2.5, seconds=1.0, fps=10, width=160)`:
  `frame_count == 10`, width 160, and the first frame decoded with PIL
  (`pytest.importorskip("PIL")`; `Image.open(gif).convert("RGB")`) is
  blue-dominant (b > r + 50).
- `media_gif(format="webp")` produces a file ffprobe reads as `webp`.
- `media_thumbnail(at_seconds=1.0, width=640)` on
  `tests/fixtures/media_generated/test_clip_1080p2997_5s.mp4`: output 640x360
  JPEG. `at_seconds=99` clamps (success, and the returned timestamp is below
  5.005).
- Auto mode on `greenscreen_reporter_720.mp4` succeeds and reports
  `searched_from_seconds ≈ 2.0`.
- An audio-only source (`music_cinematic_short.mp3`): error, no file.
- The existing `tests/integration/test_clip_preview_mcp_tool.py` still
  passes unchanged.
- `assert_registered("media_gif", "media_thumbnail")`.

## Acceptance criteria

- Both tools registered and bare-file. The palette never lands next to the
  source or output.
- `clips_preview_gif` behaviour is unchanged (same argv at `start=0`).
- Unit suite, full suite and ruff clean.

## Do NOT

- Do not refactor `clips_preview_gif` or `thumbnail_generate`. Only add the
  defaulted `start` keyword to the shared builders.
- Do not add Pillow as a runtime dependency. It is only in the `test` group and
  the optional `research` extra. These tools are ffmpeg-only.
- Do not use `extract_frame_burst` here.

## When done

1. Mark `media_gif` and `media_thumbnail` done in Phase 5 of the expansion
   plan.
2. Add both tools to the "Working on plain files" section of
   `docs/video-editing-guide/13-formats-codecs-export.md`, and add one line to
   `docs/video-editing-guide/15-publishing-to-youtube.md` pointing at
   `media_thumbnail` (auto mode) for quick thumbnail candidates.
3. Regenerate `docs/capabilities.md`.
4. Report with the frame counts and dimensions measured.
