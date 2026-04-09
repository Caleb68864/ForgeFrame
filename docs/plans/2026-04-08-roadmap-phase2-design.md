---
date: 2026-04-08
topic: "Roadmap Phase 2 -- B-Roll, Pacing, Replay, Pattern Brain, Title Cards"
author: Caleb Bennett
status: draft
tags:
  - design
  - roadmap-phase2
---

# Roadmap Phase 2 -- Design

## Summary

Five features completing the ForgeFrame video production toolkit: B-Roll Whisperer (smart B-roll suggestions from transcript), Energy & Pacing Meter (segment-by-segment pacing analysis), Build Replay Generator (auto-create 1-minute highlight cuts), MYOG Pattern Brain (extract build data for overlays and printable notes), and Title Card Generator (chapter title cards for Kdenlive projects).

## Features

### 1. B-Roll Whisperer

**Problem:** Current auto_mark flags `broll_candidate` via keyword matching, but doesn't say WHAT kind of B-roll to shoot. "You need B-roll here" isn't as useful as "Show a close-up of the zipper being installed."

**Solution:** Enhance the marker pipeline to detect visual description patterns in transcript text and categorize B-roll needs: process_shot (show the action), material_closeup (show the material), tool_in_use (show the tool), result_reveal (show the finished result), measurement_shot (show the measurement).

**Components:**
- `detect_broll_opportunities(transcript)` in auto_mark pipeline -- pattern-based detection
- `/ff-broll-whisperer` skill -- Claude reads flagged segments and suggests specific B-roll shots
- `broll_suggestions.py` Python helper -- categorizes and formats suggestions
- MCP tool `broll_suggest` -- returns structured B-roll suggestion list
- Outputs to Obsidian note under `<!-- wvb:section:broll-suggestions -->`

### 2. Energy & Pacing Meter

**Problem:** The rough-cut review identifies pacing issues qualitatively, but doesn't quantify them. No way to see at a glance "minutes 3-5 are slow, minute 7 is too fast."

**Solution:** Calculate pacing metrics per segment: words-per-minute, speech density, word variety (unique/total ratio), average sentence length. Score each segment as fast/medium/slow. Flag weak intros (first 30s) and energy drops. Output a pacing report.

**Components:**
- `pacing_analyzer.py` pipeline -- calculates metrics from transcript
- `PacingReport` model -- per-segment scores + overall summary
- `/ff-pacing-meter` skill -- presents analysis with improvement suggestions
- MCP tool `pacing_analyze` -- returns pacing report
- CLI `wvb pacing analyze`

### 3. Build Replay Generator

**Problem:** After making a 15-minute tutorial, you often want a 1-minute highlight version for social media or YouTube Shorts.

**Solution:** Use chapter markers + high-confidence markers to select the most valuable 60 seconds. Generate a condensed Kdenlive project with just the highlights, connected by crossfades.

**Components:**
- `replay_generator.py` pipeline -- selects top segments, applies transitions
- Takes: markers (ranked), chapters, target_duration (default 60s)
- Outputs: condensed .kdenlive project in workspace
- MCP tool `replay_generate` -- configurable target duration
- CLI `wvb replay generate`

### 4. MYOG Pattern Brain

**Problem:** Tutorial videos contain structured build information (materials, measurements, steps, tips) but it's buried in narration. Extracting it for overlays or printable notes is manual.

**Solution:** Parse transcript for build-specific patterns: material mentions with quantities, measurements with units, step transitions, tips and warnings. Output as structured data, overlay text suggestions, and printable build notes markdown.

**Components:**
- `pattern_brain.py` pipeline -- regex + keyword extraction for build data
- `BuildData` model -- materials list, measurements, steps, tips
- `/ff-pattern-brain` skill -- Claude refines extracted data into polished build notes
- MCP tool `pattern_extract` -- returns structured build data
- Output: `build_notes.md` in workspace (printable), overlay text suggestions

### 5. Title Card Generator

**Problem:** Each chapter in a tutorial should have a title card. Creating them manually in Kdenlive is tedious.

**Solution:** Take chapter markers + project metadata and generate title card data. Each chapter gets: title text, timestamp, optional subtitle, duration (default 3 seconds). Output as Kdenlive guide markers with title metadata and as a standalone title cards JSON that can be imported or used for manual creation.

**Components:**
- `title_cards.py` pipeline -- generates title card data from chapters
- `TitleCard` model -- chapter_title, timestamp, subtitle, duration_seconds, style
- MCP tool `title_cards_generate` -- generates title cards for all chapters
- CLI `wvb title-cards generate`
- Outputs: title_cards.json in workspace, Kdenlive guides with title labels

## Architecture

All five features follow the same pattern as existing features:
```
transcript/markers (existing data)
  → new pipeline function (pure Python, no side effects)
    → new model (Pydantic)
      → MCP tool (thin wrapper)
      → CLI command (thin wrapper)
      → Skill (Claude instructions for refinement)
      → Obsidian note section (via NoteUpdater)
```

No new dependencies. No new infrastructure. Just new pipeline functions, models, tools, skills.

## Error Handling

All features: gracefully handle missing transcript/markers (return empty/default), log warnings for malformed data, idempotent on re-run.
