# Prompt 12: auto-editor engine and `media_remove_silence`

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not repeated here.

## Summary

This prompt adds [auto-editor](https://github.com/WyattBlue/auto-editor) as
an optional silence-cut engine. ForgeFrame runs its CLI, reads its **timeline
JSON** cut list, and turns that into **keep-ranges** (source seconds to
keep). It **never** imports auto-editor's `--export kdenlive` project, because
that bypasses our serializer rules.

There is also a no-dependency **ffmpeg** engine, so the feature always works.
On top of both engines sits a new bare-file tool, `media_remove_silence`. It
renders a tightened copy of the file by cutting out the silent parts with
ffmpeg.

Prompt 13 reuses the same keep-ranges to build a jump-cut `.kdenlive`
timeline, so get the keep-range contract right.

Source: `docs/plans/2026-10-13-media-mcp-expansion.md` Phase 2.

**Name clash:** a skill `ff-auto-editor` already exists. It is unrelated
(script assembly). Do not touch, rename or reuse it, and do not create any
new skill named after auto-editor.

Paths are under `workshop-video-brain/src/workshop_video_brain/` unless
they start with `tests/`, `docs/`, `vault/` or `.github/`.

## What we already know about auto-editor (verified 2026-10-14 with 29.3.1; re-verify)

- `pip install auto-editor` installs a thin Python launcher with **no Python
  dependencies**. On first run it **downloads a native binary from GitHub**
  into `site-packages/auto_editor/bin/auto-editor` and prints
  "Downloading auto-editor binary..." to **stdout**.
  - It is offline-hostile, and the first run's stdout is polluted.
  - Linux builds exist only for x86_64.
  - Resolve the binary as follows: `auto_editor/bin/auto-editor` (or
    `auto-editor.exe`) next to the package if it exists, else
    `shutil.which("auto-editor")` (a system install). If neither exists, raise
    `EngineUnavailable`, with a hint to run
    `uv run --project <repo> auto-editor --version` once (this downloads it)
    or to install the binary.
  - Locate the package with `importlib.util.find_spec("auto_editor").submodule_search_locations`.
    Never trigger the download from the adapter.
- `--export json` is **rejected** ("Unknown export format: json").
  - Use `--export v3`. It writes the timeline v3 JSON and **forces a `.v3`
    extension**: `-o out.json` actually writes `out.v3`. Pass `-o <tmpdir>/cut.v3`
    and read that exact path. If it is missing, glob `<tmpdir>/*.v3`.
  - `--export v1` keeps `.json` and gives `chunks: [[start, end, speed], ...]`,
    with `99999.0` meaning cut. It has **no timebase**, so do not use it.
- Useful flags:
  - `--edit audio:threshold=<linear 0..1>` (0.04 is the default, about -28 dBFS);
  - `--margin 0.2s` (the default);
  - `--progress none`;
  - `-q`;
  - `--no-open`;
  - `--temp-dir <dir>`.
- Real output for `tests/fixtures/media_generated/test_audio_with_silence.mp4`.
  The fixture is 320x180 h264 at 30 fps with mono AAC, 5.0 s long, and silent
  from 1.5 s to 3.5 s.
  ```json
  {"version": "3", "timebase": "30/1", "resolution": [320, 180], "samplerate": 48000, "layout": "mono",
   "v": [[{"name": "video", "src": "/abs/test_audio_with_silence.mp4", "start": 0,  "dur": 51, "offset": 0,  "stream": 0},
          {"name": "video", "src": "/abs/test_audio_with_silence.mp4", "start": 51, "dur": 51, "offset": 99, "stream": 0}]],
   "a": [[ ...same two clips with "name": "audio"... ]]}
  ```
  - Units are **timebase frames**. `offset` is the source in-frame, `dur` is
    the length, and `start` is the timeline position.
  - The keep-ranges are therefore `offset/tb .. (offset+dur)/tb`: here
    `[0, 1.7)` and `[3.3, 5.0)`, i.e. 3.4 s kept.
- Before coding, run it yourself on the fixture and on an audio-only file.
  Check the `music_cinematic_short.mp3` fixture: is `v` empty or missing? Is
  there a `speed` key on clips?

## Steps

### 1. Extra, doctor and mark

- Add `auto-editor = ["auto-editor>=29"]` to **both** pyproject files and run
  `uv lock` for both, as in prompt 10. Pin a lower bound you verified.
- Install it into the dev venv with `uv pip install`. Then run
  `uv run --project /home/caleb/Projects/ForgeFrame auto-editor --version`
  once to fetch the binary.
- Doctor (`app/doctor.py`):
  - add `'auto_editor': 'auto_editor'` to the `optional` map;
  - add a feature `silence_cut_auto_editor`. It is true only when the binary
    resolves (reuse the adapter's resolver; doctor may import it lazily) and
    `_probe(binary, ['--version'])` succeeds;
  - add a suggestion line.
- In `tests/_testkit.py`, add `HAVE_AUTO_EDITOR` (the adapter's resolver
  returns a path) and `requires_auto_editor`.
- CI `full` job: add the step `uv pip install 'auto-editor>=29' && uv run auto-editor --version`.
  The second command fetches the binary. Comment that it needs network.

### 2. Adapter: `edit_mcp/adapters/autoeditor/`

Use `__init__.py` (docstring only) and `cli.py`. `cli.py` contains:

```python
class AutoEditorError(RuntimeError): ...          # nonzero exit / missing or unparsable v3
def resolve_binary() -> Path | None
def build_command(binary, source, out_v3, *, threshold_linear, margin_seconds, temp_dir) -> list[str]
def run_v3(source: Path, *, threshold_db: float = -30.0, margin_seconds: float = 0.2) -> dict  # parsed v3 JSON
def keep_ranges_from_v3(v3: dict) -> list[tuple[float, float]]                                 # pure
```

- `run_v3` does the following:
  - convert dB to linear: `10 ** (threshold_db / 20)`;
  - create a `tempfile.TemporaryDirectory()` for both `-o` and `--temp-dir`;
  - call `subprocess.run(cmd, capture_output=True, text=True, timeout=ANALYSIS_TIMEOUT_SECONDS)`,
    importing the constant from `adapters/ffmpeg/runner.py`;
  - let `subprocess.TimeoutExpired` propagate unchanged.
    `errors._classify_subprocess_exception` (~line 407) already turns a raw
    `TimeoutExpired` into an actionable "timed out after" error, naming
    `cmd[0]`. Do not wrap it in `FFmpegTimeout`, which would mislabel it as
    ffmpeg;
  - a nonzero exit, a missing `.v3` or bad JSON raises `AutoEditorError`
    with the stderr tail.
- `keep_ranges_from_v3`:
  - parse `timebase` as a `Fraction` (`"30/1"`, or `"30000/1001"`);
  - take the first non-empty layer of `v`, else of `a`;
  - map each clip to `(offset/tb, (offset+dur)/tb)` in seconds, rounded to
    6 decimal places;
  - raise `AutoEditorError` if any clip has a `speed` not equal to 1;
  - merge touching ranges and sort.
- Add an AST-scan check: `tests/unit/test_subprocess_timeouts.py` must stay green.

### 3. Pipeline: `edit_mcp/pipelines/silence_cut.py`

```python
ENGINES = {"auto-editor": {...module "auto_editor", pip hint...}, "ffmpeg": {...}}
_AUTO_ORDER = ("auto-editor", "ffmpeg")
def resolve_engine(requested="auto") -> str              # copy the ai_mask pattern
def keep_ranges(source, *, engine="auto", threshold_db=-30.0, min_silence=0.5, margin=0.2) -> tuple[str, list[tuple[float, float]], float]
        # -> (engine_used, ranges, source_duration)
def build_cut_filter(ranges, *, has_video: bool, has_audio: bool) -> str   # pure
def render_keep_ranges(source, ranges, output_path) -> dict   # renders given ranges; reused by prompt 38
def remove_silence_file(source, output_path, *, engine="auto", threshold_db=-30.0,
                        min_silence=0.5, margin=0.2, dry_run=False) -> dict
```

`remove_silence_file` = `keep_ranges(...)` + `render_keep_ranges(...)`.
Keep `render_keep_ranges` public and independent of silence detection:
prompt 38 (text-based editing) calls it with its own ranges.

- **auto-editor engine:** `run_v3`, then `keep_ranges_from_v3`.
  - `min_silence` maps to nothing directly. auto-editor's nearest knob is
    `--margin`. Document that `min_silence` is ignored by this engine; do not
    invent a mapping.
  - "Available" means the package is installed **and** `resolve_binary()`
    is not None. Otherwise, `auto` falls back to ffmpeg.
- **ffmpeg engine** (no dependency):
  - `adapters/ffmpeg/silence.detect_silence(source, threshold_db, min_duration=min_silence)`,
    then `pipelines/timeline_audio.invert_silence(silences, 0, duration)`,
    then pad each kept range by `margin` on both sides, clamped to
    `[0, duration]`, then `timeline_audio.merge_intervals`.
  - Note: the plan says to "expose `adapters/ffmpeg/audio.remove_silence` as
    the fallback". Do **not** use it for video. It passes `-vn` and drops
    the picture, and it only trims the start and end unless `trim_middle` is
    set. Record this deviation in the report.
  - Wire `remove_silence` in only if you also handle audio-only input
    cleanly. Optional; skip it by default.
- Get the duration from `adapters/ffmpeg/probe.probe_media(source).duration`.
  If it is zero or the probe fails, return `error_type="media_unreadable"`.
- `build_cut_filter`, per range `i`:
  - video: `[0:v]trim=start=S:end=E,setpts=PTS-STARTPTS[v{i}]`;
  - audio: `[0:a]atrim=start=S:end=E,asetpts=PTS-STARTPTS[a{i}]`;
  - then `concat=n=N:v={1|0}:a={1|0}[outv][outa]`.
  - Use `seconds` with 6 decimal places.
  - No paths go in the filtergraph, so `escape_filter_path` is not needed.
  - Above 500 ranges, raise `ValueError("too many ranges ...")` rather than
    building a huge argv.
- `render_keep_ranges` (and so `remove_silence_file`):
  - `assert_not_protected(output_path)`; refuse `output_path == source`;
  - refuse zero keep-ranges (`error_type="invalid_input"`, "the whole file
    is silent at this threshold");
  - call `run_ffmpeg(["-filter_complex", f, "-map", "[outv]", "-map", "[outa]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac"], input_path=source, output_path=output_path)`,
    dropping the video or audio maps and codecs when that stream is absent;
  - return `{success, engine, source, output_path, keep_ranges, kept_seconds, removed_seconds, source_duration}`;
  - on failure, call `cleanup_partial_output`.

### 4. Tool: `edit_mcp/server/bundles/media_remove_silence.py`

`media_remove_silence(source: str, output_path: str, engine: str = "auto", threshold_db: float = -30.0, min_silence: float = 0.5, margin: float = 0.2) -> dict`

- This is a bare-file tool that leads with `source`. `output_path` is
  required. If it is empty, return `invalid_input` with the suggestion to
  give a path outside `media/raw/`.
- Validate before any work:
  - the source exists (`missing_file`);
  - the engine name (`invalid_input`);
  - `threshold_db < 0`, `min_silence > 0`, `margin >= 0`, all finite
    (`nonfinite_guard`).
- `EngineUnavailable` maps to `missing_dependency("auto-editor", hint)`, and
  `AutoEditorError` maps to `operation_failed` with a one-line cause.
- Map pipeline results with `error_from_pipeline_result`.
- Also add `media_silence_keep_ranges(source, engine="auto", threshold_db=-30.0, min_silence=0.5, margin=0.2)`.
  It is analysis-only and returns `{engine, keep_ranges, source_duration}`.
  This exposes the cut list without rendering, and prompt 13 builds on it.
  Keep both tools in the same module.

### 5. Tests

- **Unit** (`tests/unit/test_silence_cut.py`, no binaries):
  - `keep_ranges_from_v3` on the exact JSON above (inline it) gives
    `[(0.0, 1.7), (3.3, 5.0)]`.
  - An NTSC timebase `"30000/1001"` gives exact fractional seconds.
  - `v` empty falls back to `a`.
  - A `speed != 1` clip raises.
  - `build_command` contains `--export v3`, `--progress none`, `--no-open`,
    and `audio:threshold=0.0316...` for -30 dB.
  - `build_cut_filter` for 2 ranges is an exact string, and its `v=0`
    variant works for audio-only input.
  - `resolve_engine("auto")` falls back to ffmpeg when `resolve_binary`
    returns None (monkeypatch it).
  - The tool refuses an empty `output_path` and an `output_path` under
    `<tmp>/media/raw/`.
- **Integration** (`tests/integration/test_silence_cut_smoke.py`, `requires_ffmpeg_ffprobe`).
  For `engine="ffmpeg"`, and for `engine="auto-editor"` under `requires_auto_editor`:
  - run `media_remove_silence` on `test_audio_with_silence.mp4`;
  - ffprobe the output: the duration must be **between 3.0 and 3.8 s** (the
    source is 5.0 s and 2.0 s is silent; the margins add back about 0.4 s);
  - there must be both a video and an audio stream;
  - the `volumedetect` `mean_volume` of the output must be **above -40 dB**
    and higher than the source's mean volume, because the silence was removed;
  - run `silencedetect` (`n=-40dB:d=0.5`) on the output and expect **no**
    silence of 0.5 s or more;
  - the two engines' keep-ranges agree within 0.15 s per edge.

  Add the same checks for an audio-only input. Make an mp3 or wav with
  `make_test_clip(kind="tone")`, concatenated with `anullsrc` silence, using
  ffmpeg in the test. The output must have no video stream.

  CLAUDE.md requires adapter integration tests "in
  `tests/integration/test_audio_ffmpeg_smoke.py` (or analogous)". This new
  file is the analogue; reference it in the module docstring.

## Acceptance criteria

- `media_remove_silence` works with **no** auto-editor installed (ffmpeg engine), and with it installed (auto-editor engine).
- The fixture output is 3.0-3.8 s long, keeps both streams, and has no silence of 0.5 s or more.
- Every subprocess has `timeout=`. No auto-editor kdenlive export is used anywhere.
- `wvb doctor` shows `silence_cut_auto_editor`. `docs/capabilities.md` is regenerated.

## Do NOT

- Do not import or parse auto-editor's `--export kdenlive`/`premiere`/`resolve` outputs. An optional experiment is allowed below, but it is report-only.
- Do not let the adapter download the binary implicitly.
- Do not modify `adapters/ffmpeg/audio.remove_silence` or `media_segment_at_silence`.
- Do not write outputs next to the source by default, or ever into a protected tree.
- Do not add or rename an `ff-*` skill.

## Optional experiment (report only, no code)

Run `auto-editor <fixture> --export kdenlive -o /tmp/ae.kdenlive`. Then open
it headless with `xvfb-run -a kdenlive --render /tmp/ae.kdenlive /tmp/ae.mp4`
and `melt /tmp/ae.kdenlive -consumer null: terminate_on_pause=1`. Record
whether each loads. Compare it against CLAUDE.md hard rules 1-9 and list the
violations. This answers the open question in
`vault/Research/Kdenlive Automation Architecture and Tool Pairing.md` (line ~84).
Add the answer there.

## When done

- Add a vault note, `vault/wiki/auto-editor-cut-list.md`, covering:
  - the v3 schema and units;
  - the `.v3` extension quirk;
  - the binary download on first run;
  - the threshold conversion;
  - why the kdenlive export is not imported.
- Add a short section on removing silence from a file to
  `docs/video-editing-guide/10-audio-production.md`.
- Mark the Phase 2 adapter and `media_remove_silence` bullets done in the expansion plan.
- Run `wvb capabilities --markdown > docs/capabilities.md`.
- Report in the shared format. Include output durations and mean volumes per engine, the keep-ranges from both engines, and the auto-editor version used.
