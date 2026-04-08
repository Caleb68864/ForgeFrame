---
date: 2026-04-08
topic: "Voiceover Fixer"
author: Caleb Bennett
status: draft
tags:
  - design
  - voiceover-fixer
---

# Voiceover Fixer -- Design

## Summary

Add an `/ff-voiceover-fixer` skill that identifies rambling, repetitive, or filler-heavy transcript sections and presents them alongside tightened rewrites for voiceover re-recording. Uses existing transcript and marker data from the workspace. Output appends to the Obsidian video note.

## Approach Selected

**Skill + Obsidian note section** -- Claude Code skill reads workspace data via a Python helper, Claude rewrites flagged segments, results go into the Obsidian note under a dedicated section.

## Architecture

```
Existing: transcript → auto_mark → markers (mistake_problem, repetition, dead_air)
                                        ↓
New:    voiceover.py extracts flagged segments + context
                                        ↓
        /ff-voiceover-fixer skill gives Claude rewriting instructions
                                        ↓
        Claude produces: original vs rewritten pairs
                                        ↓
        voiceover.py saves to Obsidian note <!-- wvb:section:voiceover-fixes -->
```

## Components

| Component | Owns |
|---|---|
| `ff-voiceover-fixer/SKILL.md` | Rewriting instructions: tutorial tone, brevity, clarity rules, output format |
| `production_brain/skills/voiceover.py` | Extract flagged segments, group with context, format, save to note |

## Data Flow

1. `extract_fixable_segments(workspace_root)` reads `transcripts/*.json` and `markers/*.json`
2. Filters markers to: mistake_problem, repetition, dead_air (confidence > 0.5)
3. For each marker: pulls the transcript segment text + 2 segments of surrounding context
4. Groups overlapping/adjacent markers into single fix regions
5. `format_for_review(segments)` produces markdown with original text, timestamp, reason
6. Claude (via skill) reads the formatted segments and rewrites each one
7. `save_fixes_to_note()` appends to Obsidian note under bounded section

## Error Handling

- No markers found: skill says "No segments flagged for fixing. Your narration looks clean."
- No transcript in workspace: skill returns error with suggestion to run transcript generation first
- Obsidian note doesn't exist: creates one from template first

## Open Questions

None.

## Next Steps

- [ ] Build it
