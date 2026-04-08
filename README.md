# ForgeFrame -- Workshop Video Brain

A local-first Claude Code plugin for tutorial video creators.

Workshop Video Brain connects Obsidian-based project planning with
Kdenlive timeline automation through a Model Context Protocol (MCP) server.
Plan your video with AI, then let the MCP server drive the tedious parts of
your edit.

## What You Get

- **5 Claude Code Skills** -- from rough idea to rough cut:
  - `ff-video-idea-to-outline` -- structured tutorial outline from a brain dump
  - `ff-tutorial-script` -- full script with hook, steps, and mistakes section
  - `ff-shot-plan` -- production shot list covering A-roll, B-roll, and pickups
  - `ff-obsidian-video-note` -- creates/updates a living Obsidian project note
  - `ff-rough-cut-review` -- pacing and structure feedback from transcript + edit notes

- **Kdenlive MCP Server** -- XML-level project automation:
  - Insert clips, set cut points, add title cards
  - Run FFmpeg proxy generation and exports
  - Transcribe audio with Whisper (faster-whisper)
  - Copy-first safety: originals are never touched

## Installation

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- FFmpeg (optional -- required for video processing)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (optional -- required for transcription)

### Setup

```bash
git clone https://github.com/calebbbennett/forgeframe.git
cd forgeframe

# Install dependencies
uv sync

# Copy environment template and fill in your paths
cp .env.example .env
$EDITOR .env
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `WVB_VAULT_PATH` | _(none)_ | Path to your Obsidian vault |
| `WVB_WORKSPACE_ROOT` | _(cwd)_ | Root directory for project working copies |
| `WVB_FFMPEG_PATH` | `ffmpeg` | Path to FFmpeg binary |
| `WVB_WHISPER_MODEL` | `small` | Whisper model size (`tiny`, `small`, `medium`, `large`) |

## Quick Start

```bash
# Verify the server starts
uv run workshop-video-brain-server &
# (it responds to MCP ping over stdio)

# Check the CLI
uv run wvb version

# Run tests
uv run pytest
```

### Using the Claude Code Plugin

Add the plugin to your Claude Code installation by pointing it at the
`workshop-video-brain/` directory. The `.mcp.json` inside that directory
declares the MCP server; Claude Code will start it automatically.

## Tech Stack

| Layer | Technology |
|---|---|
| MCP server | [FastMCP](https://github.com/jlowin/fastmcp) |
| Data models | [Pydantic v2](https://docs.pydantic.dev/) |
| CLI | [Click](https://click.palletsprojects.com/) |
| Templating | [Jinja2](https://jinja.palletsprojects.com/) |
| Video processing | FFmpeg |
| Transcription | faster-whisper |
| Build / deps | [uv](https://docs.astral.sh/uv/) + hatchling |

## Architecture

See `docs/adr/` for Architecture Decision Records:

- [ADR 001](docs/adr/001-python-stack.md) -- Python stack rationale
- [ADR 002](docs/adr/002-file-based-integration.md) -- File-based Kdenlive integration
- [ADR 003](docs/adr/003-copy-first-safety.md) -- Copy-first safety policy
- [ADR 004](docs/adr/004-two-module-architecture.md) -- Two-module architecture

## License

MIT -- see [LICENSE](LICENSE).
