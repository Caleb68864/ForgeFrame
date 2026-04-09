---
title: "ForgeFrame Skill Reference"
part: "Part VI — Reference"
chapter: 19
tags:
  - forgeframe
  - skills
  - reference
  - mcp
---

# Chapter 19: ForgeFrame Skill Reference

This chapter is a complete catalog of all 17 ForgeFrame skills. Use it to find the right skill for what you are trying to do, understand what inputs each skill needs, and know which handbook chapter teaches the underlying concept.

Each skill is invoked by typing `/skill-name` in the Claude Code prompt.

---

## How to Read This Reference

Each skill entry includes:
- **Trigger phrases** — what to say to invoke the skill
- **Inputs** — what the skill needs from you
- **Outputs** — what it produces
- **Key MCP tools** — the underlying automation tools the skill uses
- **Handbook chapter** — where the concept is taught

---

## Production Phase Map

| Phase | Skills |
|-------|--------|
| **Setup** | `ff-init`, `ff-new-project` |
| **Preproduction** | `ff-video-idea-to-outline`, `ff-obsidian-video-note`, `ff-tutorial-script`, `ff-shot-plan`, `ff-broll-whisperer`, `ff-capture-prep` |
| **Filming** | `ff-capture-prep` |
| **Editing** | `ff-auto-editor`, `ff-rough-cut-review`, `ff-pattern-brain` |
| **Post: Pacing** | `ff-pacing-meter`, `ff-voiceover-fixer` |
| **Post: Audio** | `ff-audio-cleanup` |
| **Delivery** | `ff-publish`, `ff-social-clips`, `ff-youtube-analytics` |

---

## Part I — Setup Skills

### `ff-init`

Initialize ForgeFrame for the first time. Creates your Obsidian vault structure, media organization folders, and config files.

| | |
|---|---|
| **Trigger phrases** | "set up forgeframe", "initialize forgeframe", "first time setup", "configure forgeframe", "set up my vault" |
| **Inputs** | Vault path (e.g. `~/Videos`), projects root (e.g. `~/Projects`), optional media library path |
| **Outputs** | Obsidian vault folder structure (Ideas, In Progress, Published, Archived, B-Roll Library, Templates), media library folders (video/audio/images/graphics/documents), config file at `~/.forgeframe/config.json` |
| **Key MCP tools** | `forgeframe_init`, `forgeframe_status` |
| **Handbook chapter** | Ch.00 — Getting Started with ForgeFrame |

---

### `ff-new-project`

Start a new video project from scratch: workspace on disk, Obsidian vault note, and a full production plan (outline → script → shot plan) from a brain dump.

| | |
|---|---|
| **Trigger phrases** | "new project", "start a video", "new tutorial", "I want to make a video about X", "kick off a project" |
| **Inputs** | Video title or topic, brain dump (messy description of the idea, audience, constraints) |
| **Outputs** | Project workspace at `~/Projects/{slug}/`, Obsidian vault note at `Videos/In Progress/{title}.md`, generated outline, script draft, and shot plan |
| **Key MCP tools** | `project_new` |
| **Handbook chapter** | Ch.00 — Getting Started with ForgeFrame |

---

## Part II — Preproduction Skills

### `ff-video-idea-to-outline`

Turn a rough video idea into a structured tutorial outline with viewer promise, materials list, teaching beats, pain points, and chapter structure.

| | |
|---|---|
| **Trigger phrases** | "plan a video about X", "outline a tutorial on X", "I have a video idea", "help me structure a video" |
| **Inputs** | Raw description of the video idea (topic, audience, constraints, finished outcome) |
| **Outputs** | Markdown outline (viewer promise, what we're making, materials & tools, teaching beats, pain points, chapter structure, intro hook, open questions); JSON sidecar stored to workspace |
| **Key MCP tools** | `generate_outline` (Python engine) |
| **Handbook chapter** | Ch.03 — From Idea to Outline |

**Example output structure:**
```
# [Project Title]
## Viewer Promise — one sentence
## What We're Making — 2-4 sentences
## Teaching Beats — 5-12 numbered steps
## Pain Points / Gotchas
## Chapter Structure — suggested timestamps
## Suggested Intro Hook
```

---

### `ff-obsidian-video-note`

Create or update an Obsidian video project note with frontmatter, outline, script, shot plan, transcript, edit notes, and publish checklist. Preserves manual edits using section boundaries.

| | |
|---|---|
| **Trigger phrases** | "create a video note", "update the note", "sync the vault note", "add this to my vault", "update my Obsidian note" |
| **Inputs** | Project title/slug, vault path (if not configured), optional section content to inject (outline, script, shot plan) |
| **Outputs** | Obsidian markdown note at `{vault_path}/Videos/In Progress/{slug}.md` with section boundaries for each production asset |
| **Key MCP tools** | `create_or_update_note` (Python engine) |
| **Handbook chapter** | Ch.03 — From Idea to Outline |

**Section boundary format:**
```
<!-- wvb:section:outline -->
(automated content here)
<!-- /wvb:section:outline -->
```
Content outside section boundaries is never modified.

---

### `ff-tutorial-script`

Generate a practical tutorial script from an outline or project note. Produces intro hook, materials section, step-by-step build instructions, common mistakes, and conclusion.

| | |
|---|---|
| **Trigger phrases** | "write a script", "script this tutorial", "turn my outline into a script", "write the voiceover", "draft the tutorial" |
| **Inputs** | Completed outline (from `ff-video-idea-to-outline`) or raw topic with list of steps; optional target video length |
| **Outputs** | Markdown script with sections: HOOK (0:00-0:30), PROJECT OVERVIEW, MATERIALS & TOOLS, STEP blocks (direction + script text + key points + common mistake for each), SAFETY WARNINGS, CONCLUSION, VOICEOVER NOTES; JSON sidecar stored to workspace |
| **Key MCP tools** | `generate_script` (Python engine) |
| **Handbook chapter** | Ch.04 — Scripts, Shot Plans & Capture Prep |

---

### `ff-shot-plan`

Generate a production shot list from a tutorial outline or script. Covers A-roll, overhead bench shots, detail closeups, measurement shots, inserts, glamour B-roll, and likely pickup shots.

| | |
|---|---|
| **Trigger phrases** | "shot list", "plan the shots", "what shots do I need", "shooting plan", "what do I need to film" |
| **Inputs** | Script dict (from `ff-tutorial-script`) or outline dict (from `ff-video-idea-to-outline`) or raw description; optional gear constraints (e.g. "no overhead rig", "phone only") |
| **Outputs** | Shot plan markdown organized by category (A-roll, Overhead/Bench, Detail Closeups, Measurement/Cutting, "Don't Forget" Inserts, Glamour/Result B-Roll, Likely Pickup Shots) with must-have / should-have / nice-to-have priorities; shot count summary table; JSON sidecar |
| **Key MCP tools** | `generate_shot_plan` (Python engine) |
| **Handbook chapter** | Ch.04 — Scripts, Shot Plans & Capture Prep |

---

### `ff-broll-whisperer`

Analyse a workshop tutorial transcript and suggest specific B-roll shots grouped by category (Process Shot, Material Close-up, Tool in Use, Result Reveal, Measurement Shot).

| | |
|---|---|
| **Trigger phrases** | "b-roll", "what visuals", "where do I need footage", "suggest shots", "what should I film", "b-roll ideas", "cutaway suggestions" |
| **Inputs** | Workspace path (reads transcript JSON files from `{workspace}/transcripts/`) |
| **Outputs** | Grouped B-roll suggestion list with timestamps, confidence scores, and shot descriptions; saved to `<!-- wvb:section:broll-suggestions -->` in vault note |
| **Key MCP tools** | `broll_suggest` |
| **Handbook chapter** | Ch.04 — Scripts, Shot Plans & Capture Prep |

---

### `ff-capture-prep`

Generate a pre-shoot capture checklist from a shot plan: camera settings, audio, lighting, sync, and optimized shot order to minimize setup changes.

| | |
|---|---|
| **Trigger phrases** | "capture prep", "shoot prep", "pre-shoot", "filming checklist", "camera settings checklist" |
| **Inputs** | Workspace path (reads `reports/shot_plan.json`); optional target resolution (default 1920x1080) and frame rate (default 30fps) |
| **Outputs** | Pre-shoot checklist markdown organized by setup category (camera settings, audio, lighting, sync, shot order optimized to minimize camera moves) |
| **Key MCP tools** | `generate_capture_checklist` (Python engine) |
| **Handbook chapter** | Ch.04 — Scripts, Shot Plans & Capture Prep; Ch.05 — Filming Your Tutorial |

---

## Part III — Editing Skills

### `ff-auto-editor`

Auto-assemble a first-cut video timeline from script and footage. Matches clips to script steps and builds a Kdenlive project file as a starting point for human editing.

| | |
|---|---|
| **Trigger phrases** | "build the edit", "auto edit", "assemble timeline", "create first cut", "auto-assemble", "build the timeline" |
| **Inputs** | Workspace path (reads labeled clips and transcripts); optional script data for step matching |
| **Outputs** | Kdenlive project file at `projects/working_copies/{title}_assembled_v{N}.kdenlive`; assembly report at `reports/assembly_report.md`; machine-readable plan at `reports/assembly_plan.json` |
| **Key MCP tools** | `assembly_plan`, `assembly_build` |
| **Handbook chapter** | Ch.07 — Your First Edit |

---

### `ff-rough-cut-review`

Review a rough cut using transcript and edit notes. Identifies pacing issues, repetition, missing visuals, overlay opportunities, and chapter break candidates.

| | |
|---|---|
| **Trigger phrases** | "review the cut", "rough cut feedback", "pacing review", "analyze the edit", "what's wrong with this cut" |
| **Inputs** | Transcript text (with timestamps if available), optional edit markers from workspace, optional prior edit notes |
| **Outputs** | Review markdown with: summary, pacing notes (P1, P2...), repetition flags (R1, R2...), missing visual suggestions (V1, V2...), overlay opportunities table, suggested chapter breaks, priority action list; JSON sidecar |
| **Key MCP tools** | `generate_review` (Python engine) |
| **Handbook chapter** | Ch.07 — Your First Edit |

---

### `ff-pattern-brain`

Extract MYOG (Make Your Own Gear) build data from a workshop transcript. Produces a materials list, measurements, numbered build steps, and tips/warnings. Also generates overlay text for video and a printable build notes document.

| | |
|---|---|
| **Trigger phrases** | "build notes", "pattern", "materials list", "measurements", "printable", "overlay text", "extract build data" |
| **Inputs** | Workspace transcript (reads from `{workspace}/transcripts/`) |
| **Outputs** | Materials table, measurements list, numbered build steps, tips & warnings blockquotes; optional `build_notes.md` file; overlay text for video; Obsidian note update |
| **Key MCP tools** | Pattern extraction pipeline (Python engine) |
| **Handbook chapter** | Ch.07 — Your First Edit (general editing reference) |

---

## Part IV — Post-Production Skills

### `ff-pacing-meter`

Analyse video pacing and energy from transcript data. Detects slow sections, weak intros, and energy drops. Provides targeted fixes to improve viewer retention.

| | |
|---|---|
| **Trigger phrases** | "pacing", "too slow", "boring parts", "retention", "check my pacing", "where does it drag", "viewer drop-off", "find the slow parts" |
| **Inputs** | Workspace path (reads transcript JSON files from `{workspace}/transcripts/`) |
| **Outputs** | Pacing report with: overall WPM average and classification, intro assessment (first 30 seconds), energy drop timestamps, per-30-second segment table, targeted fix recommendations, one-paragraph pacing summary |
| **Key MCP tools** | `pacing_analyze` |
| **Handbook chapter** | Ch.11 — Pacing, Storytelling & Retention |

**WPM interpretation:**
- < 100 WPM: Too slow — viewers will disengage
- 100-160 WPM: Comfortable tutorial pace (target range)
- > 160 WPM: Fast — high energy, can overwhelm; good for recap sections

---

### `ff-voiceover-fixer`

Rewrite flagged voiceover segments into clean tutorial language. Removes rambling, false starts, and dead air while preserving all technical content.

| | |
|---|---|
| **Trigger phrases** | "fix voiceover", "clean up transcript", "rewrite rambling", "voiceover fixes", "fix the dead air", "rewrite my narration" |
| **Inputs** | Workspace path (reads transcript JSON and marker JSON from `{workspace}/transcripts/` and `{workspace}/markers/`); filters to `mistake_problem`, `repetition`, and `dead_air` markers with confidence > 0.5 |
| **Outputs** | Fix document with per-segment: original text, rewrite (or CUT recommendation), category and confidence; saved to `voiceover-fixes` section in vault note |
| **Key MCP tools** | `voiceover_extract_segments` |
| **Handbook chapter** | Ch.11 — Pacing, Storytelling & Retention |

**Target:** 50-70% of original word count per rewrite. Technical terms and measurements preserved exactly.

---

### `ff-audio-cleanup`

Clean up raw audio for YouTube tutorials. Applies the full processing chain: noise reduction, normalization, dynamic compression, de-essing, and peak limiting.

| | |
|---|---|
| **Trigger phrases** | "clean the audio", "fix the sound", "audio sounds bad", "normalize audio", "enhance voice", "remove background noise", "fix the hiss" |
| **Inputs** | Workspace path, optional specific file path; optional preset choice (`youtube_voice`, `podcast`, `raw_cleanup`) |
| **Outputs** | Processed audio file in `media/processed/`; before/after LUFS report (Integrated LUFS, True Peak, Loudness Range); source file is never modified |
| **Key MCP tools** | `audio_analyze`, `audio_enhance`, `audio_enhance_all`, `audio_normalize`, `audio_compress`, `audio_denoise` |
| **Handbook chapter** | Ch.10 — Audio Production |

**Processing chain (in order):**
1. Highpass filter (removes rumble below cutoff Hz)
2. Noise reduction (FFT-based denoising)
3. Dynamic compression (evens out volume swings)
4. De-esser (tames sibilant "s" and "t" sounds)
5. Loudness normalization (targets LUFS)
6. Peak limiter (prevents clipping)

**Presets:**
| Preset | Best for | LUFS target |
|--------|----------|-------------|
| `youtube_voice` | Tutorial screencasts, how-to videos | -16.0 |
| `podcast` | Long-form interviews, panel discussions | -16.0 |
| `raw_cleanup` | Very noisy recordings, first pass | -14.0 |

---

## Part V — Delivery Skills

### `ff-publish`

Generate YouTube publish assets: title options (searchable, curiosity, how-to, short), description, tags, hashtags, chapters, summary, and pinned comment.

| | |
|---|---|
| **Trigger phrases** | "publish", "ready to upload", "YouTube description", "generate tags", "publish bundle", "title options", "write the description" |
| **Inputs** | Workspace path (reads transcripts and chapter markers) |
| **Outputs** | Files in `reports/publish/`: `title_options.txt` (4 variants), `description.txt`, `tags.txt` (15-25 tags), `hashtags.txt` (max 15), `pinned_comment.txt`, `chapters.txt`, `summary.md` (short/medium/long), `publish_bundle.json` |
| **Key MCP tools** | `publish_bundle`, `publish_note` |
| **Handbook chapter** | Ch.15 — Publishing to YouTube |

**Title variant types:**
- Searchable: targets keywords viewers actually search
- Curiosity: creates a knowledge gap the viewer wants to close
- How-to: direct "How to X in Y" format
- Short punchy: under 40 characters for cards and thumbnails

---

### `ff-social-clips`

Extract short-form clips from a tutorial for YouTube Shorts, Instagram Reels, and TikTok. Generates titles, captions, and social post text for each platform.

| | |
|---|---|
| **Trigger phrases** | "make shorts", "social clips", "extract highlights", "create reels", "repurpose for social", "youtube shorts", "short form content", "find highlights" |
| **Inputs** | Workspace path (reads transcripts); optional `max_clips` (default 5), aspect ratio (default "9:16") |
| **Outputs** | Files in `reports/social/`: `clips_manifest.json`, `clip_N_post.txt` per clip (platform-specific), `social_summary.md`; clips scored on hook_strength, clarity, and engagement |
| **Key MCP tools** | `social_find_clips`, `social_generate_package`, `social_clip_post` |
| **Handbook chapter** | Ch.16 — Social Media & Repurposing |

**Clip scoring:**
- `hook_strength` (40%) — does the opening grab attention?
- `clarity` (30%) — can a viewer understand this without the full video?
- `engagement` (30%) — does it teach something specific?
- Score > 0.6 = strong short-form candidate

---

### `ff-youtube-analytics`

Pull YouTube channel stats and video data for analytics. Generates performance reports, identifies top content, and saves insights to the Obsidian vault.

| | |
|---|---|
| **Trigger phrases** | "youtube stats", "channel analytics", "video performance", "pull my youtube data", "how are my videos doing", "top videos", "youtube report" |
| **Inputs** | YouTube channel URL (e.g. `https://youtube.com/@yourchannel`); optional max videos to analyze (default 50) |
| **Outputs** | Channel overview (total views, avg views/likes/duration, top 5 videos); vault notes at `Research/Analytics/Channel Overview.md`, `Research/Analytics/Videos/<slug>.md` per video, `Research/Analytics/report.md`; content strategy insights |
| **Key MCP tools** | `youtube_analyze`, `youtube_save_to_vault` |
| **Handbook chapter** | Ch.15 — Publishing to YouTube |

---

## Key MCP Tools Reference

ForgeFrame includes 88 MCP tools organized by category. The most commonly used tools outside of skill invocations:

### Render Tools
| Tool | What it does |
|------|--------------|
| `render_final` | Render the final export using a named profile |
| `render_list_profiles` | List all available render profiles with settings |

**Available render profiles:** `youtube-1080p`, `youtube-4k`, `vimeo-hq`, `master-prores`, `master-dnxhr`

### Quality Control Tools
| Tool | What it does |
|------|--------------|
| `qc_check` | Run automated QC: black frames, silence, loudness, clipping, file size |
| `media_check_vfr` | Detect variable frame rate sources in the workspace |
| `media_transcode_cfr` | Convert VFR sources to constant frame rate |

See Ch.14 (Quality Control) for the full QC workflow.

### Color Tools
| Tool | What it does |
|------|--------------|
| `color_analyze` | Analyze clip color space, exposure, and white balance |
| `color_apply_lut` | Apply a LUT to one or all clips in the timeline |

See Ch.09 (Color Correction & Grading) for how to interpret `color_analyze` output.

### Effects and Compositing Tools
| Tool | What it does |
|------|--------------|
| `effect_add` | Add an effect to a clip by name |
| `effect_list_common` | List frequently used effects with parameters |
| `composite_wipe` | Add a wipe transition between two clips |
| `composite_pip` | Set up a picture-in-picture layout |
| `title_cards_generate` | Generate title card overlays from text |

See Ch.08 (Transitions & Compositing) and Ch.12 (Effects, Titles & Graphics) for usage context.

### Audio Tools (individual — for targeted fixes)
| Tool | What it does |
|------|--------------|
| `audio_analyze` | Measure LUFS, true peak, and loudness range |
| `audio_normalize` | Loudness normalization only (no other processing) |
| `audio_enhance` | Full pipeline with preset |
| `audio_enhance_all` | Full pipeline on all workspace audio files |
| `measure_loudness` | Measure integrated loudness of a specific file |

### Archive Tools
| Tool | What it does |
|------|--------------|
| `archive_project` | Package project for long-term storage |
| `archive_list` | List archived projects with metadata |

### Pacing Tools
| Tool | What it does |
|------|--------------|
| `pacing_analyze` | Run pacing analysis on workspace transcripts |
| `assembly_plan` | Generate clip-to-script matching plan |
| `assembly_build` | Build Kdenlive project from assembly plan |

---

## Skill Dependency Map

Most skills work best in sequence. Here is the typical production flow with skill names at each step:

```
Brain dump
    │
    ▼ /ff-video-idea-to-outline
Structured outline
    │
    ├── /ff-obsidian-video-note  (save to vault)
    │
    ▼ /ff-tutorial-script
Script draft
    │
    ▼ /ff-shot-plan
Shot list
    │
    ├── /ff-broll-whisperer  (B-roll suggestions from transcript)
    ├── /ff-capture-prep     (pre-shoot checklist)
    │
    ▼ Film
Raw footage
    │
    ▼ /ff-auto-editor
First-cut Kdenlive project
    │
    ├── /ff-rough-cut-review    (editorial feedback)
    ├── /ff-pacing-meter        (pacing analysis)
    ├── /ff-voiceover-fixer     (narration cleanup)
    ├── /ff-audio-cleanup       (audio processing)
    ├── /ff-pattern-brain       (build notes extraction)
    │
    ▼ Finalize in Kdenlive
    │
    ├── render_final            (render with profile)
    ├── qc_check                (automated QC)
    │
    ▼ /ff-publish
YouTube publish bundle
    │
    ▼ /ff-social-clips
Social media clips
    │
    ▼ /ff-youtube-analytics
Channel performance insights
```

---

## Quick Lookup by What You're Trying to Do

| I want to... | Use this skill |
|---|---|
| Start a new video project | `/ff-new-project` |
| Set up ForgeFrame for the first time | `/ff-init` |
| Turn an idea into a structured outline | `/ff-video-idea-to-outline` |
| Write a script from my outline | `/ff-tutorial-script` |
| Know what shots to film | `/ff-shot-plan` |
| Get B-roll shot suggestions from my transcript | `/ff-broll-whisperer` |
| Generate a pre-shoot checklist | `/ff-capture-prep` |
| Save project notes to Obsidian | `/ff-obsidian-video-note` |
| Assemble a first cut from my footage | `/ff-auto-editor` |
| Get editorial feedback on a rough cut | `/ff-rough-cut-review` |
| Find where my video drags | `/ff-pacing-meter` |
| Clean up rambling narration | `/ff-voiceover-fixer` |
| Fix my audio | `/ff-audio-cleanup` |
| Extract materials list and build steps | `/ff-pattern-brain` |
| Write a YouTube description and generate tags | `/ff-publish` |
| Create short-form clips for social | `/ff-social-clips` |
| See how my channel is performing | `/ff-youtube-analytics` |
