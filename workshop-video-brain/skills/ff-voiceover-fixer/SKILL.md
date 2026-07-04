---
name: ff-voiceover-fixer
description: >
  Rewrite flagged voiceover segments into clean tutorial language. Use when
  user says 'fix voiceover', 'clean up transcript', 'rewrite rambling',
  'voiceover fixes', 'clean up my script', or 'fix the dead air'.
---

# Skill: ff-voiceover-fixer

You rewrite flagged transcript segments into clean, practical tutorial
language. Your job is to remove the noise — the rambling, the false starts,
the dead air filler — and keep the useful instruction.

---

## When to invoke this skill

Trigger on any of these:
- "fix voiceover"
- "clean up transcript"
- "rewrite rambling"
- "voiceover fixes"
- "clean up my script"
- "fix the dead air"
- "rewrite my narration"
- "clean up these segments"
- When the user provides a transcript and wants narration improvements.

---

## Your process

### Step 1 — Extract flagged segments

Use the Python helper to extract segments from the workspace:

```python
from workshop_video_brain.production_brain.skills.voiceover import (
    extract_fixable_segments,
    format_for_review,
    save_fixes_to_note,
)
from pathlib import Path

workspace_root = Path("<workspace_path>")
segments = extract_fixable_segments(workspace_root)
review_md = format_for_review(segments)
```

The helper reads transcript JSON files from `{workspace_root}/transcripts/`
and marker JSON files from `{workspace_root}/markers/`. It filters to
`mistake_problem`, `repetition`, and `dead_air` markers with confidence > 0.5,
pulls context, and groups overlapping regions.

Alternatively, via the MCP tool:

```
voiceover_extract_segments(workspace_path="<workspace_path>")
```

### Step 2 — Review each flagged segment

For each segment returned, show the user:

```
## [MM:SS] – [MM:SS] | [category] (confidence: [0.XX])

**Why flagged:** [reason from marker]

**Original:**
> [original_text]

**Context before:** [context_before]
**Context after:** [context_after]
```

Present all segments before proposing any rewrites. Ask the user to confirm
they want rewrites or if any should be skipped.

### Step 3 — Rewrite each segment

Apply these rules to every segment you rewrite:

**Keep the information, cut the noise.**
Every rewrite must preserve the technical content. If the original explains
how to apply glue, the rewrite must still explain how to apply glue — just
without the false starts and ramblings.

**Tutorial tone: practical, conversational, not robotic.**
Write like you're talking to someone in your shop. Contractions are fine.
Short sentences are fine. Avoid passive voice. Avoid corporate-speak.
Wrong: "It should be noted that the surface must be prepared prior to..."
Right: "Prep the surface first — a light sand with 220 will do it."

**Target 50-70% of the original word count.**
Tighter is almost always better for tutorial narration.

**Preserve technical terms and measurements exactly.**
If the original says "three-quarter inch", the rewrite says "three-quarter
inch". Do not convert units. Do not paraphrase dimensions. Do not simplify
tool names.

**Dead air / pure filler — suggest a cut, not a rewrite.**
If the segment is only filler words with no instructional content ("uh so
um like you know uh"), recommend cutting it entirely. Do not invent content
to fill the gap.

**Repetition — merge the best parts.**
If two segments cover the same ground, produce one merged version that takes
the clearest explanation from each. Note which original segments were merged.

### Step 4 — Output the fixes

Produce a markdown document with this structure for each segment:

```markdown
## Fix [N]: [MM:SS] – [MM:SS]

**Category:** [mistake_problem | repetition | dead_air]
**Confidence:** [score]
**Reason:** [why it was flagged]

### Original

> [original text verbatim]

### Rewrite

[your rewritten version]

---
```

If the segment should be cut entirely:

```markdown
## Fix [N]: [MM:SS] – [MM:SS]

**Category:** dead_air
**Recommendation:** CUT — no instructional content, pure filler.

---
```

### Step 5 — Save to Obsidian note

After presenting fixes and getting user approval, save to the vault:

```python
note_path = save_fixes_to_note(
    workspace_root=workspace_root,
    vault_path=Path("<vault_path>"),
    fixes_markdown=approved_fixes_markdown,
)
```

This appends the fixes under the `voiceover-fixes` section boundary in the
video note. Confirm the path to the user when done.

---

## Re-recording a fix and dropping it back in

When a rewrite (or a "CUT") means the user re-records that line rather than
keeping the original audio, use the VO loop to place the new take on the
timeline without hand-nudging clips:

- `vo_plan` — split the corrected script into numbered VO cues and lay them on
  an audio track (each cue is a slot).
- `vo_attach` — attach the recorded take for a cue: it probes the file, places
  it on the track, and reports **drift** vs. the planned duration (so you know if
  the new read runs long/short against the picture).
- `vo_status` — the cue table: planned / recorded / missing, estimated vs.
  actual, drift. Use it to see which fixes still need a re-record.

Once the corrected VO is on the timeline, level it:

- `audio_normalize_two_pass` — match the new take's loudness to the rest
  (accurate two-pass `loudnorm`) so the drop-in doesn't jump in volume.
- `track_volume` / `track_eq` — set the voice track's overall level and roll off
  rumble/harshness so re-recorded lines sit with the originals.
- `audio_duck` — keyframe any music bed down under the corrected narration.

(For the file-level cleanup of raw audio, see `/ff-audio-cleanup`; for the full
finishing mix, `/ff-finishing`.)

---

## Quality guidelines

- Never invent technical content. If you don't know what the presenter meant,
  ask rather than guess.
- Do not change the order of instructions. Sequence matters in tutorials.
- Short rewrites are better than long ones, as long as nothing is lost.
- If a segment is genuinely good and the flag looks like a false positive,
  say so. Not every flagged segment needs a rewrite.
- After all fixes, give the user a one-paragraph summary: how many segments
  fixed, how many cut, estimated word-count reduction.

---

## Handoff

After producing the fixes:
- Summarize: "N segments rewritten, M cut. Estimated word count reduced by ~X%."
- Offer to update the Obsidian note with the fixes.
- If the transcript has pervasive quality issues (more than 30% of segments
  flagged), suggest a re-record rather than a full rewrite pass — then use the
  VO loop above (`vo_plan` → `vo_attach` → `vo_status`) to drop the new takes in.
- **Failure contract:** tools return a structured error dict (`error_type` +
  `suggestion`), never a traceback — read `suggestion` first. Full taxonomy: the
  vault's [[MCP Error Catalog]].
