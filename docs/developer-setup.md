# Developer Setup

## Prerequisites

- **Python 3.12+** — the project uses modern Python features
- **uv** — fast Python package/project manager ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **FFmpeg** — required for video processing, proxy generation, and audio extraction
- **Kdenlive** *(optional)* — open-source video editor for working with generated `.kdenlive` files; version 25.12 recommended

### Installing FFmpeg (Linux)

```bash
# Debian/Ubuntu/Arch (use your distro package manager)
sudo apt install ffmpeg
# or
sudo pacman -S ffmpeg
```

### Installing uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Clone and Setup

```bash
git clone <repo-url>
cd ForgeFrame

# Install all dependencies (including dev + test groups)
uv sync --all-groups
```

This installs the `workshop-video-brain` package in editable mode along with:
- `fastmcp` — MCP server framework
- `pydantic`, `pyyaml`, `jinja2`, `click` — core dependencies
- `pytest`, `pytest-cov` — test tooling
- `ruff`, `mypy` — linting and type checking

---

## faster-whisper Model Download

Transcription uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Models are downloaded automatically on first use from HuggingFace.

```bash
# Install faster-whisper (adds transcription capability)
uv add faster-whisper

# Pre-download the small model (recommended for development)
uv run python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu')"
```

Available model sizes (tradeoff: speed vs. accuracy):
- `tiny` — fastest, least accurate (~39 MB)
- `small` — good balance, **recommended default** (~244 MB)
- `medium` — better accuracy (~769 MB)
- `large-v3` — highest accuracy (~1.5 GB)

Set the default model via environment variable:

```bash
export WVB_WHISPER_MODEL=small
```

---

## Configure .env

Create a `.env` file in the project root (or set environment variables):

```bash
# Optional: path to your Obsidian vault root
WVB_VAULT_PATH=/path/to/your/obsidian-vault

# Optional: default workspace root (used by MCP server resources)
WVB_WORKSPACE_ROOT=/path/to/workspaces

# Optional: override ffmpeg binary path if not on PATH
WVB_FFMPEG_PATH=ffmpeg

# Optional: default whisper model
WVB_WHISPER_MODEL=small
```

---

## Run Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=workshop_video_brain --cov-report=term-missing

# Run only unit tests
uv run pytest tests/unit/ -v

# Run only integration tests
uv run pytest tests/integration/ -v
```

Tests that require FFmpeg are automatically skipped when it is not found on PATH.

---

## Run MCP Server

The MCP server exposes all tools and resources over the stdio transport (for use with Claude or any MCP-compatible client):

```bash
uv run workshop-video-brain-server
```

Or directly:

```bash
uv run python -m workshop_video_brain.server
```

To use with Claude Code, add to `.mcp.json`:

```json
{
  "mcpServers": {
    "workshop-video-brain": {
      "command": "uv",
      "args": ["run", "workshop-video-brain-server"],
      "cwd": "/path/to/ForgeFrame"
    }
  }
}
```

---

## Run CLI

The CLI is installed as `wvb`:

```bash
# Show all commands
uv run wvb --help

# Workspace management
uv run wvb workspace create "My Tutorial" --media-root /path/to/footage
uv run wvb workspace status /path/to/workspace

# Full ingest pipeline
uv run wvb media ingest /path/to/workspace

# Generate markers and timeline
uv run wvb markers auto /path/to/workspace
uv run wvb timeline review /path/to/workspace

# Validate project
uv run wvb project validate /path/to/workspace

# Guided workflow (all in one)
uv run wvb prepare-tutorial-project /path/to/footage --title "My Tutorial"
```

---

## Plugin Development

The project is structured as a plugin in the ForgeFrame monorepo:

```
ForgeFrame/
  workshop-video-brain/
    src/workshop_video_brain/
      server.py               # MCP server entry point
      app/cli.py              # CLI entry point
      edit_mcp/
        server/
          tools.py            # MCP tool registrations
          resources.py        # MCP resource registrations
        pipelines/            # Processing pipelines
        adapters/             # External tool adapters (ffmpeg, kdenlive, stt, render)
      production_brain/
        skills/               # Content planning engines
        notes/                # Obsidian note management
      workspace/              # Workspace lifecycle management
      core/models/            # Shared data models
```

### Adding a New Tool

1. Add a function to `edit_mcp/server/tools.py` decorated with `@mcp.tool()`
2. Implement it to return `{"status": "success", "data": {...}}` or `{"status": "error", "message": "..."}`
3. Add a corresponding CLI command in `app/cli.py`
4. Add integration tests in `tests/integration/test_mcp_tools.py`

### Adding a New Pipeline

1. Create `edit_mcp/pipelines/your_pipeline.py`
2. Export the main entry function
3. Call it from an MCP tool and CLI command
4. Add tests in `tests/unit/` and `tests/integration/`

### Code Quality

```bash
# Lint
uv run ruff check .

# Type check
uv run mypy workshop-video-brain/src/

# Format
uv run ruff format .
```
