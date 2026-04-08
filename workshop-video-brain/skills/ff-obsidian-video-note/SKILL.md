---
name: ff-obsidian-video-note
description: >
  Create or update an Obsidian video project note with frontmatter, outline,
  script, shot plan, transcript, edit notes, and publish checklist.
  Preserves manual edits using section boundaries. Use when user says
  'create video note', 'update the note', 'project note', or 'sync the vault'.
---

# Skill: ff-obsidian-video-note

You create and maintain Obsidian project notes for workshop video productions.
Your primary responsibilities:
1. Create new notes from the project template when a project is new.
2. Update existing notes without destroying any manual edits.
3. Sync frontmatter fields from the workspace manifest.
4. Inject skill outputs (outline, script, shot plan) into named sections.

---

## When to invoke this skill

Trigger on any of these:
- "create a video note"
- "create the project note"
- "update the note"
- "sync the vault note"
- "project note"
- "add this to my vault"
- "update my Obsidian note"
- After any skill produces output (outline, script, shot plan) and the user
  wants it saved to their vault.

---

## Core principle: preserve manual edits

The note belongs to the human. Automated content goes inside section boundaries.
Content outside section boundaries is NEVER modified.

Section boundary syntax:
```
<!-- wvb:section:name -->
...automated content here...
<!-- /wvb:section:name -->
```

If a section boundary does not exist, append it to the end of the file.
Never delete content that exists outside a boundary.

---

## Section inventory

A full video project note has these sections (all optional — create only what
is relevant):

| Section name | Contents | Auto-updated? |
|---|---|---|
| `outline` | Output from `/ff-video-idea-to-outline` | Yes |
| `script` | Output from `/ff-tutorial-script` | Yes |
| `shot-plan` | Output from `/ff-shot-plan` | Yes |
| `transcript` | STT transcript output | Yes |
| `edit-notes` | Rough cut review output | Yes |
| `publish-checklist` | Pre-publish checklist | Yes |
| `manual-notes` | Human notes — NEVER auto-updated | No |

The `manual-notes` section is special: it is created empty and never touched
again by automated processes.

---

## Frontmatter fields

The note frontmatter is synced from the workspace manifest. These fields are
always kept in sync:

```yaml
title: "Video title"
slug: "kebab-case-slug"
status: "idea | outlining | scripting | filming | editing | review | published"
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
content_type: "tutorial | review | build-log | timelapse"
tags: []
vault_folder: "Videos/In-Progress"
```

Additional frontmatter fields added by the human are preserved and never
removed.

---

## Your process

### Step 1 — Detect create vs. update

Check if a note already exists at `vault_path / vault_note_path`.

**If the note does NOT exist:** go to CREATE workflow.
**If the note exists:** go to UPDATE workflow.

### Step 2a — CREATE workflow

1. Determine the vault folder from the workspace manifest or user input.
   Default: `Videos/In-Progress`
2. Build the filename: `{slug}.md` or `{title-kebab}.md`
3. Build frontmatter from manifest data + any user-supplied overrides.
4. Render using the `video-idea.md` template.
5. Call the Python engine:

```python
from production_brain.skills.video_note import create_or_update_note
from pathlib import Path

note_path = create_or_update_note(
    workspace_root=Path(workspace_root),
    vault_path=Path(vault_path),
    data={
        "title": project_title,
        "slug": project_slug,
        "status": project_status,
        "content_type": content_type,
        "sections": {
            "outline": outline_markdown,   # if available
            "shot-plan": shot_plan_markdown,  # if available
        }
    }
)
```

6. Report the created note path to the user.

### Step 2b — UPDATE workflow

When updating an existing note:

1. **Frontmatter sync**: merge workspace manifest fields into existing
   frontmatter. Fields present in the note but absent from the manifest are
   preserved.
2. **Section update**: for each section in `data["sections"]`, call
   `update_section(note_path, section_name, content)`.
3. **Never touch**: content outside section boundaries, the `manual-notes`
   section, or any custom frontmatter keys.

```python
from production_brain.skills.video_note import create_or_update_note

note_path = create_or_update_note(
    workspace_root=Path(workspace_root),
    vault_path=Path(vault_path),
    data={
        "slug": project_slug,
        "sections": {
            "outline": new_outline_markdown,
        }
    }
)
```

---

## Conflict resolution rules

When automated content conflicts with existing manual content:

1. Content **inside** a `wvb:section` boundary is always replaceable by the
   corresponding skill. The human should not edit inside these boundaries.
2. Content **outside** any boundary is always preserved, always.
3. Frontmatter keys that exist in the note but are absent from the manifest
   are preserved unchanged.
4. If the user has manually edited content inside a section boundary, warn
   them before overwriting. Do not silently discard their work.

---

## Template structure

A newly created note looks like this:

```markdown
---
title: "My Video Title"
slug: "my-video-title"
status: "idea"
created: "2024-01-15"
updated: "2024-01-15"
content_type: "tutorial"
tags: []
---

# My Video Title

<!-- wvb:section:outline -->
<!-- /wvb:section:outline -->

<!-- wvb:section:script -->
<!-- /wvb:section:script -->

<!-- wvb:section:shot-plan -->
<!-- /wvb:section:shot-plan -->

<!-- wvb:section:transcript -->
<!-- /wvb:section:transcript -->

<!-- wvb:section:edit-notes -->
<!-- /wvb:section:edit-notes -->

<!-- wvb:section:publish-checklist -->
<!-- /wvb:section:publish-checklist -->

<!-- wvb:section:manual-notes -->

<!-- /wvb:section:manual-notes -->
```

---

## Status field values

The `status` field uses these values, matching the workspace manifest:

| Value | Meaning |
|---|---|
| `idea` | Just an idea, not yet outlining |
| `outlining` | Working on the outline |
| `scripting` | Script in progress |
| `filming` | Filming/capturing |
| `ingesting` | Bringing footage into workspace |
| `editing` | Active editing |
| `review` | Rough cut review |
| `rendering` | Final render in progress |
| `published` | Video is live |
| `archived` | Project archived |

---

## Quality guidelines

- Always report the full path of the created/updated note.
- When creating a new note, confirm that the vault folder exists or will be
  created.
- When updating, tell the user which sections were updated and which were
  skipped (because they had no new content).
- If vault_path is not set in the workspace manifest, ask the user for it
  before proceeding — do not guess.

---

## Handoff

After creating or updating the note:
- Report the note path.
- List which sections were written.
- Remind the user: "The `manual-notes` section is yours — automated tools
  will never overwrite it."
