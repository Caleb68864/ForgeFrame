# Prompt 11: scene-detection tools: engine parameter, `media_split_scenes`, scene guides

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not repeated here.

## Summary

Prompt 10 added the engine layer. In `pipelines/scene_detect.py` it added
`resolve_engine`, `scan_cuts(source, *, engine, threshold, detector,
detector_threshold, min_scene_seconds, start_seconds, end_seconds)` returning
`(engine_used, hits)`, and engine-aware `detect_scenes`. It also added a
`scan=` injection hook on `adapters/ffmpeg/scene.detect_scene_changes`.
**Read prompt 10's diff before starting.** If any of those names differ, use
the real names and say so in the report.

This prompt exposes the engines to users:
1. an `engine` parameter on the existing consumers;
2. a new bare-file tool, `media_split_scenes`, that writes one file per shot;
3. a new tool that turns detected cuts into **guides on a Kdenlive timeline**.

Source: `docs/plans/2026-10-13-media-mcp-expansion.md` Phase 1, "Consumers".

Paths are under `workshop-video-brain/src/workshop_video_brain/` unless
they start with `tests/`, `docs/` or `vault/`.

## Steps

### 1. Engine parameter on existing consumers

Add `engine: str = "ffmpeg"`, `detector: str = "content"` and
`detector_threshold: float | None = None` to the three consumers below.
Append the new parameters at the end; never reorder. **The default stays
`"ffmpeg"`**, so current outputs and tests do not change. Document `"auto"`
in each docstring: it prefers PySceneDetect when the `scene-detect` extra is
installed.

1. `clips_detect_scenes` (`edit_mcp/server/bundles/scene_detect.py`, ~line 32):
   - Pass the new parameters through to `detect_scenes`.
   - A pipeline `error_type="missing_dependency"` result must become
     `missing_dependency("scenedetect", "<install hint>")`. Check that
     `bundles/_pipeline_errors.error_from_pipeline_result` already maps it,
     and add the mapping if not.
   - An unknown engine must return `invalid_input` before any work.
   - Add `engine` to the report JSON.
2. `research_detect_scenes` (`edit_mcp/server/tools/research_media.py`, ~line 176):
   - When `engine` resolves to `pyscenedetect`, call `detect_scene_changes(..., scan=<a function wrapping pipelines.scene_detect.scan_cuts with engine="pyscenedetect" and the detector args>)`.
     The tool layer may import pipelines. The adapter must not.
   - Catch `EngineUnavailable` and return `missing_dependency`.
   - Catch prompt 10's `SceneDetectError` and return `media_unreadable`.
   - Add `"engine"` to the `_ok` payload.
3. Visual-research candidates (`edit_mcp/pipelines/visual_research/candidates.py`, ~line 92):
   - Add `engine: str = "ffmpeg"` to `_SceneDetectionConfig` in
     `core/models/visual_research.py` (~line 167).
   - Pre-existing bug: `generate_candidates` ignores
     `config.scene_detection.threshold` and `.min_scene_length_seconds`. It
     calls `detect_scene_changes` with defaults. Pass
     `threshold=config.scene_detection.threshold`,
     `minimum_gap_seconds=config.scene_detection.min_scene_length_seconds`
     and the engine scan hook.
   - Defaults are 0.3 and 1.0, the same as the adapter defaults, so default
     behaviour is unchanged. Say so in the report.

### 2. Pipeline: `edit_mcp/pipelines/scene_split.py`

Pure planning plus one ffmpeg call per shot:

```python
def shot_ranges(cuts: list[float], duration: float, min_shot_seconds: float = 0.5) -> list[tuple[float, float]]
def build_shot_command_args(start: float, end: float, *, reencode: bool, has_video: bool, has_audio: bool) -> tuple[list[str], list[str]]
def split_scenes(source: Path, output_dir: Path, *, engine="auto", threshold=0.4, detector="content",
                 detector_threshold=None, min_shot_seconds=0.5, reencode=True, dry_run=False) -> dict
```

`shot_ranges`:
- builds `[0, c1), [c1, c2), ..., [cn, duration)`;
- merges any shot shorter than `min_shot_seconds` into its predecessor (the
  first shot merges forward);
- drops cuts at or below 0 and at or above `duration`;
- returns an empty list for `duration <= 0`.

`build_shot_command_args` returns `(pre_input_args, args)` for `run_ffmpeg`:
- `pre_input_args = ["-ss", f"{start:.3f}"]`;
- `args = ["-t", f"{end-start:.3f}", "-map", "0:v:0?", "-map", "0:a:0?"]`;
- if `reencode`, also `-c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p -c:a aac`;
- otherwise `-c copy`. Stream copy cuts on keyframes. Document that, as
  `pipelines/silence_segment.py` does.

`split_scenes`:
1. Validate `output_dir` with `core/utils/paths.assert_not_protected(output_dir, "scene split output")`.
   This refuses `media/raw/` and `projects/source/`, so files are never
   written beside a source that lives in a protected tree. Then `mkdir(parents=True, exist_ok=True)`.
2. Probe with `adapters/ffmpeg/probe.probe_media` to get the duration, fps
   and stream presence. If the file has no video stream, return
   `success=False, error_type="media_unreadable"`.
3. Call `scene_detect.scan_cuts(...)` to get the cuts, then `shot_ranges(...)`.
4. For each range, call
   `run_ffmpeg(args, input_path=source, output_path=output_dir / f"{source.stem}_shot_{i:03d}{source.suffix or '.mp4'}", pre_input_args=..., timeout=DEFAULT_TIMEOUT_SECONDS)`.
   - Use `.mp4` when re-encoding a non-mp4 container that cannot hold H.264.
     Keep it simple: re-encode always writes `.mp4`.
   - On a failed shot, delete the files already written in this call
     (`bundles/_pipeline_errors.cleanup_partial_output`) and return
     `success=False, error_type="operation_failed"` with the ffmpeg stderr tail.
5. Return:
   `{"success", "source", "output_dir", "engine", "cuts": [...], "shots": [{"index", "start", "end", "path"}], "shot_count"}`.

### 3. Tool: `edit_mcp/server/bundles/media_split_scenes.py`

`media_split_scenes(source: str, output_dir: str, engine: str = "auto", threshold: float = 0.4, detector: str = "content", detector_threshold: float | None = None, min_shot_seconds: float = 0.5, reencode: bool = True) -> dict`

- This is a bare-file tool: it leads with `source` and takes no workspace.
  `output_dir` is required. An empty value returns `invalid_input` with the
  suggestion "pass a folder outside media/raw".
- Validate in this order, all before any ffmpeg work:
  - the source exists (`missing_file`);
  - the engine name (`invalid_input`);
  - `min_shot_seconds > 0` and finite (`nonfinite_guard` / `invalid_input`).
- A `ProtectedPathError` from the pipeline becomes `invalid_input`. Check
  that `tool_guard` already does this; CLAUDE.md says it does.
- Map the result through `error_from_pipeline_result`.
- No snapshot, because no project is touched.
- `@mcp.tool()`, then `@tool_guard`, then a thin shell, as in
  `bundles/silence_segment.py`.

### 4. Scene cuts as timeline guides

Existing machinery:
- the `AddGuide` intent (`core/models/timeline.py:55`, applied in
  `adapters/kdenlive/patcher_intents.py` ~line 326);
- `pipelines/guides.add_guide(project, at_seconds, label, category)` (~line 81);
- `bundles/guides.py` `guide_add`.

The serializer writes guides to `kdenlive:sequenceproperties.guides` and
`kdenlive:docproperties.guides` (`serializer.py` ~740-800).

Pipeline: add to `pipelines/guides.py`, or a new `pipelines/scene_guides.py`
if `guides.py` would need a pipelines import cycle:

```python
def cut_positions_on_timeline(project, source_path: Path, cuts_seconds: list[float]) -> list[int]
```

For every real entry, on every track, whose producer `resource` resolves to
the same file as `source_path`:
- compare `Path(...).resolve()`, and also check the producer's
  `properties["resource"]`;
- map each cut inside the entry's `[in_point, out_point]` (source frames,
  using `pipelines/_common.seconds_to_frames` at the project fps) to the
  timeline frame `entry_start + (cut_frame - in_point)`;
- compute `entry_start` with `pipelines/clip_place.entry_length`, summed over
  the preceding entries, blanks included.

Return the sorted, de-duplicated frames. A source that is not on the
timeline gives `[]`.

Tool: `guide_add_scene_cuts(workspace_path: str, source: str, project_file: str = "", engine: str = "ffmpeg", threshold: float = 0.4, detector: str = "content", detector_threshold: float | None = None, label_prefix: str = "Scene", category: str | None = None) -> dict`.
Put it in a new module `bundles/scene_guides.py`, not inside `guides.py`; one
module per feature. Order:
1. parse the project (an explicit `project_file`, else
   `tools_helpers.latest_project` / `_load_latest_project`; catch
   `ProjectParseError` and return `corrupt_project`);
2. validate (source exists, engine);
3. detect (`scan_cuts`);
4. map positions;
5. if there are no positions, return `_ok` with `guides_added: 0` and a
   `note`, without writing;
6. otherwise apply one `AddGuide` per position via `patch_project`, with
   labels `f"{label_prefix} {n}"`;
7. serialize with `serialize_project`, which snapshots;
8. return `_ok` with `guides_added`, `positions_frames`, `engine` and `snapshot_id`.

Copy `guide_add` for the snapshot calls.

### 5. Tests

- **Unit**:
  - `tests/unit/test_scene_split_plan.py`: `shot_ranges` edge cases (no
    cuts, a cut at 0 or at the end, short-shot merging, unsorted input) and
    `build_shot_command_args` for both modes.
  - `tests/unit/test_scene_guides_mapping.py`: `cut_positions_on_timeline`
    on a hand-built project with two entries of the same source at different
    in-points plus a blank. Assert the exact frames. Include a cut outside
    every entry; it must be dropped.
  - The tools via `call_tool` with the engine monkeypatched to a fake:
    - `media_split_scenes` refuses an empty `output_dir` and an `output_dir`
      under `<tmp>/media/raw/`;
    - an unknown engine gives `invalid_input`;
    - `research_detect_scenes(engine="pyscenedetect")` with the package
      missing gives `missing_dependency`;
    - `clips_detect_scenes` reports include `engine`;
    - `assert_registered("media_split_scenes", "guide_add_scene_cuts")`.
- **Integration** (`tests/integration/test_scene_tools.py`, `requires_ffmpeg_ffprobe`):
  - Run `make_hard_cut_clip(..., with_audio=True)` (prompt 10's testkit
    helper) and `media_split_scenes` with `engine="ffmpeg"`.
  - Expect 2 files. ffprobe durations must be 2.0 s within 0.1 s each. Shot 2
    must have an audio stream.
  - Extract shot 2's first frame (ffmpeg `-frames:v 1` to png in `tmp_path`)
    and check its mean colour is blue-dominant (B > 150, R < 80). Read the
    pixels with Pillow, as `_oracle.mean_color` does.
  - Run the same with `engine="pyscenedetect"` under `requires_scenedetect`.
- **External proof** (`tests/integration/external/test_scene_guides_render.py`, melt):
  - Build a workspace project.
  - Insert the hard-cut clip with `clip_insert` (in-point 0) after a 1 s
    colour clip, or use a `_testkit.sequence_project`-style builder with the
    real clip as the producer.
  - Run `guide_add_scene_cuts`.
  - Expect one guide at timeline frame `25 + 50 = 75` (1 s colour plus 2 s, at 25 fps).
  - Re-parse the file and assert the guide.
  - `_oracle.melt_accepts(project)` returns an `OracleResult`, and it must
    report acceptance. Read the dataclass for the field name.
  - Render frames 74 and 76 with `_oracle.render_frame` and assert they
    differ (`frames_differ`): the guide sits on the visible cut.
  - Every `melt ... -consumer null:` call must include `terminate_on_pause=1`.

## Acceptance criteria

- Existing scene tests pass unchanged, which proves the default is still ffmpeg.
- `media_split_scenes` on the hard-cut clip gives 2 shots of about 2 s each, and shot 2 starts blue.
- The guide from `guide_add_scene_cuts` lands on the exact cut frame on the timeline, not at the source time, and melt accepts the project.
- `docs/capabilities.md` is regenerated and lists both new tools.
- ruff is clean. No unit test needs ffmpeg unless it carries a `requires_*` mark.

## Do NOT

- Do not change default engines to `auto` on existing tools.
- Do not write shot files next to the source by default, and never into `media/raw/` or `projects/source/`.
- Do not hand-roll ffprobe or `ET` in tool shells.
- Do not use `clip`. Any clip-index parameter is `clip_index`; none is needed here.
- Do not edit `bundles/guides.py` beyond what is strictly needed. Prefer the new module.

## When done

- Run `wvb capabilities --markdown > docs/capabilities.md`.
- In the guide, add a short subsection to
  `docs/video-editing-guide/19-forgeframe-skill-reference.md` (or
  `16-social-media-repurposing.md` if it fits better) on splitting a recording
  into shots and marking scene cuts as guides. Add a line to
  `vault/wiki/scene-detection-engines.md`, which prompt 10 created.
- Mark the Phase 1 consumer bullets done in `docs/plans/2026-10-13-media-mcp-expansion.md`.
- Report in the shared format. Include the shot durations, the blue-frame mean colour and the guide frame.
