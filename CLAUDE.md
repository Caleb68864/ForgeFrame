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
