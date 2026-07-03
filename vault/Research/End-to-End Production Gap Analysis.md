---
title: End-to-End Production Gap Analysis
date: 2026-07-03
type: reference
tags: [forgeframe, workflow, gap-analysis, research]
---

# End-to-End Production Gap Analysis

Scenario: the user hands over (1) a pile of raw clips, (2) the build
instructions for the item being made in the tutorial, (3) script highlights.
What information and tools are still missing to produce the finished video
through the MCP, start to finish?

Written 2026-07-03, after the placement fix, Wave 1/2 bundles, the ffmpeg
ingest-brain, subtitles, speed ramping, and (in flight) timeline audio +
proxy wiring.

## What already works end-to-end

Ingest → transcribe → QC-flag junk → scene-detect → segment at silences →
thumbnail for vision tagging → b-roll index → rough assembly (selects/review
timelines from markers) → effects/color/titles/subtitles → track mixing +
ducking (in flight) → render (incl. alpha) → QC → publish package. The
pipeline exists; the gaps below are the friction points inside it.

## Information still needed from the user (no tool fixes these)

1. **Machine-readable build steps.** The item instructions need to be a
   numbered step list (even rough) so footage can be aligned step-by-step.
   A photo/diagram set per step is a bonus — becomes overlays and B-roll.
2. **Script intent: highlights → full VO?** Are the script highlights the
   narration itself, or beats to expand? Who voices it — user-recorded VO
   (needs a record-and-drop-in loop) or on-camera audio only?
3. **Take preferences.** When 4 takes of "gluing the panel" exist, QC scores
   pick the technically best; only the user knows the *performance* best.
   A one-pass "star your takes" review (or a rule: trust QC + latest take).
4. **Style contract**: target length, platform(s) + aspect ratios, pacing
   reference ("like this video"), branding kit (font, colors, logo file,
   intro/outro clips), music tracks with licenses.
5. **Camera/color info**: log profile or not (drives conversion-LUT choice),
   multi-camera or single.

## Tool gaps that would actually block or hurt

Ranked by how hard they'd bite during a real edit.

1. **Timeline placement upgrades (SYNTHESIS #6 — still unbuilt).** The
   biggest blocker. No insert-at-time-T-on-track-N (only playlist-index
   insertion), no overwrite-vs-insert semantics, no cross-track clip_move,
   no match-length insert. Real assembly = placing B-roll over A-roll at
   precise times; today that needs the light-leak agent's private
   model-level workaround. Promote it to a public `clip_place(track,
   at_seconds, mode=insert|overwrite)` + cross-track move.
2. **Transcript search index (designed, never built).** The SQLite FTS5
   design in [[Local Transcription and Clip Search Index]] is exactly the
   glue for this scenario: "find the clip where I glue the panel" =
   transcript_search over per-clip transcripts + segment timestamps.
   Without it, an agent re-reads every transcript per query.
3. **Shot-to-step alignment.** The composite move this scenario lives on:
   match build-step list ↔ clip transcripts (FTS) ↔ vision tags (thumbnail
   sheets). Pieces exist or are designed; a `shots_map_to_script(steps_file)`
   orchestration producing a step→clips table would make assembly agentic.
4. **Still-image producer / PNG overlay (SYNTHESIS #9 remainder).** The
   instructions' diagrams and the branding logo can't be placed on the
   timeline — media_slideshow renders image *sequences* to video, but a
   single PNG on a track (logo watermark, step diagram) has no path.
5. **Voiceover loop.** voiceover_extract_segments exists, but there is no
   VO-first flow: script → per-section VO stubs → user records → drop-in
   at markers → timeline ripples to VO length. (Optional research: local
   TTS for scratch VO to time the edit before recording.)
6. **Agent self-review loop.** After a render, the agent can't "watch" it.
   Cheap formalization: `render_review_frames(project, every_n_seconds |
   at_markers)` → contact sheet + frame paths for vision inspection +
   qc_check in one call. All pieces exist (render_preview,
   media_thumbnail_sheet, qc_check); it needs one orchestrating tool.
7. **Thumbnail generator.** Extract best frame (thumbnail filter) +
   title-style text overlay (titles builder) + export PNG. All primitives
   exist post-titles; small composite tool, high publish value.
8. **Motion tracking (§5 — still unbuilt).** For pointing at parts of the
   build ("this bracket here") via tracked zoom/arrows. Deferred but real.
9. **Music beat alignment (nice-to-have).** pacing_analyze covers speech
   rhythm; no onset/beat grid from a music track to snap cuts to.

## Suggested build order for this scenario

1. `clip_place` / cross-track move (unblocks assembly) —
2. transcript_index_build + transcript_search (unblocks find-by-script) —
3. `shots_map_to_script` orchestration —
4. image producer / PNG overlay —
5. render_review_frames (closes the agent loop) —
6. thumbnail generator, VO loop, beat grid.

With 1–3 built and the info list answered, the honest answer to "what would
you still need?" is: *nothing structural — an agent could assemble a
reviewable first cut, and the remaining items are polish speed-ups.*
