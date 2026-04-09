---
name: ff-publish
description: >
  Generate YouTube publish assets: title options, description, tags, hashtags,
  chapters, summary, and pinned comment. Use when user says 'publish', 'ready to
  upload', 'YouTube description', 'generate tags', or 'publish bundle'.
---

# Skill: ff-publish

You generate publish-ready YouTube assets from a finished workshop tutorial
workspace. Your job is to turn transcript and chapter data into a complete
upload package — titles, description, tags, hashtags, pinned comment, and
summary — ready for copy-paste into YouTube Studio.

---

## When to invoke this skill

Trigger on any of these phrases:
- "publish"
- "ready to upload"
- "YouTube description"
- "generate tags"
- "publish bundle"
- "title options"
- "write the description"
- "hashtags"
- "pinned comment"
- "video summary"
- When the user asks to prepare a video for YouTube.

---

## Your process

### Step 1 — Read workspace data and generate bundle

Use the Python helper to generate everything at once:

```python
from workshop_video_brain.edit_mcp.pipelines.publishing import package_publish_bundle
from pathlib import Path

workspace_root = Path("<workspace_path>")
bundle = package_publish_bundle(workspace_root)
```

Alternatively, via the MCP tool:

```
publish_bundle(workspace_path="<workspace_path>")
```

This reads transcripts from `{workspace_root}/transcripts/` and chapter markers
from `{workspace_root}/markers/`, generates all assets, and saves them to
`{workspace_root}/reports/publish/`.

### Step 2 — Present for review

Show the creator each asset for approval:

**Title Options** (pick one or combine):
```
Searchable: [title_variants.searchable]
Curiosity:  [title_variants.curiosity]
How-to:     [title_variants.how_to]
Short:      [title_variants.short_punchy]
```

**Description** (show full text for review)

**Tags** (list all, ask if any should be added/removed)

**Hashtags** (list all)

**Chapters** (review timestamps against the actual edit)

**Pinned Comment** (show for approval)

**Summary**:
- Short (1-2 sentences for cards/thumbnails)
- Medium (3-5 sentences for elsewhere)

### Step 3 — Save to vault

After the creator approves, create the Obsidian publish note:

```python
from workshop_video_brain.edit_mcp.pipelines.publishing import generate_publish_note
from pathlib import Path

note_path = generate_publish_note(
    workspace_root=Path("<workspace_path>"),
    vault_path=Path("<vault_path>"),
    bundle=bundle,
    video_url="<youtube_url>",  # optional, add after upload
)
```

Or via MCP:

```
publish_note(workspace_path="<workspace_path>", video_url="<url>")
```

### Step 4 — Handoff

- Confirm all files are in `reports/publish/`
- Remind creator to verify chapter timestamps against the final export
- Offer to update the note with the YouTube URL once published

---

## Output files saved to reports/publish/

| File | Contents |
|------|----------|
| `title_options.txt` | All 4 title variants |
| `description.txt` | Full YouTube description |
| `tags.txt` | One tag per line |
| `hashtags.txt` | One hashtag per line |
| `pinned_comment.txt` | Pinned comment text |
| `chapters.txt` | MM:SS - Title lines |
| `summary.md` | Short / medium / long summaries |
| `resources.txt` | Detected tool/material mentions |
| `publish_bundle.json` | Full bundle as JSON |

---

## Quality guidelines

- All title variants must be under 70 characters.
- Short punchy title should target under 40 characters.
- Tags should be 15-25, all lowercase, no duplicates.
- Hashtags should be max 15, prefixed with #.
- Chapter timestamps should be verified against the actual video timeline.
- If no transcript exists, generate graceful defaults from the title.

---

## Handoff

After producing the publish bundle:
- Summarise: "Bundle complete — N tags, M chapters, 4 title variants."
- Offer to update the description after the creator reviews and edits it.
- Offer to create the Obsidian publish note with the video URL.
