---
title: "ForgeFrame Workflow Example: Brain Dump to Published Video"
tags:
  - example
  - forgeframe
  - workflow
---

# ForgeFrame Workflow Example: Brain Dump to Published Video

This walkthrough shows the complete ForgeFrame-assisted production pipeline for a tutorial video — from raw idea through published upload. Every step shows the exact command to run and what it produces.

**Scenario:** You want to make a 10-minute tutorial titled "How I Set Up My Woodworking Bench for Hand Tool Work."

---

## Phase 1: Idea and Pre-Production

### Step 1 — Turn your idea into a structured outline

Start with a rough one-liner and let ForgeFrame build the full structure.

```
/ff-video-idea-to-outline How I Set Up My Woodworking Bench for Hand Tool Work
```

**What it produces:**
- A working title with a clear viewer promise
- 5–8 teaching beats in logical order
- Common pain points the viewer likely has
- A suggested chapter structure for timestamps
- A hook/payoff pair

Review the outline in your Claude conversation. When you're happy with the structure, proceed.

---

### Step 2 — Create the project workspace

```
/ff-new-project
```

ForgeFrame will prompt you for:
- Project title (paste from the outline)
- Target duration (e.g., 10 minutes)
- Target platform (YouTube)

**What it creates:**
- A dated workspace folder under `projects/` (e.g., `projects/2026-04-09-workbench-setup/`)
- Subfolders: `intake/`, `transcripts/`, `exports/`, `notes/`
- An Obsidian vault note pre-filled with your outline
- A production plan with estimated time per phase

---

### Step 3 — Write the script

```
/ff-tutorial-script
```

ForgeFrame reads your outline from the vault note and produces:
- A full script with hook (first 30 seconds), step-by-step beats, and an outro
- Common mistakes callouts ("A mistake I see beginners make here is...")
- Voiceover notes: pacing cues, emphasis marks, natural pause points

**Output:** The script is saved to your vault note and to `notes/script.md`.

---

### Step 4 — Build the shot list

```
/ff-shot-plan
```

**What it produces:**
- A-roll shots (you talking to camera, in order)
- Overhead shots (workbench from above showing tool placement)
- Closeups (hand tool detail, marking gauge, chisel edge)
- Insert shots (before/after comparisons)
- Glamour shots (finished bench, aesthetically composed)

Shot list is saved to `notes/shot-plan.md`.

---

### Step 5 — Generate the capture checklist

```
/ff-capture-prep
```

**What it produces:**
- Camera settings checklist (resolution, frame rate, white balance, ND filter guidance)
- Audio setup checklist (mic placement, gain level check, room treatment tips)
- Lighting notes (window direction for this type of subject)
- Shot order optimized to minimize setup changes (e.g., all overhead shots batched together)

Print this checklist or keep it open on your phone while filming.

---

## Phase 2: Filming

Film your shots following the capture checklist. Keep this guide nearby:
→ [[../05-filming-your-tutorial|Ch. 05: Filming Your Tutorial]]

After filming, copy footage to your workspace:

```bash
wvb media ingest projects/2026-04-09-workbench-setup/intake/
```

This copies files from your camera/SD card, verifies checksums, and logs the ingested clips.

---

## Phase 3: Editing

### Step 6 — Transcribe your footage

```bash
wvb transcribe projects/2026-04-09-workbench-setup/intake/
```

ForgeFrame runs faster-whisper locally and saves transcripts to `transcripts/`. Each clip gets its own `.txt` and `.json` file with word-level timestamps.

---

### Step 7 — Assemble the first cut

```
/ff-auto-editor
```

**What it produces:**
- A Kdenlive `.kdenlive` project file with clips arranged on the timeline, matched to script steps
- Rough sync between your A-roll audio and the script structure
- Suggested B-roll gaps marked with markers

Open the generated project in Kdenlive and review the rough cut.

---

### Step 8 — Get pacing feedback on the rough cut

```
/ff-rough-cut-review
```

ForgeFrame analyzes your transcript and flags:
- Segments where WPM drops below 110 (slow/rambling)
- Repeated phrases or filler words ("um", "basically", "kind of")
- Missing B-roll coverage for technical steps
- Suggested cut points

---

### Step 9 — Fix voiceover segments (if any)

If the review flagged rambling segments:

```
/ff-voiceover-fixer
```

Paste or reference the flagged transcript segment. ForgeFrame rewrites it as clean tutorial narration, preserving your voice and meaning.

---

### Step 10 — Identify B-roll opportunities

```
/ff-broll-whisperer
```

ForgeFrame reads your transcript and suggests specific B-roll shots to cover each technical step, including:
- What to show
- How long the clip should be
- Where it sits in the timeline

---

### Step 11 — Clean up the audio

```
/ff-audio-cleanup
```

**What it runs automatically:**
1. Noise reduction (removes background hum, HVAC)
2. EQ (high-pass filter to remove low rumble, presence boost for clarity)
3. Dynamic compression (evening out loud/quiet variation)
4. De-essing (softens harsh sibilants)
5. Loudness normalization to −14 LUFS (YouTube standard)
6. Peak limiting at −1 dBTP

Output: a processed audio file ready to replace your raw audio in Kdenlive.

---

## Phase 4: Export and Publish

### Step 12 — Export from Kdenlive

In Kdenlive: `Project > Render > youtube-1080p` profile (installed by ForgeFrame), then render.

Or via CLI once you have your `.kdenlive` project ready:

```bash
wvb render projects/2026-04-09-workbench-setup/ --profile youtube-1080p
```

Output is saved to `exports/`.

---

### Step 13 — Run quality control

```bash
wvb qc projects/2026-04-09-workbench-setup/exports/workbench-setup-final.mp4
```

Checks for:
- Black frames or gaps
- Silent segments (missed audio)
- Loudness outside −14 ± 2 LUFS
- Audio clipping above −1 dBTP
- Variable frame rate (VFR) issues
- Codec and container compliance

Fix any flagged issues before uploading.

---

### Step 14 — Generate YouTube metadata

```
/ff-publish
```

**What it produces:**
- 5 title options ranked by click-through potential
- Full description with chapters, links, and timestamps
- Tag list (25–30 tags)
- Chapter markers formatted for YouTube (`0:00 Intro`, `1:23 ...`)
- Suggested pinned comment

Copy the metadata to YouTube Studio when uploading.

---

### Step 15 — Create short-form clips

```
/ff-social-clips
```

ForgeFrame analyzes your transcript for:
- "Hook moments" — a single punchy insight that stands alone
- Visual moments that work without context
- The best 30–60 second segment for YouTube Shorts

**Output:** Trim points (start/end timestamps) for each suggested clip, plus a caption and hashtag set.

---

### Step 16 — Update your Obsidian vault note

```
/ff-obsidian-video-note
```

Marks the video as published and syncs:
- Final title and description
- YouTube URL (paste when prompted)
- Upload date
- Performance baseline (to check against analytics later)

---

### Step 17 — Track analytics (after 48 hours)

```
/ff-youtube-analytics
```

ForgeFrame pulls your channel analytics and reports:
- Click-through rate vs. your channel average
- Average view duration and drop-off points
- Top traffic sources
- Suggested next topic based on viewer comments and search terms

---

## Time Summary

| Phase | Manual (no ForgeFrame) | With ForgeFrame |
|-------|----------------------|-----------------|
| Idea → outline | 1–2 hours | 10–15 minutes |
| Script | 2–4 hours | 30–60 minutes review |
| Shot list + checklist | 1 hour | 10 minutes review |
| Audio cleanup | 30–90 minutes | 5 minutes |
| YouTube metadata | 30–60 minutes | 5 minutes review |
| **Total pre/post** | **~8 hours** | **~1.5 hours** |

ForgeFrame handles the mechanical work. Your creative time goes to reviewing, adjusting, and filming.

---

## Related Chapters

- [[../00-getting-started-with-forgeframe|Ch. 00: Getting Started with ForgeFrame]] — Install and configure ForgeFrame
- [[../01-pipeline-overview|Ch. 01: The Video Production Pipeline]] — How all these skills fit the pipeline
- [[../03-from-idea-to-outline|Ch. 03: From Idea to Outline]] — Manual version of Step 1
- [[../04-scripts-shot-plans-capture-prep|Ch. 04: Scripts, Shot Plans & Capture Prep]] — Manual versions of Steps 3–5
- [[../10-audio-production|Ch. 10: Audio Production]] — What `/ff-audio-cleanup` does under the hood
- [[../15-publishing-to-youtube|Ch. 15: Publishing to YouTube]] — Manual version of Steps 14–17
- [[../19-forgeframe-skill-reference|Ch. 19: ForgeFrame Skill Reference]] — Full catalog of all 17 skills
