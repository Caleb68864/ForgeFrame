---
title: "Workflow Cheatsheet"
part: "Appendices"
tags:
  - workflow
  - reference
  - cheatsheet
  - forgeframe
---

# Appendix A: Workflow Cheatsheet

Complete production pipeline from brain dump to archive, with the ForgeFrame skill at each step.

---

## The 15-Step Tutorial Production Workflow

| Step | What Happens | ForgeFrame Skill | Manual Alternative | Handbook Chapter |
|------|-------------|------------------|--------------------|-----------------|
| **1. Brain Dump** | Capture the raw idea: topic, audience, outcome, constraints | `/ff-new-project` — takes your brain dump and scaffolds the full project | Write a rough paragraph in your notes app | Ch.00, Ch.03 |
| **2. Outline** | Structure the idea into viewer promise, teaching beats, chapter structure, pain points | `/ff-video-idea-to-outline` — generates a production-ready outline | Draft your outline in Obsidian or a text editor | Ch.03 |
| **3. Script** | Expand the outline into a full narration script with directions, key points, and common mistakes | `/ff-tutorial-script` — writes a complete script from the outline | Write the script section by section using the outline as a guide | Ch.04 |
| **4. Shot Plan** | Identify every shot needed: A-roll, overhead, closeups, measurements, inserts, glamour, pickups | `/ff-shot-plan` — generates a categorized shot list with must-have / should-have priorities | Review each teaching beat and note what needs to be visible on screen | Ch.04 |
| **5. Capture Prep** | Generate the pre-shoot checklist: camera settings, audio, lighting, sync, optimized shot order | `/ff-capture-prep` — produces a printable checklist optimized for your shot list | Walk through each setup category manually using the Ch.05 filming checklist | Ch.04, Ch.05 |
| **6. Film** | Capture footage using the shot plan and checklist | No skill — ForgeFrame cannot operate a camera | Follow the shot plan category by category; check off shots as you go | Ch.05 |
| **7. Ingest** | Bring footage into the workspace; check for VFR; transcode phone/screen-capture footage to CFR | `media_check_vfr` + `media_transcode_cfr` — detects and converts VFR sources automatically | Run `ffprobe` on each clip; transcode VFR files with the FFmpeg command in Ch.17 | Ch.13, Ch.14 |
| **8. Edit** | Assemble first cut from clips and script; refine rough cut editorially | `/ff-auto-editor` → `/ff-rough-cut-review` — builds Kdenlive project then reviews it for pacing, repetition, and missing visuals | Import clips into Kdenlive; manually assemble following the script structure | Ch.06, Ch.07 |
| **9. Color** | Correct exposure, white balance, contrast, saturation; optionally apply look LUT | `color_analyze` → `color_apply_lut` — analyzes clips and applies correction | Use Kdenlive's Lift/Gamma/Gain effect; verify on waveform and vectorscope | Ch.09 |
| **10. Audio** | Apply full processing chain: noise reduction → EQ → compression → de-esser → normalization → limiter | `/ff-audio-cleanup` — runs the full chain automatically with the `youtube_voice` preset | Apply LADSPA effects in Kdenlive's audio effect stack in the order listed in Ch.10 | Ch.10 |
| **11. Pacing** | Review speaking pace, energy drops, and viewer retention risk; fix dead air and rambling narration | `/ff-pacing-meter` + `/ff-voiceover-fixer` — detects slow sections and rewrites flagged segments | Read the transcript aloud; time each section; cut anything below 100 WPM without a visual reason | Ch.11 |
| **12. Export** | Render the final video using the correct profile for the destination platform | `render_final` with a named profile — one command to render with verified settings | Use Kdenlive's Render dialog; select the appropriate preset from Ch.13's profile table | Ch.13 |
| **13. QC** | Verify the export: black frames, silence, loudness, clipping, file integrity, VFR | `qc_check` — automated pre-publish QC scan with pass/fail report | Watch the full export at 1x speed; check the QC checklist at the end of Ch.17 | Ch.14, Ch.17 |
| **14. Publish** | Generate YouTube metadata (title, description, tags, hashtags, chapters, pinned comment) and upload | `/ff-publish` — generates the complete publish bundle ready for copy-paste into YouTube Studio | Write the description manually using the Ch.15 title and description guidelines | Ch.15 |
| **15. Social + Archive** | Create short-form clips for Shorts/Reels/TikTok; archive the project for long-term storage | `/ff-social-clips` → `archive_project` — extracts highlights and packages the project | Manually identify clip-worthy segments; copy the project folder to archive storage | Ch.16 |

---

## Quick-Reference: Skills by Phase

### Preproduction
```
/ff-new-project          Start here — one command to scaffold the whole project
/ff-video-idea-to-outline  Structure a raw idea into a production-ready outline
/ff-tutorial-script      Write the narration script from the outline
/ff-shot-plan            Generate the shot list from script or outline
/ff-broll-whisperer      Identify B-roll moments from a transcript
/ff-capture-prep         Pre-shoot checklist with optimized shot order
/ff-obsidian-video-note  Save and sync all production assets to Obsidian vault
```

### Editing
```
/ff-auto-editor          First-cut assembly from clips + script
/ff-rough-cut-review     Editorial feedback: pacing, repetition, missing visuals
/ff-pattern-brain        Extract materials list, measurements, build steps from transcript
```

### Post-Production
```
/ff-pacing-meter         Find slow sections and energy drops
/ff-voiceover-fixer      Rewrite rambling or flagged narration segments
/ff-audio-cleanup        Full audio processing chain (noise → normalize → limit)
```

### Delivery
```
/ff-publish              YouTube title, description, tags, chapters, pinned comment
/ff-social-clips         Short-form highlight clips for Shorts/Reels/TikTok
/ff-youtube-analytics    Channel performance data and content strategy insights
```

---

## Key MCP Tools (Called Directly)

```
media_check_vfr          Detect variable frame rate sources before editing
media_transcode_cfr      Convert VFR to constant frame rate
color_analyze            Analyze clip color space and exposure
color_apply_lut          Apply a LUT to clips
render_final             Render with a named profile
qc_check                 Automated pre-publish QC scan
audio_analyze            Measure LUFS, true peak, loudness range
pacing_analyze           WPM and energy analysis from transcripts
archive_project          Package project for long-term storage
```

---

## The Minimum Viable Workflow

If you just want to get a video done without using ForgeFrame at all, the eight steps that matter most:

1. **Outline** your teaching beats (even 5 bullet points works)
2. **Script** the narration (even rough notes)
3. **Shoot** with a simple shot list
4. **Transcode VFR** if you filmed on a phone
5. **Edit** rough cut in Kdenlive
6. **Normalize audio** to -14 LUFS
7. **Render** with the YouTube 1080p preset
8. **QC** by watching the full export before upload

ForgeFrame automates the labor-intensive parts of this workflow — it does not change what the workflow is.
