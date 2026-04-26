# Kdenlive smoke verification checklist

What to look for when opening each `.kdenlive` smoke output in
Kdenlive 25.08.3.  Files live at
`C:/Users/CalebBennett/Videos/Video Production/tests/mcp_output/`.

For each smoke:
* **Opens clean** = no warning dialog, no "project corrupted" message, no
  "non standard framerate" warning.
* **Visually correct** = the described visual/auditory effect actually
  happens during playback.
* **UI state correct** = the relevant control reflects the model state
  (e.g. mute toggle off for muted tracks, fade-from-black checkbox
  ticked when the brightness fade is applied).

If any check fails, copy the **exact** Kdenlive error text and tell me;
the matching upstream test-suite file is in
`tests/fixtures/kdenlive_references/` for diffing.

---

## Batch 8 (audio fades)

### `025-audio-fade-in-out.kdenlive`
* **Opens clean.**
* Single video clip on V1 (with audio routed to A1 separately).
* Play A1: the audio fades IN over the first 2 seconds, plays at full
  volume in the middle, then fades OUT over the last 3 seconds.
* The fade filters live on the A1 entry, NOT the V1 entry.

### `026-audio-fade-in-music-bed.kdenlive`
* **Opens clean.**
* V1 video clip + A2 music-bed clip.
* The music bed on A2 fades up over 2 seconds.

---

## Batch 9 (avfilter, video fades, effect zones, 3-way grade, dissolves)

### `027-avfilter-gblur.kdenlive`
* **Opens clean.**
* Single clip on V1.  Starts visually sharp, ramps to **heavy
  gaussian blur** by the end (sigma 0 → 20).
* Effect panel for the clip shows an `avfilter.gblur` filter with the
  sigma keyframes.

### `028-video-fade-from-to-black.kdenlive`
* **Opens clean.**
* Single clip on V1.  Fades **from black** over the first ~3 seconds,
  plays clean in the middle, fades **to black** over the last ~3 seconds.
* In the effect panel: `Fade from Black` and `Fade to Black` checkboxes
  are **ticked** (this is what `start=1` controls).
* If the fade animates but the checkbox is unticked, `start=1` is missing.

### `029-effect-zone-scoped-brightness.kdenlive`
* **Opens clean.**
* Brightness boost applied only to a sub-range (frames 30-89) of the
  clip.  Outside that zone the clip plays untouched.
* The timeline header should show the effect-zone bracket on the clip.

### `030-lift-gamma-gain-3way-grade.kdenlive`
* **Opens clean.**
* Clip has a 3-way colour grade: lifted shadows, slightly warm
  midtones, cooled highlights.  The look is subtle, not dramatic.
* Effect panel shows a `lift_gamma_gain` filter with 9 scalars.

### `031-long-cross-dissolve.kdenlive` ✅ VERIFIED 2026-04-26
* **Opens clean.**
* Two clips on V1 + V2 with a **3-second cross-dissolve** between them.
* The dissolve must visually crossfade — clip A becoming gradually
  transparent while clip B becomes opaque.  If it's a hard jump cut
  with no blend, the `kdenlive:mixcut` regression has come back (this
  was smoke 031's earlier failure).

---

## Batch 10 (build pipeline producer shape)

### `032-selects-timeline.kdenlive`
* **Opens clean.**
* Multiple clips on V1 representing the "selects" cut.

### `033-review-timeline.kdenlive`
* **Opens clean.**
* Review-cut layout opens without producer-shape errors.

---

## Batch 11 (track mute / hide)

### `034-track-mute-and-hide.kdenlive`
* **Opens clean.**
* Three tracks: V2 (top, hidden), V1 (visible), A1 (muted).
* In the timeline header: V2's **eye toggle** is OFF, A1's
  **speaker toggle** is OFF, V1 is normal.
* Press play: NO sound from A1, NO video from V2.  Only V1 plays.
* If the toggles look normal (visible/unmuted), the `hide="both"`
  attribute didn't take effect.

---

## Batch 12 (avfilter geometry / stylise / drawing)

### `035-avfilter-hflip.kdenlive`
* **Opens clean.**
* Clip plays **mirrored horizontally** (text appears reversed).

### `036-avfilter-crop-centered.kdenlive`
* **Opens clean.**
* Clip is cropped to a **centred 1280×720 window** of the original
  1920×1080 source.  You should see less of the periphery than normal.

### `037-avfilter-sepia.kdenlive`
* **Opens clean.**
* Clip plays with a **warm sepia tone** (vintage-photo look) via the
  colour-channel-mixer matrix.

### `038-avfilter-negate.kdenlive`
* **Opens clean.**
* Clip plays as a **photographic negative** (colours inverted).

### `039-avfilter-drawbox.kdenlive`
* **Opens clean.**
* A **filled red rectangle** (200×200, ~60% opacity) appears at the
  top-left of the frame for the duration of the clip.

### `040-avfilter-drawgrid-thirds.kdenlive`
* **Opens clean.**
* A **rule-of-thirds grid overlay** (white, ~40% opacity, 2px lines)
  is visible across the frame.  Useful framing reference.

---

## Batch 13 (avfilter colour-grade / artistic)

### `041-avfilter-eq-warm-contrasty.kdenlive`
* **Opens clean.**
* Clip plays with a mild brightness lift, slight contrast bump, and
  slightly more saturation than the source.

### `042-avfilter-huesaturation-teal-shift.kdenlive`
* **Opens clean.**
* Clip has a **teal-shifted look** — hue rotated -15°, saturation
  bumped.  Not a heavy grade; should be subtle.

### `043-avfilter-curves-vintage.kdenlive`
* **Opens clean.**
* Clip has the ffmpeg "vintage" preset look — crushed shadows, lifted
  blacks, slight desaturation.

### `044-avfilter-boxblur.kdenlive`
* **Opens clean.**
* Clip is heavily **box-blurred** (luma_radius=10).  Different blur
  character than gblur (027) — boxier, less smooth.

### `045-avfilter-chromahold-red.kdenlive`
* **Opens clean.**
* Clip plays with **only red preserved** — everything not red is
  desaturated to greyscale.  The "Schindler's List red dress"
  effect.  If the source has very little red, the effect will look
  almost monochrome (still correct — just nothing to highlight).

### `046-avfilter-edgedetect-canny.kdenlive`
* **Opens clean.**
* Clip plays as a **Canny edge-detected line drawing** (graphic-novel
  / comic-book look).

---

## Batch 14 (same-track audio mix — NEW PATTERN)

### `047-same-track-audio-mix.kdenlive`
* **Opens clean.**  This is the FIRST verification of the
  `TrackMixTransition` shape — important to confirm.
* In the timeline: TWO clips on A1, adjacent, with a **1-second
  crossfade** between them (the second clip's leading edge fades in
  while the first clip's trailing edge fades out).
* Listen carefully at the cut: the audio should crossfade smoothly,
  NOT jump-cut.  If it jump-cuts, the in-tractor mix transition
  isn't taking effect (Kdenlive likely silently dropped it).
* In Kdenlive's UI the cut may appear as a "Mix" cut with an X-shape
  overlay rather than a hard line.

---

## Batch 15 (same-track slide/wipe — NEW PATTERN)

### `048-same-track-slide-in.kdenlive`
* **Opens clean.**
* Two clips on V1 with a **1-second slide-in** transition: clip 2
  slides in from the LEFT to replace clip 1 (clip 2 starts off-screen
  to the left and translates rightward into frame).
* Note: I used the same source file for both clips, so the visual
  effect is "the same image slides in over itself" — what you're
  verifying is that the slide animation actually plays, not that two
  different images appear.

---

## Batch 16 (frei0r colour effects — NEW PREFIX SHAPE)

### `049-frei0r-brightness.kdenlive`
* **Opens clean.**
* Clip plays slightly brighter than source (Brightness=0.6, where 0.5
  is neutral).  Effect panel shows `frei0r.brightness`.

### `050-frei0r-colorize-warm.kdenlive`
* **Opens clean.**
* Clip has a **warm orange colorize**.  Different look than the
  avfilter sepia — more saturated and uniform.

### `051-frei0r-contrast0r.kdenlive`
* **Opens clean.**
* Clip has a **contrast bump** (Contrast=0.6, neutral=0.5).

### `052-frei0r-saturat0r-muted.kdenlive`
* **Opens clean.**
* Clip plays with **reduced saturation** (Saturation=0.3, neutral=0.5)
  — a muted/desaturated look.

---

## Batch 17 (typewriter title)

### `053-typewriter-title-animation.kdenlive` ✅ VERIFIED 2026-04-26
* **Opens clean.**
* A 5-second editable title card on V1 with the text "Hello, world!".
* On playback: the text **types itself out character-by-character**
  rather than appearing all at once.  ~8 frames per character with
  mild timing jitter.
* If the text appears all at once, the `typewriter="1;..."` attribute
  didn't take effect (the leading `1` is the enable flag).

---

## Batch 18 (native MLT effects)

### `054-chroma-key-green.kdenlive` ✅ VERIFIED 2026-04-26
* **Opens clean.**
* Two video tracks: V1 = solid **magenta** colour generator, V2 =
  Mixkit reporter clip on a green background (downloaded to
  `tests/fixtures/media_generated/greenscreen_reporter_720.mp4`)
  with the chroma key applied.
* Play back: the **reporter is preserved**, the green background
  becomes transparent, and **magenta from V1 bleeds through** where
  the green used to be.
* If the entire frame stays green (with no magenta showing), the key
  isn't taking effect.  If everything is magenta, `variance` is too
  high and the key is matching too much.

### `055-lumakey-white-isolation.kdenlive` ✅ VERIFIED 2026-04-26
* **Opens clean.**
* Two video tracks: V1 = solid **cyan** colour generator, V2 = the
  same Mixkit reporter clip with the lumakey applied
  (threshold=200, slope=20, keep bright pixels above ~210 luma).
* Play back: the **green background** (luma ~182) becomes
  transparent and **cyan bleeds through** where the green used to
  be.  Dark suit and shadow areas may also tint cyan.  Bright
  whites (the shirt, edge highlights) stay opaque.
* If everything stays green/black, threshold is too low and the
  green BG isn't crossing the transparency boundary.  If the
  reporter vanishes entirely, threshold is too high.
* Note on 80→200 threshold change: the original threshold=80 silently
  did nothing because no part of the green-screen clip has luma
  below 80 except deep shadows in the suit.

### `056-dynamictext-timecode-overlay.kdenlive` ✅ VERIFIED 2026-04-26
* **Opens clean.**
* Clip plays with a **live-updating "TC HH:MM:SS  •  Frame N"
  overlay** in the bottom-right corner.  The numbers must change
  per-frame as playback advances.  If they're frozen at frame 0, the
  `#tag#` substitution isn't working.

### `057-timer-count-up.kdenlive`
* **Opens clean.**
* Clip plays with a **large count-up clock** centered in the frame
  ("00:00.000" climbing up to ~00:01.667 for the 4-second clip).
* Format string is `MM:SS.SSS`.

---

## What to do if a smoke fails

1. Copy the EXACT Kdenlive error message (or describe the visual
   problem if it opens but plays wrong).
2. Note which smoke number.
3. Compare against the matching upstream reference in
   `tests/fixtures/kdenlive_references/`:
   - `audio_mix_upstream_kde.kdenlive` — for 047
   - `mix_slide_upstream_kde.kdenlive` — for 048
   - `qtblend_freeze_upstream_kde.kdenlive` — for 049-052 (frei0r)
   - `typewriter_effect_upstream_kde.kdenlive` — for 053
   - `mlt_plus_video_effects_upstream_kde.kdenlive` — for 054-057
   - `video_fade_black_native.kdenlive` (user-saved) — for 028

4. The contract details for the trickiest patterns are documented in:
   - [[kdenlive-avfilter-and-effect-zones]]
   - [[kdenlive-audio-fade-pattern]]
   - [[kdenlive-cross-dissolve-pattern]]
   - [[kdenlive-test-suite-coverage-audit]] — running gap inventory
