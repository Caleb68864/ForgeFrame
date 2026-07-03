---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: lower-thirds & title clips"
author: analysis agent
tags: [kdenlive-mcp, research, titles, lower-thirds, kdenlivetitle]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
scout: vault/Research/Kdenlive Tutorial Landscape - Uncovered Effects.md
---

# Lower-Thirds & Title-Clip Tutorials → MCP Tool Surface Mapping

Two tutorials — scout top-5 item #3 (tutorials #8 + #9) — analysed against the
workshop-video-brain MCP surface, and used to design + **build** the first real
on-screen title capability (§6 of the improvements plan). Prior to this work
`title_cards_generate` only wrote **guides**; nothing ever rendered text on
screen. Transcripts:

- `vault/Transcripts/Kdenlive Tutorials/How to Create Lower Thirds Titles (Animated Lower Thirds) - Kdenlive Tutorial Geekoutdoors.com EP995.md`
- `vault/Transcripts/Kdenlive Tutorials/Kdenlive Tutorial - Clean Smooth Lower Thirds.md`

Map vs `docs/research/2026-07-03-tutorial-effect-analysis/SYNTHESIS.md`: both
videos exercise SYNTHESIS gap **#5 "Title clips" (§6)** and **#4 effect_transform**
/ **#7 effect_alpha_shape**; #8 (EP995) additionally leans on the **composite_wipe**
family for its reveal.

## Cross-cutting findings

| Capability | MCP status | Notes |
|---|---|---|
| **Title clip (`kdenlivetitle` producer)** | **BUILT (this work)** | New `pipelines/titles.py` `build_title_xml(TitleSpec)` + `title_card_add` bundle tool. Registers a real `kdenlivetitle` producer (clip_type 6) with `xmldata`, places it on a top video track. Was entirely absent before. |
| **Text over background rect** | **BUILT** | `TitleSpec.background` emits a `QGraphicsRectItem` behind the text (both tutorials' core anatomy: a bar + text). |
| **Profile-aware safe areas** | **BUILT** | Font sizes and margins are fractions of profile height/width (title-safe `safe_margin=0.1`); verified across 1080p / 4K / 9:16 vertical. No hardcoded 1080p. |
| **Slide-in / animated reveal (keyframed `transform`)** | **PARTIAL / DEFERRED** | Both videos animate the card in with a keyframed **Transform** (EP995 uses a **wipe composition**; #9 uses **Transform** + **alpha-shape** grow). `effect_keyframe_set_rect` exists to write the keyframes, but is subject to the §1.1 root-placement risk; `title_card_add` ships the static placement and leaves animation to a follow-up. |
| **Alpha-shape reveal (grow rectangle)** | **PARTIAL** | `mask_set_shape("rect", ..., alpha_operation="sub")` exists but is static frame-0 only; video #9's animated grow (size 0→full, keyframed) needs keyframed alpha shape (SYNTHESIS #7). |
| **Wipe / composition transition reveal** | **PARTIAL/BROKEN** | EP995's whole animation is a `wipe` **composition** with selectable luma. `composite_wipe` exists but transitions are §1.1-suspect and lack custom-luma/softness (SYNTHESIS #7). |
| **Template title reuse / save-as-template** | **BUILT (style tier)** | `templates/titles/*.yaml` styles (`lower-third`, `chapter-card`); both tutorials stress "save it and reuse, just swap the text". On-disk `.kdenlivetitle` template files with `%s` substitution remain deferred. |
| **Duplicate title clip + reverse keyframes (out animation)** | **MISSING** | Video #9's disappear phase = copy clip, reverse keyframes. No clip-duplicate / keyframe-reverse op. |

## Video 8 — "How to Create Lower Thirds Titles (Animated)" — Geek Outdoors EP995 (w1-Drj1-l-0, 7:29)

Beginner-level: build a custom title clip (text + rectangle), then animate it on
with a **wipe composition** rather than the (disliked) built-in title animation.

### a) Technique breakdown

1. **[00:00]** Reviews the three **template titles** (scrolling / graphics-overlay /
   plain-text) — dismisses them as too basic; builds a custom one instead.
2. **[01:31]** *Add Title Clip*: shows the background to place text over video. Title
   editor tools = **add text**, **add rectangle**, **add image**, **save as template**.
3. **[01:31]** Type the text; change **color / text style**; add a **rectangle** (only
   shape available). Rectangle covers the text → **lower object to bottom** (z-order),
   then resize/position as a backing bar.
4. **[02:16]** Notes Kdenlive's built-in title **animation** is "not intuitive / basic"
   — deliberately avoids it.
5. **[03:03]** Real animation via **compositions** (formerly transitions): picks
   **Wipe** for its many reveal types; default sub-type is **Dissolve** (fade). Warns
   of a v19.04.1 bug where a composition placed at clip start covers the whole clip.
6. **[03:50]** Swaps the wipe type (e.g. **bilinear** "grows in"); adds the **same
   composition at the end reversed** for the out. Mentions **downloadable extra wipes**.
7. **[06:09]** Closing advice: for fancier lower-thirds, play with **shapes** in the
   title editor and reuse the saved title.

### b) Kdenlive features / effects named

Template titles (scrolling / graphics / text); Add Title Clip; title editor text +
color + style; rectangle shape; z-order ("lower object to bottom"); save-as-template;
built-in title animation (rejected); **Wipe composition** (Dissolve/bilinear/clock/…);
reversed composition for out; downloadable wipe luma files.

### c) Capability mapping

| Step | MCP tool | Status | Why |
|---|---|---|---|
| Add custom title (text) | `title_card_add(text=…)` | **BUILT** | `kdenlivetitle` producer w/ `QGraphicsTextItem`. |
| Backing rectangle behind text | `title_card_add(background=True via style)` | **BUILT** | `QGraphicsRectItem` z-index 0 under the text. |
| Color / font / size | `TitleSpec` (`font_color`, `font_family`, `title_font_scale`) | **BUILT** | Profile-aware sizing. |
| Z-order rect under text | builder z-index (rect 0, title 1, subtitle 2) | **BUILT** | Deterministic ordering. |
| Save as template / reuse | `templates/titles/*.yaml` styles | **PARTIAL** | Named styles reusable; on-disk `.kdenlivetitle` w/ `%s` deferred. |
| Wipe-composition reveal in/out | `composite_wipe` | **PARTIAL/§1.1** | Exists but transition placement suspect; no custom-luma/softness. |
| Place on top track over footage | `title_card_add(track=None)` | **BUILT** | Creates a dedicated top video track. |

## Video 9 — "Clean Smooth Lower Thirds" — Arkengheist 2.0 (KEjZH1PRYPk, 12:41)

Advanced/manual: two rectangles + two text lines, each on its own track, animated
with **Transform** keyframes and **alpha-shape** grows for a polished slide/reveal;
disappear phase built by duplicating clips and reversing keyframes.

### a) Technique breakdown

1. **[00:04]** Build the graphics as **title clips**: a big rectangle + a smaller
   rectangle (matched offsets); **duplicate** the title and delete one rect from each
   copy so each rect lives on its own clip/track.
2. **[01:38]** Small rect on **V2** (*insert track*), ~4 s. Add **Transform**;
   keyframe it sliding in from the right; add **mid keyframes** and drag left to fake
   an **ease** ("Kdenlive doesn't have curved keyframes → do it manually").
3. **[02:24]** Big rect underneath, starting ~½ s later; animate it with **Alpha
   shapes** (not Transform) so it **grows** from bottom-left: size 0 at frame 0 →
   full, keyframed; feather via **transition width** (0).
4. **[03:58]** Text: new **title clip** (Ctrl-T) placed after the bars; **Transform**
   slide-in keyframes so the text is hidden left of the bar then reveals; **Alpha
   shapes (subtract)** to clip the text to the bar; timing nudged later.
5. **[07:05]** Second text line: same recipe; **reuse the alpha-shapes** by copying
   the effect onto the second clip; set opacity 0 on the first keyframe so it grows
   in.
6. **[08:38]** A small graphic/logo line: **Transform** scaled to ~8–9 %, opacity
   0→100, slide to final position.
7. **[10:14]** **Disappear phase**: rather than just fading opacity, **copy-paste each
   clip and reverse all keyframes** to mirror the entrance; align timings (e.g. frame
   290 / −324) and set opacity endpoints to 0.

### b) Kdenlive features / effects named

Title clips (rectangles + text); duplicate title clip; insert track; **Transform**
(keyframed position/scale/opacity, manual easing); **Alpha shapes** (grow, subtract,
transition-width feather, keyframed size); copy effect between clips; opacity
keyframes; copy-paste clip + **reverse keyframes** for the out.

### c) Capability mapping

| Step | MCP tool | Status | Why |
|---|---|---|---|
| Title clips (rects + text) | `title_card_add` | **BUILT** | Text + rect items; multi-line via `subtitle`. |
| Two rects on separate tracks | `title_card_add(track=…)` ×N + `track_add` | **PARTIAL** | Can place per-track; the two-clip split trick is manual. |
| Transform slide-in keyframes | `effect_add("qtblend"/"affine")` + `effect_keyframe_set_rect` | **PARTIAL/§1.1** | Keyframe writer exists; placement risk; no ease-curve helper. |
| Manual easing (mid keyframes) | `effect_keyframe_set_rect` (multi-kf string) | **PARTIAL** | Expressible; no smoothing/ease operator surfaced. |
| Alpha-shape grow (size 0→full) | `mask_set_shape("rect", alpha_operation="sub")` | **PARTIAL** | Static frame-0 only; animated grow missing (SYNTHESIS #7). |
| Feather via transition width | `mask_set_shape(feather=…)` | **PARTIAL** | Maps to feather; slider semantics approximate. |
| Opacity 0→100 keyframes | `effect_keyframe_set_scalar` | **PARTIAL/§1.1** | Scalar keyframes exist; placement risk. |
| Copy effect to 2nd clip | `effects_copy` / `effects_paste` | **EXISTS** | Stack copy/paste shipped. |
| Scale logo ~8 % | `effect_keyframe_set_rect` | **PARTIAL** | Expressible. |
| Copy clip + reverse keyframes (out) | — | **MISSING** | No clip-duplicate / keyframe-reverse op. |

## d) Bundle tool spec — `title_card_add` (BUILT)

```
title_card_add(
  project_file: str,          # path to the .kdenlive to modify
  text: str,                  # primary line
  subtitle: str | None = None,
  style: str = "lower-third", # templates/titles/<style>.yaml (lower-third | chapter-card)
  at_seconds: float = 0.0,
  duration_seconds: float = 4.0,
  track: int | None = None,   # None → new dedicated top video track
)
```

Composes: `build_title_xml(TitleSpec)` → register `Producer(mlt_service=kdenlivetitle,
xmldata=…, length=frames)` in `KdenliveProject.producers` → create/resolve a top
video track → place a `PlaylistEntry` at `at_seconds` (blank-padded) →
snapshot-before-write → `serialize_project` (serializer already writes producers +
`xmldata` from the model; serializer/patcher untouched).

`TitleSpec` (pure, in `pipelines/titles.py`): text/subtitle, profile
`width/height/fps`, `duration_seconds`, `font_family` (default **DejaVu Sans**),
`title/subtitle_font_scale` (height-relative) or explicit px, colors (hex or
`r,g,b,a`), outline, `align`, `anchor` (lower-third/center/top/bottom),
`safe_margin`, background rect toggle/color. Geometry via `compute_layout(spec)`.

**Follow-on primitives (not built here, per achievable-subset):** animated slide-in
(keyframed `transform` — §1.1 placement fix first), keyframed alpha-shape grow
(SYNTHESIS #7), reversed-keyframe "out" animation, on-disk `.kdenlivetitle` template
files with `%s` substitution, `title_cards_generate` rewire (marker → real titles),
`title_style_list`.

## e) Empirical melt verification

`melt -query producer=kdenlivetitle` → **present** (schema_version 7.2, "Kdenlive
Titler", image_formats rgba; local MLT 7 has the Qt titler). Distro MLT logs
harmless dlopen failures for sox/movit/rtaudio — unrelated.

Render check (in `tests/integration/test_title_renders.py`, gated on melt+ffmpeg):
build a title over a solid blue color clip via `title_card_add`, `melt`-render the
card's mid frame, `ffmpeg signalstats` the frame. **Result: PASS** — bright text
pixels present (frame `YMAX=255`; lower-third text band `YMAX=255` vs mid-blue bg
`YAVG≈60`). `font-pixel-size` is the attribute the titler renders with.

**Important caveat discovered:** a **standalone** `kdenlivetitle` producer rendered
directly (`melt kdenlivetitle:file …`) flattens its item layer onto black — only the
document background survives; text/rect items appear black. The card renders
correctly **only when composited over a track below** (the real use case, and the
task's "title over a color" path). `title_card_add` always places the card on a top
track over footage, so this is handled; the render test uses the same composite path.

## Raw summary (per video)

### Video 8 — Geek Outdoors EP995 (Animated Lower Thirds)
- **Effect/tool:** `title_card_add` (custom text+rect title, wipe-composition reveal)
- **Built:** `pipelines/titles.py` (`TitleSpec`, `build_title_xml`), `title_card_add`, `templates/titles/lower-third.yaml`
- **Missing/deferred:** wipe/composition reveal (§1.1 + custom luma/softness), on-disk `.kdenlivetitle` templates with `%s`
- **§1.1 deps:** composition/transition placement for the in/out reveal

### Video 9 — Arkengheist 2.0 (Clean Smooth Lower Thirds)
- **Effect/tool:** `title_card_add` + keyframed `transform`/alpha-shape reveal (multi-rect, multi-text)
- **Built:** same title builder + tool + styles; `chapter-card.yaml`
- **Missing/deferred:** animated slide-in (keyframed transform, §1.1), animated alpha-shape grow (SYNTHESIS #7), reversed-keyframe out, clip-duplicate
- **§1.1 deps:** transform/scalar/alpha keyframe root-placement for the reveal

### Shared takeaway
The **title producer itself** was the hard blocker for both videos and is now
**built and melt-verified**. The remaining polish (slide-in / grow / reverse-out
animation) all funnels into the same two pending primitives — §1.1 filter/transition
placement and keyframed alpha-shape — already tracked in SYNTHESIS (#4/#7) and plan
§1.1/§6 step 4.
