---
name: ff-shot-plan
description: >
  Generate a production shot list from a tutorial outline or script.
  Covers A-roll, overhead bench shots, detail closeups, measurement shots,
  inserts, glamour B-roll, and likely pickup shots. Use when user says
  'shot list', 'plan the shots', 'what shots do I need', or 'shooting plan'.
---

# Skill: ff-shot-plan

You produce a practical, production-ready shot list for workshop tutorial videos.
Your output tells the camera operator exactly what to capture, in what order,
and why it matters. You think in terms of editorial needs, not just coverage.

---

## When to invoke this skill

Trigger on any of these:
- "build a shot list"
- "what shots do I need"
- "plan the shots for this video"
- "shot plan"
- "shooting plan"
- "what do I need to film"
- After the user has a script (from `/ff-tutorial-script`) or outline
  (from `/ff-video-idea-to-outline`).

---

## Shot categories

Use exactly these seven categories. Every shot belongs in one category.

### A-Roll (Talking Head)
The presenter on camera, explaining or narrating. These are the primary
continuity shots. They are usually filmed after the work is done, using
the finished piece as a prop.

### Overhead / Bench
Camera mounted above or at high angle looking down at the work surface.
Used for assembly steps, layout, and anything where spatial relationships
between parts matter. Often the workhorse of a workshop video.

### Detail Closeups
Tight shots of surfaces, joints, grain, texture, or any feature the viewer
needs to see clearly. Not measurement-related — those go in Measurements.

### Measurement / Cutting
Shots showing dimensions, marks, tape measure readings, saw fence settings,
angles. These must be legible in the final video — note if text overlay
will be needed.

### "Don't Forget" Inserts
One- or two-second cutaways that editors often miss during shooting but wish
they had: applying finish, wiping excess, tightening a fastener, checking
with a square. These are usually the difference between a rough cut and a
polished one.

### Glamour / Result B-Roll
Beauty shots of the finished piece. Shot at end of filming day.
Multiple angles, different lighting if possible. Used in the intro hook,
chapter thumbnails, and conclusion.

### Likely Pickup Shots
Shots that you probably cannot get during the main shoot (wrong time of day,
need a second take, etc.). Flag these explicitly so the filmmaker knows to
plan a pickup session.

---

## Your process

### Step 1 — Parse input

Accept one of:
- A script dict from `/ff-tutorial-script`
- An outline dict from `/ff-video-idea-to-outline`
- A raw description of the project

Extract: list of steps/beats, materials, tools, any specific measurements or
techniques mentioned.

### Step 2 — Build shot list by category

For each teaching beat, determine:
- Which categories need coverage
- How many distinct shots are needed
- What the shot must show (not just "close-up of wood" but "close-up showing
  grain direction and any defects in the mating surface")

Assign a `beat_ref` to each shot linking it back to the tutorial step.
Use "GENERAL" for shots not tied to a specific beat.

Assign a priority:
- `must-have` — the edit cannot work without this
- `should-have` — strongly recommended, skip only if time is short
- `nice-to-have` — would improve the video but not critical

### Step 3 — Emit dual output

Output:
1. Shot plan in markdown (print and take to the shop)
2. Structured dict via Python engine

```python
from production_brain.skills.shot_plan import generate_shot_plan
md, data = generate_shot_plan(
    outline_or_script=<dict>,
    gear_constraints=<"no overhead rig" or None>,
)
```

---

## Output format specification

### Shot plan markdown

```markdown
# Shot Plan: [Project Title]

Generated from: [outline / script]
Gear constraints: [none / list any]

---

## A-Roll (Talking Head)

| # | Beat | Description | Priority | Notes |
|---|------|-------------|----------|-------|
| A1 | GENERAL | Intro on-camera with finished piece | must-have | Film last |
| A2 | Step 3 | Explain glue-up technique at bench | must-have | Hold finished piece |

---

## Overhead / Bench

| # | Beat | Description | Priority | Notes |
|---|------|-------------|----------|-------|
| O1 | Step 1 | Board layout showing grain | must-have | Wide frame |

---

## Detail Closeups

| # | Beat | Description | Priority | Notes |
|---|------|-------------|----------|-------|
| C1 | Step 2 | Mating surface showing glue spread | must-have | Macro if available |

---

## Measurement / Cutting

| # | Beat | Description | Priority | Notes |
|---|------|-------------|----------|-------|
| M1 | Step 1 | Tape on board edge - 12" mark visible | must-have | Text overlay needed |

---

## "Don't Forget" Inserts

| # | Beat | Description | Priority | Notes |
|---|------|-------------|----------|-------|
| I1 | Step 5 | Wiping excess finish with the grain | must-have | 2-3 sec |

---

## Glamour / Result B-Roll

| # | Beat | Description | Priority | Notes |
|---|------|-------------|----------|-------|
| G1 | GENERAL | Finished piece - 3/4 view, natural light | must-have | Film last |
| G2 | GENERAL | Board in use - food being prepared | should-have | Props needed |

---

## Likely Pickup Shots

| # | Beat | Description | Why Pickup |
|---|------|-------------|------------|
| P1 | Step 4 | Hand plane shaving end grain | Hard to get while working |

---

## Shot Count Summary

| Category | Must-Have | Should-Have | Nice-to-Have | Total |
|----------|-----------|-------------|--------------|-------|
| A-Roll | 3 | 1 | 0 | 4 |
| Overhead | 5 | 2 | 1 | 8 |
| Closeup | 4 | 3 | 2 | 9 |
| Measurement | 3 | 0 | 0 | 3 |
| Inserts | 4 | 2 | 0 | 6 |
| Glamour | 2 | 2 | 2 | 6 |
| Pickups | 1 | 1 | 0 | 2 |

**Estimated shooting time:** [X hours, based on shot count and complexity]
```

---

## JSON sidecar format

```json
{
  "a_roll": [
    {
      "id": "A1",
      "type": "a_roll",
      "description": "string",
      "beat_ref": "string",
      "priority": "must-have",
      "notes": "string"
    }
  ],
  "overhead": [],
  "closeups": [],
  "measurements": [],
  "inserts": [],
  "glamour": [],
  "pickups": []
}
```

---

## Gear constraints handling

If the user mentions gear constraints, adapt accordingly:

- **No overhead rig** — lean on bench-level angles and tight A-roll; flag
  steps where overhead is the only logical angle and note a workaround
- **Single camera** — group shots by location and continuity to minimize
  camera moves; mark which shots can be faked in a second pass
- **No gimbal / no slider** — avoid recommending tracking shots; use static
  wide plus cutaway strategy instead
- **Phone only** — simplify shot complexity; prioritize overhead (easy to rig)
  and close-ups (phone excels at macro)

---

## Quality guidelines

- Every shot must have a clear `beat_ref` — no orphan shots without context
- "Don't Forget" Inserts should be identified by scanning the script/outline
  for: wiping, checking, tightening, measuring, applying — these are always
  good insert candidates
- Glamour shots should include at least one "product in use" shot, not just a
  display shot
- Pickup shots must explain WHY they are pickups (hard to get during main
  shoot, requires second take, etc.)
- Shot count summary gives the filmmaker a time estimate — be realistic

---

## Handoff

After producing the shot plan, tell the user:
- "Shot plan is ready. You can print the markdown table and take it to the shoot."
- If you identified gear constraints that affect coverage, summarize the
  workarounds.
- Suggest: "Use `/ff-obsidian-video-note` to add this shot plan to your project
  vault note."
