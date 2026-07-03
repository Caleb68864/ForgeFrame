# ForgeFrame -- Workshop Video Brain

## Conventions

### Skill Naming
All skills MUST be prefixed with `ff-` (e.g., `ff-video-idea-to-outline`, not `video-idea-to-outline`). This ensures all ForgeFrame skills group together in the `/` autocomplete menu.

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
