# Media MCP Expansion Plan (2026-10-13)

Goal: grow ForgeFrame from a Kdenlive-project editor into a full media-editing MCP
(Kdenlive projects **and** raw video/audio/image/text files), adding PySceneDetect,
auto-editor and the MLT Python bindings, and reimplementing the best ideas from
`12bijaya/MCP_Server_Kdenlive`.

Background: `vault/Research/Kdenlive Automation Architecture and Tool Pairing.md`
(Kdenlive has no scripting API; keep XML generation + melt). Not in scope now:
WhisperX, diarization, OpenTimelineIO (undecided).

## Phase 0 — Stabilise the base

- `uv` is not on PATH for the MCP launcher, so the `workshop-video-brain` server
  fails to start (`ENOENT`). Fix the launcher config (absolute uv path or PATH).
- The uncommitted 2026-10-13 reliability work (unified render, jobs, safe writes,
  doctor, guided workflow) says "No tests were added or run". Run the suite, fix,
  commit before layering new features on it.
- Merge the two ffmpeg scene detectors (`adapters/ffmpeg/scene.py` reports the
  threshold as the score and uses a local 300s timeout; `pipelines/scene_detect.py`
  is correct but its docstring says `scdet`) into one engine-dispatching function.
- Kdenlive contract: **decided 2026-10-13 — target Kdenlive 26.x (26.08.2 installed on the dev host)** (the user's
  editing version). The serializer already
  emits the GUI-confirmed 26.04 E shape; next: save native 26.04 reference
  fixtures from the installed Kdenlive, round-trip our output through it, and
  rewrite the CLAUDE.md "Hard rules" (still describing 25.x twin chains) to the
  26.04 contract.

## Phase 1 — PySceneDetect

- `scene-detect` extra (`scenedetect[opencv-headless]`) in both pyproject files.
- `adapters/scenedetect/` engine (content/adaptive/threshold detectors), lazy import.
- `engine="auto|ffmpeg|pyscenedetect"` on `pipelines/scene_detect.detect_scenes`,
  following the `ai_mask.resolve_engine` / `EngineUnavailable` pattern.
- Consumers: `clips_detect_scenes`, `research_detect_scenes`, visual-research
  candidates; new `media_split_scenes` (per-shot files) and scene markers/guides on
  a timeline.
- Doctor row, `requires_scenedetect` mark (find_spec), CI `full` install.

## Phase 2 — auto-editor

- `adapters/autoeditor/` runs the CLI with `--export json` (timeline v3) under
  `ANALYSIS_TIMEOUT_SECONDS`; pipeline converts it to keep-ranges.
  Do **not** import its `--export kdenlive` output (bypasses our serializer rules);
  optionally test it as a compatibility experiment.
- Uses: `media_remove_silence` (bare file → tightened file via ffmpeg concat),
  `timeline_build_jump_cut` (keep-ranges → `.kdenlive` via the selects builder,
  generalised to the source's profile instead of hard-coded 1080p25).
- Also expose the existing unused `adapters/ffmpeg/audio.remove_silence` as the
  no-dependency fallback engine.
- Rename-clash note: the `ff-auto-editor` skill is unrelated (script assembly).

## Phase 3 — MLT Python bindings (out-of-process)

Bindings are system-only (Arch: Python 3.14; Ubuntu 24.04 `python3-mlt`: 3.12),
not on PyPI, absent on Windows/macOS, and segfault on bad handles. So:

- `adapters/mlt/_worker.py` runs under whichever interpreter can `import mlt7`
  (`WVB_MLT_PYTHON`, else venv python, else `/usr/bin/python3`), JSON over stdio,
  with timeouts. `adapters/mlt/engine.py` falls back to the melt CLI.
- Features in value order: (1) post-serialize **load-check** (profile, tracks,
  clip ids/in-out vs model), (2) frame-accurate timeline **thumbnails** without a
  temp render, (3) **per-frame render progress** into job records, (4) in-memory
  **service registry** replacing `melt -query`, rejecting unregistered services
  before write, (5) playlist inspection for parser debugging.
- Doctor row, `requires_mlt_bindings` mark, optional `python3-mlt` in CI `full`.

## Phase 4 — Harvest from 12bijaya (reimplement; repo has no licence)

1. Undo/redo stack + atomic `timeline_batch` with rollback-to-depth, built on the
   existing snapshots.
2. Render progress from melt's `percentage:` log lines (CLI path) + probe before
   reporting done (merge with Phase 3 progress).
3. Applied-effect editing: `effect_param_get/set`, `effect_toggle`, `effect_remove`
   (`clip_index`).
4. melt load-check in `project_validate` (`terminate_on_pause=1`, bounded frames).
5. Trim tools as patcher intents: slip, slide, replace clip, ripple insert.
6. Easing presets baked as dense keyframes; named camera moves (zoom-punch,
   orbit, handheld).
7. `snapshot_diff` (LLM-readable).
8. Beat-synced cuts/zooms/flashes from `music_beat_grid`.
9. External round-trip test of their "one chain per placement" claim vs our rule 14.

Do not import their XML habits (bin ids from 2, no bin twin, no control_uuid on
the main tractor, `dynamictext` titles, non-canonical 29.97 profile, unsorted
dissolve tracks, single-sequence save).

## Phase 5 — General media layer (bare files)

New bare-file tools (lead with `source`/`file_path`, take `output_path`/`output_dir`,
never write into protected trees):

- Video: `media_trim`, `media_concat`, `media_reframe` (9:16/1:1 with
  crop/pad/smart-centre; also render `social_clips` output), `media_speed`,
  `media_rotate_flip`, `media_convert` (expose `convert_format`/`export_compressed`),
  `media_extract_audio`, `media_gif`, `media_thumbnail` (no workspace).
- Audio: `audio_mix_music` with ducking on files, `audio_fade`, file-level
  loudness without a workspace, `audio_waveform_image`.
- Text/transcripts: `transcribe_file` → SRT/VTT/JSON; subtitle file ops
  (shift, merge/split, restyle, convert); **text-based editing** — delete
  transcript words/lines → cut list → file render or `.kdenlive`.
- Images: resize/convert/watermark/overlay on files.
- Generalise `selects_timeline` / `assembly` builders to the source profile.

Each tool follows the CLAUDE.md checklist (pipeline logic, `@tool_guard`,
specific error constructors, `_testkit`, external render proof for
timeline-affecting tools, vault guide note, regenerated `docs/capabilities.md`).
