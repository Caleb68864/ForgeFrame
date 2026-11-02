# Prompt 15: timeline thumbnails and per-frame render progress via the MLT worker (Phase 3)

Hand this whole file to the implementing model.

---

Prompt 14 added an out-of-process MLT worker
(`edit_mcp/adapters/mlt/_worker.py` + `engine.py`). This task uses it for two
things:

- **(a) Frame-accurate timeline thumbnails.** Seek the loaded project to frame
  F and grab the composited image directly, with no temp render. The melt CLI
  is the fallback.
- **(b) Per-frame render progress written into persistent job records.**
  Add a progress callback from the render executor up to the `wvb jobs`
  worker, and an opt-in bindings render engine that streams frame positions.

Prompt 18 adds the melt-CLI `percentage:` parser to the **same** callback. Both
prompts define the callback the same way; whichever lands second reuses it.

Read `docs/prompts/00-README.md` first. Prompt 14 must be merged. Read
`edit_mcp/adapters/mlt/engine.py` and `_worker.py` before starting.

## Verified facts (MLT 7.42, this machine)

Frame grab, inside the worker (keep every object bound to a name):

```python
prof = mlt.Profile(); prod = mlt.Producer(prof, "xml", path)
prod.seek(frame); fr = prod.get_frame()
w = width; h = round(w * prof.height() / prof.width() / 2) * 2      # even height
img = fr.get_image(mlt.mlt_image_rgb, w, h)    # bytes, len == w*h*3
# get_image(fmt, 0, 0) returns EMPTY -- always pass explicit w, h.
# fr.get_int("width"), fr.get_int("height") give the actual size.
```

- Tracks **are composited**. With red on V1 and blue on V2 from frame 20 to
  29, frame 25 returned (0,0,255) and frames 5 and 45 returned (255,0,0)
  (`frei0r.cairoblend`).
- `qtblend` needs X11 on MLT 7.22 (CI). Pass `DISPLAY` through; the tests run
  under `xvfb-run -a`.
- The system Python has no Pillow. Write PNG with the stdlib: a signature,
  then `IHDR` (bit depth 8, colour type 2), one `IDAT` holding
  `zlib.compress(b"".join(b"\x00" + row for row in rows))`, then `IEND`.
  Each chunk is `struct.pack(">I", len) + tag + data + struct.pack(">I", zlib.crc32(tag + data))`.

Render with progress, inside the worker:

```python
con = mlt.Consumer(prof, "avformat", out_path)
for k, v in props.items(): con.set(k, v)      # same key=value pairs melt CLI gets
con.set("terminate_on_pause", "1"); con.set("real_time", "-1")
con.connect(prod); con.start()
while not con.is_stopped():
    emit({"event": "progress", "frame": prod.position(), "total": prod.get_length()})
    time.sleep(0.25)
con.stop()
```

A 50-frame render observed positions up to 49 (`get_length() == 50`).

Melt CLI single frame (the fallback):

```
melt <project> in=F out=F -consumer avformat:<dir>/f_%05d.png width=W height=H terminate_on_pause=1
```

This writes exactly one PNG, and the composite is correct for the cairoblend
case above. **But** `pipelines/review_loop.py::_render_kdenlive_frame` (around
line 385) deliberately renders frames `0..F` and keeps the last, "so a title
composited on a top track shows correctly". Do not trust either method for
titles until the test in step 6 decides.

## Steps: (a) thumbnails

### 1. Worker op `frames`

- Args: `{"path", "frames": [int], "width": int, "out_dir": str}`.
- Load once, then for each frame: seek, get the frame, get the image, write
  `out_dir/f_<frame:06d>.png`.
- Clamp frames to `[0, get_length()-1]` and report the clamped value.
- Result: `{"frames": [{"requested", "frame", "path", "width", "height"}], "length": n}`.

### 2. Engine function `timeline_frames(project_path, frames, width, out_dir, engine="auto")`

Put it in `adapters/mlt/engine.py`.

- Try the bindings first. Use a timeout of `ANALYSIS_TIMEOUT_SECONDS`.
- Fall back to melt, one CLI call per frame, into a per-frame temp dir under
  `out_dir`. Move the single PNG to the same final name and remove the temp
  dir.
- Return the same dict shape plus `"engine"`.
- Raise `MltUnavailable` when neither engine exists.

### 3. Pipeline `edit_mcp/pipelines/timeline_thumbnails.py`

- Resolve the project: explicit `project_file`, else `latest_project` from
  `projects/working_copies`.
- Precondition: `adapters/render/media_check.missing_media(project)`. If
  anything is missing, raise `FileNotFoundError(missing_media_message(...))`.
  This is the same rule `_render_kdenlive_frame` uses; a black thumbnail must
  never pass as success.
- Convert seconds to frames with `pipelines/_common.seconds_to_frames`, using
  the parsed project fps.
- Output dir: `reports/timeline_frames/<project-stem>/`. Pass `out_dir`
  explicitly. Never write beside the project or into a protected tree
  (CLAUDE.md "Scratch frames never go beside the source video").

### 4. Tool `edit_mcp/server/bundles/timeline_thumbnails.py`

```
timeline_thumbnails(workspace_path: str, times: str = "", frames: str = "",
                    width: int = 640, project_file: str = "") -> dict
```

- `times` and `frames` are comma-separated lists. Exactly one must be
  non-empty, else `invalid_input`.
- Reject a non-finite time with `nonfinite_guard`, a negative frame with
  `nonneg_index`, and a width outside `16..3840` with `invalid_input`.
- Error mapping:
  - `ProjectParseError` -> `corrupt_project`;
  - `FileNotFoundError` -> `missing_file`;
  - `MltUnavailable` -> `missing_binary("melt", ...)`.
- Payload: `{"engine", "project_file", "frames": [...], "output_dir"}`.
- The tool is read-only, so no snapshot is needed.

### 5. Reuse it in `review_loop`

Replace the body of `_render_kdenlive_frame`
(`pipelines/review_loop.py`, around line 385) with a call to
`timeline_frames(..., frames=[F], width=<project width>)`. Then move the PNG
to `out_png`.

- Keep the missing-media precondition and the bool return contract.
- If the step 6 title test shows the single-frame grab is wrong for titles,
  keep the old `0..F` melt path as the fallback, and write down why in the
  docstring.

### 6. Tests: thumbnails

All of these go in `tests/integration/test_timeline_thumbnails.py`.

- `requires_mlt_bindings`: serialize `two_track_project` plus a blue clip on
  V2 at frames 20-29 (build it like the testkit does). Grab frames 5, 25 and
  45 and read the centre pixel (`PIL` from the test group). Expect red, blue,
  red, each channel within 20.
- The same assertions with `requires_melt` and `find_mlt_python` patched to
  None (the melt fallback).
- A title test, `requires_melt` + `requires_mlt_bindings`: build a project with a
  title card on V2 over a colour clip. Copy the setup from
  `tests/integration/test_title_renders.py::test_title_card_renders_text_pixels`
  (around line 92).
  - Compare the bindings grab at frame F with the old `0..F` melt method.
  - Use `frame_delta` / `frames_similar` from
    `tests/integration/external/_oracle.py` (around line 260). Mean absolute
    pixel difference must be at most 3.
  - If it is not, report the numbers and keep the old method for the
    fallback, as in step 5.
- Missing media: point a project at a deleted file. The tool must return a
  `missing_file` error and write no PNG.

## Steps: (b) per-frame render progress

### 7. Shared callback (create it if prompt 18 has not already)

`edit_mcp/adapters/render/progress.py`:

```python
@dataclass(frozen=True)
class RenderProgress:
    frame: int          # last frame rendered (0-based)
    total_frames: int   # 0 when unknown
    percent: float      # 0..100
    engine: str         # "mlt" | "melt"
ProgressCallback = Callable[[RenderProgress], None]
```

Add a `Throttle` helper. It calls the wrapped callback at most once per
second, or when `percent` changes by 1 or more, and always for the final
update.

### 8. Thread it through

- Add `execute_render(..., on_progress: ProgressCallback | None = None)` in
  `adapters/render/executor.py` (around line 72).
- Add `run_render(..., on_progress=None)` in
  `pipelines/render_pipeline.py` (around line 187) and pass it to
  `execute_render`.
- In `workspace/jobs.py::_run_worker`, render branch (around line 327): pass

  ```python
  on_progress=lambda p: progress("rendering", p.frame + 1, p.total_frames or 1,
                                 percent=round(p.percent, 1), engine=p.engine)
  ```

  wrapped in `Throttle`. `progress()` already persists
  `{stage, completed, total, **details}` into the SQLite job record.
- Every SQLite write opens `BEGIN IMMEDIATE`, so the throttle is mandatory.

### 9. Opt-in bindings render engine

Select it with `WVB_RENDER_ENGINE` = `melt` (**default**), `mlt`, or `auto`
(bindings if available, else melt).

- In `execute_render`, when the engine is `mlt` and the project is a
  `.kdenlive`, call a new worker op `render`.
  - Args: `{"path", "out", "props"}`.
  - Build `props` from the same `key=value` list `_build_melt_command`
    produces: split every `k=v` token after `avformat:<out>`, so both engines
    get identical consumer properties.
  - Stream progress events into `on_progress`.
- Use `subprocess.Popen` for this op, since it streams. Keep these rules:
  - Send stdout to a pipe that you read line by line.
  - Send stderr to a temp **file**, never to an unread pipe; a full pipe
    deadlocks MLT's noise.
  - Enforce `timeout_seconds` with a deadline. On expiry, kill the worker
    and handle it exactly like the existing `TimeoutExpired` branch.
- Write the log file in the same `Command / Return code / stdout / stderr`
  format.
- Then run the **same** `verify_render_output` the melt path runs. Do not
  add a second verification.
- Partial-output cleanup (`_fail`) applies unchanged.
- Job cancellation already works: the jobs worker runs in its own process
  group, and `cancel_job` sends SIGTERM to the whole group.
- The default stays `melt`. Make `auto` the default only after the
  equivalence proof (step 10) passes on both this host and CI. That is a
  separate decision; report the numbers.

### 10. Tests: progress

- Unit: test `Throttle` with a fake clock.
- Unit: test `execute_render(on_progress=...)` with the engine `mlt` and a
  fake worker that emits three progress events. The callback must see
  increasing frames, and the final job must succeed. Patch
  `verify_render_output`.
- Unit: test `_run_worker` for a render job with `run_render` patched to call
  `on_progress`. The job record's `progress` must hold `stage="rendering"`,
  `completed`, `total` and `percent`.
- External render proof (`tests/integration/external/`, `requires_melt` +
  `requires_mlt_bindings`): render `sequence_project` (and one real-media
  clip from `make_test_clip`) with `melt` and with `mlt`.
  - Assert equal frame counts (ffprobe `-count_frames`).
  - Assert durations within 1 frame.
  - Assert PSNR of at least 40 dB between the two outputs (use
    `ffmpeg -lavfi psnr`).
  - Assert that the progress callback fired at least twice with `frame`
    non-decreasing.

## Acceptance criteria

- `timeline_thumbnails` returns correct colours from the bindings in under
  2 s for 3 frames on the testkit project, and correct colours from the melt
  fallback.
- A `wvb jobs submit <ws> render` run with `WVB_RENDER_ENGINE=mlt` shows
  `progress.completed` rising while `wvb jobs status` is polled.
- Default render behaviour (melt) is unchanged. All existing render tests
  pass without edits.

## Do NOT

- Do not import `mlt7` in the venv process.
- Do not flip the default render engine.
- Do not write thumbnails beside the project or into `media/raw`.
- Do not change `_build_melt_command`'s output (prompt 18 owns melt CLI
  flags).
- Do not add a second output probe after the render.
- Do not persist progress more often than the throttle allows.

## When done

1. `docs/plans/2026-10-13-media-mcp-expansion.md`, Phase 3: mark the
   thumbnails and per-frame progress items done, with the equivalence
   numbers.
2. Extend `vault/wiki/mlt-python-bindings-worker.md` (from prompt 14) with the
   frame-grab recipe, the `get_image(0,0)` trap, the stdlib PNG writer and the
   title-composite finding.
3. Mention `timeline_thumbnails` in
   `docs/video-editing-guide/14-quality-control.md`.
4. Regenerate `docs/capabilities.md` (command in prompt 14 "When done").
5. Report per 00-README, including:
   - the title-test pixel difference;
   - the equivalence PSNR and frame counts;
   - whether you recommend making `auto` the default.
