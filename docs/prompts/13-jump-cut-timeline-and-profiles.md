# Prompt 13: source-matched timeline profiles, then `timeline_build_jump_cut`

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not repeated here.

## Summary

Two parts, done in order.

**Part A.** Every timeline builder hardcodes a 1920x1080 @ 25 fps profile,
and the serializer writes a non-canonical profile name such as
`1920x1080_fps25`, even for standard formats. CLAUDE.md hard rule 4 says a
canonical MLT name (e.g. `atsc_1080p_2997`) must be used when one exists,
otherwise Kdenlive warns about a "non standard framerate". Kdenlive's own
reference files use canonical names
(`tests/fixtures/kdenlive_references/clip_speed_400_native.kdenlive:336` has
`atsc_1080p_2997`, and `audio_mix_upstream_kde.kdenlive:776` has
`atsc_1080p_25`). Part A:
- makes the selects and assembly builders derive the profile from the source media;
- makes the serializer emit canonical names and descriptions.

**Part B.** Add `timeline_build_jump_cut`. It turns prompt 12's keep-ranges
(silence removed) into a `.kdenlive` jump-cut timeline:
- video entries on a video track;
- the matching audio entries on an audio track at the same timeline frames,
  following prompt 02's audio contract;
- an external melt render proof.

Sources: `docs/plans/2026-10-13-media-mcp-expansion.md` Phase 2 (and Phase 5,
"Generalise builders"). Prerequisites: prompt 02 (audio placement) and
prompt 12 (`pipelines/silence_cut.keep_ranges`) must be merged. **Read both
diffs first.** If a name differs, use the real one and report it.

Paths are under `workshop-video-brain/src/workshop_video_brain/` unless
they start with `tests/`, `docs/` or `vault/`.

## Part A: profiles

### A1. The hardcoded sites (verify the line numbers)

- `edit_mcp/pipelines/selects_timeline.py` ~142: `build_selects_timeline`,
  `ProjectProfile(width=1920, height=1080, fps=25.0, colorspace="709")`.
- `edit_mcp/pipelines/assembly.py` ~444-449: `assemble_timeline`, `fps = 25.0`
  plus the same profile line.
- `edit_mcp/pipelines/review_timeline.py` ~139: the same. Treat it the same
  way if the change is mechanical; otherwise list it in the report.
- Callers pass `assets=[]` (`tools/timeline_project.py` ~151, `app/cli.py`
  ~660, `pipelines/guided_workflow.py` ~249, `tools/assembly_titles.py` ~357).
  So the producer `resource` is the clip ref, or `source_path` for assembly,
  and is often a real file path.
- The serializer (`edit_mcp/adapters/kdenlive/serializer.py`) works like this:
  - ~467-480 builds `<profile>` from `project.profile` via `_fps_to_rational` (~131);
  - ~486-489 builds the name `f"{w}x{h}_fps{round(fps)}"`;
  - ~790 writes it as `kdenlive:docproperties.profile`.
- Existing helper: `pipelines/project_profile.match_profile_to_source(path)`
  returns `{width, height, fps_num, fps_den, colorspace}` via `probe_media`.

### A2. Profile from media

In `pipelines/project_profile.py`, add:

```python
DEFAULT_PROFILE = ProjectProfile(width=1920, height=1080, fps=25.0, colorspace="709")
def profile_from_media(paths: Iterable[str | Path]) -> ProjectProfile
```

- It returns the profile of the **first** path that exists and probes with
  a video stream: width and height from the probe, and
  `fps = fps_num / fps_den` from `match_profile_to_source`.
- A NaN or zero fps skips that path. If no path qualifies, it returns a copy
  of `DEFAULT_PROFILE`. This keeps today's behaviour for tests that use fake
  resources.
- It logs at INFO which file decided the profile.

### A3. Builders accept and derive the profile

- Add `profile: ProjectProfile | None = None` (keyword, last) to
  `build_selects_timeline` and `assemble_timeline` (and `build_review_timeline`
  if you include it). When it is `None`, call `profile_from_media(...)` over
  the clip resources in plan order.
- Replace every local `fps = 25.0` with `project.profile.fps`.
- Seconds-to-frames stays `pipelines/_common.seconds_to_frames`.

### A4. Canonical profile names (serializer)

- Add a pure helper:
  `canonical_profile_name(width, height, fps_num, fps_den, progressive=True) -> tuple[str, str] | None`.
  It returns `(name, description)`. Put it in `serializer.py` or a small
  `adapters/kdenlive/profiles.py`.
- Build its table from the MLT profile files on this host:
  `ls /usr/share/mlt-7/profiles/`. Each file has `description`,
  `frame_rate_num/den`, `width`, `height`, `progressive`, and so on. Hardcode
  the table; do not read the system directory at run time, because Windows
  and CI differ. Cover at least:
  - `atsc_720p_{2398,24,25,2997,30,50,5994,60}`;
  - `atsc_1080p_{2398,24,25,2997,30,50,5994,60}`;
  - `qhd_1440p_*`;
  - `uhd_2160p_{2398,24,25,2997,30,50,5994,60}`;
  - `vertical_hd_30`/`vertical_hd_60` (check their dimensions in the file).
  - Copy each `description` verbatim, e.g. `HD 1080p 29.97 fps`.
- The serializer uses the canonical name when one matches, else the current
  anonymous `WxH_fpsN` string. On a match it also sets
  `profile_elem.set("description", description)`; the native fixture has that
  attribute at line 3.
- **Risk:** this changes the output of every project at 1080p25, which is
  most of the tests. Run the unit suite immediately after this step.
  - Expected fallout is limited to tests asserting the old name string; update those.
  - If a golden or structural test compares whole files, update the golden
    file only after confirming the diff is just the name and description.
  - List every test you changed.

### A5. Part A tests

- `tests/unit/test_project_profile_from_media.py`:
  - `profile_from_media` with fake paths gives the default;
  - with `make_test_clip(size=(320, 180), fps=30)` it gives 320x180 at 30;
  - with the 1080p29.97 fixture `tests/fixtures/media_generated/test_clip_1080p2997_5s.mp4`
    it gives fps 30000/1001.
  - Mark it `requires_ffmpeg_ffprobe`.
- `tests/unit/test_canonical_profile_name.py`: 1920x1080 30000/1001 gives
  `atsc_1080p_2997`; 3840x2160 24000/1001 gives `uhd_2160p_2398`; 320x180 30
  gives `None`.
- Add a serializer round-trip assertion: a 1080p29.97 project writes
  `kdenlive:docproperties.profile == "atsc_1080p_2997"` and
  `<profile description="HD 1080p 29.97 fps" ...>`.
- In the `assemble_timeline` tests, a real 320x180@30 clip must produce a
  project whose `<profile>` is 320x180 at 30/1.

## Part B: `timeline_build_jump_cut`

### B1. A lower-level ranges builder

In `edit_mcp/pipelines/selects_timeline.py`, factor out:

```python
def build_ranges_project(source: Path, ranges: list[tuple[float, float]], *, profile: ProjectProfile | None = None,
                         has_audio: bool = True, title: str = "Jump Cut", guides: list[Guide] | None = None) -> KdenliveProject
```

- **Range convention.** Keep-ranges are half-open `[start, end)` in source
  seconds, so `in = seconds_to_frames(start, fps)` and
  `out = seconds_to_frames(end, fps) - 1`. Skip a range if `out < in`.
  - Note: today `build_selects_timeline` sets `out = seconds_to_frames(end)`,
    which is one frame long per entry. Do **not** change that in this prompt
    (it changes existing output); mention it in the report.
- It uses one producer for the source (`resource` = the absolute path, with
  forward slashes per hard rule 6). The serializer derives the rest.
- **Rule 14:** the producer is reused at many in-points. Set
  `producer.properties["length"] = str(max_out + 1)`, or the source's total
  frames if that is larger.
  - If prompt 04 (bin clip ids and ranges) already centralised this in the
    serializer, rely on that instead and say so.
- Video track: entries are back to back, which is what makes it a jump cut.
- Audio track, only if `has_audio`: an identical entry list on the audio
  playlist, so every audio entry starts at the same timeline frame as its
  video twin.
  - This is the builder form of prompt 02's contract: a clip with audio has a
    video entry and an audio entry at the same frame.
  - If prompt 02 introduced a helper for this, or AVSplit groups, use it.
  - If `has_audio` is False, there is no audio entry.
- Optionally add one guide per cut point (timeline frame where two ranges
  meet), labelled `cut N`, controlled by `guides`/a flag. Positions are
  **timeline** frames, not source frames.
  - Note: `build_selects_timeline` currently puts its guides at the
    **source** `in_point` (~line 197). That is a bug when a selects list is
    not source-ordered. Report it; do not fix it here.

### B2. Pipeline entry: `edit_mcp/pipelines/jump_cut.py`

```python
def build_jump_cut(workspace_root: Path, source: Path, *, engine="auto", threshold_db=-30.0,
                   min_silence=0.5, margin=0.2, ranges: list[tuple[float, float]] | None = None,
                   add_cut_guides: bool = False) -> dict
```

1. If `ranges` is None, get them from `silence_cut.keep_ranges(...)` (prompt 12).
2. Probe the source with `probe_media` to get `has_audio` (`channels > 0` or
   `audio_codec`) and the duration.
3. Use `profile_from_media([source])`.
4. Clamp the ranges to `[0, duration]`.
5. `build_ranges_project`, then `serialize_versioned(project, workspace_root, "jump_cut_<slug(source.stem)>")`.
6. Return `{success, kdenlive_path, engine, keep_ranges, kept_seconds, timeline_frames, profile: {width, height, fps}, audio_placed}`.

### B3. Tool: `edit_mcp/server/bundles/jump_cut.py`

`timeline_build_jump_cut(workspace_path: str, source: str, engine: str = "auto", threshold_db: float = -30.0, min_silence: float = 0.5, margin: float = 0.2, keep_ranges_json: str = "", add_cut_guides: bool = False) -> dict`

- `workspace_path` comes first.
- Resolve `source` under the workspace unless it is absolute
  (`pipelines/analysis_common.resolve_under_workspace`).
- If `keep_ranges_json` is given:
  - parse it as `[[start, end], ...]`; on failure return
    `bad_json_param("keep_ranges_json", "[[0.0, 1.7], [3.3, 5.0]]", given)`;
  - validate that the values are finite, `start < end` and sorted;
  - skip detection.
- The order is parse, validate, build, serialize. This tool **creates** a new
  versioned working copy and never overwrites one, so no pre-snapshot is
  needed; the serializer snapshots on overwrite anyway.
- `EngineUnavailable` maps to `missing_dependency`.

### B4. Part B tests

- **Unit** (`tests/unit/test_jump_cut_builder.py`, hermetic, with a fake
  source path and an explicit profile):
  - for ranges `[(0, 1.7), (3.3, 5.0)]` at 30 fps, video entries are
    `(0, 50)` and `(99, 149)`;
  - the audio entries are identical;
  - the cumulative timeline starts are `[0, 51]` on both tracks;
  - producer `length` is at least 150;
  - `has_audio=False` gives no audio entries;
  - `add_cut_guides` gives a guide at frame 51;
  - `keep_ranges_json` errors: bad JSON, unsorted ranges, `start >= end`.
- **External proof** (`tests/integration/external/test_jump_cut_render.py`,
  marks `requires_melt_ffmpeg` / the `melt_bin` fixture):
  1. Create a workspace in `tmp_path` and copy
     `tests/fixtures/media_generated/test_audio_with_silence.mp4` into it,
     **not** under `media/raw` if the tool would write there. It writes only
     `projects/working_copies/`.
  2. Run `timeline_build_jump_cut(..., engine="ffmpeg")`.
  3. Render the whole timeline with `_oracle.render_video(project, out, frames=<timeline_frames>)`.
  4. Assert with `_oracle.probe`:
     - width x height == **320x180** and fps == **30**, proving the profile
       follows the source, not 1080p25;
     - duration within 2 frames of `kept_seconds` (about 3.4 s).
  5. Assert with `_oracle.audio_stats`: RMS **above -40 dB** (not silent; the
     prompt 02 bug was -91 dB).
  6. Run ffmpeg `silencedetect=n=-40dB:d=0.5` on the render: no silence of
     0.5 s or more.
  7. Run `_oracle.melt_accepts(project)`.
  8. Add a second case with the 1080p29.97 fixture (no silence; give it
     `keep_ranges_json="[[0.5, 2.0], [3.0, 4.5]]"`). The rendered fps must be
     29.97 (30000/1001 within 0.01), and the project must contain
     `atsc_1080p_2997`.
  - Every `melt ... -consumer null:` call needs `terminate_on_pause=1`.
- **Kdenlive check** (required, not in pytest): render the first case's
  project with `xvfb-run -a kdenlive --render <project> /tmp/jc_kden.mp4`.
  Record the duration and mean volume next to the melt numbers. Confirm there
  is no "non standard framerate" or "clip not found" message in the output.

## Acceptance criteria

- No builder hardcodes 1920x1080/25 any more. With unknown media they fall back to it.
- Canonical names are emitted for standard formats; the anonymous form is kept otherwise. Unit and full suites are green, and changed tests are listed.
- `timeline_build_jump_cut` renders, in both melt and Kdenlive 26.08, to a source-sized, source-rate, about 3.4 s, non-silent video with no 0.5 s silences.
- Audio entries start on the same timeline frames as their video entries.

## Do NOT

- Do not import auto-editor's `.kdenlive` export, or any other external project file.
- Do not change the dissolve or transition logic, `kdenlive:id` numbering, or the `main_bin` `out`. Those belong to other prompts.
- Do not "fix" `build_selects_timeline`'s out-point or guide-position quirks here. Report them.
- Do not read `/usr/share/mlt-7/profiles` at run time.
- Do not edit `__init__.py` files or add a skill.

## When done

- Add a vault note, `vault/wiki/kdenlive-canonical-profile-names.md`: the table source, rule 4, the `description` attribute, and the fixture evidence. Add a section on jump cuts from silence to `docs/video-editing-guide/11-pacing-storytelling-retention.md`.
- In CLAUDE.md, add the new vault note to the "Detailed notes" list. Do not rewrite the hard rules.
- Mark the Phase 2 `timeline_build_jump_cut` bullet and the Phase 5 "Generalise selects_timeline / assembly builders" bullet done (dated) in the expansion plan.
- Run `wvb capabilities --markdown > docs/capabilities.md`.
- Report in the shared format. Include the melt and Kdenlive duration, RMS and resolution numbers, the list of tests changed by the profile-name switch, and the two `build_selects_timeline` quirks.
