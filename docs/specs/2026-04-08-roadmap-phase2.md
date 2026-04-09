---
title: "Roadmap Phase 2 -- B-Roll, Pacing, Replay, Pattern Brain, Title Cards"
project: ForgeFrame
repo: Caleb68864/ForgeFrame
date: 2026-04-08
author: Caleb Bennett
quality_scores:
  outcome: 5
  scope: 5
  edges: 4
  criteria: 5
  decomposition: 5
  total: 24
---

# Roadmap Phase 2 -- Master Spec

## Outcome

Five new features completing the ForgeFrame video production toolkit. After implementation: B-roll suggestions with specific shot types, segment-by-segment pacing analysis, auto-generated 1-minute highlight cuts, structured build data extraction for overlays/printable notes, and chapter title card generation. Each feature has MCP tools, CLI commands, and Claude Code skills.

## Context

ForgeFrame v1 is complete with 414 tests, 24 MCP tools, 7 skills. All new features extend existing pipeline infrastructure -- transcript, markers, chapters, Kdenlive adapter, Obsidian notes. No new external dependencies needed.

## Requirements

1. All new skills MUST use ff- prefix
2. All new pipeline functions MUST be pure (no side effects except file writes to workspace)
3. All MCP tools MUST return structured dict with status/data pattern
4. All features MUST handle missing transcript/markers gracefully
5. All features MUST be idempotent on re-run
6. All existing 414 tests MUST still pass

## Sub-Specs

### Sub-Spec 1: B-Roll Whisperer
**Scope:** Enhanced B-roll detection in transcript, categorized suggestions (process_shot, material_closeup, tool_in_use, result_reveal, measurement_shot), skill, MCP tool, CLI.

**Files:**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/broll_suggestions.py`
- `workshop-video-brain/skills/ff-broll-whisperer/SKILL.md`
- `workshop-video-brain/src/workshop_video_brain/production_brain/skills/broll.py`
- `edit_mcp/server/tools.py` (add broll_suggest tool)
- `app/cli.py` (add broll group)
- `tests/unit/test_broll.py`

**Acceptance criteria:**
- [ ] `detect_broll_opportunities(transcript)` detects visual descriptions and categorizes them
- [ ] Categories: process_shot, material_closeup, tool_in_use, result_reveal, measurement_shot
- [ ] Each suggestion includes: timestamp, category, description of what to show, transcript context
- [ ] Detection patterns: "show", "look at", "you can see", tool names, material names, measurement words + visual context
- [ ] `/ff-broll-whisperer` skill reads suggestions and helps refine them
- [ ] MCP tool `broll_suggest` returns categorized suggestions
- [ ] CLI `wvb broll suggest <workspace>` works
- [ ] Saves to Obsidian note under `<!-- wvb:section:broll-suggestions -->`
- [ ] Empty transcript returns empty suggestions list
- [ ] Tests cover all 5 categories + empty + no-matches

**Dependencies:** none

### Sub-Spec 2: Energy & Pacing Meter
**Scope:** Per-segment pacing metrics (WPM, speech density, word variety, sentence length), segment scoring (fast/medium/slow), weak intro detection, pacing report model, skill, MCP tool.

**Files:**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/pacing_analyzer.py`
- `workshop-video-brain/src/workshop_video_brain/core/models/pacing.py`
- `workshop-video-brain/skills/ff-pacing-meter/SKILL.md`
- `edit_mcp/server/tools.py` (add pacing_analyze tool)
- `app/cli.py` (add pacing group)
- `core/models/__init__.py` (re-export)
- `tests/unit/test_pacing.py`

**Acceptance criteria:**
- [ ] `PacingSegment` model: start, end, wpm, speech_density, word_variety, avg_sentence_length, pace (fast/medium/slow), text_preview
- [ ] `PacingReport` model: segments list, overall_wpm, overall_pace, weak_intro (bool), energy_drops (list of time ranges), summary
- [ ] WPM calculation: word_count / duration_minutes per segment
- [ ] Pace thresholds: slow < 100 WPM, medium 100-160, fast > 160
- [ ] Speech density: speech_time / segment_duration
- [ ] Word variety: unique_words / total_words
- [ ] Weak intro: first 30s has pace=slow or speech_density < 0.3
- [ ] Energy drops: 3+ consecutive slow segments
- [ ] `/ff-pacing-meter` skill presents analysis with suggestions
- [ ] MCP tool `pacing_analyze` returns PacingReport
- [ ] CLI `wvb pacing analyze <workspace>` works
- [ ] Tests cover: normal tutorial, fast speaker, slow speaker, empty transcript, weak intro, energy drops

**Dependencies:** none

### Sub-Spec 3: Build Replay Generator
**Scope:** Auto-create condensed highlight timeline from markers + chapters. Configurable target duration. Generates Kdenlive project with crossfades between highlights.

**Files:**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/replay_generator.py`
- `edit_mcp/server/tools.py` (add replay_generate tool)
- `app/cli.py` (add replay group)
- `tests/unit/test_replay.py`

**Acceptance criteria:**
- [ ] `generate_replay(workspace_root, target_duration=60.0)` selects highest-value segments
- [ ] Selection algorithm: rank markers by score, greedily add segments until target_duration reached
- [ ] Each segment gets 2s padding on each end for context
- [ ] Adjacent segments (< 3s gap) merged into one
- [ ] Crossfade transitions (medium preset, 24 frames) between segments
- [ ] Outputs Kdenlive project to `projects/working_copies/{title}_replay_v{N}.kdenlive`
- [ ] Guide markers in replay project label each segment's source reason
- [ ] MCP tool `replay_generate` accepts optional target_duration parameter
- [ ] CLI `wvb replay generate <workspace> [--duration 60]` works
- [ ] Handles: no markers (error message), markers but not enough for target (use what's available), single long clip
- [ ] Tests cover: normal generation, insufficient markers, custom duration, segment merging

**Dependencies:** none (uses existing Kdenlive serializer + transition helpers)

### Sub-Spec 4: MYOG Pattern Brain
**Scope:** Extract build-specific data from transcript (materials with quantities, measurements with units, step transitions, tips/warnings). Generate overlay text suggestions and printable build notes.

**Files:**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/pattern_brain.py`
- `workshop-video-brain/src/workshop_video_brain/core/models/patterns.py`
- `workshop-video-brain/skills/ff-pattern-brain/SKILL.md`
- `workshop-video-brain/src/workshop_video_brain/production_brain/skills/pattern.py`
- `edit_mcp/server/tools.py` (add pattern_extract tool)
- `app/cli.py` (add pattern group)
- `core/models/__init__.py` (re-export)
- `tests/unit/test_pattern_brain.py`

**Acceptance criteria:**
- [ ] `BuildData` model: materials (list of {name, quantity, notes}), measurements (list of {value, unit, context}), steps (list of {number, description, timestamp}), tips (list of {text, timestamp}), warnings (list of {text, timestamp})
- [ ] Material extraction: regex for patterns like "X-Pac", "3 yards of", "number 5 zipper", quantity + material name
- [ ] Measurement extraction: regex for "X inches", "X cm", "X mm", "X yards", decimal numbers + units
- [ ] Step extraction: transcript segments following transition words ("first", "next", "step N"), numbered
- [ ] Tip extraction: segments with "tip", "trick", "pro tip", "here's a tip"
- [ ] Warning extraction: segments with "careful", "don't", "watch out", "safety"
- [ ] `generate_overlay_text(build_data)` produces short text strings suitable for video overlays
- [ ] `generate_build_notes(build_data, project_title)` produces printable markdown
- [ ] Build notes saved to workspace `reports/build_notes.md`
- [ ] `/ff-pattern-brain` skill helps Claude refine extracted data
- [ ] MCP tool `pattern_extract` returns BuildData
- [ ] Tests cover: MYOG transcript with materials/measurements, non-MYOG transcript (sparse results), empty transcript

**Dependencies:** none

### Sub-Spec 5: Title Card Generator
**Scope:** Generate title card data from chapter markers + project metadata. Output as JSON + Kdenlive guide markers with title labels.

**Files:**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/title_cards.py`
- `workshop-video-brain/src/workshop_video_brain/core/models/title_cards.py`
- `edit_mcp/server/tools.py` (add title_cards_generate tool)
- `app/cli.py` (add title-cards group)
- `core/models/__init__.py` (re-export)
- `tests/unit/test_title_cards.py`

**Acceptance criteria:**
- [ ] `TitleCard` model: chapter_title, timestamp_seconds, subtitle (optional), duration_seconds (default 3.0), style (default "standard")
- [ ] `generate_title_cards(workspace_root)` reads chapter markers from workspace, creates TitleCard per chapter
- [ ] First title card is always "Intro" at 0:00 if no chapter marker exists at start
- [ ] Title text derived from chapter marker label, cleaned (remove confidence scores, category prefixes)
- [ ] `title_cards_to_json(cards)` exports as JSON array
- [ ] `apply_title_cards_to_project(project, cards)` adds Kdenlive guide markers with "TITLE: {text}" labels
- [ ] Cards saved to workspace `reports/title_cards.json`
- [ ] MCP tool `title_cards_generate` returns list of title cards
- [ ] CLI `wvb title-cards generate <workspace>` works
- [ ] Tests cover: normal chapters, no chapters (just intro card), custom duration, application to Kdenlive project

**Dependencies:** none

## Edge Cases

1. All features: no transcript → graceful empty result with clear message
2. Replay generator: insufficient markers for target duration → use all available, note in report
3. Pattern brain: non-MYOG content → sparse results (some materials/steps but no measurements) -- that's fine
4. Title cards: no chapter markers → single "Intro" card at 0:00
5. Pacing: very short clips (< 5 seconds) → skip pacing analysis for those segments

## Out of Scope

- Computer vision for B-roll detection
- Actual title card image generation (just data + Kdenlive guides)
- Cross-project clip memory (separate future feature)
- AI-powered content generation (skills guide Claude, pipelines extract data)

## Verification

1. Run full test suite: `uv run pytest tests/ -v` -- all pass including new tests
2. Process a sample video through the full pipeline including all new features
3. Open generated Kdenlive projects (review + replay) -- both load correctly
4. Check workspace outputs: broll suggestions, pacing report, build notes, title cards
