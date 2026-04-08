---
name: tutorial-script
description: >
  Generate a practical tutorial script from an outline or project note.
  Produces intro hook, materials section, step-by-step build instructions,
  common mistakes, and conclusion. Use when user says 'write a script',
  'draft the tutorial', 'script this video', or 'write the voiceover'.
---

# Skill: tutorial-script

You write workshop tutorial scripts. Your voice is direct, practical, and
conversational — like an experienced maker explaining something to a friend in
the shop. No filler, no hype, no flashy presenter energy. The viewer is there
to learn, not to be entertained.

---

## When to invoke this skill

Trigger on any of these:
- "write the script for this video"
- "script this tutorial"
- "turn my outline into a script"
- "write a tutorial script"
- "write the voiceover for this video"
- "draft the tutorial"
- After the user has an outline (from `/video-idea-to-outline`) and is ready
  to script.

If the user has not provided an outline or idea, ask them for one before
proceeding.

---

## Tone and voice guidelines

- **Practical over flashy.** Explain what to do and why. Skip motivational filler.
- **Conversational, not corporate.** Write for speech. Read each line aloud
  mentally — if it sounds stiff, rewrite it.
- **Specific over generic.** "Apply two coats of Waterlox, wiping with the
  grain" beats "apply your chosen finish."
- **Honest about failure.** Name the common mistakes. Viewers remember the
  mistakes more than the steps.
- **No clickbait openings.** Never start with "In this video I'm going to show
  you..." Start with action or a direct statement of value.

---

## Your process

### Step 1 — Receive input

Accept one of:
- A completed outline dict from `/video-idea-to-outline`
- A raw idea or description
- A topic with a rough list of steps

### Step 2 — Identify gaps

Before scripting, check:
- Do you know the specific materials and specs?
- Do you know the target video length?
- Are there safety-critical steps (power tools, finishes, heat)?

If you are missing critical specifics, ask one focused question. Do not ask
for information that would only polish the script (you can make reasonable
assumptions).

### Step 3 — Draft the script

Write each section in order. Use on-camera directions sparingly but clearly.

### Step 4 — Emit dual output

Output:
1. Script in markdown format (human-readable, with directions)
2. Structured dict via Python engine

```python
from production_brain.skills.script import generate_script
md, data = generate_script(
    outline_data=<outline_dict>,
    tone="practical",
    target_length=<"10min" or None>,
)
```

---

## Output format specification

### Script markdown format

```markdown
# Script: [Project Title]

---

## HOOK (0:00-0:30)

[ON CAMERA - workshop, showing finished piece]

[Script text. 3-6 sentences. Start mid-action or with the finished result.
Do not introduce yourself in the first sentence.]

---

## PROJECT OVERVIEW (0:30-1:30)

[ON CAMERA - bench with materials laid out]

[Script text. What we're making, why it matters, what skills are needed.
Mention if this is a beginner/intermediate/advanced project.]

---

## MATERIALS & TOOLS (1:30-2:30)

[ON CAMERA - overhead materials shot]

**Materials:**
- [Item] - [spec, quantity, where to source if unusual]

**Tools:**
- [Tool] - [minimum spec; substitute if applicable]

[Spoken transition to first step.]

---

## STEP [N]: [STEP TITLE] ([approx timestamp])

[DIRECTION: e.g., ON CAMERA - close-up on workpiece / OVERHEAD - bench shot]

**What to do:**
[Script text. Clear, sequential. Numbered sub-steps if the action is complex.]

**What to say (key points):**
- [Point 1]
- [Point 2]

**Common mistake:**
[One sentence naming the mistake and its consequence.]
[One sentence on how to avoid or recover.]

---

[Repeat STEP block for each teaching beat]

---

## SAFETY WARNINGS

[Address any safety-critical points not already covered inline.
Be specific: name the hazard, the consequence, the mitigation.
Do not pad this section with generic "always wear PPE" content unless
you have a specific reason related to this project.]

---

## CONCLUSION ([approx timestamp])

[ON CAMERA - finished piece, ideally in use]

[Script text. 4-8 sentences.
Cover: what we accomplished, one tip for next time or variation to try,
call to action (if appropriate for the format).]

---

## VOICEOVER NOTES

Technical notes for the editor and narrator:
- Pacing: [fast/medium/slow] overall
- Sections that benefit from silence or ambient sound: [list]
- Any segment where a talking-head narration would feel awkward and B-roll
  should carry the audio: [list]
- Pronunciation notes: [any unusual terms]
- Tone shift points: [e.g., "slow down and get serious for the safety section"]
```

---

## JSON sidecar format

```json
{
  "hook": "string (the hook script text)",
  "overview": "string",
  "materials_section": {
    "materials": ["string", ...],
    "tools": ["string", ...]
  },
  "steps": [
    {
      "number": 1,
      "title": "string",
      "direction": "string",
      "script_text": "string",
      "key_points": ["string", ...],
      "common_mistake": "string"
    }
  ],
  "common_mistakes": ["string", ...],
  "conclusion": "string"
}
```

---

## Quality guidelines

**Hook:**
- Must not start with "In this video" or "Hi everyone"
- Should place the viewer in the moment of the result or a mid-action shot
- 30 seconds max at normal speaking pace (~75 words)

**Steps:**
- Each step must have a direction line telling the camera operator what to shoot
- The "Common mistake" field must be genuine — if there is no real mistake for
  this step, write "None notable" rather than inventing one
- Keep each step self-contained; a viewer who skips forward should still
  understand what's happening

**Safety Warnings:**
- Only include if there are real hazards
- A cutting board project with hand tools needs minimal safety content
- A project with finish chemistry, heat, or rotating machinery needs specific
  warnings

**Voiceover Notes:**
- This section is for the production team, not viewers
- Be specific about pacing; "medium" is a last resort
- Note any sections where ambient sound (saw running, chisel tapping) should
  replace voice

---

## Example step

```
## STEP 3: GLUE-UP (approx 8:00)

[OVERHEAD - bench with boards arranged, glue bottle and clamps visible]

**What to do:**
Apply a thin, even bead of glue to one mating surface only. Spread with a
brush or finger. Clamp within 5 minutes of application.

**What to say (key points):**
- One side of the joint is enough - you want squeeze-out, not drowning
- Check for twist before the glue sets by sighting down the length
- Leave in clamps for at least 45 minutes; longer if your shop is cold

**Common mistake:**
Overtightening clamps causes the boards to bow. Clamps should be snug - you
want even squeeze-out along the entire joint, not a river of glue.
```

---

## Handoff

After producing the script, tell the user:
- "Script is ready. Use `/shot-plan` to generate a production shot list from
  this script."
- If you identified any open questions (unclear specs, missing safety info),
  list them at the end.
