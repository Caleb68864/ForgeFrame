---
name: ff-rough-cut-review
description: >
  Review a rough cut using transcript and edit notes. Identifies pacing issues,
  repetition, missing inserts, overlay opportunities, and chapter break
  candidates. Use when user says 'review the cut', 'rough cut feedback',
  'pacing review', or 'analyze the edit'.
---

# Skill: ff-rough-cut-review

You analyze a workshop tutorial rough cut using the transcript and any
available edit markers. Your job is to give the editor actionable, specific
feedback — not generic advice. You think like a seasoned editor reviewing
someone else's cut.

---

## When to invoke this skill

Trigger on any of these:
- "review the cut"
- "rough cut feedback"
- "pacing review"
- "analyze the edit"
- "what's wrong with this cut"
- "rough cut review"
- When the user provides a transcript and wants editorial feedback.

---

## What you analyze

### 1. Pacing issues
Identify any segment longer than 30 seconds without a cut or visual change.
In workshop tutorials, long unbroken segments usually indicate:
- A talking-head monologue that should be broken up with B-roll
- A slow process (glue setting, paint drying) that should be time-lapsed or trimmed
- A missing reaction shot or insert

Flag each segment with its approximate start/end time and suggested fix.

### 2. Repetition flags
Scan for cases where similar information is conveyed more than once.
Common forms:
- The same instruction repeated in the A-roll and then again in a subsequent B-roll take
- An intro that summarizes what the conclusion already covers
- A material already mentioned in the hook and again in the materials section

Flag with: the two (or more) segments, what they repeat, and whether to cut
one or merge them.

### 3. Missing visuals
Identify moments where the presenter mentions a detail, measurement, or
technique but no corresponding visual coverage exists. Look for:
- "you can see that..." — if there's no cut to what they're pointing at
- Mention of a specific measurement or dimension — needs a close-up or text overlay
- Reference to a mistake or defect — needs a visual example
- "like this" or "like so" — almost always needs a corresponding shot

Flag with: the transcript excerpt, the timestamp, and the suggested shot type.

### 4. Overlay opportunities
Identify moments where a text or graphic overlay would help the viewer.
Look for:
- Measurements called out verbally ("three-quarter inch")
- Lists of materials or steps
- Tool names the viewer might not recognize
- Safety warnings that deserve visual emphasis
- Chapter titles at natural topic transitions

### 5. Chapter breaks
Suggest chapter markers at natural topic transitions.
A good chapter break has:
- A clear topic shift (from layout to glue-up, from assembly to finishing)
- A natural pause or reset in the footage
- A timestamp that makes sense as a YouTube chapter

Aim for 4-8 chapters for a 10-15 minute video. More granular for longer.

---

## Your process

### Step 1 — Receive input

Accept one or more of:
- `transcript_text` — the full transcript (with approximate timestamps if available)
- `markers` — list of edit markers from the workspace (from auto_mark or manual)
- `edit_notes` — any notes from a previous review pass

If you have timestamps, use them. If not, work with relative position in the
transcript.

### Step 2 — Analyze each dimension

Work through the five analysis dimensions in order. Be specific — quote the
transcript where relevant. Do not invent problems that aren't there.

### Step 3 — Emit dual output

Output:
1. Review in markdown (give directly to editor)
2. Structured dict via Python engine

```python
from production_brain.skills.review import generate_review
md, data = generate_review(
    transcript_text=<transcript>,
    markers=<list_of_marker_dicts>,
    edit_notes=<edit_notes or None>,
)
```

---

## Output format specification

### Review markdown

```markdown
# Rough Cut Review: [Project Title]

Review date: [date]
Transcript length: [approximate word count]
Markers analyzed: [count]

---

## Summary

[2-4 sentences overall assessment. Is this cut in good shape? What are the
top 2-3 things the editor should address first?]

---

## Pacing Notes

[List each pacing issue]

### Issue P1: [brief description]
- **Segment:** [start] - [end]
- **Problem:** [what's wrong]
- **Suggestion:** [specific fix]

---

## Repetition Flags

[List each repetition]

### Issue R1: [brief description]
- **Segments:** [segment A] and [segment B]
- **What repeats:** [quote or paraphrase]
- **Suggestion:** [cut one / merge / keep both if intentional]

---

## Missing Visuals

[List each missing visual]

### Issue V1: [brief description]
- **Transcript excerpt:** "[quote]"
- **Timestamp:** [approx]
- **Needed shot:** [specific description]
- **Priority:** [must-have / should-have / nice-to-have]

---

## Overlay Opportunities

[List each overlay opportunity]

| # | Timestamp | Type | Content |
|---|-----------|------|---------|
| 1 | [time] | measurement | "3/4 inch" |
| 2 | [time] | list | Materials list |
| 3 | [time] | chapter-title | "Step 2: Glue-Up" |

---

## Suggested Chapter Breaks

| # | Timestamp | Chapter Title | Reason |
|---|-----------|---------------|--------|
| 1 | 0:00 | Intro | - |
| 2 | [time] | [title] | [why here] |

---

## Priority Action List

Ordered by impact:
1. [Most important fix]
2. [Second most important]
3. [Third]
```

---

## JSON sidecar format

```json
{
  "pacing_notes": [
    {
      "id": "P1",
      "segment_start": "string",
      "segment_end": "string",
      "problem": "string",
      "suggestion": "string"
    }
  ],
  "repetition_flags": [
    {
      "id": "R1",
      "segments": ["string", "string"],
      "what_repeats": "string",
      "suggestion": "string"
    }
  ],
  "insert_suggestions": [
    {
      "id": "V1",
      "transcript_excerpt": "string",
      "timestamp": "string",
      "needed_shot": "string",
      "priority": "must-have"
    }
  ],
  "overlay_ideas": [
    {
      "timestamp": "string",
      "type": "measurement | list | chapter-title | safety | tool-name",
      "content": "string"
    }
  ],
  "chapter_breaks": [
    {
      "timestamp": "string",
      "title": "string",
      "reason": "string"
    }
  ]
}
```

---

## Analysis heuristics

**Pacing — 30-second rule:**
Any A-roll segment running more than 30 seconds without a cut should be
flagged. Exception: a deliberate slow demo (hand-planing, hand-sewing) where
the uncut duration is the point. Use judgment.

**Repetition detection:**
Compare the first and last quarter of the transcript. Tutorial conclusions
often repeat the intro. Also compare the materials mention in the hook vs.
the materials section — this is nearly always redundant.

**Missing visual scan:**
Search the transcript for these trigger words and check if corresponding
markers exist:
- "you can see", "look at", "notice", "here", "like this", "like so"
- Any number followed by a unit ("three inches", "90 degrees", "220 grit")
- Tool names on first mention

**Overlay identification:**
Every measurement spoken aloud is an overlay opportunity. Every list (materials,
steps, safety rules) is an overlay opportunity.

**Chapter breaks:**
Good break points are often preceded by a verbal transition: "now that X is
done, let's move on to Y" or "the next step is." Look for these patterns.

---

## Quality guidelines

- Be specific. Quote the transcript. Give timestamps. Name the shot type needed.
- Do not flag things that are fine. A 35-second A-roll monologue with perfect
  energy and no B-roll need is not a pacing problem.
- Prioritize. The editor does not have infinite time. Tell them what matters most.
- The Priority Action List at the end should have no more than 5 items.
  If you have more, consolidate or demote to "additional notes."

---

## Handoff

After producing the review:
- Tell the user the top 2-3 things to fix.
- Offer to update the Obsidian note: "Use `/ff-obsidian-video-note` to save this
  review to your vault."
- If the cut has major structural problems, suggest going back to
  `/ff-video-idea-to-outline` to re-examine the chapter structure.
