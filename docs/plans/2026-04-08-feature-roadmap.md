---
date: 2026-04-08
topic: "ForgeFrame Feature Roadmap"
author: Caleb Bennett
status: active
tags:
  - roadmap
  - planning
---

# ForgeFrame Feature Roadmap

## Priority Stack (post Phase 1)

### Next: High Impact / Medium Difficulty

- **Voiceover Fixer** -- Rewrite rambling explanations into clean tutorial language. Low effort, big clarity boost.
- **B-Roll Whisperer** (enhance existing) -- Smarter B-roll suggestions beyond keyword matching. Flag where visuals are needed with specific suggestions.
- **Energy & Pacing Meter** (mostly built) -- Slow section detection, repetition, weak intros. Most of this exists in auto_mark + rough-cut-review.

### Then: Medium-High Value

- **Clip Memory System** -- Tag and reuse clips across projects (zippers, stitching, cutting, etc.). Turns footage into a reusable library.
- **Build Replay Generator** -- Auto-create shorts, recap cuts, "1-minute build" versions.

### Long-Term / Data-Dependent

- **Future You Assistant** -- Learns patterns over time, suggests improvements based on past videos.

### Niche But Powerful (MYOG domain)

- **MYOG Pattern Brain** -- Extract steps from builds, generate overlays, chapter structure, printable build notes. Partially covered by existing skills.

### Experimental / Advanced

- **Experiment Engine** -- Generate multiple edit styles (fast vs slow). Powerful but complex.

### Skip For Now

- **Tool-Aware Editing** -- Computer vision for tool detection. Requires CV models, not worth early.

## What's Already Built (Phase 1 Complete)

- Transcript generation (faster-whisper)
- Auto-marking (14 categories + phrase detection + repetition detection)
- Chapter generation
- Obsidian note CRUD with section-safe updates
- Review/selects timelines
- Kdenlive project adapter (parse/write/validate)
- Transitions + render pipeline
- 5 Production Brain skills (ff-prefixed)
- 21 MCP tools + 8 resources
- Full CLI with guided workflow
- 345 tests passing
