---
name: ff-assemble-from-script
description: >
  Assemble a reviewable first cut straight from a build-step / script list and a
  pile of raw clips. Indexes transcripts, maps each step to candidate footage,
  places clips on a timeline, and self-reviews the render. Use when user says
  'assemble from the script', 'build the cut from my steps', 'match footage to
  the instructions', 'turn my steps into a timeline', or 'auto-assemble from script'.
---

# Skill: ff-assemble-from-script

You take the end-to-end production scenario — a pile of raw clips plus a
numbered build-step list (or script highlights) — and drive it to a reviewable
first cut through the MCP. This is the composite move the whole pipeline is built
around: **step list ↔ clip transcripts ↔ timestamps → placed clips → watch it.**

This is the heavier, more precise sibling of `/ff-auto-editor`. Use it when you
have a real step list and want an agent to find, place, and review footage
step-by-step, not just run a one-shot assembly.

---

## When to invoke this skill

Trigger on any of these:
- "assemble from the script" / "build the cut from my steps"
- "match footage to the instructions"
- "turn my steps into a timeline"
- "auto-assemble from script"
- "put the clips where the steps are"
- When the user hands over raw clips + a numbered instruction/step list and wants
  a first cut assembled against it.

---

## Prerequisites (get these before you start)

1. **A working copy.** All placement tools operate on the latest working copy.
   If none exists, run `project_create_working_copy`.
2. **Ingested, transcribed footage.** Clips should be in the workspace with
   transcripts. If not, run `media_ingest` first (scan → proxy → transcribe →
   detect silence). Wire proxies with `proxy_attach` for a responsive edit.
3. **A machine-readable step list.** A numbered list of build steps, even rough.
   If the user only has prose, ask them to number it, or derive it from the
   outline's Teaching Beats (`/ff-video-idea-to-outline`) or `pattern_extract`.

---

## Your process

### Step 1 — Build the transcript search index

Index every per-clip transcript so steps can be matched by content:

```
transcript_index_build(workspace_path="<workspace_path>")
```

This is incremental — safe to re-run after new footage lands. Sanity-check it
with a `transcript_search` for a phrase you know is in the footage.

### Step 2 — Map steps to clips

Point the mapper at the step list:

```
shots_map_to_script(workspace_path="<workspace_path>", steps_file="<path or inline steps>")
```

This aligns each numbered step to candidate clips + timestamps, combining
transcript FTS with any vision tags / labels. Present the step → clips table to
the user:

```
Step 1: "Cut the fabric"  → overhead_003.mp4 @ 00:12 (0.85) · closeup_ruler.mp4 @ 00:04 (0.61)
Step 2: "Apply glue"      → closeup_glue.mp4  @ 00:31 (0.77)
Step 3: "Clamp and wait"  → (no strong match — needs footage or a title card)
...
```

Flag steps with **no match** — those are gaps the user must fill (film it, or
cover with a title card / B-roll). Use `transcript_search` to hunt manually for
any step the mapper missed before declaring it a gap.

### Step 3 — Review the mapping with the user

Ask:
1. Any step mapped to the wrong clip?
2. For steps with multiple candidates, which take do they prefer? (QC scores pick
   the technically cleanest, but only the user knows the best *performance* take —
   `clips_qc_scan` can rank candidates on junk/dead-air if helpful.)
3. Any unmatched step they want to cover with a title card instead of footage?

Wait for confirmation before placing anything.

### Step 4 — Place the clips on the timeline

Walk the approved mapping in step order and place each clip at its target time
using the placement engine:

- `clip_place(track, at_seconds, mode="overwrite"|"insert")` — drop the primary
  clip for a step. Use `insert` to build a growing A-roll spine (ripples content
  right); use `overwrite` to lay a B-roll insert over A-roll at a precise time.
- `clip_place_matched` — place an insert cut to exactly the duration of a
  reference clip (cover an A-roll span with one B-roll shot).
- `clip_move_to` (cross-track), `clip_trim`, `clip_split`, `clip_ripple_delete`
  for tightening after the first pass.

Add a track with `track_add` if you need a separate B-roll or title layer. Every
mutating call snapshots first, so you can always `snapshot_restore` to back out.

### Step 5 — Self-review the render (close the loop)

Do not hand back a blind cut. Watch it the way an agent can:

```
render_review_frames(workspace_path="<workspace_path>", every_n_seconds=5)
```

This renders the cut, extracts frames (interval or at markers), tiles a contact
sheet, and runs `qc_check` in one call. Inspect the frames: wrong clip at a step,
black frame, dead air, jump cut. Fix with the Step 4 tools and re-review. Loop
until the cut reads correctly.

### Step 6 — Report

Tell the user:
- Path to the assembled `.kdenlive` working copy.
- Steps covered vs. steps still gapped (unmatched).
- What the self-review flagged and what you fixed.
- Suggested next skills: `/ff-rough-cut-review` for editorial feedback,
  `/ff-finishing` to mix/color/title/render, `/ff-broll-whisperer` for gaps.

---

## Quality guidelines

- The mapping is a starting point. Never place a clip on a step the user hasn't
  confirmed if the match confidence is low.
- Keep placements frame-exact by letting `clip_place` do the time math — don't
  hand-compute frames.
- An honest "Step N has no coverage" beats forcing an unrelated clip onto it.
- Prefer `insert` mode to build the spine, `overwrite` for cutaways — mixing them
  carelessly desyncs everything downstream.
- **Failure contract:** every tool returns a structured error dict carrying
  `error_type` + a plain `suggestion` (never a traceback). "No working copy" →
  `project_create_working_copy`; an out-of-range track/clip → `project_summary`.
  Full taxonomy: the vault's [[MCP Error Catalog]].

---

## Handoff

After assembly:
- Confirm the working-copy path and the covered/gapped step counts.
- Hand off to `/ff-finishing` for mix → color → titles → render → publish.
- If many steps gapped, hand off to `/ff-broll-whisperer` to plan the missing
  shots, or `/ff-shot-plan` for a pickup session.
