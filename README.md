# ForgeFrame -- Workshop Video Brain

A local-first Claude Code plugin for tutorial video creators. Plan, edit, and publish workshop videos using AI-powered skills, 88 MCP tools, and a comprehensive video editing handbook.

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

## 17 Claude Code Skills

### Pre-Production
| Skill | What It Does |
|-------|-------------|
| `/ff-init` | Initialize ForgeFrame environment with vault structure and config |
| `/ff-new-project` | Create a complete project (workspace + outline + script + shot plan) from a brain dump |
| `/ff-video-idea-to-outline` | Structured tutorial outline from a brain dump |
| `/ff-tutorial-script` | Full script with hook, materials, steps, mistakes, and conclusion |
| `/ff-shot-plan` | Production shot list covering 7 categories (A-roll, overhead, closeup, measurements, inserts, glamour, pickups) |
| `/ff-capture-prep` | Pre-shoot checklist: camera settings, audio, lighting, optimized shot order |
| `/ff-broll-whisperer` | B-roll suggestions from transcript analysis (5 shot type categories) |
| `/ff-obsidian-video-note` | Create/update a living Obsidian project note with section-safe sync |

### Post-Production
| Skill | What It Does |
|-------|-------------|
| `/ff-auto-editor` | Assemble a first-cut Kdenlive project from clips + script |
| `/ff-rough-cut-review` | Pacing and structure feedback from transcript + markers |
| `/ff-pacing-meter` | Per-segment energy analysis: WPM, speech density, energy drops |
| `/ff-voiceover-fixer` | Identify rambling sections with tightened rewrites |
| `/ff-audio-cleanup` | Full voice processing pipeline: denoise → EQ → compress → normalize → limit |
| `/ff-pattern-brain` | Extract materials, measurements, steps for MYOG overlays + printable notes |

### Publishing
| Skill | What It Does |
|-------|-------------|
| `/ff-publish` | YouTube metadata bundle: titles, description, tags, chapters, summary |
| `/ff-social-clips` | Extract highlight clips for Shorts/Reels with platform-specific posts |
| `/ff-youtube-analytics` | Fetch and analyze YouTube channel data with engagement insights |

## 88 MCP Tools

| Category | Tools | Count |
|----------|-------|-------|
| **Workspace** | create, status, snapshot_list, snapshot_restore | 4 |
| **Media** | ingest, list_assets, proxy_generate, check_vfr, transcode_cfr | 5 |
| **Transcript** | generate, export | 2 |
| **Markers** | auto_generate, list | 2 |
| **Clips** | label, search, insert, remove, move, split, trim, ripple_delete, speed | 9 |
| **Timeline** | build_review, build_selects | 2 |
| **Project** | create_working_copy, validate, summary, setup_profile, match_source, archive | 6 |
| **Transitions** | apply, apply_at, apply_between | 3 |
| **Compositing** | composite_pip, composite_wipe | 2 |
| **Effects** | effect_add, effect_list_common | 2 |
| **Color** | color_analyze, color_apply_lut | 2 |
| **Audio** | fade, normalize, compress, denoise, enhance, enhance_all, analyze | 7 |
| **Tracks** | add, mute, visibility, gap_insert | 4 |
| **Subtitles** | generate, export | 2 |
| **Render** | preview, final, list_profiles, status | 4 |
| **QC** | qc_check | 1 |
| **Assembly** | plan, build | 2 |
| **Analysis** | broll_suggest, pacing_analyze, pattern_extract, replay_generate, title_cards_generate, voiceover_extract_segments | 6 |
| **B-Roll Library** | index, search, tag, stats | 4 |
| **Social** | find_clips, generate_package, clip_post | 3 |
| **Publishing** | bundle, description, titles, tags, summary, note | 6 |
| **YouTube** | fetch_channel, fetch_video, analyze, save_to_vault | 4 |
| **ForgeFrame** | init, status, project_new, project_list | 4 |
| **Server** | ping | 1 |

## Installation

### As a Claude Code Plugin (recommended)

```bash
# Add the ForgeFrame marketplace
/plugin marketplace add Caleb68864/ForgeFrame

# Install Workshop Video Brain
/plugin install workshop-video-brain@forgeframe
```

This gives you all 17 skills and starts the MCP server automatically.

### Manual Setup

```bash
git clone https://github.com/Caleb68864/ForgeFrame.git
cd ForgeFrame
uv sync
```

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
