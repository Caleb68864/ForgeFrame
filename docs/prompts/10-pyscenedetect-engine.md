# Prompt 10: PySceneDetect as an optional scene-detection engine

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not repeated here.

## Summary

Scene detection today is ffmpeg only. Commit `787e1b5` unified it into a
single ffmpeg scorer, `adapters/ffmpeg/scene.scan_scene_cuts`, which returns
real scores, raises `FFmpegNotFound`/`FFmpegTimeout`/`SceneScanError`, and
uses `ANALYSIS_TIMEOUT_SECONDS`. `pipelines/scene_detect.detect_scenes`
delegates to it.

This prompt adds PySceneDetect as a second, **optional** engine. It covers:
- an optional-dependency extra;
- a lazy-import adapter in `adapters/scenedetect/`;
- an `engine="auto|ffmpeg|pyscenedetect"` dispatch in the pipeline, following
  the `ai_mask` `ENGINES`/`resolve_engine`/`EngineUnavailable` pattern;
- a doctor row, a `requires_scenedetect` mark, a CI install, and tests.

It **does not** change any MCP tool. Prompt 11 wires the tools. Source:
`docs/plans/2026-10-13-media-mcp-expansion.md` Phase 1.

All paths below are under
`workshop-video-brain/src/workshop_video_brain/` unless they start with
`tests/`, `docs/` or `.github/`.

## Facts to verify first (they decide the dependency line)

PyPI, checked 2026-10-14:
- `scenedetect` **0.7.x** (latest 0.7.2) depends on **`opencv-python`**
  unconditionally. That is the GUI build, which needs `libGL` on Ubuntu, and
  0.7 has no `opencv-headless` extra.
- `0.6.7.1` still has the `opencv-headless` extra.
- Both put a module named `cv2` on disk. So do two other packages:
  - `rembg` (the ai-mask extra, installed in CI) pulls `opencv-python-headless`;
  - the `motion-track` extra pulls `opencv-contrib-python-headless`.
- Two opencv wheels in one venv overwrite each other's `cv2` files.

So:
1. In a scratch venv, try both candidate lines and record which works:
   - `uv venv /tmp/sd && uv pip install --python /tmp/sd/bin/python 'scenedetect[opencv-headless]>=0.6.7,<0.7'`
   - the same with `'scenedetect>=0.7'`.

   Then:
   - Run `python -c "import cv2, scenedetect; print(scenedetect.__version__, cv2.__version__)"`.
   - Check that `from scenedetect import detect, open_video, SceneManager, StatsManager, ContentDetector, AdaptiveDetector, ThresholdDetector` works.
2. Default choice: `scene-detect = ["scenedetect[opencv-headless]>=0.6.7,<0.7"]`.
   - Use 0.7 only if the 0.6 line is broken on Python 3.12, and then document
     the libGL requirement.
   - Record the decision and the reason in the report and in a comment above
     the extra.
3. Check co-installation with `motion-track` (`opencv-contrib-python-headless`).
   If `import cv2` breaks when both are installed, say so in the extra's comment
   and in the doctor suggestion text. Do not try to solve opencv packaging.

## Steps

### 1. Extra (both pyproject files, both lockfiles)

- Add `scene-detect` to `[project.optional-dependencies]` in
  `/home/caleb/Projects/ForgeFrame/pyproject.toml` (one-line style, like
  `motion-track`) and in `workshop-video-brain/pyproject.toml` (commented
  style, like `ai-mask`). The two lists must be identical.
- Regenerate both lockfiles:
  `uv lock --project /home/caleb/Projects/ForgeFrame` and
  `uv lock --project /home/caleb/Projects/ForgeFrame/workshop-video-brain`.
- Install it into the dev venv for the integration tests:
  `uv pip install --python /home/caleb/Projects/ForgeFrame/.venv/bin/python '<the chosen spec>'`.
  Do **not** add it to default groups.

### 2. Adapter: `edit_mcp/adapters/scenedetect/`

Create `__init__.py` (docstring only, no eager imports) and `engine.py`:

```python
class SceneDetectError(RuntimeError): ...   # decode/open failure; never a silent []
DETECTORS = ("content", "adaptive", "threshold")

def is_available() -> bool          # importlib.util.find_spec("scenedetect") and find_spec("cv2")
def scan_cuts(video_path: Path, *, detector: str = "content",
              detector_threshold: float | None = None,
              min_scene_seconds: float = 0.5,
              start_seconds: float = 0.0,
              end_seconds: float | None = None) -> list[tuple[float, float]]
```

- `import scenedetect` happens **inside** `scan_cuts`.
- `scan_cuts` returns `[(cut_time_seconds, score)]`: one tuple per boundary,
  i.e. the start of every scene except the first. Times are absolute, sorted
  and de-duplicated. This is the same shape as `scan_scene_cuts`.
- Recipe (verify against the installed version; the API changed between 0.6 and 0.7):
  ```python
  video = open_video(str(video_path))
  stats = StatsManager()
  sm = SceneManager(stats_manager=stats)
  sm.add_detector(det)   # ContentDetector(threshold=..., min_scene_len=frames) etc.
  if start_seconds: video.seek(start_seconds)
  sm.detect_scenes(video, end_time=end_seconds, show_progress=False)
  scenes = sm.get_scene_list()
  ```
  - Each cut is `scenes[i][0].get_seconds()` for `i >= 1`.
  - `min_scene_len` is in **frames**:
    `max(1, round(min_scene_seconds * video.frame_rate))`.
  - When `detector_threshold is None`, do not pass `threshold=`, so the library
    default applies (content 27.0, adaptive 3.0, threshold 12; verify).
- Score: read the detector's metric at the cut frame from the `StatsManager`.
  - The key comes from `det.get_metrics()[0]`; for content it is
    `content_val`. Verify.
  - Normalise it to 0..1 as `min(1.0, value / 255.0)` for `content` and
    `threshold`. For `adaptive`, use `min(1.0, value / (4 * adaptive_threshold))`.
  - If the metric is missing, use `0.0`. Document this as "relative, not
    comparable to ffmpeg's score".
- Errors:
  - an unopenable or undecodable file raises `SceneDetectError` with a
    one-line cause (catch the library's own exception types, verify their
    names, and `OSError`);
  - a missing package raises the pipeline's `EngineUnavailable` (step 3), not
    `ImportError`.
- PySceneDetect runs in-process, so there is no subprocess and no `timeout=`
  applies. Note that in the docstring. Do not add a thread-based timeout.

### 3. Pipeline dispatch: `edit_mcp/pipelines/scene_detect.py`

- Add an engine registry modelled on `pipelines/ai_mask.py` (~lines 62-150):
  `ENGINES = {"ffmpeg": {...}, "pyscenedetect": {"module": "scenedetect", "pip": "uv pip install -e '.[scene-detect]'", ...}}`,
  `_AUTO_ORDER = ("pyscenedetect", "ffmpeg")`, `engine_available(name)` and
  `resolve_engine(requested="auto") -> str`.
  - Reuse `EngineUnavailable` by importing it from `pipelines.ai_mask`, or
    define a local one with the same contract. Pick one and say which. A local
    one is preferable if importing `ai_mask` drags heavy imports in. Check its
    module-level imports.
  - `auto` falls back to `ffmpeg`, which is always "available" (the binary
    check happens at run time and raises `FFmpegNotFound`).
- Add a single dispatch function. Both consumers call it in prompt 11:
  ```python
  def scan_cuts(source, *, engine="ffmpeg", threshold=0.4, detector="content",
                detector_threshold=None, min_scene_seconds=0.5,
                start_seconds=0.0, end_seconds=None) -> tuple[str, list[tuple[float, float]]]
  ```
  It returns `(engine_used, hits)`.
  - `threshold` is the ffmpeg 0..1 knob and is ignored by pyscenedetect.
  - `detector_threshold` is the pyscenedetect native knob and is ignored by
    ffmpeg.
  - Unknown engine or detector names raise `ValueError`.
- `detect_scenes(...)`:
  - Add keyword args `engine="ffmpeg"`, `detector="content"`,
    `detector_threshold=None`. The default stays `"ffmpeg"` so existing tool
    output does not change.
  - Add `"engine": engine_used` to the result dict.
  - Map `SceneDetectError` to `error_type="media_unreadable"`, exactly as
    `SceneScanError` is mapped today.
  - Map `EngineUnavailable` to `error_type="missing_dependency"`.
    `server/errors.py` has `MISSING_DEPENDENCY` and
    `missing_dependency(pkg, pip_hint)`. `bundles/ai_mask.py:78` shows how a
    tool catches `EngineUnavailable`.
  - Keep `dry_run` working: for pyscenedetect, return `command: None` and
    `engine`.
- In `adapters/ffmpeg/scene.detect_scene_changes` (~line 135), add an optional
  keyword `scan: Callable[[Path, float, float, float | None], list[tuple[float, float]]] | None = None`.
  `_run_scene_filter` uses it in place of `scan_scene_cuts` when given. This
  lets prompt 11 inject the pyscenedetect scanner without the adapter
  importing the pipeline (layering: adapters < pipelines). The default
  behaviour must stay byte-for-byte the same.

### 4. Doctor row (`app/doctor.py`)

- Add `'scene_detect': 'scenedetect'` to the `optional` find_spec map.
- Add the feature `'scene_detect_pyscenedetect': optional['scene_detect'] and importlib.util.find_spec('cv2') is not None`.
- Mention `scene-detect` in `suggestions['optional_engines']`.
- Update `tests/unit/test_discovery_commands.py` if it asserts the exact key set.

### 5. Test mark (`tests/_testkit.py`)

Next to the binary marks (~line 52), add:
```python
HAVE_SCENEDETECT = importlib.util.find_spec("scenedetect") is not None and importlib.util.find_spec("cv2") is not None
requires_scenedetect = pytest.mark.skipif(not HAVE_SCENEDETECT, reason="scenedetect (scene-detect extra) not installed")
```
Also add a fixture helper,
`make_hard_cut_clip(path, *, first="red", second="blue", seconds_each=2.0, fps=25, size=(320, 240), with_audio=False) -> Path`.
It builds a clip with one hard cut, using ffmpeg's two `color=` lavfi inputs
and `concat=n=2:v=1:a=0` (add a sine track when `with_audio`), and goes
through the existing `_run_ffmpeg`. The cut is at exactly `seconds_each`.

### 6. CI (`.github/workflows/tests.yml`, `full` job)

After the ai-mask install step (~line 68), add a step
"Install scene-detect extra", `uv pip install '<the chosen spec>'`, with a
two-line comment, like the rembg step. If you confirmed in "Facts" that rembg's
headless cv2 conflicts with it, install scene-detect **before** rembg, or
document which one wins, and make sure `python -c "import cv2"` works after
both. Put a verification `run:` line in the workflow.

### 7. Tests

- **Unit** (`tests/unit/test_scene_detect_engines.py`, no binaries, no scenedetect needed):
  - `resolve_engine("auto")` picks pyscenedetect when `engine_available` is
    monkeypatched True, and ffmpeg otherwise.
  - An unknown engine raises `ValueError`.
  - `pyscenedetect` with the package missing raises `EngineUnavailable` whose
    message contains the install hint.
  - `scan_cuts(engine="pyscenedetect")` with the adapter's `scan_cuts`
    monkeypatched to a fake returns `("pyscenedetect", fake_hits)` and passes
    `detector`/`detector_threshold` through.
  - `detect_scenes` maps `SceneDetectError` to `media_unreadable` and never
    reports success with zero cuts.
  - `detect_scene_changes(..., scan=fake)` uses the fake. It needs a
    monkeypatched `probe_media`; see how existing unit tests stub it.
  - Default `detect_scenes(...)` still calls the ffmpeg path, guarded by a
    monkeypatch spy.
- **Integration** (`tests/integration/test_scenedetect_engine.py`, marks
  `requires_scenedetect` + `requires_ffmpeg_ffprobe`):
  - `make_hard_cut_clip(tmp_path/"cut.mp4")` (red 2 s, then blue 2 s, 25 fps).
  - For each detector in `content`, `adaptive`, `threshold`: exactly one cut
    within 1 frame (0.04 s) of 2.0 s, and the score is in [0, 1]. The
    `threshold` detector fades to black, so red-to-blue may not trigger it.
    If it does not, assert that and document it, rather than tuning until it
    passes.
  - The ffmpeg engine on the same file also finds one cut near 2.0 s. This
    is the cross-engine agreement check.
  - A file with no cuts (`make_test_clip(kind="color")`) gives `[]`.
  - A truncated or garbage file (write 1 KB of random bytes to `.mp4`) raises
    `SceneDetectError`.

## Acceptance criteria

- `uv run ... python -c "from workshop_video_brain.edit_mcp.pipelines.scene_detect import resolve_engine; print(resolve_engine('auto'))"` prints `pyscenedetect` with the extra installed and `ffmpeg` without it.
- The unit tests pass in an environment **without** scenedetect. Check this:
  `uv pip uninstall scenedetect`, run unit, reinstall.
- The integration tests pass with it installed. The cut time is within 0.04 s of 2.0 s for at least `content` and `adaptive`.
- `wvb doctor` lists `scene_detect_pyscenedetect`.
- Existing scene tests (`tests/integration/test_scene_detection_smoke.py`, `tests/unit/test_analysis_tools.py`, `tests/unit/test_research_media_tools.py`) are unchanged and green.

## Do NOT

- Do not change any MCP tool signature (that is prompt 11), and do not change the default engine of any existing caller.
- Do not import `scenedetect` or `cv2` at module level anywhere.
- Do not make the extra a default dependency or add it to `[tool.uv] default-groups`.
- Do not add a thread or subprocess timeout wrapper around PySceneDetect.
- Do not rename or remove the existing ffmpeg functions. `research_detect_scenes` and the visual-research candidates import them.

## When done

- Add a vault note, `vault/wiki/scene-detection-engines.md`, covering:
  - ffmpeg vs PySceneDetect: what each scores and the scale;
  - detector defaults;
  - the opencv packaging trap;
  - the measured cut times from your integration test.
- In `docs/plans/2026-10-13-media-mcp-expansion.md` Phase 1, mark the extra, adapter, dispatch, doctor, mark and CI bullets done (dated).
- Do not regenerate `docs/capabilities.md`; no tool changed.
- Report in the shared format. Include the dependency decision (0.6 vs 0.7, and why), the cut times per detector, and any cv2 co-install conflict.
