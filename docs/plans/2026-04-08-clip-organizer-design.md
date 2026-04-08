---
date: 2026-04-08
topic: "Clip Organizer -- Auto-Label + Search"
author: Caleb Bennett
status: draft
tags:
  - design
  - clip-organizer
---

# Clip Organizer -- Design

## Summary

Auto-label clips with content descriptions after transcription, then make them searchable via MCP. Each clip gets a ClipLabel with content type, topics, shot type, speech density, summary, and tags -- all derived from existing transcript and marker data. A new MCP search tool lets Claude (or the CLI) find clips by content across the workspace.

## Approach Selected

**Approach A: Auto-label + search within project** -- label clips from transcript data, add MCP search, design so cross-project index can be added later.

## Architecture

```
Existing pipeline: ingest → transcribe → auto_mark → markers

New step (after auto_mark):
  transcript + markers → clip_labeler → ClipLabel per asset → clips/ folder

New MCP tool:
  clip_search(query) → text match against ClipLabels → ranked results
```

## Components

| Component | Owns |
|---|---|
| `clip_labeler.py` (pipeline) | Generate ClipLabel for each asset from transcript + markers. Detect content type, extract topics, estimate shot type, calculate speech density, generate summary, derive tags. |
| `ClipLabel` model | Pydantic model: clip_ref, content_type, topics list, shot_type, has_speech, speech_density, summary, tags list, duration, source_path |
| `clip_search.py` (pipeline) | Search ClipLabels by text query. Score results by relevance. Return ranked matches. |
| MCP tool `clips_label` | Trigger labeling for workspace |
| MCP tool `clips_search` | Search clips by content query |
| CLI `wvb clips label` | CLI equivalent of labeling |
| CLI `wvb clips search` | CLI equivalent of search |

## Data Flow

1. After `auto_mark` completes, `clip_labeler.generate_labels()` runs
2. For each asset with a transcript:
   - **content_type**: classify from marker distribution (mostly step_explanation → "tutorial_step", mostly materials_mention → "materials_overview", few markers + high speech → "talking_head", low speech → "b_roll")
   - **topics**: extract distinctive noun phrases from transcript text (simple: split on common tutorial transition words, take key nouns)
   - **shot_type**: heuristic from markers (closeup_needed markers → likely "closeup", broll_candidate → "b_roll", default → "medium")
   - **speech_density**: `sum(segment durations with speech) / total clip duration`
   - **summary**: first 2 sentences of transcript text, cleaned up
   - **tags**: union of topics + content_type + shot_type, lowercased
3. Labels saved as `workspace/clips/{asset_stem}_label.json`
4. Search reads all label JSONs, matches query against: tags, topics, summary, content_type
5. Results scored: exact tag match = 1.0, topic match = 0.8, summary word match = 0.5
6. Results returned sorted by score with clip path, timestamp, summary

## Error Handling

- No transcript for a clip: label with content_type="unlabeled", has_speech=false, summary="No transcript available", tags from filename only
- Empty workspace: search returns empty list with message "No clips labeled yet"
- Malformed label JSON: skip file, log warning, continue searching others
- Re-running labeler: overwrites existing labels (idempotent)

## Open Questions

None.

## Approaches Considered

**Approach B: Cross-project library** -- Central index across all workspaces. Deferred -- the per-project labels this approach creates are the building blocks. Adding a cross-project index later just means aggregating these label files.

**Approach C: Obsidian-native** -- Tag clips in Obsidian and use Dataview. Rejected because it doesn't let Claude search clips during MCP sessions.

## Next Steps

- [ ] Build it via forge pipeline
