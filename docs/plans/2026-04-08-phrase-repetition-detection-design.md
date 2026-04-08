---
date: 2026-04-08
topic: "Phrase + Repetition Detection for Auto-Marking"
author: Caleb Bennett
status: draft
tags:
  - design
  - mistake-hunter
  - auto-marking
---

# Phrase + Repetition Detection -- Design

## Summary

Add two new marker sources to the existing `auto_mark.py` pipeline: regex-based filler/redo phrase detection and text-similarity-based repetition detection. These fill the gap between the keyword-based tutorial markers we already have and the "mistake hunter" concept from the original Phase 1 PRD.

## Approach Selected

**Extend existing pipeline** -- add new detection functions that produce `Marker` objects using the existing model, then integrate them into `generate_markers()`. No new modules or restructuring needed.

## Architecture

```
Existing auto_mark.py pipeline:
  transcript segments → keyword matching → markers
  silence gaps → dead_air markers
  position heuristics → intro/ending markers

New additions (slot in alongside existing):
  transcript segments → phrase_detection → redo/filler markers
  transcript segments → repetition_detection → repetition markers
```

Both produce standard `Marker` objects with the existing `MarkerCategory` enum values. No new categories needed -- `mistake_problem` covers redo phrases, `repetition` covers repeated content.

## Components

### 1. Phrase Detector (`detect_phrases`)

**What it owns:** Regex-based detection of redo phrases, filler words, and false starts in transcript segments.

**What it does NOT own:** Silence detection (already exists), keyword matching (already exists).

**Patterns to detect:**
- Redo phrases: "let me redo", "actually wait", "hold on", "let me start over", "that's wrong", "scratch that", "one more time"
- Filler clusters: 3+ "um"/"uh"/"like"/"you know" within 10 seconds
- False starts: sentence fragments followed by a restart of the same thought (same first 3 words within 15 seconds)

**Output:** `list[Marker]` with category `mistake_problem`, confidence based on pattern strength (exact redo phrase = 0.9, filler cluster = 0.6, false start = 0.5).

### 2. Repetition Detector (`detect_repetition`)

**What it owns:** Finding segments where the speaker says essentially the same thing twice.

**What it does NOT own:** Chapter-level topic detection (that's auto_chapters territory).

**Approach:** Compare each segment's text against the next N segments (window = 5). Use simple word overlap ratio (Jaccard similarity on word sets). If similarity > 0.6 and segments are within 60 seconds, flag the later one as repetition.

**Output:** `list[Marker]` with category `repetition`, confidence = similarity score, reason = "Similar to segment at {time}: '{first 50 chars}'".

### 3. Aggregated Mistake Export

Add `export_mistakes(markers: list[Marker], output_path: Path) -> Path` that filters markers to mistake-related categories (dead_air, mistake_problem, repetition) and writes a clean `mistakes.json`.

## Data Flow

```
Transcript (from whisper_engine)
  → detect_phrases(transcript) → phrase markers
  → detect_repetition(transcript) → repetition markers
  → existing generate_markers() merges all sources
  → export_mistakes() writes mistakes.json to workspace
```

## Error Handling

- Empty transcript: return empty marker list (no crash)
- Very short segments (< 2 words): skip similarity comparison
- Regex compilation failure: log warning, skip that pattern, continue with others

## Open Questions

None -- this is a straightforward extension of existing infrastructure.

## Approaches Considered

**Approach A: New mistake_hunter module** -- Create a separate `libs/mistake_hunter/` package as the PRD suggested. Rejected because it duplicates infrastructure that already exists in `auto_mark.py` and creates unnecessary module boundaries.

**Approach B: Extend existing pipeline (Selected)** -- Add functions to the existing auto_mark pipeline. Simpler, uses existing models, no restructuring needed.

## Next Steps

- [ ] Turn this design into a Forge spec (`/forge docs/plans/2026-04-08-phrase-repetition-detection-design.md`)
- [ ] Build and test
- [ ] Save the original Phase 1 PRD as reference in docs/reference/
