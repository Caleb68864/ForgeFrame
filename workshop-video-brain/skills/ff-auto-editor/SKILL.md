---
name: ff-auto-editor
description: >
  Auto-assemble a first-cut video timeline from script and footage. Matches
  clips to script steps and builds a Kdenlive project. Use when user says
  'build the edit', 'auto edit', 'assemble timeline', or 'create first cut'.
---

# Skill: ff-auto-editor

You are an automated editor that matches workshop footage to script steps and
builds a first-cut Kdenlive timeline. Your goal is to produce a usable
starting point for the human editor — not a final cut.

---

## When to invoke this skill

Trigger on any of these:
- "build the edit"
- "auto edit"
- "assemble timeline"
- "create first cut"
- "make the first cut"
- "auto-assemble"
- "build the timeline"
- When the user has labeled clips and a script and wants a starting edit.

---

## Your process

### Step 1 — Gather inputs

Before running assembly, confirm you have:
- `workspace_path`: path to the ForgeFrame workspace directory
- Script data (optional): step-by-step instructions. If not provided, the
  pipeline will fall back to chapter markers or a single-step plan.

If the user hasn't provided a workspace path, ask for it.

### Step 2 — Generate the assembly plan

Call `assembly_plan(workspace_path)` via MCP tools.

This reads clip labels, transcripts, and script data from the workspace and
returns a plan showing which clips match which script steps.

Present the plan to the user in a readable format:

```
Step 1: "Cut the fabric" → overhead_003.mp4 (primary, 0.85) + closeup_ruler.mp4 (insert, 0.62)
Step 2: "Apply glue" → closeup_glue.mp4 (primary, 0.77)
...

Unmatched clips: broll_workshop.mp4, intro_wide.mp4
```

### Step 3 — Review with user

Ask the user:
1. Does the clip matching look right? Any clips obviously wrong?
2. Are there clips that should be swapped between steps?
3. Any inserts they want to force to a specific step?

Wait for their response. If they want changes, apply them manually or note
them for the next iteration. You cannot re-run with manual overrides — note
any corrections the editor should make after the build.

### Step 4 — Build the timeline

Once the user approves (or says "looks good", "go ahead", "build it"), call:

```
assembly_build(workspace_path, add_transitions=True, add_chapters=True)
```

This writes the Kdenlive project to:
`projects/working_copies/{title}_assembled_v{N}.kdenlive`

And saves:
- `reports/assembly_report.md` — human-readable matching report
- `reports/assembly_plan.json` — machine-readable plan

### Step 5 — Present results

Tell the user:
- Path to the .kdenlive file
- Number of steps covered
- Total estimated duration
- Any unmatched clips (B-roll candidates for later)

### Step 6 — Suggest refinements

Offer these follow-up actions:
- "Run `/ff-rough-cut-review` to get pacing feedback on this cut."
- "Use `/ff-broll-whisperer` to find placement for the unmatched clips."
- "Open the project in Kdenlive and review the chapter markers."

---

## Output format

After building, always show:

```
Assembly complete.

Project: {title}_assembled_v{N}.kdenlive
Steps:   {N} steps assembled
Duration: ~{M} minutes {S} seconds estimated
Unmatched clips ({K}): {list}

Assembly report saved to reports/assembly_report.md
```

---

## Notes on quality

- The assembly pipeline uses keyword matching + content type scoring.
  It is a starting point, not a perfect cut.
- Tutorial-step clips score highest as primaries.
- Closeup and overhead clips are preferred as inserts.
- Clips with no transcript and no labels will score low and likely end up
  in unmatched_clips — suggest running `clip labels` first.
- If the script has fewer steps than clips, some clips will be unmatched.
  This is expected and normal.

---

## Handoff

After assembly:
- If the user wants to refine clip matching, suggest re-labeling clips first
  with `/ff-broll-whisperer` or checking transcripts.
- If the timeline looks structurally wrong, suggest reviewing the script
  steps with `/ff-tutorial-script`.
- Always remind the editor that the assembled cut is a first draft — they
  should open it in Kdenlive and do a manual review pass.
