---
name: ff-finishing
description: >
  Take a locked rough cut to a delivered, published video: audio mix + music
  ducking, color grade / LUT, titles + subtitles, QC, render (incl. alpha
  profiles), then the publish bundle with chapters and thumbnail. Use when user
  says 'finish the video', 'finishing pass', 'final render', 'export the video',
  'ready to deliver', 'polish and publish', or 'take this to publish'.
---

# Skill: ff-finishing

You run the finishing pass — everything between a locked picture edit and a
published video. The cut is assembled; now you make it sound right, look right,
read right, pass QC, render at the correct profile, and produce the publish
package. Work in this order — each stage assumes the previous is done.

---

## When to invoke this skill

Trigger on any of these:
- "finish the video" / "finishing pass" / "polish and publish"
- "final render" / "export the video" / "render it out"
- "ready to deliver" / "take this to publish"
- After `/ff-assemble-from-script` or `/ff-auto-editor` and a review pass, when
  the picture edit is locked.

---

## Prerequisites

- A locked working copy (picture edit done; `project_create_working_copy` if none).
- Audio already cleaned at the file level is a bonus (`/ff-audio-cleanup`), but
  the mix here happens at the **track** level on the timeline.

---

## The finishing pipeline (in order)

### Stage 1 — Audio mix & ducking

Balance the tracks so narration is always intelligible over music/ambient:

- `audio_loudness_scan` — measure where each track sits before touching levels.
- `track_volume` — set each track's overall level (voice up front, music under).
- `track_eq` — multi-band EQ per track (roll off rumble on voice, thin a boomy
  music bed).
- `track_pan` / `track_mute` — placement and killing dead tracks.
- `audio_duck` — keyframe the music track's volume **down under speech** on the
  voice track. This is the core move — do it after levels are roughly set.
- If voiceover still needs dropping in, use the VO loop
  (`vo_plan` → `vo_attach` → `vo_status`); see `/ff-voiceover-fixer`.

Target integrated loudness for the final master is handled at render/normalize
time; `audio_normalize_two_pass` gives an accurate delivery loudness if you're
exporting audio separately.

### Stage 2 — Color grade / LUT

Make it look consistent and intentional:

- `color_analyze` — inspect a clip's colour metadata (log profile? flat?).
- `color_apply_lut` — apply a conversion or creative LUT (`.cube`) — the fast
  path if the user has a log profile or a branded LUT.
- `effect_color_grade` — correction + grade chain in one snapshot for clips that
  need shaping rather than a LUT.
- `effect_color_wash` / `effect_day_to_night` for stylised looks.

For anything beyond a straight grade (keying, masks, motion, signature looks),
hand the specific shot to `/ff-effect-cookbook`.

### Stage 3 — Titles & subtitles

- `title_card_add` — on-screen title cards (intro title, step labels).
  `title_cards_generate` builds them from chapter markers in one pass.
- `effect_drop_shadow` — for lower-third name/label overlays and PiP layers.
- `overlay_insert` / `watermark_apply` — logo / branding stills, full-duration
  corner watermark.
- Subtitles — two different outputs, pick per platform:
  - `subtitles_generate` → `subtitles_attach` — a **real soft subtitle track**
    in the Kdenlive project (viewer-toggleable; YouTube upload).
  - `subtitles_generate` → `subtitles_burn_in` — **permanently baked** captions
    on the delivered file (muted-autoplay / social). Also `subtitles_export`
    for standalone SRT/VTT.

### Stage 4 — Chapter guides

Add timeline guides at topic transitions so chapters export exactly later:

- `guide_add` (place a guide at a time), `guide_list`, `guide_remove`.
- Or `markers_auto_generate` → derive guides from markers.

These feed `publish_chapters` in Stage 7 with exact timestamps.

### Stage 5 — QC

Before rendering, catch problems:

- `render_review_frames` — render a cut, tile a contact sheet, run QC in one
  call; inspect the frames.
- `qc_check` — automated checks on a rendered file (black frames, levels, etc.).
- `project_validate` — catch dangling media references that would fail the render.

Fix anything flagged, then re-QC.

### Stage 6 — Render

- `render_list_profiles` — see what's available.
- `render_final_tool(profile="final-youtube")` — the delivery master
  (`draft-youtube` for a fast check, `preview`/`render_preview` for a quick look).
- **Alpha profiles** — when you're rendering a *layer* with transparency (a
  keyed element, an animated title/overlay to composite elsewhere) rather than a
  flat master, use `prores-4444-alpha`, `mov-alpha`, `webm-alpha`, or
  `ffv1-alpha`. The flat deliverable stays a normal profile.
- `render_status` — track running jobs.

### Stage 7 — Publish bundle

Produce the upload package:

- `publish_bundle` — titles, description, tags, hashtags, chapters, summary,
  pinned comment — all saved to `reports/publish/`.
- `publish_chapters` — export the Stage-4 guides as exact YouTube chapter text
  (prefer this over transcript-estimated chapters).
- `thumbnail_generate` — pull the best frame and overlay bold title text → a
  publish thumbnail PNG. Ask the user which moment and what headline.
- `publish_note` — write the Obsidian publish note with the full bundle.

For the full publish-copy workflow (title variants, SEO, review), hand off to
`/ff-publish`.

---

## Quality guidelines

- Order matters: mix → color → titles/subs → QC → render → publish. Rendering
  before the mix or grade means re-rendering.
- Duck music **after** setting levels, not before.
- Match the render profile to the deliverable: flat master = normal profile,
  transparency layer = alpha profile.
- Always QC (`render_review_frames` / `qc_check`) before the final render — a
  black frame or dangling media caught here saves a full re-render.
- Every mutating tool snapshots first — back out any stage with `snapshot_restore`.
- **Failure contract:** every tool returns a structured error dict carrying
  `error_type` + a plain `suggestion` (never a traceback). A render failure is
  often a `missing_file` (moved media — run `project_validate`) or a `not_found`
  profile (check `render_list_profiles`). Full taxonomy: the vault's
  [[MCP Error Catalog]].

---

## Handoff

After finishing:
- Report the rendered file path + profile, and the QC verdict.
- Confirm the publish bundle is in `reports/publish/` and the thumbnail path.
- Hand off to `/ff-publish` to refine titles/description, `/ff-social-clips` to
  cut shorts from the master, and `/ff-obsidian-video-note` to log it in the vault.
