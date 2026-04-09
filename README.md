# ForgeFrame -- Workshop Video Brain

A local-first Claude Code plugin marketplace for tutorial video creators.

Workshop Video Brain is a complete video pre-production and edit-preparation
system. It connects Obsidian-based project planning with Kdenlive timeline
automation through a Model Context Protocol (MCP) server. Plan your video
with AI skills, process footage with automated pipelines, and open a
ready-to-review project in Kdenlive.

## What You Get

### 12 Claude Code Skills

**Pre-Production:**
- `/ff-video-idea-to-outline` -- structured tutorial outline from a brain dump
- `/ff-tutorial-script` -- full script with hook, steps, and mistakes section
- `/ff-shot-plan` -- production shot list covering A-roll, B-roll, and pickups
- `/ff-obsidian-video-note` -- creates/updates a living Obsidian project note

**Post-Production:**
- `/ff-rough-cut-review` -- pacing and structure feedback from transcript + edit notes
- `/ff-voiceover-fixer` -- identifies rambling sections with tightened rewrites
- `/ff-broll-whisperer` -- smart B-roll suggestions with 5 shot type categories
- `/ff-pacing-meter` -- per-segment energy and pacing analysis (WPM, density, drops)
- `/ff-pattern-brain` -- extract materials, measurements, steps for overlays + printable notes

### 29 MCP Tools

| Category | Tools |
|---|---|
| Workspace | create, status, snapshot_list, snapshot_restore |
| Media | ingest, list_assets, proxy_generate |
| Transcript | generate, export |
| Markers | auto_generate, list |
| Clips | label, search |
| Timeline | build_review, build_selects |
| Project | create_working_copy, validate, summary |
| Transitions | apply, batch_apply |
| Subtitles | generate, import, export |
| Render | preview, final, status |
| Analysis | broll_suggest, pacing_analyze, pattern_extract, replay_generate, title_cards_generate, voiceover_extract_segments |

### Full CLI (`wvb`)

```bash
wvb workspace create "My Video" --media-root ./footage/
wvb media ingest ./workspace/
wvb transcript generate ./workspace/
wvb markers auto ./workspace/
wvb clips label ./workspace/
wvb clips search ./workspace/ "zipper"
wvb timeline review ./workspace/
wvb replay generate ./workspace/ --duration 60
wvb pacing analyze ./workspace/
wvb pattern extract ./workspace/
wvb title-cards generate ./workspace/
wvb broll suggest ./workspace/
wvb project validate ./workspace/
wvb render preview ./workspace/
wvb prepare-tutorial-project ./footage/ --title "Pouch Build"
```

## Installation

### As a Claude Code Plugin (recommended)

```bash
# Add the ForgeFrame marketplace
/plugin marketplace add Caleb68864/ForgeFrame

# Install Workshop Video Brain
/plugin install workshop-video-brain@forgeframe
```

This gives you all 12 skills and starts the MCP server automatically.

### Manual Setup

```bash
git clone https://github.com/Caleb68864/ForgeFrame.git
cd ForgeFrame
uv sync
cp .env.example .env
# Edit .env with your vault path
```

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- FFmpeg (optional -- required for video processing)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (optional -- required for transcription)

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `WVB_VAULT_PATH` | _(none)_ | Path to your Obsidian vault |
| `WVB_WORKSPACE_ROOT` | _(cwd)_ | Root directory for project workspaces |
| `WVB_FFMPEG_PATH` | `ffmpeg` | Path to FFmpeg binary |
| `WVB_WHISPER_MODEL` | `small` | Whisper model size (`tiny`, `small`, `medium`, `large`) |

## Quick Start

### 1. Plan a video

```
/ff-video-idea-to-outline "I want to make a tutorial about sewing a zippered bikepacking pouch"
/ff-tutorial-script
/ff-shot-plan
```

### 2. Process footage

```bash
wvb prepare-tutorial-project ./footage/ --title "Zippered Pouch"
```

This runs the full pipeline: workspace creation, media scan, proxy generation, transcription, auto-marking, clip labeling, review timeline, and Obsidian note creation.

### 3. Review in Kdenlive

```bash
kdenlive ./workspace/projects/working_copies/*_review_*.kdenlive
```

Open the generated project -- clips are ranked by importance, guide markers explain why each segment was included.

### 4. Analyze and refine

```
/ff-pacing-meter          # Find slow sections
/ff-voiceover-fixer       # Get rewrite suggestions for rambling
/ff-broll-whisperer       # Get specific B-roll shot suggestions
/ff-pattern-brain         # Extract materials list and build steps
```

## Pipeline Features

| Feature | What it does |
|---|---|
| **Transcript** | faster-whisper local STT with SRT/JSON/text export |
| **Auto-Marking** | 14 marker categories + phrase detection + repetition detection |
| **Clip Labels** | Auto-label clips by content (tutorial_step, talking_head, b_roll, etc.) |
| **Review Timeline** | Best-guess-first ranked review in Kdenlive |
| **Selects Timeline** | Filtered timeline of high-confidence segments |
| **Replay Generator** | 1-minute highlight cut with crossfades |
| **Pacing Analysis** | Per-segment WPM, speech density, energy drops |
| **B-Roll Suggestions** | 5 categories: process, material, tool, result, measurement |
| **Pattern Brain** | Materials, measurements, steps, tips extraction for MYOG tutorials |
| **Title Cards** | Chapter title card data + Kdenlive guide markers |
| **Voiceover Fixer** | Flagged sections with rewrite suggestions |
| **Transitions** | Crossfade, dissolve, fade in/out with presets |
| **Render** | Preview and final render via melt/ffmpeg |
| **Obsidian Sync** | Section-safe note updates with frontmatter merge |
| **Snapshots** | Copy-first safety -- originals never touched |

## Tech Stack

| Layer | Technology |
|---|---|
| MCP server | [FastMCP](https://github.com/jlowin/fastmcp) |
| Data models | [Pydantic v2](https://docs.pydantic.dev/) |
| CLI | [Click](https://click.palletsprojects.com/) |
| Templating | [Jinja2](https://jinja.palletsprojects.com/) |
| Video processing | FFmpeg / ffprobe |
| Transcription | faster-whisper |
| Build / deps | [uv](https://docs.astral.sh/uv/) + hatchling |

## Documentation

- [Testing with Kdenlive](docs/testing-with-kdenlive.md) -- step-by-step testing guide
- [Developer Setup](docs/developer-setup.md) -- development environment setup
- [User Workflow](docs/user-workflow.md) -- end-to-end usage guide
- [AI Handoff Notes](docs/ai-handoff.md) -- module boundaries and extension points
- [Architecture Decisions](docs/adr/) -- ADRs for key design choices

## Testing

```bash
uv run pytest tests/ -v    # 568 tests
```

## License

MIT -- see [LICENSE](LICENSE).
