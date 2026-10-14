# 01 -- Automate the Kdenlive-vs-melt differential (roadmap step 1)

Turn the manual Kdenlive 26.08 differential (`scripts/kdenlive_check_pack.py`
plus hand-run `kdenlive --render` / `melt` / ffmpeg comparisons) into a
`requires_kdenlive` external pytest. It builds the 7-step check pack once,
renders every project with both Kdenlive and melt, and asserts matching frames
(PSNR), matching duration and audible audio. Checks that fail today because of
known bugs are marked `xfail(strict=True)` and point at the prompt that fixes
them, so they flip to XPASS (a failure under `strict`) the moment the fix lands
and the fixer has to remove the marker.

Read `docs/prompts/00-README.md` first; its shared rules apply. This prompt
adds test infrastructure only. Do not change any source under
`workshop-video-brain/src/`.

---

## Background (measured 2026-10-14, Kdenlive 26.08.2, MLT 7.42)

Whole-video comparison of `kdenlive --render` vs `melt` for each pack project:

| Project | PSNR (dB) | Duration K / M (s) | mean_volume K / M |
| --- | --- | --- | --- |
| 01_single_clip | 35.2 | 4.011 / 4.011 | -91 / -91 |
| 02_two_clips | 37.4 | 8.000 / 8.000 | -91 / -91 |
| 03_speed | 36.5 | 6.016 / 6.016 | -91 / -91 |
| 04_dissolve | 36.6 | 5.056 / 5.056 | -91 / -91 |
| 05_audio_fade | 36.6 | 5.056 / 5.056 | -91 / -91 |
| 06_effect_blur | **27.1** | 5.056 / 5.056 | -91 / -91 |
| 07_title | **27.7** | 5.056 / 5.056 | -91 / -91 |

- A real match is 35-38 dB (two encoders over the same pixels). A dropped
  effect is 25-28 dB. Use **33 dB** as the threshold.
- `07_title` is low only because the pack is cumulative: it still contains the
  dropped blur from step 06. It is fixed by prompt 03, not by a title fix.
- Audio is -91 dB (digital silence) everywhere: prompt 02. The test media has
  a 440 Hz / 660 Hz tone, so a correct render is around -20 dB.
- `kdenlive --render` returns rc 0 even when it silently drops content, and
  aborts with rc 134 (`std::out_of_range ... unordered_map::at`) when a filter
  carries an unknown `kdenlive_id`. Always assert rc 0 **and** the comparisons.

## The fix: steps in order

### 1. `requires_kdenlive` mark (`tests/_testkit.py`, around lines 44-60)

Copy the existing pattern (`HAVE_MELT = shutil.which("melt") is not None`,
`requires_melt = pytest.mark.skipif(...)`):

- `HAVE_KDENLIVE = shutil.which("kdenlive") is not None`
- `HAVE_XVFB_RUN = shutil.which("xvfb-run") is not None`
- `requires_kdenlive = pytest.mark.skipif(not (HAVE_KDENLIVE and HAVE_XVFB_RUN), reason="kdenlive (and xvfb-run for a headless display) not available on PATH")`

Also add a session fixture `kdenlive_bin` to
`tests/integration/external/conftest.py` next to `melt_bin`, using the same
`_require(...)` helper (it skips when the binary is missing).

### 2. Move the pack builder into an importable helper

Create `tests/integration/external/_check_pack.py` (leading `_` means pytest
does not collect it). Move the body of `main()` from
`scripts/kdenlive_check_pack.py` into:

```python
@dataclass(frozen=True)
class PackStep:
    index: int        # 1..7
    slug: str         # "single_clip", "two_clips", ...
    path: Path        # <out>/NN_<slug>.kdenlive
    expect: str       # the CHECKLIST text

def build_check_pack(out: Path) -> list[PackStep]: ...
def write_checklist(out: Path, steps: list[PackStep]) -> Path: ...
```

- Keep the tool calls, arguments and order **byte-for-byte the same** as the
  script today (same media, same 7 steps, same `effect_add` / `title_card_add`
  arguments). The numbers in the table above depend on them.
- Replace `sys.exit(...)` in `_check` / `latest_project` with
  `raise RuntimeError(...)`. A helper must never exit the test process.
- Import `make_test_clip` with `from tests._testkit import make_test_clip`
  (same style as `tests/integration/external/builders.py`).
- Rewrite `scripts/kdenlive_check_pack.py` as a thin CLI: parse `OUT_DIR`,
  `rmtree` it if it exists, call `build_check_pack`, `write_checklist`, print
  the summary. Keep its docstring and `sys.path.insert(0, str(REPO))` so
  `from tests.integration.external._check_pack import ...` resolves. Running
  the script must produce the same files as before.

### 3. Render and measurement helpers (`tests/integration/external/_oracle.py`)

Add, next to `render_video` / `audio_stats`. Every `subprocess.run` gets
`timeout=`:

- `kdenlive_render(project, out, kdenlive_bin="kdenlive", timeout=300) -> Path`
  - Command: `["xvfb-run", "-a", kdenlive_bin, "--render", str(project), str(out)]`.
  - Use `subprocess.Popen(..., start_new_session=True)` and
    `proc.communicate(timeout=timeout)`. On `TimeoutExpired`, kill the whole
    process group (`os.killpg(proc.pid, signal.SIGKILL)`), because `xvfb-run`
    leaves Kdenlive and Xvfb running otherwise. Then raise `RuntimeError`.
  - Raise `RuntimeError` with the rc and the last 1500 chars of stderr if
    `rc != 0` or `out` does not exist.
  - A render takes about 7 s on this machine.
- `melt_render_full(project, out, melt_bin="melt", timeout=180) -> Path`:
  `[melt_bin, project, "-consumer", f"avformat:{out}", "vcodec=libx264", "acodec=aac", "terminate_on_pause=1"]`.
  Do not pass `out=` (render the whole project, like Kdenlive does).
- `video_psnr(a, b, ffmpeg_bin="ffmpeg", timeout=600) -> float`:
  `ffmpeg -hide_banner -i a -i b -lavfi "[0:v][1:v]psnr" -f null -`. Parse
  `average:<x>` from stderr. `inf` (identical) returns `math.inf`. Raise if not
  found.
- `video_frame_count(path, ffprobe_bin="ffprobe", timeout=120) -> int`:
  `ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 path`.
- `mean_volume_db(path, ffmpeg_bin="ffmpeg", timeout=600) -> float`:
  `ffmpeg -hide_banner -i path -vn -af volumedetect -f null -`. Parse
  `mean_volume: <x> dB`. A file with no audio stream returns `-math.inf`.

Optional (recommended; later prompts use this technique for diagnosis):
`kdenlive_render(..., capture_playlist: Path | None = None)`. While Kdenlive
renders it writes its rebuilt MLT playlist to
`$TMPDIR/kdenlive-XXXXXX-1.mlt` (usually `/tmp`), then empties it. Poll every
50 ms while the process runs, glob `kdenlive-*.mlt` in
`tempfile.gettempdir()`, ignore files that existed before the start, and keep
the largest content you read. That file shows exactly which filters,
transitions and entries Kdenlive kept. A failing assertion should mention its
path.

### 4. The test (`tests/integration/external/test_kdenlive_differential.py`)

- Module marks: `pytestmark = [pytest.mark.external, requires_kdenlive, requires_melt_ffmpeg]`
  (import the marks from `tests._testkit`). The pack build also needs ffprobe
  (`clip_insert` probes media), so also add `requires_ffmpeg_ffprobe`.
- A `scope="module"` fixture `pack` that calls
  `build_check_pack(tmp_path_factory.mktemp("kdenlive_pack"))` once.
- A `scope="module"` fixture `renders` that returns a dict cache. A helper
  `_rendered(renders, step, kdenlive_bin, melt_bin)` renders the step with both
  renderers on first use and returns `(kdenlive_mp4, melt_mp4)`. Each project
  is rendered at most once per renderer, no matter how many checks use it.
- Three test functions, each parametrized over the 7 slugs with
  `pytest.param(slug, id=slug, marks=...)`:
  1. `test_frames_match`: `video_psnr(k, m) >= 33.0`. Message includes the dB
     value and the project path.
  2. `test_duration_match`: `abs(frames_k - frames_m) <= 1` using
     `video_frame_count`.
  3. `test_audio_audible`: `mean_volume_db(k) > -60` **and**
     `mean_volume_db(m) > -60`.
- Request `melt_bin` in each test. The external conftest then auto-applies
  `render_retry`, which is wanted here.
- Expected failures, each `pytest.mark.xfail(strict=True, reason=...)`:
  - `test_audio_audible`, all 7 slugs:
    `"audio lost on clip_insert -- docs/prompts/02-audio-on-insert.md"`.
  - `test_frames_match` for `effect_blur` and `title`:
    `"Kdenlive drops effect_add filter (no kdenlive_id) -- docs/prompts/03-effects-kdenlive-identity.md"`.
  - Everything else must pass today. Keep the xfail lists in two module-level
    sets (`AUDIO_XFAIL`, `FRAMES_XFAIL`) so prompts 02/03 remove entries
    rather than editing decorators.
- Do not use `xfail(raises=...)`. A render crash (rc 134) must fail loudly, not
  be absorbed as an expected failure. Build the renders inside the test body
  (via the cache helper), not in fixture setup, so an error is reported against
  the step that caused it.

### 5. CI

`.github/workflows/tests.yml` `full` does not install Kdenlive, so the new
tests skip there. **Do not** add Kdenlive to CI. Ubuntu's packaged Kdenlive is
not 26.08, and a different version would measure something else. Add one line
under the "CI" heading of `CLAUDE.md`: the Kdenlive differential is local-only
(`requires_kdenlive`).

## Tests and verification

1. `xvfb-run -a uv run --project /home/caleb/Projects/ForgeFrame pytest /home/caleb/Projects/ForgeFrame/tests/integration/external/test_kdenlive_differential.py -v -p no:cacheprovider -rxXs`
   Expected: 12 passed, 9 xfailed, 0 xpassed. Takes roughly 1-2 minutes.
2. Script still works:
   `uv run --project /home/caleb/Projects/ForgeFrame python /home/caleb/Projects/ForgeFrame/scripts/kdenlive_check_pack.py /tmp/ff-pack-check`
   writes 7 `.kdenlive` files plus `CHECKLIST.md`.
3. Prove the oracle bites: temporarily change the PSNR threshold to 40 and see
   `test_frames_match` fail for at least one non-xfail step, then restore 33.
   Report the run.
4. Unit suite, full suite (expect the baseline from `00-README.md` plus the new
   tests) and `uvx ruff check --select F401,F841` on every file you touched.
5. Simulate CI (no Kdenlive): temporarily set `HAVE_KDENLIVE = False` in
   `_testkit.py`, run the test file, confirm 21 skipped, then revert. Say in
   the report that you did this.

## Acceptance criteria

- `requires_kdenlive` exists in `tests/_testkit.py`, and `kdenlive_bin` exists
  in the external conftest.
- One pack-building implementation, used by both the script and the test.
- 21 test cases: 12 pass and 9 are strict xfails with the reasons above.
- Every subprocess call has a timeout, and a Kdenlive timeout kills the
  process group.

## Do NOT

- Do not change any file under `workshop-video-brain/src/`. If a step outside
  the xfail lists fails, stop and report the numbers instead of fixing code.
- Do not relax the threshold below 33 dB to make something pass.
- Do not compare against golden files or checked-in renders. The comparison is
  Kdenlive vs melt on the same project.
- Do not pass `-n` to pytest (xdist is not installed).

## When done

1. `docs/plans/2026-04-08-feature-roadmap.md`, step 1: mark it
   `**Done YYYY-MM-DD.**` (fill in the date) and add a 2-3 line summary in the
   style of step 4: test path, threshold, xfail map.
2. `docs/testing/2026-10-13-kdenlive-2608-differential.md`: add a paragraph
   "Automated" naming the test file and the command, and refresh the PSNR
   column with your measured numbers.
3. `vault/wiki/`: add `kdenlive-headless-render-differential.md`. Cover
   `xvfb-run -a kdenlive --render`, the playlist-capture trick, rc 0 on silent
   drops, rc 134 on an unknown `kdenlive_id`, and the 33 dB threshold
   rationale.
4. Report (format in `00-README.md`), including the per-step PSNR / frame
   count / mean_volume table from your run.
