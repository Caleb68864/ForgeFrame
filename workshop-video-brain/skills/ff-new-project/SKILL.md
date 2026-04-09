---
name: ff-new-project
description: >
  Start a new video project from scratch. Creates workspace, vault note, and
  generates outline, script, and shot plan from a brain dump. Use when user
  says "new project", "start a video", "new tutorial", or "I want to make a
  video about".
---

# Skill: ff-new-project

You set up a complete video project from a rough idea — workspace on disk,
Obsidian vault note, and a full production plan (outline → script → shot plan)
— in one shot.

---

## When to invoke this skill

Trigger on any of these:
- "new project"
- "start a video"
- "new tutorial"
- "I want to make a video about X"
- "let's start a new video"
- "kick off a project"
- "I have an idea for a video"
- Any time the user describes a video idea and seems ready to begin production

---

## Your process

### Step 1 — Get the title / topic

If the user has not provided a clear title or topic, ask:

> "What's the title or topic for this video?"

Keep the question short. Do not ask multiple questions at once.

### Step 2 — Get the brain dump

Once you have a title, ask for a brain dump:

> "Give me a brain dump — what's the idea? What are you making or teaching?
> Who is it for? Any constraints on tools, materials, or time?"

Encourage them to be messy and unfiltered. The brain dump does not need to be
structured — that's your job.

If the user already provided a brain dump in their initial message, skip this
step and move straight to Step 3.

### Step 3 — Run project_new

Call the `project_new` tool with:
- `title`: the video title from Step 1
- `brain_dump`: the full text from Step 2
- `project_type`: one of `tutorial`, `review`, `vlog`, `build`
  (infer from context; default to `tutorial` if unclear)

```
project_new(
    title="...",
    brain_dump="...",
    project_type="tutorial",
)
```

### Step 4 — Present the generated outline

Once `project_new` returns, show the user:
1. Where the workspace was created (`workspace_path`)
2. Where the vault note lives (`vault_note_path`) if available
3. A summary of what was generated (outline / script / shot plan)

Then present the outline for review. Ask:

> "Here's the outline I generated. Does this capture what you're going for?
> Any beats to add, remove, or reorder?"

### Step 5 — Offer to refine

After the user reviews the outline, offer:
- "I can refine the script if any steps need more detail."
- "I can adjust the shot plan if you have gear constraints (e.g., no overhead
  rig, phone only)."

### Step 6 — Remind about next steps

Close with the standard next-steps reminder:

1. Review and refine the outline in your vault note
2. Drop raw footage into the `intake/` folder when you're ready to film
3. Run `wvb media ingest <workspace_path>/` after filming to process footage

---

## Quality guidelines

- Do not over-engineer the brain dump prompt. One clear question is enough.
- The outline is a starting point, not a final product. Treat it as a draft to
  iterate on with the user.
- If the user gives you a very short brain dump (one sentence), generate the
  outline anyway. You can ask clarifying questions about the outline afterward.
- Always confirm the workspace and vault note paths were created successfully
  before presenting the outline.
- If `vault_note_path` is empty in the result, warn the user that no vault note
  was created and suggest running `wvb init` to configure ForgeFrame.

---

## Example conversation

**User:** "I want to make a video about making a zippered bikepacking pouch
from X-Pac fabric. It's for intermediate sewers who already know basic machine
sewing. I want to cover pattern layout, cutting, zipper install, and final
assembly."

**You (Step 3):** Call `project_new` with the above as brain_dump.

**You (Step 4):**
> Project created at `~/Projects/zippered-bikepacking-pouch/`
> Vault note: `~/Videos/In Progress/Zippered Bikepacking Pouch.md`
>
> Here's the outline I generated:
>
> [outline content]
>
> Does this capture what you're going for? Any beats to add or reorder?

---

## Handoff

After completing setup, tell the user which skill to use next:
- For script refinement: `/ff-tutorial-script`
- For shot list changes: `/ff-shot-plan`
- After filming: `/ff-auto-editor` or `wvb media ingest`
