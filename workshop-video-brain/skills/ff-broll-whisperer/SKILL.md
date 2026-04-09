---
name: ff-broll-whisperer
description: >
  Analyse a workshop tutorial transcript and suggest specific B-roll shots
  grouped by category. Use when user says 'b-roll', 'what visuals', 'where do
  I need footage', 'suggest shots', 'what should I film', or 'b-roll ideas'.
---

# Skill: ff-broll-whisperer

You analyse workshop tutorial transcripts and surface the moments where B-roll
footage would make the edit more engaging and instructive. Your job is to find
the shots that show rather than just tell — the close-ups, the action, the
reveal — and give the creator a concrete shot list they can go film.

---

## When to invoke this skill

Trigger on any of these phrases:
- "b-roll"
- "what visuals"
- "where do I need footage"
- "suggest shots"
- "what should I film"
- "b-roll ideas"
- "shot list"
- "cutaway suggestions"
- When the user asks what visual footage to capture for their tutorial.

---

## Your process

### Step 1 — Extract B-roll suggestions

Use the Python helper to extract suggestions from the workspace:

```python
from workshop_video_brain.production_brain.skills.broll import extract_and_format
from pathlib import Path

workspace_root = Path("<workspace_path>")
markdown, suggestions = extract_and_format(workspace_root)
```

The helper reads all transcript JSON files from `{workspace_root}/transcripts/`
and runs the B-roll detection pipeline over each one.

Alternatively, via the MCP tool:

```
broll_suggest(workspace_path="<workspace_path>")
```

### Step 2 — Review and present suggestions

Present the suggestions grouped by category. For each suggestion show:

```
**[MM:SS – MM:SS]** (confidence: 0.XX)
> [transcript context that triggered this suggestion]
Shot: [what to film]
```

Categories you will encounter:
- **Process Shot** — show the action happening (sewing, cutting, gluing)
- **Material Close-up** — tight shot of a specific material or fabric
- **Tool in Use** — show the tool being held or operated
- **Result Reveal** — the finished item or completed step
- **Measurement Shot** — ruler, tape, or marked line showing a dimension

After listing all suggestions, ask the creator:
1. Are there any shots you've already filmed that we can skip?
2. Are there any moments I missed that you want to add?

### Step 3 — Refine the shot list

Work with the creator to filter the list down to the most impactful shots.
Prioritise:
- Result reveals (high viewer value)
- Process shots that explain a complex or non-obvious step
- Tool-in-use shots for any tool the viewer might not recognise
- Measurement shots where precision matters

For each keeper, confirm:
- What angle (overhead, macro, side-on, POV)
- Any special lighting or setup note
- Whether it can be captured in a single take or needs a re-do

### Step 4 — Save to Obsidian note

After the creator approves the shot list, save it to the vault:

```python
from workshop_video_brain.production_brain.skills.broll import save_to_note

note_path = save_to_note(
    workspace_root=workspace_root,
    vault_path=Path("<vault_path>"),
    markdown=approved_markdown,
)
```

This writes the list under the `<!-- wvb:section:broll-suggestions -->` boundary
in the video note. Confirm the path to the creator when done.

---

## Quality guidelines

- Never invent shots that are not grounded in what the transcript actually says.
  If the transcript does not mention a measurement, do not suggest a measurement
  shot.
- A short, focused shot list beats a long one. Aim for quality over quantity.
- Low-confidence suggestions (below 0.6) should be flagged as optional.
- If the transcript has very few visual triggers, say so honestly and suggest
  the creator add a more descriptive narration pass before filming B-roll.

---

## Handoff

After producing the refined shot list:
- Summarise: "N shots identified across M categories."
- Offer to save the shot list to the Obsidian note.
- Offer to cross-reference the shot list against any existing footage using the
  `clips_search` tool to see if anything is already in the media library.
