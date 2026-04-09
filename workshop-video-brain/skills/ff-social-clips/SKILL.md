---
name: ff-social-clips
description: >
  Extract short-form clips from a tutorial for YouTube Shorts, Instagram Reels,
  and TikTok. Generates titles, captions, and social post text. Use when user
  says 'make shorts', 'social clips', 'extract highlights', 'create reels', or
  'repurpose for social'.
---

# Skill: ff-social-clips

You extract short-form clip candidates from long tutorial videos and generate
all the social media assets needed to publish them: titles, captions, overlay
suggestions, and platform-specific post text.

---

## When to invoke this skill

Trigger on any of these:
- "make shorts"
- "social clips"
- "extract highlights"
- "create reels"
- "repurpose for social"
- "youtube shorts"
- "instagram reels"
- "tiktok clips"
- "short form content"
- "clip extraction"
- "find highlights"
- "best moments"
- "social media package"

---

## Your process

### Step 1 — Find highlight clips

Use the MCP tool to scan the transcript for clip-worthy segments:

```
social_find_clips(workspace_path="<workspace_path>", max_clips=5)
```

Or via Python:

```python
from pathlib import Path
from workshop_video_brain.core.models.transcript import Transcript
from workshop_video_brain.edit_mcp.pipelines.social_clips import find_highlight_segments

workspace_root = Path("<workspace_path>")
transcripts_dir = workspace_root / "transcripts"

all_segments = []
for json_path in sorted(transcripts_dir.glob("*_transcript.json")):
    transcript = Transcript.from_json(json_path.read_text(encoding="utf-8"))
    for seg in transcript.segments:
        all_segments.append({
            "start_seconds": seg.start_seconds,
            "end_seconds": seg.end_seconds,
            "text": seg.text,
        })

candidates = find_highlight_segments("", all_segments, min_duration=15.0, max_duration=60.0)
```

### Step 2 — Generate the full social package

```
social_generate_package(workspace_path="<workspace_path>", max_clips=5, aspect_ratio="9:16")
```

This writes to `reports/social/`:
- `clips_manifest.json` — export specs for all clips
- `clip_1_post.txt`, `clip_2_post.txt`, etc. — platform post text
- `social_summary.md` — overview of all clips with timestamps and scores

### Step 3 — Generate platform-specific posts

```
social_clip_post(workspace_path="<workspace_path>", clip_index=0, platform="instagram")
```

Platforms: `youtube`, `instagram`, `tiktok`, `twitter`

---

## Interpreting clip scores

Each candidate is scored 0-1 on three dimensions:

- **hook_strength**: Does the opening line grab attention? Questions, bold
  statements, and strong action verbs score higher. References to prior
  context score lower.
- **clarity**: Can a viewer understand this clip without watching the full
  video? Self-contained explanations score higher. Dangling pronouns ("This
  is how...") and back-references score lower.
- **engagement**: Does it teach something specific? Measurements, named
  techniques, and concrete materials score higher. Vague filler language
  scores lower.
- **overall_score** = hook_strength × 0.4 + clarity × 0.3 + engagement × 0.3

A clip with overall_score > 0.6 is a strong short-form candidate.

---

## Presenting findings to the user

1. **List clips** in score order with timestamps, duration, and hook text.
2. **Flag the top clip** as the strongest short-form candidate and explain why.
3. **Identify any clips** that need context and note they may need a title card
   or caption to stand alone.
4. **Summarise** how many clips were found, the best platform for each, and
   what files were written.

---

## Quality guidelines

- Never invent content. Use only what is in the transcript.
- Short-form clips should work without the full video. Flag any clip that
  heavily references prior steps.
- Titles must be under 50 characters for YouTube Shorts compatibility.
- Captions must be under 60 characters per line for overlay readability.
- Twitter posts must be under 280 characters including hashtags.
- For TikTok, ultra-short hooks work best. Lead with the most surprising or
  actionable line.
