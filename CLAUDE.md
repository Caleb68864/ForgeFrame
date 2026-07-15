# ForgeFrame -- Workshop Video Brain

## Conventions

### Skill Naming
All skills MUST be prefixed with `ff-` (e.g., `ff-video-idea-to-outline`, not `video-idea-to-outline`). This ensures all ForgeFrame skills group together in the `/` autocomplete menu.

### Tool Parameter Naming
- **New tools use `clip_index`** (not `clip`) for the clip-index-within-a-track
  parameter. The live registry has a legacy split -- 56 older effect/mask/composite
  tools use `clip`, 18 newer clip-editing tools use `clip_index` -- for the same
  concept. This is documented, deliberate debt: renaming the 56 positionally would
  break every caller for zero functional gain, so **no renames** (consistency
  passes 2-4 verdict). If a future unification is ever justified it must go through
  a `@param_alias` shim (`clip` <-> `clip_index`), never a positional break. Until
  then: author new tools with `clip_index` so the newer convention wins by accretion.
- Prefer `workspace_path` as the first parameter (177/201 tools do); tools that
  operate on a URL / library / bare file / name legitimately lead with that instead.

### Project Structure
- Plugin marketplace root: `.claude-plugin/marketplace.json`
- Plugin directory: `workshop-video-brain/`
- Skills: `workshop-video-brain/skills/ff-*/SKILL.md`
- Python source: `workshop-video-brain/src/workshop_video_brain/`
- Tests: `tests/unit/`, `tests/integration/`
- Layering (enforced by `tests/unit/test_module_boundaries.py`, see ADR 005):
  `core < edit_mcp.adapters < edit_mcp.pipelines < production_brain.{skills,notes}
  < edit_mcp.server < app`.

### MCP Tool Modules (auto-discovered)
A new tool is a **new file**, never an edit to a shared registry. Both tool
packages are `pkgutil`-auto-discovered on import, so dropping a module in either
one registers its `@mcp.tool()` functions with zero shared-file edits:
- **`edit_mcp/server/bundles/<x>.py`** -- one module per feature/effect
  (single-tool shells). Preferred home for a new self-contained tool.
- **`edit_mcp/server/tools/<x>.py`** -- grouped multi-tool domain modules
  (e.g. `clips_nle`, `transitions`). Also auto-discovered; it additionally
  preserves a historical re-export surface via PEP 562 `__getattr__`.
Both layers are thin **shells** (validate -> snapshot -> call a pipeline ->
envelope); real logic lives in `edit_mcp/pipelines/` and `edit_mcp/adapters/`.
`_`-prefixed modules are skipped by discovery (use for shared helpers).

### Authoring a New MCP Tool (checklist)
1. **Logic in a pipeline/adapter, not the shell.** Put pure logic in
   `edit_mcp/pipelines/<x>.py` (or `adapters/` for ffmpeg/ffprobe/melt). The
   `bundles/`/`tools/` module is a thin shell only.
2. **Drop-in module.** Create `edit_mcp/server/bundles/<x>.py` (or add to a
   `tools/` domain module) with `@mcp.tool()` -- auto-discovery registers it; do
   not touch any `__init__.py`.
3. **Error contract (`server/errors.py`).** Put `@tool_guard` *directly under*
   `@mcp.tool()` (the outer backstop -> `operation_failed`, one-line cause, full
   traceback to the log, never the payload). Import and return **only the
   specific** constructors you use -- `missing_file`, `invalid_index`,
   `bad_json_param`, `missing_binary`, `corrupt_project`, `media_unreadable`,
   `not_found`, `invalid_input`, `operation_failed` -- not the whole vocabulary.
   Catch `ProjectParseError` explicitly -> `corrupt_project` before any generic
   `except`. Never a silent fake success. Envelope is `{"status", "message"/"data"}`
   via `tools_helpers._ok`/`_err`. Message/suggestion voice: see
   `docs/research/2026-07-03-hardening/error-contract.md`.
4. **Canonical order for a timeline-affecting tool:**
   **parse -> validate -> snapshot -> mutate -> serialize.** Validate inputs
   (workspace, indices, JSON) and take the safety snapshot *before* writing;
   surface the post-write `snapshot_id` in the `_ok` payload.
5. **Reuse the canonical helpers, don't re-roll:**
   - `edit_mcp/pipelines/_common.py` -- `seconds_to_frames` (the one half-up
     converter), `seconds_to_mmss`, the three filter-XML builders, unit/text/DSP
     primitives.
   - `edit_mcp/server/tools_helpers/` (package) -- `_ok`/`_err`,
     `_validate_workspace_path`/`_require_workspace`, `latest_project`/
     `_load_latest_project`/`_save_patched`, `apply_simple_effect`,
     `find_source_or_latest`.
   - `adapters/kdenlive/patcher` (intents) + `serializer` for project mutation;
     `adapters/ffmpeg/probe` for ffprobe. Never hand-roll `ET`/ffprobe argv in a
     shell module.
6. **Test with `tests/_testkit.py`** (`unwrap`, `call_tool`, `assert_registered`,
   `make_test_clip`, the hermetic `*_project` builders, `requires_*` skip marks).
   A **timeline-affecting** tool needs an **external render proof** under
   `tests/integration/external/` (real `melt`, `color:`-producer builders,
   auto-`render_retry`) verifying pixels/acceptance -- not just a dict assertion.
7. **Guide note in the vault.** Document the tool/effect behaviour in the
   video-editing guide / vault research notes so it is discoverable to users.

### Safety Rules
- Never overwrite files in `media/raw/` or `projects/source/`
- Always create snapshots before writing project files
- Obsidian section boundaries: `<!-- wvb:section:name -->` ... `<!-- /wvb:section:name -->`
- Frontmatter updates merge, never overwrite unrelated keys

### Testing
- Run all tests: `uv run pytest tests/ -v`
- Dead-code check: `uvx ruff check --select F401,F841` (F-level only). Clean state
  is **zero** except the deliberate `adapters/kdenlive/patcher.py` compatibility
  shim (documented re-export block; ~38 F401 are intentional) and a handful of
  test-side `result = tool(...)` call-for-side-effect locals. Do not "fix" the
  patcher shim.
- Python 3.12+ required
- `pytest` + `pytest-cov` + `pillow` live in the `test` dependency-group and are
  synced by default (`[tool.uv] default-groups = ["dev", "test"]` in the root
  `pyproject.toml`). Run `uv sync` after changing groups so `uv run pytest`
  resolves the in-venv `pytest`/`fastmcp` instead of a `~/.local` fallback.
- Two `tests/integration/test_ai_mask_tool.py` cases need the optional `ai-mask`
  extra: `uv pip install rembg onnxruntime` (or `uv pip install -e '.[ai-mask]'`).
  It is intentionally NOT in the default sync (rembg pulls a heavy transitive
  stack); without it those two tests fail with `EngineUnavailable`.

### CI
- `.github/workflows/tests.yml` runs on push to `main` and every pull_request.
  Two jobs: `unit` (`uv run pytest tests/unit -q`, no system deps, fast gate)
  then `full` (`uv run pytest tests/ -q`) which `apt-get install`s
  `melt ffmpeg frei0r-plugins` so the `tests/integration/external/` melt/ffprobe
  oracle tier runs instead of self-skipping. Missing optional MLT modules (e.g.
  `opencv.tracker`) degrade gracefully via `melt_has_service`.
- ai-mask decision: CI does `uv pip install rembg onnxruntime` in the `full` job
  so the rembg-gated case executes rather than skips (CPU-only, ~200 MB). Note:
  those cases are `skipif`-gated, so they SKIP (not fail) when rembg is absent --
  the suite is green either way; installing it just exercises the real engine.

## Kdenlive XML serialization

The `.kdenlive` files this project produces target **Kdenlive 25.x / MLT 7.x**. The format is much stricter than a flat MLT XML — getting it wrong yields silent "Project corrupted. Clip ... not found in project bin" errors.

Detailed notes (one concept per page) live in `vault/wiki/`:
- `kdenlive-25-document-shape.md` — full structural contract
- `kdenlive-uuid-vs-control-uuid.md` — the most important trap (cost 3 iteration rounds)
- `kdenlive-twin-chain-pattern.md` — every avformat clip needs two `<chain>` elements
- `kdenlive-per-track-tractor-pattern.md` — per-track tractor + audio filter wiring
- `kdenlive-title-card-pattern.md` — editable titles (`kdenlivetitle` + `xmldata`)
- `kdenlive-cross-dissolve-pattern.md` — stacked-track dissolves; `a_track < b_track` always; direction via `reverse`
- `kdenlive-image-and-qtblend-pattern.md` — image producers + Ken Burns transform filter (entry-local keyframes)
- `kdenlive-clip-speed-pattern.md` — clip speed via timewarp producer (`PlaylistEntry.speed`)
- `kdenlive-bin-loader-source-pointers.md` — exact Kdenlive C++ files/lines for load checks
- `kdenlive-not-all-avfilter-shapes-registered.md` — `avfilter.crop`, `avfilter.curves`, `avfilter.boxblur` are NOT in Kdenlive's effect registry; substitute native MLT or frei0r equivalents
- `kdenlive-frei0r-curves-all-numbered-props.md` — `frei0r.curves` reads numbered props 1-15 at render time; setting only the ones referenced by `kdenlive:curve` flatlines the curve to white
- `kdenlive-color-producer-pattern.md` — MLT `color` producer needs `resource=0xRRGGBBAA` hex; named colours render as black
- `kdenlive-producer-length-must-cover-all-uses.md` — when one media producer is reused at multiple in-points (audio crossfade, multi-region selects), `length` must cover the largest out-point or Kdenlive silently drops the over-range entry
- `kdenlive-lumakey-threshold-tuning.md` — lumakey threshold must straddle a luma boundary actually present in the source clip
- `kdenlive-smoke-test-visible-values.md` — smoke parameter values must produce an unambiguously visible effect, not just a technically-correct subtle one
- `kdenlive-smoke-verification-checklist.md` — manual-review checklist for every smoke output (what to look for in Kdenlive 25.08.3)
- `golden-fixture-testing.md` — testing strategy without launching Kdenlive

### Hard rules (read before editing the serializer)

1. **`kdenlive:uuid` belongs ONLY on the main sequence tractor.** Putting it on a `<chain>` or `<producer>` makes Kdenlive's bin loader skip the entry. Use `kdenlive:control_uuid` for media instead. The main sequence carries *both* `kdenlive:uuid` and `kdenlive:control_uuid` (same value).
2. **Every avformat media file emits two `<chain>` elements** — a timeline twin (`mlt_service=avformat-novalidate`) referenced by playlist entries, and a bin twin (`mlt_service=avformat`, `kdenlive:kextractor=1`, `kdenlive:monitorPosition=0`) referenced by `main_bin`. They share `kdenlive:control_uuid` and `kdenlive:id`. Both twins carry `kdenlive:kextractor=1`.
3. **Each track is its own `<tractor>`** wrapping a content playlist plus an empty `*_kdpair` playlist. Audio track tractors carry `volume`/`panner`/`audiolevel` filters with `internal_added=237`.
4. **Profile names must be canonical** when they exist (`atsc_1080p_2997` for 1920×1080 @ 30000/1001). Anonymous names trigger a "non standard framerate" warning.
5. **`<entry>` `out` attribute on `main_bin` references must be `length-1`**, not `0`. Zero-span entries are rejected.
6. **Resource paths use forward slashes** even on Windows. Backslashes confuse Kdenlive's bin loader.
7. **Every timeline `<entry>` carries `<property name="kdenlive:id">N</property>`** matching the bin clip's integer id. Without it the timeline parser can't resolve the entry to its bin clip.
8. **The sequence's `<track producer="black_track">` has NO `hide` attribute.** Adding `hide="video"` makes Kdenlive consider the sequence unrecoverable.
9. **User clip `kdenlive:id` integers start at 4.** 2 is reserved for the "Sequences" bin folder, 3 for the project's main sequence; collisions corrupt the project.
10. **Title cards use `mlt_service=kdenlivetitle`** with an `xmldata` property holding a `<kdenlivetitle>` document; `kdenlive:clip_type=2` (not 6); `font=` must name a font installed on the host (Windows: `Segoe UI`, Linux: `DejaVu Sans`).
11. **Effect-prefix dispatch is not uniform.** Kdenlive's effect registry recognises *most* `avfilter.X` services but not all — `avfilter.crop`, `avfilter.curves`, and `avfilter.boxblur` are flagged as missing on load and removed. Substitute native MLT (`crop`, `box_blur`) or frei0r (`frei0r.curves`) equivalents. When in doubt, find the upstream `*.kdenlive` test fixture and copy the service id and full property set verbatim — do not assume an `avfilter.X` will work just because adjacent ones do.
12. **`avfilter.huesaturation` has a silent gate**: `av.strength` defaults to 0 and gates ALL hue/saturation/intensity output. Set `av.strength=1` explicitly or the filter loads, the panel displays your values, and playback shows zero effect.
13. **`frei0r.curves` reads numbered props 1-15 at render**, not the `kdenlive:curve` string. Setting only the props your curve string references (e.g. 8/9/10/11) flatlines the curve to white because the unset higher-numbered props are read as zeros. Copy ALL 15 numbered props verbatim from a working upstream reference.
14. **When a media producer is reused at multiple in-points** (audio crossfade, speed ramps, multi-region selects), override `producer.properties["length"]` to cover the maximum out-point of any referencing entry. Otherwise Kdenlive silently drops the over-range entry on load.

### Files

- Serializer (E-shape, verified against Kdenlive 26.04): `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/serializer.py`
- Parser (handles legacy + v25/E-shape): `.../kdenlive/parser.py`
- Patcher: `.../kdenlive/patcher.py` is a compatibility shim; the intent logic that seeds chain properties on clip insert lives in `.../kdenlive/patcher_intents.py`
- Reference fixture: `tests/fixtures/kdenlive_references/single_clip_kdenlive_native.kdenlive`
- Structural tests: `tests/unit/test_serializer_bin.py`, `tests/unit/test_kdenlive_parser.py`
- Bin round-trip: `tests/integration/test_kdenlive_bin_roundtrip.py`

### When Kdenlive rejects a file

1. Copy the **exact** error message from Kdenlive's dialog.
2. Grep the [KDE/kdenlive source](https://invent.kde.org/multimedia/kdenlive) for the literal English text — it's in an `i18n(...)` call.
3. Read the function emitting the error to find the precise condition.
4. Compare your output's relevant element/property against the reference fixture.
5. Fix, run `tests/unit/test_serializer_bin.py`, regenerate the smoke output, re-open in Kdenlive.

This loop is dramatically faster than guessing.

## ffmpeg subprocess hygiene

All ffmpeg subprocess calls in `adapters/ffmpeg/*` and `adapters/stt/whisper_engine.py` must pass `timeout=` to `subprocess.run`. Without timeouts, the MCP server blocks indefinitely on UHD proxy generation or Whisper transcription, and the client RPC times out. Existing timeouts: 600s for proxy/runner, 300s for whisper extraction and silence detection. Catch `subprocess.TimeoutExpired` and clean up partial outputs.

### Audio adapter rules (`adapters/ffmpeg/audio.py`)

1. **Every audio function must pass `-vn`** to `run_ffmpeg`. Without it, video-input -> audio-output (mp4 -> wav) fails because ffmpeg tries to copy the video stream into a container that can't hold it.
2. **ffmpeg filter syntax uses `=` between the filter name and its first option**, then `:` between subsequent options. `silenceremove=start_periods=1:start_duration=0.5` is correct; `silenceremove:start_periods=1:...` is a parse error.
3. **`normalize_audio` is single-pass loudnorm** and won't hit the LUFS target accurately (typically off by 2-4 LU). For broadcast-conformant normalization, the function needs a two-pass rewrite. See `vault/wiki/ffmpeg-audio-adapter-bugs.md`.

### Testing requirement

Any new ffmpeg adapter function MUST have an integration test in `tests/integration/test_audio_ffmpeg_smoke.py` (or analogous) that:
- Runs against a real fixture (audio fixtures live in `tests/fixtures/media_generated/`).
- Asserts the output exists and is non-empty.
- Where a parameter has a measurable target (LUFS, sample rate, duration), probes the output to confirm the target was hit -- "ffmpeg returned 0" is not sufficient.

The audio fixtures available today are `music_cinematic_short.mp3` (full-band stereo music) and `test_audio_with_silence.mp4` (mono with intentional silence gaps). `greenscreen_reporter_720.mp4` is video-only -- it has NO audio stream and cannot be used as an audio fixture.
