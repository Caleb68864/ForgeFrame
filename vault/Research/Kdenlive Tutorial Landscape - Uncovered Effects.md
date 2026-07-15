---
title: Kdenlive Tutorial Landscape - Uncovered Effects
date: 2026-07-03
type: reference
tags: [kdenlive, tutorials, research]
---

# Kdenlive Tutorial Landscape — Uncovered Effects

Scan of the YouTube / blog / docs tutorial landscape for Kdenlive effects and
features **not** covered by the Nuxttux playlist we already analyzed (see
`docs/research/2026-07-03-tutorial-effect-analysis/SYNTHESIS.md`). Goal: find the
next batch of tutorials to feed through `scripts/download_playlist_transcripts.py`
+ effect analysis, prioritized by which coverage holes / missing MCP primitives
they exercise.

## Legend

- **NEW** = effect/workflow territory the Nuxttux batch never touched.
- **REINFORCE** = a technique already flagged as a known gap in
  SYNTHESIS.md or the MCP improvements plan §3/§5/§6 — still worth analyzing if
  it demonstrates the workflow differently, but not net-new territory.
- **Primitive** column maps to the MCP tools/gaps in
  `docs/plans/2026-07-03-kdenlive-mcp-improvements.md`.

## Already-covered note (do NOT re-analyze as if new)

We already ship primitives for several of these families, so tutorials on them
mostly *validate* existing tools rather than reveal gaps:
`effect_chroma_key`/`_advanced` (green screen), `color_apply_lut` (LUTs),
`effect_glitch_stack` + `frei0r_glitch0r`/`scanline0r`/`nosync0r` +
`effect_oldfilm`/`grain`/`scratchlines` (glitch/VHS/film), `composite_pip`,
`composite_set` blend modes. They're in the table for completeness but ranked low.

---

## Prioritized tutorial table

| # | Title | Channel | URL | ~Len | Teaches | New? | Primitive / gap exercised |
|---|---|---|---|---|---|---|---|
| 1 | How to Apply Speed Ramping in Kdenlive 2025? | "…in Kdenlive 2025?" series | https://www.youtube.com/watch?v=0yr_lMTticU | ~8m | Speed ramp via time remapping | NEW | Working speed (§3 timewarp) + time-remap keyframes; today's `clip_speed` is a §1.1 no-op |
| 2 | Slow Motion in Kdenlive - Time Remapping Tutorial | (indie) | https://www.youtube.com/watch?v=o69g-U1OAVI | ~10m | Time-remap keyframes, ease in/out ramps | NEW | `timeremap` producer, keyframe easing |
| 3 | How to Mix Your Voice with Music (EQ/ducking) | Kdenlive Tutorial (indie) | https://www.youtube.com/watch?v=oLdYnkcLUWI | ~9m | Voice-over vs music mix, EQ to carve space | NEW | Track-level audio (§3 High): volume/EQ filters, audio keyframing |
| 4 | Boost Your Sound Quality (denoise/EQ/loudness/reverb) | Kdenlive Tutorial (indie) | https://www.youtube.com/watch?v=rDGv8WEF87c | ~12m | Noise removal, EQ, normalize, reverb | NEW | Track/clip audio filter wrappers; ties to `audio_*` file tools |
| 5 | Speech to Text — Whisper subtitles in 5 Minutes | (indie) | https://www.youtube.com/watch?v=hoc_cmwptl0 | ~5m | Whisper STT → subtitle track | REINFORCE | Real subtitle track (§3 High): `kdenlive:docproperties.subtitleFile`, styling, burn-in |
| 6 | How to Set Up Speech-to-Text (Whisper AI) | (indie) | https://www.youtube.com/watch?v=hBdrewHR9Gs | ~8m | Whisper model install + captioning | REINFORCE | Subtitle track + subtitle styling |
| 7 | Object Mask - Kdenlive Tutorial (SAM2, 25.04) | (indie, DE) | https://www.youtube.com/watch?v=4Pw9b6xhO_k | ~10m | SAM2 local-AI object mask / bg removal | REINFORCE | `effect_object_mask` (exists) + AI subject focus §5; roto luma matte |
| 8 | How to Create Lower Thirds Titles (animated) | Geek Outdoors EP995 | https://www.youtube.com/watch?v=w1-Drj1-l-0 | ~10m | Animated lower-third title + slide-in | REINFORCE | Title clips §6 (`title_card_add`, `lower-third` style) + `effect_transform` |
| 9 | Kdenlive Tutorial - Clean Smooth Lower Thirds | (indie) | https://www.youtube.com/watch?v=KEjZH1PRYPk | ~12m | Rect + text lower third, keyframed reveal | REINFORCE | Title XML builder, keyframed transform, alpha shape |
| 10 | Masking & Transition Effects (masked transitions) | (indie, 2026) | https://www.youtube.com/watch?v=tHzP9kJQJeg | ~11m | Masked/shape reveal transitions | NEW | `composite_wipe` ext (custom luma, invert, softness) + `effect_luma_key` |
| 11 | Kdenlive Tutorial - Transition #2 [Custom wipes] | (indie) | https://www.youtube.com/watch?v=Ih7c65LsLZc | ~9m | Custom .pgm luma wipe files | REINFORCE | `composite_wipe` custom-luma-matte param |
| 12 | Light leaks via Screen/Lighten blend transition | (indie) | https://www.youtube.com/watch?v=-3TjF3OzECc | ~8m | Overlay light-leak footage w/ Screen blend | NEW | Additive overlay track + `composite_set` blend mode + overlay-clip insert |
| 13 | From day to night (color sim + sky) | kdenlivetutorials.com (blog) | https://www.kdenlivetutorials.com/2014/11/from-day-to-night/ | blog | Day→night via hue/sat/levels keyframes; sky overlay | NEW | Keyframed color grade (hue/levels) + overlay-track sky replacement |
| 14 | 2024 Kdenlive Tutorial - Picture in Picture | TJ Free | https://www.youtube.com/watch?v=q8zp9tKkoPs | ~10m | PiP via Transform effect | REINFORCE | `composite_pip` (exists) + `effect_transform` scale/pos |
| 15 | Two Ways To Create Split / Quad Screen Videos | (indie) | https://www.youtube.com/watch?v=7C2oP2z0m3Y | ~9m | Split/quad screen layout | REINFORCE | `effect_transform` + multi-track composite; crop |
| 16 | Zoom / Whip-Pan Transition | (indie) | https://www.youtube.com/watch?v=ex7GoLFOnio | ~7m | Zoom + whip-pan transition | REINFORCE | Keyframed `effect_transform` (scale + motion blur) |
| 17 | Smooth Transitions, Camera Shake, Drop Shadow | (indie, 2024) | https://www.youtube.com/watch?v=V0_yp-ziqvI | ~13m | Camera shake, drop shadow, smooth cuts | NEW | Keyframed transform (shake), drop-shadow effect wrapper |
| 18 | Stabilizing Video with Vidstab (no commandline) | (indie) | https://www.youtube.com/watch?v=eo7HSqKsd70 | ~9m | vidstab clip-job stabilization | REINFORCE | Stabilization wrapper (§3 Medium): analyze + `vidstab` filter |
| 19 | 2024 Kdenlive - Best Proxy Settings | TJ Free | https://www.youtube.com/watch?v=gXz-g0khrWs | ~11m | Proxy config for performance/quality | REINFORCE | Proxy wiring (§3 Medium): set `kdenlive:proxy` on producers |
| 20 | Multicam editing (multiple camera angles) | (indie) | https://www.youtube.com/watch?v=HSqwLwl6-Qk | ~12m | Multicam tool, synced cuts | REINFORCE | Multicam (§3 Low); multi-track sync, place-at-frame |
| 21 | Timelapse / Slideshow from images | (indie) | https://www.youtube.com/watch?v=dxHC_BzryuA | ~10m | Slideshow clip from image folder | BUILT (additive) | `media_slideshow` ships the additive route (folder → `.mp4` via FFmpeg, then ingestable); native image-sequence producer (SYNTHESIS #9, `%04d`) still deferred — see docs/research/2026-07-03-tutorial-effect-analysis/timelapse-slideshow.md |
| 22 | 2025 Kdenlive - Guides → YouTube Chapters | TJ Free | https://www.youtube.com/watch?v=LiKnPfPidKU | ~7m | Guides exported as YT chapters | REINFORCE | Guides as first-class tools (§3 High) + chapter export (§3 Medium) |
| 23 | 2024 Kdenlive Tutorial - How to Use Keyframes | TJ Free | https://www.youtube.com/watch?v=0DdfHgIuS-4 | ~14m | Keyframe fundamentals (pan/zoom) | REINFORCE | Keyframable wrappers (§3 Medium); `effect_keyframe_*` UX model |
| 24 | Rewind effect (VHS reverse) | (indie) | https://www.youtube.com/watch?v=MnErqP9iIWU | ~6m | Reverse-clip cassette rewind look | NEW | Reverse clip (§3 Low) + oldfilm/scanline stack |
| 25 | How to Apply LUTs for Color Grading 2025? | "…in Kdenlive 2025?" series | https://www.youtube.com/watch?v=fh3qETbfx_8 | ~7m | LUT-based cinematic grade | REINFORCE | `color_apply_lut` (exists) — validation, LUT library workflow |

**Count: 25 tutorials.**

---

## Goldmine channels (batch-download candidates)

Worth pointing `scripts/download_playlist_transcripts.py` at whole playlists:

- **TJ Free** — largest FOSS-creative channel (~280k subs). Systematic
  "20XX Kdenlive Tutorial — <topic>" series, refreshed per Kdenlive version.
  Consistent, current, covers keyframes, proxy, PiP, chapters, transitions.
  **Top batch-download priority.**
- **Geek Outdoors ("Geekoutdoors.com EP###")** — very prolific, bite-sized,
  numbered EP series (EP949 proxy, EP963 chroma, EP988/995 audio+titles,
  EP1039 speed). Dozens of single-topic episodes = ideal per-effect analysis.
- **"How to … in Kdenlive 2025?" series** — a prolific channel pumping out
  version-current single-topic how-tos (speed ramping, chroma, LUTs, proxy,
  split screen). Recent (2025) = matches Kdenlive 24/25 features.
- **Arkengheist 2.0** — text effects, transitions, timelapse, animation, lower
  thirds, rotoscoping (overlaps our known gaps; good for transform/roto depth).
- **Victoriano de Jesus** — beginner→advanced incl. motion tracking (reinforces
  the §5 subject-track gap).

Reference: [MakeUseOf — 5 Best YouTube Channels to Learn Kdenlive](https://www.makeuseof.com/youtube-channels-to-learn-kdenlive/)
and the official [Kdenlive video tutorials index](https://docs.kdenlive.org/en/getting_started/tutorials/video_tutorials.html).

---

## Top 5 to analyze next

Chosen to fill the largest **uncovered** workflow holes (not just re-run known
Nuxttux territory), each exercising a high-value missing/broken primitive.

1. **Speed ramping / time remapping** (#1 + #2) — Fills the single most broken
   primitive: `clip_speed` writes a `<filter type="speed">` that MLT ignores
   (§1.1 no-op). These teach the *ramp* workflow (ease in/out between speeds),
   which needs `timewarp`/`timeremap` producers + keyframe easing — a
   High-value gap with zero current coverage. Analyze to spec `clip_speed`
   replacement + a `speed_ramp` tool.

2. **Audio mixing & ducking** (#3 + #4) — Completely uncovered territory. All
   current `audio_*` tools operate on standalone files in `media/processed/`,
   disconnected from the timeline. These teach voice-vs-music balance, EQ
   carving, and (implied) ducking — exactly the track-level mixer control
   §3 High calls out. Analyze to spec track volume/pan/EQ filters + audio
   keyframing on timeline clips.

3. **Animated lower thirds** (#8 + #9) — On-screen animated text is the biggest
   visible gap for tutorial-style videos (§6). `title_cards_generate` only
   writes guides — no real title exists. These demonstrate the `lower-third`
   style + slide-in animation we want the title builder + keyframed transform
   to produce. Analyze to firm up `TitleSpec` and the `lower-third` template.

4. **Masked / custom-luma wipe transitions** (#10 + #11) — A whole transition
   class we can't build: `composite_wipe` has no custom luma-matte / invert /
   softness params, and `effect_luma_key` doesn't exist. Masked shape reveals
   and .pgm wipe files are bread-and-butter editing. Analyze to spec the
   `composite_wipe` extension + `effect_luma_key`.

5. **Light leaks + day-to-night grade** (#12 + #13) — Two genuinely NEW recipes
   that share one primitive pattern: an **additive overlay track** (light-leak
   footage with Screen/Lighten blend; sky image over graded footage) plus
   **keyframed color** (hue/sat/levels day→night). Neither the overlay-clip
   insert-on-new-track workflow nor keyframed grading transitions are covered.
   Analyze to spec an overlay-insert helper + keyframable color wrappers.

## Notes for future scans

- Kdenlive 25.04 shipped **SAM2 object masks** (local AI bg removal / roto) and
  25.x improved **Whisper subtitles** — both are current-version features our
  primitives partially touch (`effect_object_mask` exists; subtitle track does
  not). Prioritize 2025+ tutorials to catch 24/25-era UI.
- Green screen, LUTs, glitch/VHS, PiP, blend modes are **already primitives** —
  future tutorials on them are validation fodder, not gap-finders. Rank low.
</content>
</invoke>
