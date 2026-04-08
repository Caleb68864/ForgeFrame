# Testing ForgeFrame MCP Tools with Kdenlive

## Prerequisites

1. **Kdenlive** installed (25.04+ recommended)
2. **FFmpeg** in PATH
3. **faster-whisper** installed: `pip install faster-whisper` (downloads ~1GB model on first run)
4. **ForgeFrame** set up: `cd /home/caleb/Projects/ForgeFrame && uv sync`
5. **Sample footage** -- any video file you've shot (even a 2-minute test clip works)

## Quick Test: Full Pipeline via CLI

The fastest way to verify everything works end-to-end:

```bash
# 1. Create a workspace from your footage folder
uv run wvb workspace create "Test Video" --media-root /path/to/your/footage/

# 2. Run the full pipeline
uv run wvb media ingest /path/to/workspace/
uv run wvb transcript generate /path/to/workspace/
uv run wvb markers auto /path/to/workspace/
uv run wvb clips label /path/to/workspace/
uv run wvb timeline review /path/to/workspace/

# 3. Open the generated Kdenlive project
kdenlive /path/to/workspace/projects/working_copies/*.kdenlive
```

## What to Verify in Kdenlive

After opening the generated project:

### Markers/Guides
- Look at the timeline ruler -- you should see colored guide markers
- Each marker should have a label like: `step_explanation: "Shows zipper installation" (conf: 0.85)`
- Markers are placed at the timestamps where the auto-marking system found interesting content

### Clips on Timeline
- The review timeline places clips in ranked order (best-guess-first)
- First clips should be the highest-scored segments (likely step explanations and chapter candidates)
- Scrub through to see if the ranking makes sense

### Media References
- All clips from your footage should appear in the project bin
- If proxies were generated, they should be linked (check Project > Project Settings > Proxy)

### Subtitles
- If SRT was generated, import it: Subtitle > Import Subtitle File
- Select the SRT from `workspace/transcripts/*.srt`
- Verify timestamps align with the audio

## Testing MCP Tools via Claude

Start the MCP server, then use Claude Code to interact:

```bash
# Start the server (if not auto-started via plugin)
uv run workshop-video-brain-server
```

Or if installed as a plugin:
```
/plugin marketplace add ./
/plugin install workshop-video-brain@forgeframe
```

Then in Claude Code, you can say:

- **"Create a workspace for my pouch build video"** -- Claude calls `workspace_create`
- **"Scan the media folder"** -- Claude calls `media_ingest`
- **"Generate transcripts"** -- Claude calls `transcript_generate`
- **"Find all the mistakes in my footage"** -- Claude calls `markers_auto_generate`
- **"Label all my clips"** -- Claude calls `clips_label`
- **"Find clips about zipper installation"** -- Claude calls `clips_search`
- **"Build a review timeline"** -- Claude calls `timeline_build_review`
- **"Validate the project"** -- Claude calls `project_validate`

## Testing Individual MCP Tools

### workspace_create
```
Ask Claude: "Create a new video workspace called 'Pouch Build' with media from /home/caleb/Videos/pouch/"
Expected: Workspace folder created with all standard subdirectories
Verify: ls the workspace root -- should see media/, transcripts/, markers/, clips/, projects/, renders/, etc.
```

### media_ingest
```
Ask Claude: "Scan the media in my workspace"
Expected: All video/audio files cataloged with metadata (duration, codec, resolution)
Verify: Check workspace manifest for asset inventory
```

### transcript_generate
```
Ask Claude: "Transcribe all the footage"
Expected: Transcript JSON + SRT + TXT files in transcripts/ folder
Verify: Read the .srt file -- timestamps should roughly match when you speak
Note: First run downloads the Whisper model (~1GB). Subsequent runs are faster.
```

### markers_auto_generate
```
Ask Claude: "Find all the interesting moments and mistakes"
Expected: Marker JSON files in markers/ folder
Verify: Open markers JSON -- each marker should have category, confidence, reason
Look for: dead_air (silence), mistake_problem (filler phrases), chapter_candidate, step_explanation
```

### clips_label
```
Ask Claude: "Label all my clips"
Expected: Label JSON files in clips/ folder
Verify: Each label should have content_type, topics, tags, summary
```

### clips_search
```
Ask Claude: "Find clips where I talk about materials"
Expected: Ranked list of matching clips with scores
```

### timeline_build_review
```
Ask Claude: "Build a review timeline from my footage"
Expected: .kdenlive file in projects/working_copies/
Verify: Open in Kdenlive -- clips should be on the timeline with guide markers
```

### project_validate
```
Ask Claude: "Validate my Kdenlive project"
Expected: Validation report with severity levels (info/warning/error)
Verify: No blocking_error items. Warnings about missing media are OK if files moved.
```

## Testing Production Brain Skills

These are Claude Code skills (prompts), not MCP tools. They work in Claude Code directly:

```
/ff-video-idea-to-outline "I want to make a tutorial about sewing a zippered bikepacking pouch"
```
Expected: Structured outline with viewer promise, materials, teaching beats, pain points

```
/ff-tutorial-script
```
Expected: Script draft with hook, overview, steps, mistakes, conclusion (uses outline context from previous command)

```
/ff-shot-plan
```
Expected: Shot list with A-roll, overhead, closeups, inserts, glamour, pickups

```
/ff-obsidian-video-note
```
Expected: Obsidian note created/updated in your vault with all sections populated

```
/ff-rough-cut-review
```
Expected: Review notes identifying pacing issues, repetition, missing inserts

```
/ff-voiceover-fixer
```
Expected: Flagged transcript segments with suggested rewrites for cleaner narration

## Common Issues

### "ffmpeg not found"
Add ffmpeg to PATH or set `WVB_FFMPEG_PATH` in your `.env`

### "faster-whisper not available"
Install it: `pip install faster-whisper` or `uv add faster-whisper`
First transcription downloads the model -- be patient.

### Kdenlive project won't open
- Check that media paths in the project XML point to actual files
- If you moved footage after generating the project, paths will be broken
- Run `project_validate` to see which paths are invalid

### Markers not visible in Kdenlive
- Markers appear as guide markers on the timeline ruler
- Make sure you're looking at the right timeline (the review timeline, not a blank project)
- Zoom out to see the full timeline -- markers may be spread across the duration

### Proxy issues
- Proxies are generated in `workspace/media/proxies/`
- If Kdenlive can't find proxies, check Project > Project Settings > Proxy
- You can regenerate: `uv run wvb media ingest <workspace>` (skips already-processed, regenerates missing)

## Recommended First Test

1. Record a 2-3 minute test clip of yourself explaining how to do something (any craft/DIY topic)
2. Run the full pipeline (see Quick Test above)
3. Open the generated Kdenlive project
4. Check: Do the markers make sense? Are the chapter candidates at natural breaks? Did it catch your "um"s and redos?
5. Try the skills: `/ff-video-idea-to-outline "whatever you just filmed"`

This gives you a real feel for whether the system is useful before committing to a full video project.
