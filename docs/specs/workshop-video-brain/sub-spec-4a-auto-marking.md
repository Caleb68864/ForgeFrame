---
type: phase-spec
master_spec: "../2026-04-08-workshop-video-brain.md"
sub_spec: "4a"
title: "Auto-Marking + Review Ranking"
dependencies: [3]
date: 2026-04-08
---

# Sub-Spec 4a: Auto-Marking + Review Ranking

## Scope

Marker taxonomy with 14 categories, transcript-to-marker heuristics with keyword/rule matching, confidence scoring, clip ranking with best-guess-first and chronological fallback, selects list abstraction with JSON/Markdown export.

## Interface Contracts

### Provides (to Sub-Spec 4b)

- **Expanded marker model** in `core/models/markers.py`:
  - `MarkerCategory` enum with 14 values
  - `MarkerRule(keywords: list[str], category: MarkerCategory, base_confidence: float)`
  - `MarkerConfig(rules: list[MarkerRule], category_weights: dict[MarkerCategory, float], silence_threshold_seconds: float, segment_merge_gap_seconds: float)`

- **Auto-mark pipeline** at `edit_mcp/pipelines/auto_mark.py`:
  - `generate_markers(transcript: Transcript, silence_gaps: list[tuple], config: MarkerConfig, keywords: list[str] | None) -> list[Marker]`
  - Deterministic for same inputs

- **Review ranking** at `edit_mcp/pipelines/review_timeline.py`:
  - `rank_markers(markers: list[Marker], config: MarkerConfig) -> list[Marker]` -- sorted by score descending
  - `chronological_order(markers: list[Marker]) -> list[Marker]` -- sorted by start_seconds

- **Selects abstraction** at `edit_mcp/pipelines/selects_timeline.py`:
  - `SelectsEntry(marker: Marker, clip_ref, start, end, reason, usefulness_score)`
  - `build_selects(markers: list[Marker], min_confidence: float) -> list[SelectsEntry]`
  - `selects_to_json(selects) -> str`
  - `selects_to_markdown(selects) -> str`

### Requires (from Sub-Spec 3)

- `Transcript` and `TranscriptSegment` models
- Silence detection output (list of start/end tuples)
- Workspace with `transcripts/` and `markers/` directories populated

## Implementation Steps

### Step 1: Expand marker taxonomy

**Expand** `core/models/markers.py`:
- Ensure `MarkerCategory` enum has all 14 values: `intro_candidate`, `hook_candidate`, `materials_mention`, `step_explanation`, `measurement_detail`, `important_caution`, `mistake_problem`, `fix_recovery`, `broll_candidate`, `closeup_needed`, `dead_air`, `repetition`, `ending_reveal`, `chapter_candidate`
- Add `MarkerRule` model: `keywords`, `category`, `base_confidence`
- Add `MarkerConfig` model with default rules and weights

### Step 2: Create default marker rules

**Create** `edit_mcp/pipelines/marker_rules.py`:
- Default keyword lists per category:
  - `materials_mention`: ["you'll need", "materials", "supplies", "tools", "equipment", "grab"]
  - `step_explanation`: ["first", "next", "then", "step", "now we", "go ahead and"]
  - `important_caution`: ["careful", "watch out", "don't", "avoid", "safety", "make sure"]
  - `mistake_problem`: ["mistake", "wrong", "oops", "fix", "redo", "messed up"]
  - `chapter_candidate`: ["let's move on", "next up", "moving to", "section", "part"]
  - etc.
- Default category weights: `chapter_candidate=1.0`, `step_explanation=0.9`, `mistake_problem=0.85`, `important_caution=0.8`, `materials_mention=0.75`, `hook_candidate=0.7`, others lower
- All configurable via `MarkerConfig`

### Step 3: Create auto-mark pipeline

**Create** `edit_mcp/pipelines/auto_mark.py`:
- `generate_markers(transcript, silence_gaps, config, extra_keywords=None)`:
  1. Iterate transcript segments
  2. For each segment, check against all marker rules (keyword matching, case-insensitive)
  3. Calculate confidence: `rule.base_confidence * text_match_strength` (exact match = 1.0, partial = 0.7)
  4. Map silence gaps to `dead_air` markers
  5. Identify intro candidates (first 30 seconds of speech)
  6. Identify ending candidates (last 60 seconds of speech)
  7. Merge nearby markers of same category within `segment_merge_gap_seconds`
  8. Apply extra keywords (from shot plan) as additional matching rules
  9. Return list of `Marker` objects

### Step 4: Create ranking logic

**Add to** `edit_mcp/pipelines/review_timeline.py`:
- `rank_markers(markers, config)`:
  - Score = `confidence_score * category_weights[category]`
  - Sort descending by score
  - Return sorted list
- `chronological_order(markers)`:
  - Sort by `start_seconds` ascending
  - Return sorted list
- `group_by_clip(markers)`:
  - Group markers by `clip_ref`
  - Within each group, sort by start_seconds

### Step 5: Create selects abstraction

**Add to** `edit_mcp/pipelines/selects_timeline.py`:
- `SelectsEntry` dataclass
- `build_selects(markers, min_confidence=0.5)`:
  - Filter markers by confidence threshold
  - Exclude `dead_air` and `repetition` categories
  - Create `SelectsEntry` for each with usefulness score
- `selects_to_json(selects)` -- JSON array of entries
- `selects_to_markdown(selects)` -- markdown table with columns: Time, Category, Reason, Score

### Step 6: Write tests

**Create**:
- `tests/unit/test_auto_mark.py`:
  - Test with sample transcript containing tutorial keywords
  - Test silence gaps produce dead_air markers
  - Test determinism (same input → same output)
  - Test empty transcript (no markers, no crash)
  - Test all-silence input
  - Test marker merging (nearby segments grouped)
- `tests/unit/test_ranking.py`:
  - Test best-guess ranking orders by score
  - Test chronological ordering
  - Test selects filtering by confidence threshold

**Create** `tests/fixtures/transcripts/sample_tutorial.json` -- a realistic transcript JSON for a short MYOG tutorial.

## Verification Commands

```bash
uv run pytest tests/unit/test_auto_mark.py tests/unit/test_ranking.py -v
```

## Acceptance Criteria

- [ ] 14 marker categories defined
- [ ] Every marker includes: category, confidence_score, source_method, reason, clip_ref, time_range
- [ ] Keyword/rule-based matching with configurable keyword lists
- [ ] Silence gaps flagged as dead_air
- [ ] Nearby segments merged into ranges
- [ ] Best-guess-first ranking by confidence * weight
- [ ] Category weights configurable
- [ ] Chronological fallback ordering available
- [ ] Selects list exports as JSON and markdown
- [ ] Marker generation deterministic for same inputs
- [ ] Unit tests cover tutorial, multi-clip, empty, all-silence scenarios
