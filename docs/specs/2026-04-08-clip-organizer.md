---
title: "Clip Organizer -- Auto-Label + Search"
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

# Clip Organizer -- Master Spec

## Outcome

After implementation, running `wvb clips label` on a workspace auto-generates content labels for every clip from transcript and marker data. Running `wvb clips search "zipper"` returns matching clips ranked by relevance. Claude can do the same via MCP tools `clips_label` and `clips_search`. Labels persist as JSON in the workspace and are designed for future cross-project indexing.

## Context

ForgeFrame already has: media scanning (ffprobe), transcription (faster-whisper), auto-marking (14 categories + phrase/repetition detection), and a workspace model with structured folders. This feature adds a labeling layer on top of existing data -- no new external dependencies.

Design doc: [clip-organizer-design.md](../plans/2026-04-08-clip-organizer-design.md)

## Requirements

1. Each transcribed clip MUST get a ClipLabel with: content_type, topics, shot_type, has_speech, speech_density, summary, tags
2. Labels MUST be derived from existing transcript + marker data (no new AI calls)
3. Labels MUST be stored as JSON in `workspace/clips/` folder
4. Labeling MUST be idempotent (re-run overwrites, doesn't duplicate)
5. Clips without transcripts MUST get a minimal label (unlabeled, no-speech)
6. MCP tool `clips_search` MUST accept a text query and return ranked results
7. Search MUST match against tags, topics, summary, and content_type
8. CLI commands `wvb clips label` and `wvb clips search` MUST exist
9. All existing 363 tests MUST still pass

## Sub-Specs

### Sub-Spec 1: ClipLabel Model + Labeler Pipeline + Search + MCP + CLI + Tests
**Scope:** ClipLabel Pydantic model, clip labeling pipeline, clip search function, MCP tools, CLI commands, unit tests.

**Files:**
- `workshop-video-brain/src/workshop_video_brain/core/models/clips.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/clip_labeler.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/clip_search.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (add 2 tools)
- `workshop-video-brain/src/workshop_video_brain/app/cli.py` (add clips group)
- `workshop-video-brain/src/workshop_video_brain/core/models/__init__.py` (re-export)
- `workshop-video-brain/src/workshop_video_brain/workspace/folders.py` (add clips/ folder)
- `tests/unit/test_clip_labeler.py`
- `tests/unit/test_clip_search.py`

**Acceptance criteria:**
- [ ] ClipLabel model has fields: clip_ref, content_type, topics, shot_type, has_speech, speech_density, summary, tags, duration, source_path
- [ ] `generate_labels(workspace_root)` reads transcripts + markers, produces ClipLabel per asset
- [ ] Content type detected from marker distribution: tutorial_step, materials_overview, talking_head, b_roll, unlabeled
- [ ] Topics extracted from transcript text as distinctive noun phrases
- [ ] Shot type heuristic from markers: closeup, overhead, medium, b_roll
- [ ] Speech density calculated as speech-time / total-duration
- [ ] Summary is first ~100 chars of transcript, cleaned
- [ ] Tags are union of topics + content_type + shot_type, lowercased
- [ ] Clips without transcripts labeled as unlabeled with has_speech=false
- [ ] Labels saved as JSON to workspace clips/ folder
- [ ] Re-running is idempotent (overwrites existing labels)
- [ ] `search_clips(workspace_root, query)` returns ranked matches
- [ ] Search scores: exact tag match=1.0, topic match=0.8, summary word match=0.5
- [ ] MCP tools `clips_label` and `clips_search` registered and callable
- [ ] CLI commands `wvb clips label` and `wvb clips search` work
- [ ] workspace/clips/ added to WORKSPACE_FOLDERS
- [ ] All existing tests still pass

**Dependencies:** none (existing infrastructure sufficient)

## Edge Cases

1. No transcripts in workspace: labeler produces minimal labels for all clips (unlabeled, filename-only tags)
2. Search with no results: returns empty list with message
3. Malformed label JSON on disk: search skips it, logs warning
4. Very short clips (< 2 seconds): label with content_type based on filename heuristic, skip topic extraction

## Out of Scope

- Cross-project clip index (future feature)
- Computer vision for shot type detection
- Embedding-based semantic search
- Clip preview/thumbnail generation

## Verification

1. Create workspace with fixture media
2. Run ingest + transcribe + auto-mark
3. Run `wvb clips label` -- labels appear in clips/ folder
4. Run `wvb clips search "materials"` -- returns clips mentioning materials
5. Re-run label -- same output (idempotent)
6. All tests pass
