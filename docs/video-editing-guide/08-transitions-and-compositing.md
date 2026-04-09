---
title: "Transitions & Compositing"
tags:
  - transitions
  - compositing
  - picture-in-picture
  - kdenlive
---

# Chapter 8: Transitions & Compositing

**Part 3 — Post-Production**

This chapter covers every way you join two clips together and every way you layer multiple clips on top of each other. It covers the transition between clips, compositing for picture-in-picture (PiP) and split screens, and the restraint that separates professional edits from amateur ones.

Effects, color grading, titles, and audio tools live in their own chapters — see [Chapter 12](12-effects-titles-graphics.md) (Effects, Titles & Graphics), [Chapter 9](09-color-correction-and-grading.md) (Color Correction & Grading), and [Chapter 10](10-audio-production.md) (Audio Production).

---

## How Transitions Work in Kdenlive

Kdenlive offers two technical approaches to transitions:

- **Same-track mixes:** Two clips on the same track with an overlap zone. Kdenlive applies a built-in blend (dissolve, wipe, etc.) directly at the cut. Simpler to set up; limited to clip-level blending.
- **Composite transitions (overlap method):** Two clips on separate tracks with overlapping time ranges. The overlap is governed by a **composition** — Kdenlive's term for a two-track transition. More powerful: supports PiP, keyframed movement, and arbitrary blending modes.

Most narrative cuts use the same-track mix approach. Compositing and PiP always use the two-track overlap approach.

---

## Transitions Catalog

### Hard Cut

**Definition:** An instantaneous switch from one clip to the next with no blending, movement, or visual effect. The last frame of clip A is immediately followed by the first frame of clip B.

**Use cases:**
- Standard conversational edits (talking head, interview)
- Fast-paced montage
- Anywhere the viewer should not notice the edit

**How-to:** Place two clips adjacent on the same track with no gap and no overlap. That is it — a hard cut is the absence of a transition.

**Pitfalls:**
- A hard cut on a jump in the same camera angle produces a **jump cut**. Use B-roll, a cutaway, or a slight zoom change to disguise it.
- Cutting on action (matching movement across the cut) makes hard cuts invisible. Cutting during stillness makes them obvious.

**Performance:** Zero cost. Nothing to render.

---

### J-Cut and L-Cut

**Definition:** J-cuts and L-cuts are the two most powerful editing techniques for smooth, invisible transitions. They work by offsetting the audio and video edit points so they do not land at the same time.

- **J-cut (audio leads):** The audio from clip B begins *before* the video switches to clip B. Named because the audio track of clip B dips under clip A like the bottom of a J.
- **L-cut (video leads):** The video switches to clip B *before* the audio from clip A ends. The timeline looks like an upside-down L.

**Why they work:** When audio and video cut simultaneously, the edit is jarring and mechanical. Letting one element cross the cut first smooths the transition — the viewer is already hearing what comes next before they see it, or they see the new scene while still grounded in the previous conversation.

**Use cases:**
- J-cut: cutting to a speaker before they speak (set up the context, then see who's talking)
- J-cut: hearing ambient sound from the next scene before cutting to it (pulls the viewer forward)
- L-cut: continuing narration over a new scene (keeps the listener anchored while the visuals shift)
- L-cut: reaction shots (staying on a listener while the previous speaker finishes)

**How-to (Kdenlive):**

1. Place clip A and clip B adjacent on the same timeline track.
2. **Unlock the audio/video link** on the clip you want to offset: right-click the clip → `Ungroup Audio/Video`.
3. Ripple-trim the audio portion independently. Drag the audio in or out point to offset it from the video cut.
4. Regroup if needed, or leave ungrouped for fine-tuning.

> [!tip] J/L cuts are invisible edits
> Use J and L cuts by default for talking-head content. Reserve hard cuts for moments where you want the edit to feel deliberate — high energy, comedy beats, or when visual rhythm is the point.

**Pitfalls:**
- Ungrouping audio/video makes it easy to accidentally shift clips out of sync. Lock tracks you are not editing.
- Very long audio overlaps (more than 3--5 seconds) can disorient the viewer. Keep the offset short enough that the viewer does not lose track of which scene they are in.

**Performance:** Zero. J/L cuts are editing decisions, not rendered effects.

---

### Mixes (Same-Track Transitions)

**Definition:** A crossfade or other blend applied between two adjacent clips on the **same track**. Kdenlive calls these "mixes." They require **handle frames** — extra footage beyond the visible in/out points of each clip.

**Use cases:**
- Quick dissolves between talking head segments
- Smoothing a rough cut before committing to a specific transition style
- Any transition where a two-track workflow is unnecessary overhead

**How-to:**

1. Ensure both clips have at least ~0.5 seconds (12--15 frames at 24/30 fps) of handle beyond their trim points.
2. Double-click the cut point between two clips, or select the cut and press `U`.
3. Kdenlive creates a mix zone. Drag its edges to adjust duration.
4. Right-click the mix to change the curve (linear, ease in/out, etc.).

**Pitfalls:**
- If a clip is trimmed to its absolute start or end (no handle), Kdenlive will freeze the last available frame to fill the transition — visible as a stutter. Always capture a few extra seconds on each end of every shot.
- Mixes shift clip timing. If you are working to a music beat, add the mix before locking to the beat, or adjust after.

**Performance:** Lightweight. Renders in real time on most hardware.

---

### Composite Transitions (Overlap Method)

**Definition:** Two clips placed on separate tracks with overlapping time ranges. The overlap region is governed by a **composition** (Kdenlive's term for a two-track transition). This is the classic NLE transition workflow.

**Use cases:**
- Any transition that needs fine control over duration, position, and blending
- Picture-in-picture, split screens, and layered compositing
- When you need keyframed opacity or movement during the transition

**How-to:**

1. Place clip A on track V1 and clip B on track V2, overlapping by the desired transition duration.
2. Look for the small purple triangle/dot in the corner of the overlap zone on the upper clip.
3. Click the purple dot to create a composition, or right-click the overlap and select `Insert a composition → Wipe` (or Dissolve, Slide, etc.).
4. Adjust parameters in the Effect Stack.

**Pitfalls:**
- Track order matters. The upper track is composited **over** the lower track. If the transition looks backward, swap which track holds which clip.
- Forgetting to add a composition to the overlap means the upper clip simply covers the lower clip with no blending.

**Performance:** Moderate. Two video streams decoded simultaneously. Use proxies for 4K+ footage.

---

### Wipe and Wipe Methods

**Definition:** A transition where one image progressively replaces another along a boundary defined by a **luma map** (grayscale gradient image). The boundary can be a straight line, circle, star, clock sweep, or any arbitrary shape.

**Use cases:**
- Scene changes with a strong directional feel (left-to-right, top-to-bottom)
- Stylized reveals (iris wipe, star wipe, clock wipe)
- Custom branded transitions using hand-made `.pgm` luma files

**How-to:**

1. Create a two-track overlap (see Composite Transitions above).
2. Add a `Wipe` composition to the overlap zone.
3. In the Effect Stack, choose a wipe method (built-in options include bar, barn door, clock, iris, box, and many more).
4. Adjust **softness** to control the feathered edge width (0 = hard line, higher = softer gradient).
5. Use **Invert** to reverse the wipe direction. Use **Reverse** to swap which clip is revealed vs. hidden.

**Custom luma maps:**
- Create a grayscale `.pgm` image (Portable GrayMap) the same resolution as your project.
- Black regions transition first; white regions transition last; gray regions transition proportionally.
- Place the file in `~/.local/share/kdenlive/lumas/HD/` (or the corresponding resolution folder).
- Select it from the wipe method dropdown.

**Pitfalls:**
- Low-softness wipes on compressed footage can show banding artifacts. Increase softness to 10--20% to hide them.
- Custom `.pgm` files must be the correct resolution or Kdenlive will stretch them, distorting the wipe shape.

**Performance:** Low to moderate. The luma map is a single grayscale image; the GPU handles blending quickly.

> **ForgeFrame:** Use `/ff-composite-wipe` to apply a branded wipe transition with your project's luma map:
>
> ```
> /ff-composite-wipe
> Input: clip_a="screen-recording.mp4", clip_b="demo-step-2.mp4",
>        method="bar", direction="left", softness=15, duration_frames=18
> Output: timeline updated with Wipe composition at cut point
> ```
>
> You can also do this manually: create a two-track overlap, add a Wipe composition, choose "bar" from the method dropdown, and set softness to 15 in the Effect Stack.

---

### Dissolve and Luma Dissolve

**Definition:** A **dissolve** (also called a cross-dissolve) gradually blends the opacity of two overlapping clips so that clip A fades out while clip B fades in. A **luma dissolve** uses a grayscale map to control which parts of the frame dissolve first, combining the dissolve concept with the spatial control of a wipe.

**Use cases:**
- Dissolve: passage of time, dream sequences, gentle scene changes
- Luma dissolve: organic or textured transitions (using noise, smoke, or paint-stroke luma maps)

**How-to:**

1. Create a two-track overlap.
2. Add a `Dissolve` composition for a standard cross-dissolve.
3. For a luma dissolve, add a `Wipe` composition and set softness very high (80--100%). This blurs the boundary so much that it behaves like a dissolve with spatial variation.

**Pitfalls:**
- Long dissolves (> 2 seconds) can look muddy if both clips have high visual complexity. Keep dissolves short or use them when one clip is relatively simple (e.g., a solid color or a soft-focus shot).
- A dissolve into or out of black is a **fade**, not a dissolve. Use the `Fade in` / `Fade out` effects on a single clip for that.

**Performance:** Low. Simple alpha blending.

---

### Slide

**Definition:** One clip physically moves off-screen (or on-screen) to reveal the clip beneath it. Unlike a wipe, both images are fully visible during the transition — one is sliding over or away from the other.

**Use cases:**
- Energetic, editorial-style transitions
- Revealing a new topic or segment
- Split-screen animations where panels slide into position

**How-to:**

1. Create a two-track overlap.
2. Add a `Slide` composition.
3. Choose the slide direction (left, right, up, down).
4. Adjust duration to taste. Fast slides (8--12 frames) feel punchy; slow slides (1--2 seconds) feel cinematic.

**Pitfalls:**
- Slides that are too slow look like a software glitch rather than a creative choice. Err on the side of faster.
- Combining a slide with a dissolve requires stacking two compositions or using keyframed Transform effects instead.

**Performance:** Low. Just repositioning decoded frames.

---

## Picture-in-Picture and Compositing

### Composite (General Compositing Tool)

**Definition:** The `Composite` transition type in Kdenlive layers two clips using configurable opacity and geometry. Unlike the specialized transitions above, Composite is a general-purpose compositing tool that you control entirely through keyframes.

**Use cases:**
- Picture-in-picture (PiP) layouts
- Gradual opacity fades between layers with precise keyframe control
- Any layered effect where you need to animate position, scale, and opacity simultaneously

**How-to:**

1. Place clips on two tracks with overlap.
2. Add a `Composite` composition.
3. In the Effect Stack, set **opacity** (0--100%) and adjust the **geometry** rectangle to position and scale the upper clip.
4. Enable keyframing on opacity and geometry to animate the composite over time.
5. Adjust **softness** for feathered edges on the geometry boundary.

**Pitfalls:**
- Composite does not include blending modes (multiply, screen, etc.). For those, use the `Cairo Blend` or `Cairographics Blend` effect on the upper clip instead.
- Keyframing both geometry and opacity simultaneously can produce unexpected results if keyframe positions do not align. Add keyframes at the same timestamps for both parameters.

**Performance:** Moderate. Keyframed composites with softness at high resolution benefit from proxy editing.

---

### PiP Layouts

Picture-in-picture (PiP) is one of the most useful compositing tools for tutorial creators. A common use case: show your talking head in the corner while the screen recording fills the frame.

**Standard PiP layout for tutorials:**

| Layout | Upper clip position | Scale | Notes |
|---|---|---|---|
| Bottom-right corner | X: 70%, Y: 65% | 30% | Most common for talking head overlays |
| Bottom-left corner | X: 2%, Y: 65% | 30% | Use when screen action is in the bottom-right |
| Top-right corner | X: 70%, Y: 2% | 30% | Use when screen action is in the lower portion |
| Split screen (50/50) | Left: X: 0%, Y: 0% — Right: X: 50%, Y: 0% | 50% each | Comparison or side-by-side tutorial steps |

**How-to:**

1. Place the main clip (screen recording) on V1.
2. Place the overlay clip (talking head) on V2 with the same time range.
3. Add a `Composite` or `Composite & Transform` composition to the V2 clip.
4. In the Effect Stack, set the geometry to your desired position and scale.
5. Keyframe the geometry to animate the PiP in/out if needed (e.g., slide in from off-screen at the start of a segment).

> **ForgeFrame:** Use `/ff-composite-pip` to place a PiP overlay automatically:
>
> ```
> /ff-composite-pip
> Input: main="screen-recording.mp4", overlay="talking-head.mp4",
>        position="bottom-right", scale=0.30, fade_in=true
> Output: timeline updated with Composite composition and keyframed geometry
> ```
>
> You can also do this manually: place the overlay clip on V2, add a Composite composition, and set the geometry rectangle to 30% scale in the Effect Stack.

---

## When NOT to Use Transitions

This is the section most tutorials skip.

**The default should always be a hard cut.** Every other transition choice is a deliberate departure from that default — and departures need justification.

### The questions to ask before adding a transition

1. **Does this serve the narrative?** A dissolve can signal the passage of time. A wipe can suggest geographic change. A slide can reinforce a "moving forward" theme. If you cannot articulate why a transition fits the story at this specific moment, use a cut.

2. **Am I hiding a problem?** Transitions are often added to disguise awkward cuts, jump cuts, or mismatched audio. Fix the underlying problem instead. A dissolve over a jump cut usually looks worse than the jump cut itself.

3. **Is this consistent with my edit so far?** One wipe in a video of hard cuts draws massive attention to itself. Either commit to a style throughout a sequence or stay with cuts.

4. **Am I compensating for missing B-roll?** If a transition feels necessary because a static talking-head cut feels boring, the answer is more B-roll, not a dissolve.

### Transitions that almost always signal a mistake

| Transition | The problem it usually signals |
|---|---|
| Slow dissolve between two similar shots | Jump cut disguise — use a cutaway instead |
| Wipe in a corporate tutorial | Draws attention to itself; rarely serves the content |
| Star wipe, clock wipe | Almost never appropriate in non-comedic content |
| Any transition applied uniformly to every cut | The editor hasn't thought about each cut individually |
| Dissolve at every scene change | Passage-of-time effect loses meaning through repetition |

### When transitions genuinely work

- **Dissolve:** Time lapse, dream sequences, memory sequences, end-of-section soft landings before a chapter card
- **Wipe:** Reveal moments where you want the viewer to notice the transition (deliberately stylized)
- **Slide:** High-energy sequences, product reveals, or branded transitions where motion graphics are part of the identity
- **Fade to black / from black:** Opening and closing segments; separating major structural sections of a long video
- **J/L cuts:** Always. Use these by default for every conversational cut.

> [!tip] Restraint is craft
> Tutorial creators who use hard cuts and J/L cuts exclusively often produce cleaner, faster-paced content than creators who reach for transitions as decoration. Train yourself to cut first, then ask if a transition adds anything.

---

## Quick Reference

### Transition Type Selector

| You want to... | Use this |
|---|---|
| Connect two clips invisibly | Hard cut + J/L cut for audio |
| Show passage of time | Short dissolve (0.5--1 sec) |
| Wipe to reveal new content | Wipe composition (bar or iris) |
| Layer a talking head over screen recording | PiP with Composite composition |
| Animate text or graphics entering the frame | Slide composition or Transform + keyframes |
| Fade to black between sections | Fade out / Fade in on single clips |

### Composition Type Reference

| Composition | Best for | Track setup needed |
|---|---|---|
| Mix (same-track) | Simple dissolves between cuts | Same track |
| Dissolve | Cross-fades with minimal control | Two-track overlap |
| Wipe | Directional or shaped reveals | Two-track overlap |
| Slide | Movement-based transitions | Two-track overlap |
| Composite | PiP, opacity, animated geometry | Two-track overlap |
