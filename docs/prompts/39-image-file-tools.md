# Prompt 39: image file tools (`image_resize`, `image_convert`, `image_overlay`, `media_watermark`)

The last Phase 5 bullet is "Images: resize/convert/watermark/overlay on files".
Today image handling exists only on the **timeline**: `overlay_insert` and
`watermark_apply` in `server/bundles/image_overlay.py` add an image producer
and a `qtblend` filter to a `.kdenlive` project. Nothing touches image files,
or burns a watermark into a video file. This prompt adds four bare-file tools,
implemented with ffmpeg only (Pillow is **not** a runtime dependency; it is in
the optional `research` extra and the `test` group).

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here. **Needs prompt 30 merged** (`pipelines/media_files.py`,
`server/bundles/_media_shell.py`, `run_ffmpeg(extra_inputs=...)`). If it is
missing, stop and report.

## What exists (reuse)

- `edit_mcp/pipelines/image_overlay.py`:
  - `POSITION_PRESETS` (line 62): top_left, top_right, bottom_left,
    bottom_right, center, full.
  - `position_rect(preset, width, height, scale=0.15, margin=0.05,
    aspect=None) -> (x, y, w, h)` (line 123). Use it for every placement so
    the file tools and the timeline tools agree.
  - `IMAGE_EXTENSIONS` (includes `.svg`; ffmpeg on this host cannot decode SVG
    without librsvg, so exclude `.svg` from these tools and say so in the
    error).
- `probe_media` works on still images: on this host a PNG probes as
  `width=800, height=600, media_type="video", video_codec="png",
  duration_seconds=0.0`. Classify "image vs video" by **extension** plus
  `duration_seconds == 0`, not by `media_type`.
- Verified on this host:
  - Overlay with opacity: `[1:v]format=rgba,scale=120:60,colorchannelmixer=aa=0.5[wm];[0:v][wm]overlay=640:500:format=auto`
    then `-frames:v 1 -update 1 out.png`. 50 % white over pure blue reads
    `(128, 128, 255)` in PIL.
  - Watermark on video: the same chain with `overlay=...:enable='between(t,1,3)'`
    and `-c:a copy`. A single-frame image input repeats (overlay
    `eof_action=repeat`), so there is no `-loop 1` and the duration stays 5.005 s.

## Steps

### 1. Pipeline `edit_mcp/pipelines/image_files.py` (new)

Pure builders:
- `IMAGE_OUT_FORMATS = {".png": [], ".jpg": ["-q:v", "<q>"], ".jpeg": same,
  ".webp": ["-c:v", "libwebp", "-quality", "<q>"], ".bmp": [], ".tiff": []}`.
  `quality` is 1-100. Map it to mjpeg `-q:v` as `round(2 + (100-q)*29/100)`;
  this is a pure, unit-tested helper.
- `resize_filter(src_w, src_h, width, height, fit) -> str`:
  - `fit="contain"`:
    `scale=W:H:force_original_aspect_ratio=decrease`.
  - `fit="cover"`: `scale=W:H:force_original_aspect_ratio=increase,crop=W:H`.
  - `fit="stretch"`: `scale=W:H`.
  - `fit="pad"`: contain plus `pad=W:H:(ow-iw)/2:(oh-ih)/2:color=<c>`.
  - Only width (or only height) given: `scale=W:-1` (or `-1:H`), keeping the
    aspect. Both zero raises `ValueError`.
  - Cap each dimension at 16384.
- `overlay_graph(x, y, w, h, opacity, enable=None) -> str`. It builds the
  chain above. `opacity` is in [0, 1] (`check_unit_interval`); `enable` is an
  optional `(start, end)` and becomes `:enable='between(t,s,e)'`. The numbers
  are formatted by the code, never passed through from user strings.
- `placement(base_w, base_h, ov_w, ov_h, position, scale, margin, x, y)`:
  - a preset uses `position_rect(..., aspect=ov_w/ov_h)`;
  - `position="custom"` uses explicit `x`, `y` and width `scale*base_w`
    (height from the aspect);
  - `full` covers the frame.

I/O functions (each uses `run_ffmpeg`, `require_streams(video=True)`, and
`resolve_output`):
- `resize_image(source, output, width, height, fit, quality, pad_color)`.
- `convert_image(source, output, quality)`. The format comes from the output
  extension. Converting a PNG with alpha to `.jpg` flattens onto black by
  default; add `background="white"` that inserts
  `color=<bg>:s=WxH[bg];[bg][0:v]overlay` first, and document it.
- `overlay_image(source, overlay, output, position, scale, opacity, margin,
  x, y)`. Image on image, `-frames:v 1 -update 1`.
- `watermark_video(source, image, output, position, scale, opacity, margin,
  start=None, end=None)`. Video source: re-encode with the house video args
  and `-c:a copy`.

### 2. Shells (grouped in `server/tools/image_files.py`, or one bundle each)

- `image_resize(source, width=0, height=0, fit="contain", quality=90,
  pad_color="black", output_path="", output_dir="", overwrite=False)`.
  Default suffix `_<W>x<H>` (use the probed result size).
- `image_convert(source, format="webp", quality=90, background="",
  output_path="", output_dir="", overwrite=False)`.
- `image_overlay(source, overlay, position="bottom_right", scale=0.2,
  opacity=1.0, margin=0.03, x=0, y=0, output_path="", output_dir="",
  overwrite=False)`. `source` must be an image; for video, point the agent at
  `media_watermark` with `invalid_input`.
- `media_watermark(source, image, position="bottom_right", scale=0.15,
  opacity=0.6, margin=0.03, start_seconds=-1.0, end_seconds=-1.0,
  output_path="", output_dir="", overwrite=False)`. `-1` means the whole
  clip. The default suffix is `_wm`. In the docstring, point to
  `watermark_apply` for a timeline (editable) watermark instead.
- `pad_color`/`background` are validated like prompt 35's colour rule
  (`0xRRGGBB[AA]` or `[a-z]+`).
- A position outside `POSITION_PRESETS | {"custom"}` gives `invalid_input`
  listing the valid ones. An `.svg` input gives `invalid_input` ("rasterise
  first").

## Tests

Unit (`tests/unit/test_image_files_pure.py`, no ffmpeg):
- `resize_filter` for every fit mode, the single-dimension case, and both-zero
  raising.
- The quality-to-`-q:v` map: 100 gives 2, 1 gives 31, monotonic.
- `placement("bottom_right", 800x600, overlay 200x100, scale=0.15,
  margin=0.05)` equals `position_rect` directly (x=640, y=510, w=120, h=60; verified).
- `overlay_graph` with `enable=(1, 3)` contains `between(t,1,3)`; opacity 1.5
  raises.

Integration (`tests/integration/test_image_file_tools.py`,
`requires_ffmpeg_ffprobe`, `pytest.importorskip("PIL")` for pixel checks).
Generate the inputs with lavfi in the test: an 800x600 blue PNG, a 200x100
white RGBA PNG logo, and a 1600x900 testsrc PNG.
- `image_resize` 1600x900 to `width=800` gives 800x450. `fit="cover"`
  400x400 gives 400x400. `fit="pad"` 400x400 gives 400x400 with black pixels
  at the top row.
- `image_convert` to `.webp` gives `video_codec == "webp"`. To `.jpg` with
  `quality=50`: the file is smaller than `quality=95`'s.
- `image_overlay` of the logo onto the blue PNG, `bottom_right`, `scale=0.15`,
  `opacity=0.5`: the pixel at (700, 530) is about (128, 128, 255) (each
  channel ±6) and (10, 10) is still blue.
- `media_watermark` on a solid blue clip with audio
  (`make_test_clip(path, kind="color", color="blue", size=(640, 360),
  duration=5, with_audio=True)`; not testsrc, whose busy pattern makes the
  brightness check flaky), with `start_seconds=1, end_seconds=3,
  opacity=1.0`:
  - duration 5.0 ± 0.05;
  - the audio stream is still present (copied);
  - a frame at 2.0 s has the logo region (bottom-right box from `placement`)
    mean brightness above 200;
  - a frame at 4.0 s does not (the box is blue again, mean below 100).
- An image source passed to `media_watermark` and a video source passed to
  `image_overlay` each give `invalid_input`.
- `assert_registered("image_resize", "image_convert", "image_overlay",
  "media_watermark")`.

## Acceptance criteria

- Four tools registered and bare-file. Placement matches the timeline tools'
  `position_rect`.
- No new runtime dependency.
- Unit suite, full suite and ruff clean.

## Do NOT

- Do not change `overlay_insert` / `watermark_apply` or `image_overlay.py`'s
  existing functions. Import them; do not edit them.
- Do not add Pillow or cairosvg to runtime dependencies.
- Do not interpolate user strings into filtergraphs. Every number is
  formatted by code and colours are validated.

## When done

1. Mark the "Images" bullet done in Phase 5 of
   `docs/plans/2026-10-13-media-mcp-expansion.md`. If all of Phase 5 is now
   done except the profile generalisation (prompt 13), say so there.
2. Add an "Images and watermarks on files" section to
   `docs/video-editing-guide/12-effects-titles-graphics.md` (file vs timeline
   watermark, presets, opacity).
3. Regenerate `docs/capabilities.md`.
4. Report with the measured pixel values and sizes.
