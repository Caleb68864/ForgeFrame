# User Workflow Guide

A practical guide to using Workshop Video Brain from video idea to finished render.

---

## Install the Plugin

### Prerequisites

- Claude Code (or any MCP-compatible AI client)
- Python 3.12+ and `uv`
- FFmpeg installed and on your PATH

### Setup

```bash
# Clone the repository
git clone <repo-url>
cd ForgeFrame

# Install dependencies
uv sync --all-groups

# (Optional) Install faster-whisper for transcription
uv add faster-whisper
```

Configure your environment:

```bash
export WVB_VAULT_PATH=/path/to/your/obsidian-vault   # optional
export WVB_WHISPER_MODEL=small                         # optional
```

Start the MCP server (add to your MCP client configuration):

```bash
uv run workshop-video-brain-server
```

---

## Phase 1: Plan a Video

Before filming, use the planning skills to structure your content.

### Via MCP (in Claude)

Use the slash skills available in the Claude Code plugin:

- `/ff-video-idea-to-outline` — turn a rough idea into a structured outline
- `/ff-tutorial-script` — expand the outline into a full tutorial script
- `/ff-shot-plan` — convert the script into a production shot list

### Via CLI

```bash
# Generate an outline from an idea
uv run wvb plan outline "How to build a wooden toolbox from scratch"

# Generate a full script (uses outline internally)
uv run wvb plan script --idea "How to build a wooden toolbox"

# Generate a shot plan (uses outline internally)
uv run wvb plan shots --idea "How to build a wooden toolbox"

# Pre-shoot capture checklist from the workspace's reports/shot_plan.json
uv run wvb plan capture-prep /path/to/workspace --target-resolution 3840x2160 --target-fps 24
```

The planning phase is entirely local — no network calls, no API keys required.

---

## Phase 2: Prepare Footage

Once you have raw footage, use the workspace tools to ingest and organize it.

### Create a Workspace

```bash
uv run wvb workspace create "Wooden Toolbox Build" \
  --media-root /path/to/footage \
  --vault-path /path/to/vault      # optional
```

This creates a structured workspace directory with all required subfolders:

```
wooden-toolbox-build/
  media/raw/           ← copy your footage here
  media/proxies/       ← auto-generated proxies
  transcripts/         ← whisper output
  markers/             ← auto-generated markers
  projects/            ← .kdenlive files
  renders/             ← render output
  reports/             ← review reports
  workspace.yaml       ← manifest
```

### Ingest Media

Copy your raw footage into `media/raw/`, then run:

```bash
uv run wvb media ingest /path/to/workspace
```

This pipeline:
1. Scans `media/raw/` for all video/audio files
2. Generates proxies for large files (if needed)
3. Extracts audio and runs Whisper transcription (if available)
4. Detects silence gaps

**Requires:** FFmpeg. Transcription additionally requires faster-whisper.

### Generate Transcripts (separately)

```bash
uv run wvb transcript generate /path/to/workspace
```

### Generate Markers

```bash
uv run wvb markers auto /path/to/workspace
```

Markers are generated from:
- Keyword matching in transcripts (materials, steps, cautions, etc.)
- Silence detection (dead air markers)
- Position heuristics (intro, ending)

---

## Phase 3: Review Your Footage

### Build a Review Timeline

```bash
# Ranked by confidence (best moments first)
uv run wvb timeline review /path/to/workspace

# Chronological order
uv run wvb timeline review /path/to/workspace --mode chronological

# Selects list (high-confidence clips only)
uv run wvb timeline selects /path/to/workspace --min-confidence 0.6
```

### Open in Kdenlive

The `.kdenlive` file is written to `projects/working_copies/`. Open it in Kdenlive:

```bash
kdenlive projects/working_copies/wooden-toolbox-build_v1.kdenlive
```

The timeline has:
- Guide markers at each detected moment
- Clips ordered by usefulness (ranked mode) or timeline position
- Audio and video tracks

Review the timeline, make cuts, add b-roll, apply effects manually.

---

## Phase 4: Edit Notes

### Create / Update an Obsidian Note

Use the `/ff-obsidian-video-note` skill in Claude, or the MCP tool:

The `workspace_create` tool accepts a `vault_path` parameter that links the workspace to a note.

Notes support:
- Frontmatter metadata (title, status, tags, workspace_root)
- Bounded sections (`<!-- wvb:section:name -->`) that can be updated without duplication
- Automatic status tracking as the project progresses

---

## Phase 5: Render

### Preview Render

```bash
uv run wvb render preview /path/to/workspace
```

This renders the latest working copy using the `preview` profile (low-bitrate, fast).

**Requires:** `melt` (MLT framework) or FFmpeg.

### Check Render Status

```bash
uv run wvb render status /path/to/workspace
```

---

## Reaction GIFs

A captioned reaction GIF of a movie line, in three evidence-first steps
(skill `ff-reaction-gif`; MCP tools `gif_find_line`, `gif_fetch_scene`,
`gif_render`):

```bash
# 1. Every match of the line, with the 4 cues before it and a ~30 s window
uv run wvb gif find "https://tubitv.com/movies/..." "I've got it"
# 2. Download only that window; prints shot cuts and a contact sheet path
uv run wvb gif scene "https://tubitv.com/movies/..." 20:15 20:45 -o ./ksm --fine-sheet 15
# 3. Render (times are seconds within clip.mp4); prints size, duration, fps, width, check strip
uv run wvb gif render ./ksm/clip.mp4 15.5 17.52 "I'VE GOT IT!"
```

GIFs land in `$WVB_GIF_GALLERY` (default `~/Pictures/Reaction GIFs`).
Look at the contact sheet before choosing times and at the check strip
before sharing.

## Guided Workflow (All in One)

For new projects, the `prepare-tutorial-project` command runs the full pipeline interactively:

```bash
uv run wvb prepare-tutorial-project /path/to/footage --title "My Tutorial"
```

Or with Obsidian integration:

```bash
uv run wvb prepare-tutorial-project /path/to/footage \
  --title "Wooden Toolbox Build" \
  --vault-path /path/to/vault
```

This runs steps 1–6 with status reporting:
1. Create workspace
2. Ingest media
3. Auto-generate markers
4. Build review timeline
5. Create/update Obsidian note
6. Validate project

---

## What's Automated vs. Manual

| Step | Automated | Manual |
| --- | --- | --- |
| Workspace creation | Yes | |
| Media scanning | Yes | |
| Proxy generation | Yes | |
| Transcription | Yes (with faster-whisper) | |
| Silence detection | Yes | |
| Marker generation | Yes (heuristic) | Reviewing marker quality |
| Timeline assembly | Yes (ranked/chronological) | Final cut decisions |
| B-roll placement | No | Manual in Kdenlive |
| Color grading | No | Manual in Kdenlive |
| Audio mixing | No | Manual in Kdenlive |
| Title cards / graphics | No | Manual in Kdenlive |
| Transitions | Semi (apply-all command) | Individual placement |
| Render | Yes (preview + final profiles) | Choosing render settings |
| Obsidian notes | Yes (create + update) | Writing script content |
| Publishing | No | Manual upload + metadata |

---

## Tips

- **Transcription quality:** Use `WVB_WHISPER_MODEL=medium` for better accuracy on technical content
- **Large files:** Proxies are generated automatically for files > 4K resolution
- **Idempotency:** Ingest is safe to re-run; already-processed files are skipped
- **Snapshots:** Every project write creates a snapshot automatically; use `snapshot list` to see them
- **MCP resources:** Query workspace state via resources like `workspace://{path}/markers`
