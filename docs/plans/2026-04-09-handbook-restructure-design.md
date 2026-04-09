---
date: 2026-04-09
topic: "Video Editing Handbook Restructure"
author: Caleb Bennett
status: draft
tags:
  - design
  - handbook
  - video-editing-guide
---

# Video Editing Handbook Restructure -- Design

## Summary

Restructure the video editing handbook from 10 chapters into a 20-chapter, 6-part guide that teaches video editing concepts to amateur tutorial creators, integrates all 17 ForgeFrame skills as inline callouts, and fills educational gaps in color correction, pacing/storytelling, and audio production. The guide should work as a standalone learning resource even without ForgeFrame installed.

## Approach Selected

**Approach B: Restructure + Deepen** -- Full reorganization with new educational chapters and inline ForgeFrame integration. Chosen because the "one-stop shop" goal requires proper chapters for color, pacing, and audio rather than bolted-on callouts, and the restructure gives every skill a natural home.

## Architecture

### Chapter Structure

```
PART I: FOUNDATIONS
  00 - Getting Started with ForgeFrame     [NEW]
  01 - The Video Production Pipeline       [EXISTING, updated]
  02 - Audience, Learning Goals & Scope    [EXISTING, light update]

PART II: PREPRODUCTION
  03 - From Idea to Outline                [EXISTING Ch.3, refocused]
  04 - Scripts, Shot Plans & Capture Prep  [EXISTING Ch.3 split, + capture prep]

PART III: PRODUCTION (SHOOTING)
  05 - Filming Your Tutorial               [NEW - camera, lighting, audio capture]

PART IV: POSTPRODUCTION (EDITING)
  06 - Kdenlive Fundamentals              [EXISTING Ch.5, trimmed to core editing]
  07 - Your First Edit (Beginner Project) [EXISTING Ch.4, updated with ForgeFrame]
  08 - Transitions & Compositing          [EXISTING Ch.6, split -- visual only]
  09 - Color Correction & Grading         [NEW - dedicated deep chapter]
  10 - Audio Production                   [NEW - dedicated deep chapter]
  11 - Pacing, Storytelling & Retention   [NEW - dedicated deep chapter]
  12 - Effects, Titles & Graphics         [EXISTING Ch.6 remainder, expanded]

PART V: DELIVERY
  13 - Formats, Codecs & Export           [EXISTING Ch.7, + render profiles]
  14 - Quality Control                    [NEW - QC automation, pre-publish checks]
  15 - Publishing to YouTube              [NEW - metadata, SEO, ff-publish]
  16 - Social Media & Repurposing         [NEW - shorts, clips, ff-social-clips]

PART VI: REFERENCE
  17 - Troubleshooting                    [EXISTING Ch.8, expanded]
  18 - Hardware & Software Guide          [EXISTING Ch.9, light update]
  19 - ForgeFrame Skill Reference         [NEW - full skill/tool catalog]
  20 - Resources & Community              [EXISTING Ch.10, expanded]

APPENDICES
  A  - ForgeFrame Workflow Cheatsheet     [NEW - one-page skill chain]
  B  - Kdenlive Keyboard Shortcuts        [NEW]
  C  - Glossary                           [NEW]
```

### Integration Pattern

ForgeFrame skills appear as inline callouts after the concept is taught:

```markdown
> **ForgeFrame:** Use `/ff-capture-prep` to generate this checklist
> automatically from your shot plan. It optimizes the shooting order
> to minimize setup changes.
```

Every callout includes a "you can also do this manually" note so the guide works without ForgeFrame.

## Components

### Chapter Responsibilities

**PART I: FOUNDATIONS**
- **Ch.00 (Getting Started):** ForgeFrame install, `ff-init`, vault setup, first workspace with `ff-new-project`. Does NOT teach video concepts.
- **Ch.01 (Pipeline Overview):** Mental model of full production pipeline, where ForgeFrame fits at each phase. Does NOT deep-dive any single phase.
- **Ch.02 (Audience & Scope):** Who this is for, prerequisites, learning path through handbook.

**PART II: PREPRODUCTION**
- **Ch.03 (Idea to Outline):** Objectives, brain dumping, teaching beats. Skills: `ff-video-idea-to-outline`, `ff-obsidian-video-note`.
- **Ch.04 (Scripts, Shots, Prep):** Script structure, shot categories, B-roll planning, pre-shoot checklist. Skills: `ff-tutorial-script`, `ff-shot-plan`, `ff-broll-whisperer`, `ff-capture-prep`.

**PART III: PRODUCTION**
- **Ch.05 (Filming):** Camera settings, lighting for workshop/talking-head/closeup, mic types, gain staging, sync strategy. Research needed. May be left as structured stub initially.

**PART IV: POSTPRODUCTION**
- **Ch.06 (Kdenlive Fundamentals):** Project setup, bin organization, timeline, 3-point editing, clip operations, proxies. Tools: `project_setup_profile`, `project_match_source`.
- **Ch.07 (First Edit):** Guided capstone: ingest → `ff-auto-editor` → `ff-rough-cut-review` → refine → preview render.
- **Ch.08 (Transitions & Compositing):** Cut types, dissolves, wipes, PiP. Tools: `composite_wipe`, `composite_pip`.
- **Ch.09 (Color):** Fix white balance and exposure, apply a LUT, basic correction workflow. Scope: "make it look right" not "create a cinematic look." Tools: `color_analyze`, `color_apply_lut`.
- **Ch.10 (Audio):** Loudness standards (LUFS), noise floor, compression, EQ for voice, monitoring. Tools: `ff-audio-cleanup`, `audio_normalize`, `audio_enhance`, `measure_loudness`.
- **Ch.11 (Pacing & Storytelling):** Why viewers leave, energy curves, WPM targets, scene length, hooks, chapter markers. Tools: `ff-pacing-meter`, `ff-voiceover-fixer`, `ff-rough-cut-review`.
- **Ch.12 (Effects & Titles):** Effects stack, title cards, lower thirds, keyframes. Tools: `effect_add`, `effect_list_common`, `title_cards_generate`.

**PART V: DELIVERY**
- **Ch.13 (Formats & Export):** Container vs codec, render profiles, fast start. Tools: `render_final`, `render_list_profiles`, `check_codec_available`.
- **Ch.14 (QC):** Pre-publish checklist, automated checks. Tools: `qc_check`, `media_check_vfr`, `media_transcode_cfr`.
- **Ch.15 (Publishing):** Title writing, description SEO, tags, chapters, thumbnails. Tools: `ff-publish`, `publish_bundle`.
- **Ch.16 (Social & Repurposing):** Clip extraction, platform formats, hook-first editing. Tools: `ff-social-clips`, `social_generate_package`.

**PART VI: REFERENCE**
- **Ch.17 (Troubleshooting):** VFR, audio drift, export failures, color shifts, performance.
- **Ch.18 (Hardware & Software):** Tiers, monitor recommendations, MLT ecosystem, alternatives.
- **Ch.19 (Skill Reference):** All 17 skills + key MCP tools catalog with trigger phrases, inputs, outputs.
- **Ch.20 (Resources):** Links, channels, specs, standards, asset sources.

**Appendices:** A (workflow cheatsheet), B (Kdenlive shortcuts), C (glossary).

## Data Flow

A video project flows through the handbook chapters in order:

```
Brain dump → Ch.03 (outline) → Ch.04 (script/shots/prep)
  → Ch.05 (film) → Ch.06 (ingest/setup) → Ch.07 (first cut)
  → Ch.08-12 (refine: transitions, color, audio, pacing, effects)
  → Ch.13 (export) → Ch.14 (QC) → Ch.15 (publish) → Ch.16 (social)
```

Each chapter teaches the concepts needed at that stage, then shows the ForgeFrame shortcut. ForgeFrame callout examples with commands throughout.

## Error Handling

**Handbook tone for errors:** Normalize mistakes with "Common Mistakes" callouts per chapter. Beginners expect professional results immediately -- the guide should prevent discouragement while teaching diagnostic thinking.

**ForgeFrame graceful degradation:** Every callout framed as optional. If a tool isn't available, the reader can still do the work manually in Kdenlive.

**Top 3 beginner failure modes addressed:**
1. VFR footage from phones → Ch.05 (prevention) + Ch.14 (detection) + Ch.17 (fix)
2. Audio too quiet/inconsistent → Ch.05 (gain staging) + Ch.10 (loudness) + Ch.14 (QC check)
3. Color looks "off" → Ch.05 (white balance) + Ch.09 (correction) + `color_analyze`

## Open Questions (Resolved)

1. **plugin.json registration:** All 17 skills should be enabled. Include this in implementation.
2. **Ch.05 (Filming) content:** Research-heavy. Stub the structure with headings and key points, research and fill during implementation.
3. **Color chapter depth:** "Fix white balance and exposure, apply a LUT, understand scopes enough to diagnose" -- practical correction, not cinematic grading.
4. **Examples directory:** Include ForgeFrame commands as examples in the `examples/` folder.
5. **Chapter renumbering:** Do a cleanup pass after restructure to fix cross-references.

## Approaches Considered

**Approach A: Chapter-by-Chapter Enhancement** -- Update existing chapters in place. Rejected: overloaded chapters (Ch.5 at 8k words), no home for missing topics (color, pacing, audio, publishing).

**Approach B: Restructure + Deepen** -- Selected. Full reorg with new chapters. Creates the one-stop shop, teaches concepts beginners need, gives every skill a natural home.

**Approach C: Two-Pass** -- Quick enhancements now, restructure later. Rejected: user wants the comprehensive version, and structural debt would limit usefulness.

## Next Steps

- [ ] Register all 17 skills in plugin.json
- [ ] Turn this design into a Forge spec (`/forge docs/plans/2026-04-09-handbook-restructure-design.md`)
- [ ] Research Ch.05 (Filming), Ch.09 (Color), Ch.10 (Audio), Ch.11 (Pacing) educational content
- [ ] Implement chapter-by-chapter
- [ ] Cleanup pass for cross-references after renumbering
