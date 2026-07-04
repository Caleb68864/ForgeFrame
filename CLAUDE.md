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

### Safety Rules
- Never overwrite files in `media/raw/` or `projects/source/`
- Always create snapshots before writing project files
- Obsidian section boundaries: `<!-- wvb:section:name -->` ... `<!-- /wvb:section:name -->`
- Frontmatter updates merge, never overwrite unrelated keys

### Testing
- Run all tests: `uv run pytest tests/ -v`
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
