# Prompt 18: melt CLI render progress into job records + stricter probe before "done" (Phase 4, harvest item 2)

Hand this whole file to the implementing model.

---

Renders through the melt CLI currently block in `subprocess.run` and report
nothing until they finish. The persistent job record only ever says
`stage: "rendering"`; the roadmap notes "Progress describes stages and assets,
rather than frame-level render percentages". This task does three things:

1. Stream melt's stderr and parse its `Current Frame: N, percentage: P` lines
   into a progress callback that reaches the SQLite job record.
2. Tighten the existing post-render probe so a truncated render, or one
   missing a stream, is never reported as succeeded.

The idea comes from `12bijaya/MCP_Server_Kdenlive`. It has no licence, so
reimplement and do not copy. Their approach, in prose: tail the melt log for
the last progress match; when the process exits 0, require that the output
exists, is non-empty, probes as valid media, and has a positive duration
before marking the job completed; set 100 % only then.

Read `docs/prompts/00-README.md` first. No prerequisites. **Relation to
prompt 15:** prompt 15 (MLT bindings) defines the same progress callback and
an opt-in bindings render engine. Check whether
`edit_mcp/adapters/render/progress.py` exists:

- If it does, reuse `RenderProgress`, `ProgressCallback`, `Throttle` and the
  `on_progress` plumbing in `execute_render`, `run_render` and the jobs worker
  exactly as they are. Only add the melt source.
- If it does not, create them **with exactly the names and fields below**,
  so prompt 15 can reuse them later.

## What already exists (do not duplicate)

- `adapters/render/executor.py::execute_render` (around line 72) is the one
  executor used by every render path. That includes `run_render` in
  `pipelines/render_pipeline.py` (around line 187), `render_preview`,
  `render_final` (via `run_render`), the jobs worker
  (`workspace/jobs.py`, around line 333), `guided_workflow` and
  `review_loop`. It already:
  - pre-checks missing media;
  - writes a `Command / Return code / stdout / stderr` log;
  - cleans up partial output on failure;
  - maps timeout and missing-binary errors;
  - on exit 0, calls `verify_render_output(path)` (around line 357).
- `verify_render_output` already checks: non-empty file, ffprobe exit 0,
  at least one stream, `0 < duration < inf`. **It does not check** the stream
  kinds, or the duration against the timeline length. Extend it; do not
  write a second probe.
- `_build_melt_command` (around line 257) builds
  `["melt", project, "-consumer", "avformat:<out>", k=v...]`.
  `tests/unit/test_render_profiles.py` (around line 328) asserts on its
  output.
- `tests/unit/test_render_final.py` patches
  `executor.subprocess.run` about 10 times to fake the render call.

## Verified melt behaviour (MLT 7.42, this machine)

- melt writes its progress to **stderr**:
  - `Current Frame:         31, percentage:         62` + `\r`
    (default, or `-progress`);
  - one line per update with `\n` (`-progress2`).
  - Updates are coarse: about 2-3 per second. A 50-frame render showed 29/58
    and 49/98.
- The last report is `49, percentage: 98`. melt **never prints 100**, so set
  100 yourself after verification succeeds.
- stderr also carries about 170 lines of MLT registration noise. Keep it in
  the log, and do not let it fill an unread pipe.
- Regex, used on segments split on **both** `\r` and `\n`:
  `re.compile(r"Current Frame:\s*(\d+),\s*percentage:\s*(\d+)")`.

## Steps

### 1. Shared progress types (only if prompt 15 has not created them)

`edit_mcp/adapters/render/progress.py`:

```python
@dataclass(frozen=True)
class RenderProgress:
    frame: int; total_frames: int; percent: float; engine: str   # "melt" | "mlt"
ProgressCallback = Callable[[RenderProgress], None]
class Throttle:   # wraps a callback; at most 1 call/s or on >=1 % change; final() always fires
```

Also `parse_melt_progress(chunk: str) -> list[tuple[int, int]]`. It splits
on `\r` and `\n` and returns the `(frame, percent)` matches. Put it in the
same module.

### 2. Stream the melt process

In `executor.py`, add
`_run_render_process(cmd, timeout_seconds, on_line) -> subprocess.CompletedProcess`.

- Use `subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, text=True, errors="replace")`.
- Read stderr in a background thread, in chunks (`read(4096)`), so a `\r`
  without `\n` is still seen. Accumulate the full text and feed each chunk to
  `on_line`.
- Drain stdout in a second thread. Both pipes must be drained, or MLT's noise
  deadlocks the process.
- Enforce `timeout_seconds` with a monotonic deadline. On expiry,
  `proc.kill()`, join the threads, and raise
  `subprocess.TimeoutExpired(cmd, timeout_seconds)`. The existing `except`
  branch then handles it unchanged.
- Return `CompletedProcess(cmd, returncode, stdout_text, stderr_text)`, so
  the rest of `execute_render` (log file, returncode branch) is unchanged.
- Replace the render `subprocess.run(...)` call (around line 146) with
  `_run_render_process`.
  - Keep `subprocess.run` for ffprobe in `verify_render_output` and for
    `check_codec_available`.
  - `tests/unit/test_subprocess_timeouts.py` only scans
    `run`/`check_output`/`check_call`/`call`; Popen is still your
    responsibility.
- Update `tests/unit/test_render_final.py`: where a patch of
  `executor.subprocess.run` stands in for the **render** call, patch
  `executor._run_render_process` instead. Keep every assertion. Do not
  weaken any test.

### 3. Melt progress flag

- In `_build_melt_command`, insert `-progress2` right after `"melt"`.
- Update the expected command in `tests/unit/test_render_profiles.py`.
- Parse both separators anyway. CI's melt 7.22 must support `-progress2`:
  verify with `melt -help 2>&1 | grep progress2` and report what you saw.
- If `-progress2` is unsupported on 7.22, drop the flag. melt prints the
  `\r` form by default, and the parser handles it.

### 4. Progress callback

- Add `execute_render(..., on_progress: ProgressCallback | None = None)`.
- In the stderr reader, for each `(frame, percent)` from
  `parse_melt_progress`, call
  `on_progress(RenderProgress(frame, total, float(percent), "melt"))`.
- `total` comes from the timeline length when known: parse the project once
  before rendering, and take the max over playlists of the sum of entry
  lengths. Factor that into a helper in `adapters/render/media_check.py` or
  a new `adapters/render/timeline_length.py`; do not hand-roll XML in the
  shell. Otherwise `total = round(frame * 100 / percent)` when
  `percent > 0`, else 0.
- After `verify_render_output` succeeds, fire a final
  `RenderProgress(total-1, total, 100.0, "melt")`.
- Callback exceptions must never kill the render. Wrap the call and log at
  debug level.
- Thread `on_progress` through `run_render(..., on_progress=None)`.
- In `workspace/jobs.py::_run_worker`'s render branch, pass
  `Throttle(lambda p: progress("rendering", p.frame + 1, p.total_frames or 1, percent=round(p.percent, 1), engine=p.engine))`.
  `progress()` already persists `{stage, completed, total, **details}`, and
  `job_status` / `wvb jobs status` show it.

### 5. Stricter verification

Extend `verify_render_output(path, *, expected_duration=None, expect_video=True, expect_audio=None)`.
The existing checks stay.

- `expect_video` (default True): there must be a `codec_type == "video"`
  stream, unless the output extension is an audio container. Find that list
  in `render/profiles.py`.
- `expect_audio`: `execute_render` passes `not profile.disable_audio`.
  - **First verify** that melt writes an audio stream for a timeline with no
    audio clips (render `solid_color_project` minus its audio playlist
    entries).
  - If it does not, pass `expect_audio=None` (unchecked) for those
    timelines, and write the finding in the report.
- `expected_duration`: the timeline length / fps, from step 4.
  - Compare against the **video stream** duration, falling back to the
    format duration.
  - Fail when it is shorter than `expected - max(2 / fps, 0.005 * expected)`,
    with `ValueError("Render is shorter than the timeline: 3.20s of 10.00s -- melt stopped early; see the log")`.
  - A longer output only logs a warning (audio padding is normal).
- All new failures go through the existing `_fail(str(exc), "invalid_output")`
  path: the partial output is removed and the error is surfaced.

## Tests (all required)

- Unit, `parse_melt_progress`:
  - the `\r` stream, the `\n` stream, and a chunk split mid-line;
  - real noise lines interleaved;
  - the exact sample `Current Frame:         31, percentage:         62`.
- Unit, `_run_render_process`, with a fake command `[sys.executable, "-c", <script>]`
  whose script writes progress lines to stderr, plus 200 KB of noise (this
  proves there is no pipe deadlock):
  - the callback order;
  - the CompletedProcess contents;
  - timeout kills the process and raises `TimeoutExpired` (script sleeps 30 s,
    timeout 1 s).
- Unit, `verify_render_output` with ffprobe patched to canned JSON:
  - no video stream fails;
  - expected 10 s but got 3.2 s fails;
  - 10.04 s passes;
  - no audio stream when one is expected fails.
- Unit, jobs worker with `run_render` patched to call `on_progress` 3 times:
  the record's `progress` has `stage == "rendering"`, `percent`, and
  `engine == "melt"`.
- External render proof (`tests/integration/external/`, `requires_melt`):
  - Render `sequence_project(frames_each=50)` through `run_render` with a
    collecting callback. Expect at least 2 callbacks, with frames
    non-decreasing, and the final callback at percent 100.
  - Then render a project whose media file is truncated or replaced after
    the pre-check, or use `_command_override` with an `out=` shorter than
    the timeline. The job must end `failed`, with
    `error_type == "invalid_output"` and no output file left behind.

## Acceptance criteria

- `wvb jobs submit <ws> render` then polling `wvb jobs status` shows
  `progress.percent` increasing during a real render of a timeline of at
  least 5 s.
- A render cut short is reported as failed with a clear "shorter than the
  timeline" message.
- No render path calls ffprobe twice after a render.
- The full suite is green.

## Do NOT

- Do not add a second post-render probe anywhere (`render_final`,
  `run_render`, tools). Extend `verify_render_output` only.
- Do not change the bindings render engine or the default engine selection
  if prompt 15 added them.
- Do not report 100 % before verification passes.
- Do not write progress to SQLite without the throttle.
- Do not read the log file to get progress. Parse the live stream; the log is
  written at the end as before.
- Do not copy code from the harvest repo.

## When done

1. `docs/plans/2026-10-13-media-mcp-expansion.md`, Phase 4 item 2: mark it
   done. In `docs/plans/2026-04-08-feature-roadmap.md`, "Reliability and
   Guided Workflow": update the sentence "Progress describes stages and
   assets, rather than frame-level render percentages". Prompt 08 may also
   have added a "frame-level progress not implemented" note to item 3;
   update that too. Replace both with the new behaviour.
2. Add a vault note, `vault/wiki/melt-progress-and-render-verification.md`.
   Cover:
   - the stderr format;
   - `\r` versus `-progress2`;
   - that melt never prints 100;
   - the pipe-drain requirement;
   - the audio-stream finding from step 5.
3. Mention progress polling in `docs/video-editing-guide/13-formats-codecs-export.md`.
4. Report per 00-README. Include:
   - the measured callback count and timing for a 10 s render;
   - the `-progress2` check result;
   - the audio-stream finding.
