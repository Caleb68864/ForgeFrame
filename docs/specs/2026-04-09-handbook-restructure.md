---
title: "Handbook Restructure -- Video Editing Guide + ForgeFrame Integration"
project: ForgeFrame
repo: Caleb68864/ForgeFrame
date: 2026-04-09
author: Caleb Bennett
quality_scores:
  outcome: 5
  scope: 5
  edges: 4
  criteria: 3
  decomposition: 4
  total: 21
---

# Handbook Restructure -- Video Editing Guide + ForgeFrame Integration

## Outcome

The video editing handbook at `docs/video-editing-guide/` is restructured from 10 chapters into a 20-chapter, 6-part guide that: (1) teaches video editing concepts to amateur tutorial creators, (2) integrates all 17 ForgeFrame skills as inline callouts throughout, (3) fills educational gaps in color correction, pacing/storytelling, audio production, and filming, and (4) works as a standalone resource even without ForgeFrame installed. All 17 skills registered in plugin.json.

## Context

ForgeFrame Phase 1+2+3 is complete: 17 skills, 88 MCP tools, 28 pipelines. A video editing handbook exists with 10 chapters (~40k words) covering Kdenlive workflows. Gap analysis revealed: (1) only 3 chapters mention ForgeFrame at all, (2) color/pacing/audio taught superficially, (3) no filming chapter, (4) no publishing/social chapters, (5) no ForgeFrame getting started guide, (6) 11 of 17 skills not registered in plugin.json.

Design document: `docs/plans/2026-04-09-handbook-restructure-design.md`
Research files: `references/research-color-correction.md`, `references/research-pacing-retention.md`, `references/research-audio-production.md`, `references/research-filming-basics.md`

### ForgeFrame Callout Pattern

All chapters use this inline pattern after teaching a concept:

```markdown
> **ForgeFrame:** Use `/ff-capture-prep` to generate this checklist
> automatically from your shot plan. It optimizes the shooting order
> to minimize setup changes.
```

Every callout includes a "you can also do this manually" fallback.

### Existing Chapter Mapping

| Old # | Old Title | New # | New Title | Action |
|-------|-----------|-------|-----------|--------|
| README | So You Want to Be a Video Editor | README | (updated) | Update |
| -- | -- | 00 | Getting Started with ForgeFrame | NEW |
| 01 | Pipeline Overview | 01 | The Video Production Pipeline | Update |
| 02 | Audience & Learning Goals | 02 | Audience, Learning Goals & Scope | Light update |
| 03 | Preproduction | 03+04 | Split into Idea→Outline + Scripts/Shots/Prep | Refactor |
| 04 | Beginner Project | 07 | Your First Edit | Move + update |
| 05 | Kdenlive Workflows | 06 | Kdenlive Fundamentals | Trim + update |
| -- | -- | 05 | Filming Your Tutorial | NEW |
| 06 | Transitions, Effects, Audio | 08+12 | Split into Transitions + Effects/Titles | Refactor |
| -- | -- | 09 | Color Correction & Grading | NEW |
| -- | -- | 10 | Audio Production | NEW |
| -- | -- | 11 | Pacing, Storytelling & Retention | NEW |
| 07 | Formats, Codecs, Export | 13 | Formats, Codecs & Export | Update |
| -- | -- | 14 | Quality Control | NEW |
| -- | -- | 15 | Publishing to YouTube | NEW |
| -- | -- | 16 | Social Media & Repurposing | NEW |
| 08 | Troubleshooting | 17 | Troubleshooting | Update |
| 09 | Hardware & Software | 18 | Hardware & Software Guide | Light update |
| -- | -- | 19 | ForgeFrame Skill Reference | NEW |
| 10 | Resources & Community | 20 | Resources & Community | Update |
| -- | -- | A/B/C | Appendices | NEW |

## Requirements

1. All 20 chapters + README + 3 appendices must exist as markdown files in `docs/video-editing-guide/`
2. All 17 ForgeFrame skills must have at least one inline callout in the appropriate chapter
3. All 17 skills must be registered in `workshop-video-brain/plugin.json`
4. New educational chapters (05, 09, 10, 11) must use content from research reference files
5. Every ForgeFrame callout must include a manual fallback ("you can also...")
6. Chapter 19 (Skill Reference) must catalog all 17 skills with: name, trigger phrases, inputs, outputs, which chapter covers the concept
7. Existing handbook content must be preserved (moved, not deleted) during restructure
8. Cross-references between chapters must use correct new chapter numbers
9. README must be updated with the new 6-part structure and chapter listing
10. The `examples/` directory must include ForgeFrame command examples

## Sub-Specs

### Sub-Spec 1: Infrastructure -- File Restructure + Plugin Registration

**Scope:** Rename existing chapter files to new numbering, create stub files for all new chapters, register all 17 skills in plugin.json, update README with new structure.

**Files:**
- Rename: all existing `docs/video-editing-guide/*.md` files to new numbering
- Create: stub files for chapters 00, 05, 09, 10, 11, 14, 15, 16, 19, appendices A/B/C
- Modify: `workshop-video-brain/plugin.json` (add 11 missing skills)
- Modify: `docs/video-editing-guide/README.md` (new structure)

**Acceptance criteria:**
- [ ] All 20 chapter files exist with correct names (00 through 20)
- [ ] 3 appendix files exist (appendix-a, appendix-b, appendix-c)
- [ ] New chapter stubs have correct title, part heading, and placeholder sections
- [ ] Existing content preserved in renamed files (no content loss)
- [ ] plugin.json contains all 17 skills with correct paths
- [ ] README lists all 20 chapters grouped by 6 parts
- [ ] `uv run pytest tests/ -v` still passes (no code changes break tests)

**Dependencies:** none

### Sub-Spec 2: Chapter 00 -- Getting Started with ForgeFrame

**Scope:** New chapter covering ForgeFrame installation, `ff-init`, vault setup, first workspace creation with `ff-new-project`. First chapter a reader encounters for ForgeFrame-specific content.

**Files:**
- Modify: `docs/video-editing-guide/00-getting-started-with-forgeframe.md`

**Acceptance criteria:**
- [ ] Covers: what ForgeFrame is (1-2 paragraphs), prerequisites (Python 3.12+, Kdenlive, FFmpeg)
- [ ] Covers: installing the Claude Code plugin
- [ ] Covers: running `ff-init` with expected output
- [ ] Covers: creating first project with `ff-new-project` walkthrough
- [ ] Covers: vault structure explanation (what each folder is for)
- [ ] Covers: "what's next" pointer to Ch.01 (Pipeline Overview)
- [ ] Does NOT teach video editing concepts (that's later chapters)
- [ ] Includes troubleshooting sidebar for common setup issues

**Dependencies:** 1

### Sub-Spec 3: Part I -- Foundations (Ch.01-02 Updates)

**Scope:** Update Ch.01 Pipeline Overview with ForgeFrame phase mapping. Light update to Ch.02 with learning path through new structure.

**Files:**
- Modify: `docs/video-editing-guide/01-pipeline-overview.md`
- Modify: `docs/video-editing-guide/02-audience-and-learning-goals.md`

**Acceptance criteria:**
- [ ] Ch.01: ForgeFrame skill names appear next to each pipeline phase in the overview diagram/table
- [ ] Ch.01: "Where ForgeFrame Fits" section shows which skills automate which phases
- [ ] Ch.02: Learning path updated to reference new chapter numbers
- [ ] Ch.02: Chapter-to-skill mapping table added (which chapter teaches what, which skill automates it)
- [ ] Existing educational content preserved, not removed

**Dependencies:** 1

### Sub-Spec 4: Part II -- Preproduction (Ch.03-04)

**Scope:** Refactor existing Ch.03 (Preproduction) into two chapters. Ch.03 covers idea-to-outline with `ff-video-idea-to-outline` and `ff-obsidian-video-note` callouts. Ch.04 covers scripts, shots, and capture prep with `ff-tutorial-script`, `ff-shot-plan`, `ff-broll-whisperer`, `ff-capture-prep` callouts.

**Files:**
- Modify: `docs/video-editing-guide/03-from-idea-to-outline.md`
- Modify: `docs/video-editing-guide/04-scripts-shot-plans-capture-prep.md`

**Acceptance criteria:**
- [ ] Ch.03: Covers objective writing, brain dumping, teaching beats structure
- [ ] Ch.03: `ff-video-idea-to-outline` callout with example input/output
- [ ] Ch.03: `ff-obsidian-video-note` callout explaining vault integration
- [ ] Ch.04: Covers script structure, shot list categories, B-roll planning, pre-shoot checklist
- [ ] Ch.04: `ff-tutorial-script`, `ff-shot-plan`, `ff-broll-whisperer`, `ff-capture-prep` callouts
- [ ] All existing preproduction content from old Ch.03 preserved (redistributed between 03/04)
- [ ] Each callout includes manual fallback

**Dependencies:** 1

### Sub-Spec 5: Part III -- Ch.05 Filming Your Tutorial

**Scope:** New chapter teaching amateur tutorial creators how to film. Uses research from `references/research-filming-basics.md`. Covers camera settings, lighting, audio capture, VFR prevention, budget gear.

**Files:**
- Modify: `docs/video-editing-guide/05-filming-your-tutorial.md`
- Read: `references/research-filming-basics.md`

**Acceptance criteria:**
- [ ] Camera settings section: resolution, frame rate (30fps default), shutter speed (180-degree rule), manual white balance
- [ ] Lighting section: 3 setups (talking head, overhead bench, detail closeup) with diagrams described in text
- [ ] Audio capture section: mic types by scenario (lav, shotgun, USB), gain staging (-12dB peaks)
- [ ] Sync strategy section: clap/slate method, timecode mention
- [ ] VFR prevention section: which devices default to VFR, how to force CFR
- [ ] "Minimum viable setup" section: prioritized gear list ($100-120 budget)
- [ ] "Common filming mistakes" sidebar
- [ ] `ff-capture-prep` callout for generating the pre-shoot checklist
- [ ] Chapter works standalone without ForgeFrame

**Dependencies:** 1

### Sub-Spec 6: Part IV-A -- Ch.06-07 Kdenlive Fundamentals + First Edit

**Scope:** Trim existing Ch.05 (Kdenlive Workflows) to core editing fundamentals as new Ch.06. Update existing Ch.04 (Beginner Project) as new Ch.07 with ForgeFrame workflow integration.

**Files:**
- Modify: `docs/video-editing-guide/06-kdenlive-fundamentals.md`
- Modify: `docs/video-editing-guide/07-your-first-edit.md`

**Acceptance criteria:**
- [ ] Ch.06: Core editing only (project setup, bins, timeline, 3-point editing, clip ops, proxies)
- [ ] Ch.06: `project_setup_profile` and `project_match_source` callouts for project settings
- [ ] Ch.06: Transitions, color, audio, effects content removed (moved to their own chapters)
- [ ] Ch.07: Beginner project updated to use ForgeFrame workflow: ingest → `ff-auto-editor` → `ff-rough-cut-review` → refine
- [ ] Ch.07: Each step shows both manual way and ForgeFrame way
- [ ] Existing educational content preserved (redistributed, not deleted)

**Dependencies:** 1

### Sub-Spec 7: Part IV-B -- Ch.08 Transitions + Ch.12 Effects

**Scope:** Split existing Ch.06 (Transitions, Effects, Audio) into Ch.08 (transitions/compositing only) and Ch.12 (effects/titles/graphics). Add ForgeFrame callouts.

**Files:**
- Modify: `docs/video-editing-guide/08-transitions-and-compositing.md`
- Modify: `docs/video-editing-guide/12-effects-titles-graphics.md`

**Acceptance criteria:**
- [ ] Ch.08: Cut types (hard/J/L), dissolves, wipes, PiP layouts
- [ ] Ch.08: "When NOT to use transitions" guidance (restraint, narrative purpose)
- [ ] Ch.08: `composite_wipe` and `composite_pip` callouts with parameter examples
- [ ] Ch.12: Kdenlive effects stack, effect ordering, title cards, lower thirds, keyframe basics
- [ ] Ch.12: `effect_add`, `effect_list_common`, `title_cards_generate` callouts
- [ ] Audio content from old Ch.06 removed (moved to Ch.10)
- [ ] Each callout includes manual fallback

**Dependencies:** 1

### Sub-Spec 8: Part IV-C -- Ch.09 Color Correction & Grading

**Scope:** New chapter teaching color correction for beginners. Uses research from `references/research-color-correction.md`. Practical correction, not cinematic grading.

**Files:**
- Modify: `docs/video-editing-guide/09-color-correction-and-grading.md`
- Read: `references/research-color-correction.md`

**Acceptance criteria:**
- [ ] Core concepts explained: white balance, exposure, contrast, saturation (beginner language)
- [ ] Scope reading section: waveform, vectorscope, histogram -- what to look for, with examples
- [ ] Correction vs grading explained: correction first (fix problems), grading optional (create looks)
- [ ] 5-step practical workflow: exposure → white balance → contrast → saturation → skin check
- [ ] Lift/Gamma/Gain effect explained as the primary tool (handles 90% of correction)
- [ ] LUT section: when to use, when not to, apply AFTER correction
- [ ] BT.709 section: what it is, why not to change it, what `color_analyze` tells you
- [ ] "What good looks like for YouTube tutorials" section (natural, clean, slightly warm)
- [ ] "Common color mistakes" sidebar
- [ ] `color_analyze` and `color_apply_lut` callouts
- [ ] Best single tip highlighted: good lighting > color correction

**Dependencies:** 1

### Sub-Spec 9: Part IV-D -- Ch.10 Audio Production

**Scope:** New chapter teaching audio production for YouTube tutorials. Uses research from `references/research-audio-production.md`.

**Files:**
- Modify: `docs/video-editing-guide/10-audio-production.md`
- Read: `references/research-audio-production.md`

**Acceptance criteria:**
- [ ] YouTube loudness standard explained: -14 LUFS target, -1 dBTP true peak
- [ ] Signal chain section with correct order: noise reduction → EQ → compression → limiter → normalization
- [ ] Each processing step explained in plain English (compression = "makes quiet words louder and loud words quieter")
- [ ] EQ for voice: high-pass 80Hz, cut mud 200-400Hz, boost presence 2-5kHz
- [ ] Compression settings: 3:1-4:1 ratio, 3-6 dB gain reduction
- [ ] Room treatment section: budget DIY solutions (blankets, rugs, bookshelves)
- [ ] Monitoring section: why headphones matter during recording AND editing
- [ ] "Before/after" description of what good processing sounds like
- [ ] `ff-audio-cleanup` callout (applies entire chain automatically)
- [ ] `audio_normalize`, `audio_enhance`, `measure_loudness` callouts
- [ ] Best single tip: get mic closer to mouth

**Dependencies:** 1

### Sub-Spec 10: Part IV-E -- Ch.11 Pacing, Storytelling & Retention

**Scope:** New chapter teaching pacing and viewer engagement for tutorial content. Uses research from `references/research-pacing-retention.md`.

**Files:**
- Modify: `docs/video-editing-guide/11-pacing-storytelling-retention.md`
- Read: `references/research-pacing-retention.md`

**Acceptance criteria:**
- [ ] Retention data section: when/why viewers leave (20% in 15 sec, cliff at 1 min)
- [ ] Speaking pace: 140-160 WPM target, slow for complex steps, never exceed 180
- [ ] Visual change frequency: 15-25s talking head, 3-8s process shots, up to 40s engaging closeups
- [ ] Energy curve table for 10-20 min tutorial (hook → setup → core → bumps → climax → payoff)
- [ ] Hook formula: show result in 5 sec, state who/what in one sentence, pattern interrupt at 25-35s
- [ ] B-roll as pacing tool: 40-70% of runtime, cut at sentence breaks, let breathe 1-2s past VO
- [ ] Chapter markers: +25% watch time, convert bounces to skips
- [ ] Pro creator analysis: Savage, Diresta, Kampf structural patterns
- [ ] "Common pacing mistakes" sidebar
- [ ] `ff-pacing-meter` and `ff-voiceover-fixer` callouts
- [ ] "Good abandonment" concept explained (YouTube doesn't penalize tutorial viewers leaving after answer)

**Dependencies:** 1

### Sub-Spec 11: Part V -- Ch.13-14 Export + Quality Control

**Scope:** Update existing Ch.07 (Formats/Codecs) as new Ch.13 with render profile callouts. New Ch.14 covering QC automation.

**Files:**
- Modify: `docs/video-editing-guide/13-formats-codecs-export.md`
- Modify: `docs/video-editing-guide/14-quality-control.md`

**Acceptance criteria:**
- [ ] Ch.13: Existing codec/format content preserved + render profile table (youtube-1080p, youtube-4k, vimeo-hq, master-prores, master-dnxhr)
- [ ] Ch.13: `render_final`, `render_list_profiles` callouts
- [ ] Ch.13: Fast start / movflags explanation for streaming
- [ ] Ch.14: Pre-publish QC checklist (visual + automated)
- [ ] Ch.14: `qc_check` tool explained (black frames, silence, loudness, clipping, file size)
- [ ] Ch.14: VFR detection and transcode workflow with `media_check_vfr` / `media_transcode_cfr`
- [ ] Ch.14: "What each QC check catches" table with examples
- [ ] Ch.14: What to do when QC fails (go back to which chapter)

**Dependencies:** 1

### Sub-Spec 12: Part V -- Ch.15-16 Publishing + Social

**Scope:** New Ch.15 covering YouTube publishing workflow. New Ch.16 covering social media repurposing.

**Files:**
- Modify: `docs/video-editing-guide/15-publishing-to-youtube.md`
- Modify: `docs/video-editing-guide/16-social-media-repurposing.md`

**Acceptance criteria:**
- [ ] Ch.15: Title writing guidance (searchable vs curiosity vs how-to)
- [ ] Ch.15: Description SEO basics (keywords, chapters, links)
- [ ] Ch.15: Tags and hashtags strategy
- [ ] Ch.15: Chapter markers from timeline markers
- [ ] Ch.15: Thumbnail guidance (1280x720, contrast, readable text, face)
- [ ] Ch.15: `ff-publish` and `publish_bundle` callouts with example output
- [ ] Ch.16: Why repurpose (reach, discoverability, algorithm)
- [ ] Ch.16: Platform aspect ratios (9:16 shorts, 1:1 square, 16:9 landscape)
- [ ] Ch.16: Hook-first editing for shorts (different from long-form)
- [ ] Ch.16: `ff-social-clips` and `social_generate_package` callouts
- [ ] Both chapters work without ForgeFrame (manual publishing workflow included)

**Dependencies:** 1

### Sub-Spec 13: Part VI -- Reference Chapters + Appendices

**Scope:** Update Ch.17-18, create new Ch.19 (Skill Reference) and Ch.20 (Resources update), create appendices A/B/C.

**Files:**
- Modify: `docs/video-editing-guide/17-troubleshooting.md`
- Modify: `docs/video-editing-guide/18-hardware-and-software.md`
- Modify: `docs/video-editing-guide/19-forgeframe-skill-reference.md`
- Modify: `docs/video-editing-guide/20-resources-and-community.md`
- Modify: `docs/video-editing-guide/appendix-a-workflow-cheatsheet.md`
- Modify: `docs/video-editing-guide/appendix-b-kdenlive-shortcuts.md`
- Modify: `docs/video-editing-guide/appendix-c-glossary.md`

**Acceptance criteria:**
- [ ] Ch.17: VFR troubleshooting with `media_check_vfr` callout added
- [ ] Ch.17: Audio troubleshooting references Ch.10 and `ff-audio-cleanup`
- [ ] Ch.18: Monitor calibration sidebar for color work (reference Ch.09)
- [ ] Ch.19: All 17 skills cataloged with: name, description, trigger phrases, inputs, outputs, which chapter covers the concept
- [ ] Ch.19: Key MCP tools listed (render, QC, color, effects, compositing, VFR, archive)
- [ ] Ch.20: Updated with new resource links for color, audio, pacing
- [ ] Appendix A: One-page workflow cheatsheet (idea → ... → publish) with skill names at each step
- [ ] Appendix B: Essential Kdenlive keyboard shortcuts table
- [ ] Appendix C: Glossary of terms used throughout the handbook (LUFS, BT.709, VFR, CFR, LUT, etc.)

**Dependencies:** 1

### Sub-Spec 14: Cross-Reference Cleanup + Examples

**Scope:** Fix all cross-references between chapters after renumbering. Add ForgeFrame command examples to `examples/` directory. Final consistency pass.

**Files:**
- Modify: all chapter files (cross-reference updates)
- Create/modify: `docs/video-editing-guide/examples/` files

**Acceptance criteria:**
- [ ] No chapter references old numbering (grep for "Chapter 03" style references)
- [ ] All "see Chapter X" references point to correct new chapter
- [ ] All internal links between chapters work
- [ ] `examples/` contains ForgeFrame command examples for key workflows
- [ ] No broken wikilinks or markdown links
- [ ] README table of contents matches actual chapter files

**Dependencies:** 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13

## Edge Cases

1. **Existing bookmarks/references to old chapter numbers:** The restructure changes all chapter numbers. Sub-spec 14 does a cleanup pass. External references (outside this repo) will break -- this is acceptable.
2. **Chapter 05 (Filming) research depth:** Use content from `references/research-filming-basics.md` as the primary source. If a topic needs more depth than the research provides, note it as a future improvement rather than blocking.
3. **Oversized chapters:** If any chapter exceeds 5k words after updates, consider splitting. Flag in the worker report but don't split without team lead approval.
4. **ForgeFrame callout density:** Don't force callouts where they don't fit. Some sections are pure concept teaching with no ForgeFrame equivalent -- that's fine.
5. **Plugin.json skill paths:** Verify each skill has a valid SKILL.md at the registered path before adding to plugin.json.
6. **Handbook tone consistency:** Amateur-friendly, practical, not academic. "Fix white balance" not "correct chromatic aberration."

## Out of Scope

- HDR workflows (deferred, most tutorial creators on SDR)
- Multi-camera editing (complex, niche)
- Motion graphics / animation (Blender territory)
- Advanced audio mastering (beyond compression/EQ/normalization)
- Music licensing / copyright
- Live streaming
- Writing new ForgeFrame skills or MCP tools
- Modifying any Python source code

## Verification

1. All 20 chapter files + README + 3 appendices exist in `docs/video-editing-guide/`
2. `grep -r "ff-" docs/video-editing-guide/` returns hits in appropriate chapters for all 17 skills
3. `plugin.json` contains 17 skill entries with valid paths
4. `grep -rn "Chapter 0[1-9]\|Chapter 10" docs/video-editing-guide/` returns no references to old numbering
5. Each new chapter (00, 05, 09, 10, 11, 14, 15, 16, 19, A, B, C) has substantive content (>500 words)
6. README table of contents matches actual files
7. No Python tests broken: `uv run pytest tests/ -v`
