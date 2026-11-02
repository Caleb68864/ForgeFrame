# ForgeFrame -- Workshop Video Brain

A local-first video production assistant for tutorial creators, with ForgeFrame skills, an MCP server, a CLI, and a comprehensive video editing handbook. Use the CLI directly or connect the MCP server to Codex or Claude Code.

---

## Video Editing Handbook

**New to video editing?** The handbook is a complete guide from zero to published video -- covering Kdenlive, production concepts, and ForgeFrame automation.

[**Read the Handbook**](docs/video-editing-guide/README.md)

| Part | Chapters | What You'll Learn |
|------|----------|------------------|
| **Foundations** | Ch.00-02 | ForgeFrame setup, production pipeline, learning path |
| **Preproduction** | Ch.03-04 | Outline, script, shot plan, capture checklist |
| **Production** | Ch.05 | Camera settings, lighting, audio, VFR prevention |
| **Postproduction** | Ch.06-12 | Kdenlive editing, transitions, color, audio, pacing, effects |
| **Delivery** | Ch.13-16 | Export, QC automation, YouTube publishing, social clips |
| **Reference** | Ch.17-20 | Troubleshooting, hardware, skill catalog, resources |

Includes a [workflow cheatsheet](docs/video-editing-guide/appendix-a-workflow-cheatsheet.md), [Kdenlive shortcuts](docs/video-editing-guide/appendix-b-kdenlive-shortcuts.md), and [glossary](docs/video-editing-guide/appendix-c-glossary.md).

---

## Skills and tools

See the [generated capability catalog](docs/capabilities.md) for the complete skills and MCP tools. Run `wvb capabilities` for current registration metadata, or `wvb capabilities --markdown` to regenerate the catalog.

## Installation

### As a Claude Code Plugin (recommended)

```bash
# Add the ForgeFrame marketplace
/plugin marketplace add Caleb68864/ForgeFrame

# Install Workshop Video Brain
/plugin install workshop-video-brain@forgeframe
```

This installs the ForgeFrame skills and starts the MCP server automatically.

### Manual Setup

```bash
git clone https://github.com/Caleb68864/ForgeFrame.git
cd ForgeFrame
uv sync
```

### Codex and other MCP clients

After installing the Python package, configure an MCP stdio server with command
`workshop-video-brain-server` in your client. The same server supports both Codex
and Claude Code. Skill files live in `workshop-video-brain/skills/ff-*/SKILL.md`;
install them using your client's skill or plugin mechanism.

### Optional features

Both package roots expose the same extras: `research`, `ai-mask`,
`ai-mask-heavy`, and `motion-track`. For example:

```bash
uv sync --extra research --extra motion-track
wvb doctor
wvb doctor --json
```

Doctor checks local binaries, FFmpeg encoders, MLT effects, optional engines,
and model cache files. It does not download or initialize models. Cached model
files indicate offline readiness; the selected model still needs to match the
operation's model setting.

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- FFmpeg (required for video processing)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (required for transcription)
- Kdenlive (recommended for timeline editing)

## Quick Start

### 1. Set up ForgeFrame

```
/ff-init
```

### 2. Plan a video

```
/ff-new-project "I want to make a tutorial about building a dovetail joint"
```

This creates a workspace with outline, script, shot plan, and capture checklist in one shot.

### 3. Film and ingest

```
/ff-capture-prep                    # Get your pre-shoot checklist
# ... film your tutorial ...
wvb media ingest ./workspace/       # Scan, proxy, transcribe, detect silence
```

### 4. Edit

```
/ff-auto-editor                     # Assemble a first cut
/ff-rough-cut-review                # Get structural feedback
/ff-pacing-meter                    # Find slow sections
/ff-audio-cleanup                   # Polish the audio
```

### 5. Export and publish

```
wvb render final ./workspace/ --profile youtube-1080p
wvb qc-check ./renders/output.mp4  # Automated quality checks
/ff-publish                         # Generate YouTube metadata
/ff-social-clips                    # Extract clips for Shorts/Reels
```

## Persistent jobs and guided editing

Long operations run as persisted jobs with progress and logs:

```bash
wvb jobs submit ./workspace/ render --parameters '{"profile":"youtube-1080p"}'
wvb jobs list ./workspace/
wvb jobs status ./workspace/ JOB_ID
wvb jobs cancel ./workspace/ JOB_ID
wvb jobs retry ./workspace/ JOB_ID
wvb project-status ./workspace/
wvb workflow ./workspace/ --through review
```

The job operations include `render`, `proxy`, `transcribe`, and `workflow`.
The guided workflow follows footage, selects, assembly, preview, and review,
records completed stages, and pins the selected project version. Use project
status to see missing inputs and the next action; prepare a script with steps
before assembling a first cut. Job execution currently uses POSIX process
management.

## Pipeline Features

| Feature | What It Does |
|---------|-------------|
| **Transcript** | faster-whisper local STT with SRT/JSON/text export |
| **Auto-Marking** | 14 marker categories + phrase detection + repetition detection |
| **Clip Labels** | Auto-label clips by content (tutorial_step, talking_head, b_roll, etc.) |
| **Review Timeline** | Best-guess-first ranked review in Kdenlive |
| **Selects Timeline** | Filtered timeline of high-confidence segments |
| **Replay Generator** | Highlight cut with crossfades |
| **Color Analysis** | Color space detection, HDR flagging, LUT application |
| **QC Automation** | Black frame, silence, loudness, clipping, file size checks |
| **VFR Detection** | Scan for variable frame rate + auto-transcode to CFR |
| **Render Profiles** | YouTube 1080p/4K, Vimeo HQ, Master ProRes/DNxHR |
| **Compositing** | Picture-in-picture presets + wipe/dissolve transitions |
| **Effects** | Generic effect insertion + curated reference list |
| **Project Archive** | Streaming tar.gz/zip workspace bundling |
| **Obsidian Sync** | Section-safe note updates with frontmatter merge |
| **Snapshots** | Copy-first safety -- originals never touched |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| MCP server | [FastMCP](https://github.com/jlowin/fastmcp) |
| Data models | [Pydantic v2](https://docs.pydantic.dev/) |
| CLI | [Click](https://click.palletsprojects.com/) |
| Templating | [Jinja2](https://jinja.palletsprojects.com/) |
| Video processing | FFmpeg / ffprobe |
| Transcription | faster-whisper |
| Build / deps | [uv](https://docs.astral.sh/uv/) + hatchling |

## Documentation

- [**Video Editing Handbook**](docs/video-editing-guide/README.md) -- 20-chapter guide from zero to published video
- [ForgeFrame Skill Reference](docs/video-editing-guide/19-forgeframe-skill-reference.md) -- complete skill + tool catalog
- [Workflow Cheatsheet](docs/video-editing-guide/appendix-a-workflow-cheatsheet.md) -- one-page skill chain
- [Testing with Kdenlive](docs/testing-with-kdenlive.md) -- step-by-step testing guide
- [Developer Setup](docs/developer-setup.md) -- development environment setup
- [Architecture Decisions](docs/adr/) -- ADRs for key design choices

## Testing

```bash
uv run pytest tests/ -v    # 2,189 tests
```

## License

MIT -- see [LICENSE](LICENSE).
