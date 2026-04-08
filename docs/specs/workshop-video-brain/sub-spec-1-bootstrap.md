---
type: phase-spec
master_spec: "../2026-04-08-workshop-video-brain.md"
sub_spec: 1
title: "Bootstrap + Plugin Scaffold"
dependencies: none
date: 2026-04-08
---

# Sub-Spec 1: Bootstrap + Plugin Scaffold

## Scope

Repository structure, Claude Code plugin marketplace manifest, plugin manifest, MCP server definition, Python package setup, config loader, MCP server skeleton with ping tool, 5 stub skills, 4 ADRs, README.

## Interface Contracts

### Provides (to Sub-Spec 2+)

- **Python package structure** at `workshop-video-brain/src/workshop_video_brain/` -- importable module
- **Config loader** at `app/config.py` -- exports `load_config() -> Config` dataclass with fields: `vault_path: str | None`, `workspace_root: str | None`, `ffmpeg_path: str`, `whisper_model: str`, `whisper_available: bool`, `ffmpeg_available: bool`
- **Logging setup** at `app/logging.py` -- exports `setup_logging(workspace_path: str | None) -> logging.Logger`
- **Path resolver** at `app/paths.py` -- exports `resolve_workspace_path(config: Config) -> Path`
- **MCP server instance** at `server.py` -- exports `mcp = FastMCP("workshop-video-brain")` and `def main()` entrypoint
- **Plugin marketplace** at `.claude-plugin/marketplace.json` -- valid marketplace manifest
- **Plugin definition** at `workshop-video-brain/plugin.json` -- valid plugin with 5 skills declared
- **MCP server config** at `workshop-video-brain/.mcp.json` -- valid MCP server definition

### Requires

Nothing -- this is the foundation sub-spec.

## Patterns to Follow

- **FastMCP server pattern:** Use `from fastmcp import FastMCP; mcp = FastMCP("workshop-video-brain")` with `@mcp.tool()` decorators
- **pyproject.toml:** PEP 735 `[dependency-groups]` for dev/test. Hatchling build backend. Entry point: `workshop-video-brain-server = "workshop_video_brain.server:main"`
- **Config:** Use `os.environ.get()` with sensible defaults. Detect tools with `shutil.which()`
- **SKILL.md:** kebab-case name, description under 250 chars, includes WHAT and WHEN trigger phrases
- **Marketplace:** `.claude-plugin/marketplace.json` at repo root with `name`, `owner`, `plugins` array
- **Plugin:** `plugin.json` with `name`, `version`, `description`, `skills` map

## Implementation Steps

### Step 1: Create pyproject.toml

**Create** `pyproject.toml`:

```toml
[project]
name = "workshop-video-brain"
version = "0.1.0"
description = "Local-first video production assistant: Obsidian planning + Kdenlive edit automation"
requires-python = ">=3.12"
license = "MIT"
authors = [{name = "Caleb Bennett"}]
dependencies = [
    "fastmcp>=2.0",
    "pydantic>=2.0,<3",
    "pyyaml>=6.0",
    "jinja2>=3.1",
    "click>=8.1",
]

[project.scripts]
workshop-video-brain-server = "workshop_video_brain.server:main"
wvb = "workshop_video_brain.app.cli:main"

[dependency-groups]
dev = [
    "ruff>=0.4",
    "mypy>=1.10",
]
test = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["workshop-video-brain/src"]

[tool.ruff]
target-version = "py312"
src = ["workshop-video-brain/src"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["workshop-video-brain/src/workshop_video_brain"]
```

### Step 2: Create .env.example

**Create** `.env.example`:

```bash
# Workshop Video Brain Configuration
WVB_VAULT_PATH=          # Path to Obsidian vault (e.g., /home/user/Documents/MyVault)
WVB_WORKSPACE_ROOT=      # Default workspace root for new projects
WVB_FFMPEG_PATH=ffmpeg   # Path to ffmpeg binary (default: ffmpeg in PATH)
WVB_WHISPER_MODEL=small  # Whisper model size: tiny, base, small, medium, large
```

### Step 3: Create plugin marketplace manifest

**Create** `.claude-plugin/marketplace.json`:

```json
{
  "name": "forgeframe",
  "owner": {
    "name": "Caleb Bennett"
  },
  "metadata": {
    "description": "Kdenlive MCP and Video Production Skills for tutorial creators",
    "version": "0.1.0"
  },
  "plugins": [
    {
      "name": "workshop-video-brain",
      "source": "./workshop-video-brain",
      "description": "Local-first video production assistant: Obsidian planning + Kdenlive edit automation for tutorial makers",
      "version": "0.1.0",
      "author": "Caleb Bennett",
      "license": "MIT",
      "keywords": ["kdenlive", "video", "mcp", "obsidian", "tutorial", "production"],
      "category": "media"
    }
  ]
}
```

### Step 4: Create plugin.json

**Create** `workshop-video-brain/plugin.json`:

```json
{
  "name": "workshop-video-brain",
  "version": "0.1.0",
  "description": "Local-first video production assistant combining Obsidian planning with Kdenlive edit automation for MYOG, camping, garage, and DIY tutorial videos",
  "author": "Caleb Bennett",
  "license": "MIT",
  "skills": {
    "ff-video-idea-to-outline": {
      "path": "skills/ff-video-idea-to-outline"
    },
    "ff-tutorial-script": {
      "path": "skills/ff-tutorial-script"
    },
    "ff-shot-plan": {
      "path": "skills/ff-shot-plan"
    },
    "ff-obsidian-video-note": {
      "path": "skills/ff-obsidian-video-note"
    },
    "ff-rough-cut-review": {
      "path": "skills/ff-rough-cut-review"
    }
  }
}
```

### Step 5: Create .mcp.json

**Create** `workshop-video-brain/.mcp.json`:

```json
{
  "mcpServers": {
    "workshop-video-brain": {
      "command": "uv",
      "args": ["run", "--directory", "${CLAUDE_PLUGIN_ROOT}/..", "workshop-video-brain-server"],
      "env": {
        "WVB_VAULT_PATH": "${WVB_VAULT_PATH:-}",
        "WVB_WORKSPACE_ROOT": "${WVB_WORKSPACE_ROOT:-}"
      }
    }
  }
}
```

### Step 6: Create Python package structure

**Create** these files with `__init__.py` stubs:

- `workshop-video-brain/src/workshop_video_brain/__init__.py` -- `__version__ = "0.1.0"`
- `workshop-video-brain/src/workshop_video_brain/app/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/core/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/core/models/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/core/utils/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/core/validators/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/workspace/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/production_brain/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/production_brain/skills/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/production_brain/notes/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/stt/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/render/__init__.py` -- empty
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/__init__.py` -- empty

### Step 7: Create config loader

**Create** `workshop-video-brain/src/workshop_video_brain/app/config.py`:

Config dataclass with fields for all paths and tool availability. Use `os.environ.get()` for each setting. Use `shutil.which()` to detect ffmpeg. Try importing `faster_whisper` to detect whisper availability. Report missing tools via `warnings.warn()`.

### Step 8: Create logging setup

**Create** `workshop-video-brain/src/workshop_video_brain/app/logging.py`:

Setup structured logging using Python `logging` module. JSON-formatted handler for machine readability. Console handler for human readability. `setup_logging()` function that accepts optional workspace path for per-job log files.

### Step 9: Create path resolver

**Create** `workshop-video-brain/src/workshop_video_brain/app/paths.py`:

`resolve_workspace_path(config)` that resolves workspace root from config. Utility for making paths relative to workspace.

### Step 10: Create MCP server skeleton

**Create** `workshop-video-brain/src/workshop_video_brain/server.py`:

```python
from fastmcp import FastMCP

mcp = FastMCP("workshop-video-brain")

@mcp.tool()
def ping() -> str:
    """Health check. Returns server status."""
    return "pong: workshop-video-brain is running"

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
```

### Step 11: Create CLI stub

**Create** `workshop-video-brain/src/workshop_video_brain/app/cli.py`:

```python
import click

@click.group()
def main():
    """Workshop Video Brain -- video production assistant CLI."""
    pass

@main.command()
def version():
    """Show version."""
    from workshop_video_brain import __version__
    click.echo(f"workshop-video-brain {__version__}")

if __name__ == "__main__":
    main()
```

### Step 12: Create 5 stub SKILL.md files

**Create** each skill stub with valid frontmatter:

- `workshop-video-brain/skills/ff-video-idea-to-outline/SKILL.md`
- `workshop-video-brain/skills/ff-tutorial-script/SKILL.md`
- `workshop-video-brain/skills/ff-shot-plan/SKILL.md`
- `workshop-video-brain/skills/ff-obsidian-video-note/SKILL.md`
- `workshop-video-brain/skills/ff-rough-cut-review/SKILL.md`

Each has `name` and `description` in frontmatter. Body says: "Full implementation pending. This skill will be completed in Sub-Spec 5."

Use the descriptions from the master spec's Skill Specifications section.

### Step 13: Create 4 ADRs

**Create** `docs/adr/` with:

- `001-python-stack.md` -- Why Python 3.12+, FastMCP, Pydantic, Click
- `002-file-based-integration.md` -- Why file-based integration over GUI automation for Kdenlive
- `003-copy-first-safety.md` -- Why all mutations target copies, never originals
- `004-two-module-architecture.md` -- Why Production Brain (skills) and Kdenlive Edit MCP (server) are separate modules

Each ADR follows: Title, Status (Accepted), Context, Decision, Consequences.

### Step 14: Create README.md

**Create** `README.md` with:

- Project name and description
- Installation instructions (`/plugin marketplace add Caleb68864/ForgeFrame`)
- What you get (5 skills + MCP server)
- Quick start guide
- Technology stack
- License (MIT)

### Step 15: Create test directory structure

**Create**:
- `tests/__init__.py`
- `tests/unit/__init__.py`
- `tests/integration/__init__.py`
- `tests/fixtures/` (empty directory)

## Verification Commands

```bash
# Verify Python package is importable
cd /home/caleb/Projects/ForgeFrame && uv sync && uv run python -c "from workshop_video_brain import __version__; print(__version__)"

# Verify MCP server starts
uv run workshop-video-brain-server &
sleep 2 && kill %1

# Verify CLI works
uv run wvb version

# Verify marketplace.json is valid JSON
python -c "import json; json.load(open('.claude-plugin/marketplace.json'))"

# Verify plugin.json is valid JSON
python -c "import json; json.load(open('workshop-video-brain/plugin.json'))"

# Verify all SKILL.md files exist
ls workshop-video-brain/skills/*/SKILL.md

# Verify pytest runs (no tests yet, but infrastructure works)
uv run pytest --co -q
```

## Acceptance Criteria

- [ ] `.claude-plugin/marketplace.json` validates against Claude Code marketplace schema
- [ ] `plugin.json` declares all 5 skills and is valid JSON
- [ ] `.mcp.json` points to a runnable Python MCP server command
- [ ] `pyproject.toml` includes dependency groups: runtime, dev, test
- [ ] Config loader reads `.env` / environment variables for: vault path, workspace root, ffmpeg path, whisper model
- [ ] Config loader reports missing optional tools (ffmpeg, whisper) without crashing
- [ ] MCP server starts and responds to a `ping` tool call
- [ ] 5 stub SKILL.md files exist with valid frontmatter (name, description)
- [ ] 4 ADRs written in `docs/adr/`
- [ ] README.md includes project description and installation instructions
