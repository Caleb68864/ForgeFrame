---
name: ff-video-idea-to-outline
description: >
  Turn a rough video idea into a structured tutorial outline with viewer
  promise, materials list, teaching beats, pain points, and chapter structure.
  Use when user says 'plan a video', 'outline a tutorial', 'video idea', or
  describes a project they want to film.
---

# Skill: ff-video-idea-to-outline

You transform a rough, unstructured video idea into a production-ready tutorial
outline. You are writing for a maker/workshop context — assume the viewer is
hands-on, wants to learn a skill, and will follow along.

---

## When to invoke this skill

Trigger on any of these:
- "plan a video about X"
- "outline a tutorial on X"
- "I have a video idea"
- "what would I cover in a video about X"
- "help me structure a video"
- Whenever the user describes a project they want to film but has not yet
  structured it into a script or shot list.

---

## Your process

### Step 1 — Understand the idea

Read the user's description carefully. Identify:
- The primary skill or technique being taught
- The physical object or outcome being produced (if any)
- The implied audience experience level
- Any constraints mentioned (time, tools, budget, space)

If the idea is ambiguous, ask one focused clarifying question before proceeding.
Do not ask more than one question at a time.

### Step 2 — Draft the outline sections

Work through each section in order. Think out loud briefly if that helps you
produce a better result, but keep it concise.

### Step 3 — Emit dual output

After drafting, output:
1. The outline in markdown (human-readable)
2. A structured JSON sidecar (machine-readable)

The JSON is produced by calling the Python engine:
```
from production_brain.skills.outline import generate_outline
md, data = generate_outline(
    idea=<user_idea>,
    project_type=<detected_type or None>,
    audience=<detected_audience or None>,
    constraints=<detected_constraints or None>,
)
```

Show the markdown output to the user. The JSON sidecar is stored silently.

---

## Output format specification

### Markdown outline

Produce a markdown document with these sections in this order:

```markdown
# [Project Title]

## Viewer Promise
One sentence stating exactly what the viewer will be able to do after watching.
Format: "By the end of this video you will be able to [verb] [outcome]."

## What We're Making
2-4 sentences describing the finished project. Be concrete and specific.
Include approximate dimensions, materials, finish level.

## Why It Matters
1-3 bullets explaining why this skill/project is worth learning.
Focus on practical value, not hype.

## Materials & Tools
### Materials
- Item 1 (spec, quantity)
- Item 2 (spec, quantity)

### Tools
- Tool 1 (minimum spec or substitute)
- Tool 2

## Teaching Beats
Numbered steps, each covering one coherent action or concept.
Format:
1. [Beat title] — [1-sentence description of what happens]
2. ...

Aim for 5-12 beats depending on project complexity.

## Pain Points / Gotchas
- [Pain point 1] — brief explanation and how to avoid it
- [Pain point 2]

## Chapter Structure
Suggest 3-6 YouTube chapters with approximate timestamps.
Format:
- 0:00 — Intro / What we're making
- 0:45 — Materials overview
- ...

## Suggested Intro Hook
One paragraph (3-5 sentences) for a compelling cold open.
Start mid-action if possible.

## Open Questions
Things you or the filmmaker need to decide before scripting:
- [Question 1]
- [Question 2]
```

---

## JSON sidecar format

```json
{
  "viewer_promise": "string",
  "what_were_making": "string",
  "materials": ["string", ...],
  "tools": ["string", ...],
  "teaching_beats": [
    {"number": 1, "title": "string", "description": "string"},
    ...
  ],
  "pain_points": ["string", ...],
  "chapter_structure": [
    {"timestamp": "0:00", "title": "string"},
    ...
  ],
  "intro_hook": "string",
  "open_questions": ["string", ...]
}
```

---

## Quality guidelines

- Viewer Promise must be a single sentence. Do not use "I" — it is written from
  the perspective of what the viewer gains.
- Teaching Beats should be granular enough that each beat maps to roughly 1-3
  minutes of real video.
- Pain Points must be genuine failure modes, not generic warnings.
- The Intro Hook should start mid-action whenever possible. Avoid "Hi everyone,
  welcome to my channel."
- Chapter Structure timestamps are estimates — label them clearly as approximate.
- Open Questions are things that genuinely need a decision before scripting,
  not rhetorical filler.

---

## Example

**User input:** "I want to do a video on making a walnut cutting board"

**Viewer Promise:**
> By the end of this video you will be able to glue up, flatten, and finish a
> live-edge walnut cutting board from rough lumber.

**Teaching Beats (abbreviated):**
1. Wood selection — choosing walnut slabs, reading grain, avoiding defects
2. Rough milling — jointing one face, planing to thickness, ripping parallel edges
3. Glue-up — arranging for visual balance, clamping strategy
4. Flattening — router sled vs. hand plane vs. drum sander tradeoffs
5. Shaping the live edge — spokeshave and card scraper technique
6. Sanding progression — 80 through 220, raising the grain
7. Food-safe finish — mineral oil application, butcher block conditioner
8. Final reveal — glamour shots, wipe-down, delivery

**Pain Point example:**
> Skipping grain direction on adjacent boards — causes tearout during surfacing.
> Always alternate grain orientation or choose boards with similar run direction.

---

## Handoff

After producing the outline, tell the user:
- "Your outline is ready. Next steps: use `/ff-tutorial-script` to write the full
  script, or `/ff-shot-plan` to build a production shot list."
- If you detected open questions, highlight the most important one for the user
  to resolve first.
