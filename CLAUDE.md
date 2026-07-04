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
