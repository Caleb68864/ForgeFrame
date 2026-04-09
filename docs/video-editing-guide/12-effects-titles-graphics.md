---
title: "Effects, Titles & Graphics"
tags:
  - effects
  - titles
  - graphics
  - keyframes
  - kdenlive
---

# Chapter 12: Effects, Titles & Graphics

**Part 3 — Post-Production**

This chapter covers everything you apply *to* a clip rather than *between* clips. It includes Kdenlive's effects engine, the visual effect families you will use most often, how to build title cards and lower thirds, keyframing basics, and the judgment call of when to use effects versus when they get in the way.

Transitions between clips are covered in [Chapter 8](08-transitions-and-compositing.md). Color correction is covered in [Chapter 9](09-color-correction-and-grading.md). Audio effects are covered in [Chapter 10](10-audio-production.md).

---

## How Effects Work in Kdenlive

Kdenlive is a front-end. It does not contain its own effects engine. Instead it exposes what the underlying **MLT framework** and its plugin ecosystem provide:

- **frei0r** — open-source video effect plugins (color correction, blurs, generators)
- **avfilter** — FFmpeg's built-in filter library (stabilization, denoising, scaling)
- **LADSPA** — Linux Audio Developer's Simple Plugin API (audio effects — see [Chapter 10](10-audio-production.md))
- **SoX** — audio processing utilities exposed through MLT

Because Kdenlive wraps these libraries, the set of effects you see depends on which libraries were compiled or bundled with your particular build. A Flatpak install may have different effects than a distro package or a self-compiled build.

> [!warning] Effects vary by build and packaging
> If you follow a tutorial and cannot find an effect, it is likely missing from your build — not renamed or hidden. The **AppImage** from kdenlive.org bundles the most complete set of dependencies and is the recommended install method for maximum compatibility.

---

## The Effect Stack

The Effect Stack is where all effects on a clip live and where you control them. Understanding how it works prevents most beginner mistakes.

**Key behaviors:**

- **Effects process top-to-bottom.** The output of effect 1 becomes the input of effect 2. Order matters: a blur applied *before* a color grade looks different than a blur applied *after* one.
- **Each clip has its own independent Effect Stack.** Applying an effect to one clip does not affect other clips, even on the same track.
- **Effects are non-destructive.** Disable or delete any effect to revert to the original clip.
- **Keyframes live inside individual effects.** Each parameter can have its own keyframe timeline.

**Universal workflow for any effect:**

1. Find the effect in the Effects panel (search by name or browse categories).
2. Drag the effect onto a clip in the timeline, or select the clip and double-click the effect.
3. Adjust parameters in the **Effect Stack** panel.
4. If the effect should change over time, enable **keyframing** on individual parameters.
5. If playback becomes choppy, enable **proxy clips** (`Project → Project Settings → Proxy`) and work with lightweight copies until final render.

> **ForgeFrame:** Use `/ff-effect-add` to apply an effect by name without browsing the effects panel:
>
> ```
> /ff-effect-add
> Input: clip="talking-head-01.mp4", effect="Lift/Gamma/Gain",
>        params={gain_r: 1.05, gain_b: 0.95}
> Output: effect applied to clip with specified parameters
> ```
>
> You can also do this manually: open the Effects panel, search for the effect name, and drag it onto the clip in the timeline.

> **ForgeFrame:** Use `/ff-effect-list-common` to see which effects are most useful for your current project type:
>
> ```
> /ff-effect-list-common
> Input: project_type="tutorial", problem="shaky footage"
> Output: ranked list of recommended effects with brief explanations
> ```
>
> You can also do this manually: browse the Effects panel's categories — "Transform" for geometry, "Color" for grading, "Blur & Sharpen" for softening.

---

## Video Effects Quick-Fix Table

Use this table when you know what problem you need to fix but you are not sure which tool to reach for.

| Goal | Tool(s) | Why |
|---|---|---|
| Green screen removal | `Chroma Key: Advanced` | Handles spill suppression and edge refinement in one effect |
| Blur a face | `Auto Mask` (OpenCV) or manual `Obscure` with keyframes | Auto Mask tracks faces; Obscure gives manual rectangle/ellipse control |
| Stabilize shaky footage | `vidstab` (two-pass via `vid.stab Detect` + `vid.stab Transform`) | Industry-standard stabilization; first pass analyzes, second pass corrects |
| Fix exposure | `Curves` or `Levels` | Curves gives precise per-channel control; Levels is faster for simple lifts |
| Fix color cast | `Color Balance` or `Lift/Gamma/Gain` | Push the opposite color into the affected tonal range (shadows, mids, highlights) |
| Apply cinematic look | `Apply LUT` + `Curves` | LUT for the base look, Curves for fine-tuning contrast and rolloff |
| Track text to motion | `Motion Tracker` → copy data → `Transform` on title clip | OpenCV tracker generates position keyframes you paste onto any effect |
| Reduce noise | `3D FFT Denoiser` or `Afwtdn` | Temporal + spatial denoising; Afwtdn is lighter weight for mild noise |
| Create lower thirds | Title clip + `Transform` + `Composite` transition | Build the graphic in the titler, animate position/opacity with Transform |
| Reframe or push in | `Transform` with keyframes | Scales and repositions footage without quality loss (up to native resolution) |

---

## Core Video Effect Families

### Transform

**Definition:** Moves, scales, and rotates a clip within the frame. The single most frequently used effect in any project.

**Use cases:**
- Reframing a shot (push in to hide a wide composition, shift subject to rule-of-thirds)
- Animating position for sliding text, picture-in-picture, or split screens
- Correcting a slightly tilted horizon

**How-to:**

1. Apply `Transform` to a clip.
2. In the Effect Stack, click the monitor icon to enable **on-monitor handles** — draggable corners and edges directly on the preview.
3. Adjust **Position (X, Y)**, **Scale (Width, Height)**, and **Rotation**.
4. Add keyframes to animate any parameter over time.
5. Right-click a keyframe to change its interpolation (linear, smooth/bezier, discrete).

**Pitfalls:**
- Scaling up past 100% degrades quality. If you need to push in significantly, start with higher-resolution source footage.
- Rotation around a point other than center requires adjusting the **anchor point** (offset X/Y), which is not always obvious in the UI.

**Performance:** Very low. Hardware-accelerated on all modern systems.

---

### Position and Zoom (Ken Burns Effect)

**Definition:** A simplified version of Transform focused on animated pan-and-zoom across a still image or video clip. Often called the **Ken Burns effect** when applied to photographs.

**Use cases:**
- Animating still photos in a documentary or slideshow
- Slow push-in on a talking head for emphasis
- Reframing between two compositions within the same clip

**How-to:**

1. Apply `Position and Zoom` to the clip.
2. Set the **start rectangle** (the area visible at the beginning of the clip).
3. Set the **end rectangle** (the area visible at the end of the clip).
4. The effect smoothly pans and zooms between the two rectangles over the clip duration.
5. For multi-point movement, add intermediate keyframes.

**Pitfalls:**
- On video (not stills), fast zooms can reveal compression artifacts. Use high-bitrate source files or apply a subtle sharpening effect after the zoom.
- The effect crops the frame, so you lose edge content. Preview the full animation before committing.

**Performance:** Very low. Equivalent to Transform internally.

---

### Apply LUT

**Definition:** Loads a color Look-Up Table file (`.cube`, `.3dl`, `.csp`, `.m3d`) and remaps every pixel's color through it. LUTs can correct camera log profiles to Rec.709, apply film emulation, or establish a creative color grade.

**Use cases:**
- Converting log/flat camera profiles (S-Log, V-Log, C-Log) to standard color
- Applying a consistent creative look across all clips
- Matching footage from different cameras

**How-to:**

1. Apply `Apply LUT` to the clip.
2. Click the file browser and select your `.cube` file.
3. Set **interpolation** to `Trilinear` (best quality) or `Tetrahedral` (fastest, nearly identical).
4. If the LUT is designed for a specific input (e.g., S-Log3), make sure your footage matches that input profile. Applying a log-to-rec709 LUT to already-corrected footage will blow out the image.

**Pitfalls:**
- "Less is more." Heavy creative LUTs can crush shadow detail and clip highlights. Apply the LUT at reduced intensity by stacking it with a `Curves` effect to pull back extremes, or use Kdenlive's effect opacity slider if available.
- LUT quality varies wildly. Free LUTs from the internet are often poorly constructed. Test on a variety of shots, not just the hero frame.
- Stacking multiple LUTs compounds rounding errors. Use one LUT for the technical transform and do creative adjustments with native effects.

**Performance:** Low. A single 3D LUT lookup per pixel is trivially fast.

---

### Curves and Bezier Curves

**Definition:** A per-channel tone curve that remaps input brightness values to output brightness values. **Curves** provides point-based control; **Bezier Curves** adds smooth curve handles for more refined adjustments.

**Use cases:**
- Adding contrast with an S-curve
- Lifting shadows without affecting highlights
- Per-channel adjustments (boosting reds in highlights, cooling shadows)
- Matching exposure between shots

**How-to:**

1. Apply `Curves` (or `Bezier Curves` for smoother control).
2. Select the channel: Master (luminance), Red, Green, or Blue.
3. Click on the curve to add control points. Drag up to brighten that tonal range, drag down to darken.
4. The classic contrast S-curve: add a point in the lower-third and drag slightly down, add a point in the upper-third and drag slightly up.
5. Keyframe the curve for animated corrections (e.g., gradual exposure shift during a sunrise).

**Pitfalls:**
- Extreme curves create banding in 8-bit footage. Make gentle adjustments and consider working in a 10-bit pipeline when available.
- Per-channel curves shift hue as a side effect. If you push the blue channel, skin tones will go blue unless you compensate on the other channels. Use vectorscope to monitor.

**Performance:** Very low. Per-pixel math.

---

### Lift/Gamma/Gain (Color Wheels)

**Definition:** Three-way color corrector that separates the image into **shadows (Lift)**, **midtones (Gamma)**, and **highlights (Gain)**. Each range has a color wheel and a brightness slider. This is the primary color correction tool in Kdenlive — it handles 90% of correction needs.

See [Chapter 9](09-color-correction-and-grading.md) for a full color correction workflow using this tool.

**Use cases:**
- Primary color correction (the first effect in a grading chain)
- Removing color casts that affect only one tonal range (e.g., blue shadows from daylight fill)
- Establishing a mood (warm highlights + cool shadows = a classic cinematic look)

**How-to:**

1. Apply `Lift/Gamma/Gain`.
2. Drag the crosshair in each color wheel toward the color you want to add to that tonal range, or away from the color you want to remove.
3. Use the brightness slider beneath each wheel to raise or lower overall brightness for that range.
4. Work in order: fix Lift (shadows) first, then Gain (highlights), then Gamma (midtones) to fill in the middle.

**Pitfalls:**
- Small movements have large effects. Nudge the crosshair in tiny increments.
- The boundaries between shadow/mid/highlight are fixed in this effect. For more control over where the boundaries fall, use `Color Balance` or `Curves`.

**Performance:** Very low.

---

### Levels and Color Levels

**Definition:** **Levels** adjusts the input black point, white point, and gamma (midpoint) of the luminance channel. **Color Levels** does the same per RGB channel. Think of it as a simplified Curves with three sliders instead of a freeform curve.

**Use cases:**
- Quickly expanding a flat/washed-out image to full dynamic range
- Setting a clean black point and white point before applying a creative grade
- Per-channel corrections when Curves feels like overkill

**How-to:**

1. Apply `Levels` or `Color Levels`.
2. Drag the **input black** slider right until shadows just clip (watch the waveform scope).
3. Drag the **input white** slider left until highlights just clip.
4. Adjust the **gamma** (middle) slider to set midtone brightness.
5. For Color Levels, repeat per channel to remove color casts.

**Pitfalls:**
- Clipping destroys data permanently (within the effect chain). Set black/white points conservatively and use the scopes, not your eyes, since monitors lie.
- Levels and Curves serve overlapping purposes. Pick one approach per correction pass to avoid stacking redundant processing.

**Performance:** Very low.

---

### Chroma Key: Basic and Advanced

**Definition:** Removes a specific color (typically green or blue) from the frame and replaces it with transparency, allowing a background clip on a lower track to show through. **Basic** offers simple threshold controls. **Advanced** adds spill suppression, edge refinement, and per-channel tuning.

**Use cases:**
- Green screen / blue screen compositing
- Removing a colored backdrop for product shots
- Creative effects (making a specific colored object transparent)

**How-to (Advanced):**

1. Place the green screen clip on V2, the background on V1.
2. Add a `Composite` or `Composite & Transform` transition to the overlap.
3. Apply `Chroma Key: Advanced` to the V2 clip.
4. Use the eyedropper to pick the key color from the preview.
5. Adjust **Variance** to expand the key range (include more shades of green).
6. Adjust **Edge Mode** (Hard, Softened) and **Operation** to clean up fringing.
7. If green is spilling onto the subject (green tinge on skin/hair), enable **Despill** — this shifts the affected pixels away from the key color.

**Pitfalls:**
- Garbage in, garbage out. Uneven lighting on the green screen, wrinkled fabric, or shadows will fight the keyer. Fix these on set, not in post.
- Hair and transparency (glass, smoke) are the hardest elements to key. Increase variance and soften edges, but accept that a basic chroma key cannot match a dedicated compositing tool like Natron or After Effects.
- Despill can shift skin tones. Use it sparingly and check results on a vectorscope.

**Performance:** Moderate. Per-pixel color comparison with edge processing. Real-time at 1080p on modern hardware; may need proxies at 4K.

---

### Mask Apply and Masking Workflow

**Definition:** `Mask Apply` is a utility effect that restricts any preceding effects to a defined region (mask shape). It works by capturing the alpha channel generated by a mask-drawing effect and using it to limit the scope of effects stacked between the mask and Mask Apply.

**Use cases:**
- Applying color correction only to a face or sky region
- Blurring only a license plate
- Combining multiple effects that each target different areas of the frame

**How-to:**

1. Apply a mask-drawing effect first: `Shape Alpha (Mask)`, `Rotoscoping`, or `Alpha Shapes`.
2. Stack the effect(s) you want to constrain (e.g., `Curves`, `Blur`).
3. Apply `Mask Apply` after the constrained effects.
4. The effect chain order is critical: **Mask → Effect(s) → Mask Apply**.

> [!tip] Effect Stack order matters
> The Effect Stack processes top-to-bottom. If Mask Apply is not directly after the effects you want to constrain, the mask will not apply correctly. Drag effects to reorder them.

**Pitfalls:**
- You cannot nest masks easily. For multiple independent masked regions, duplicate the clip on another track and apply a separate mask chain to each copy.
- Rotoscoping masks require manual keyframing for moving subjects. Budget significant time for frame-by-frame adjustments.

**Performance:** Depends on the masked effect. The mask itself is cheap; the constrained effect carries its normal cost.

---

### Motion Tracker

**Definition:** Uses **OpenCV** tracking algorithms to follow a region of the frame across time, generating position (and optionally scale/rotation) keyframe data. The tracker itself does not move anything — you copy its keyframe data to another effect (typically Transform) to make elements follow the tracked motion.

**Use cases:**
- Attaching text or a graphic to a moving object
- Stabilizing a specific region of the frame
- Tracking a face for selective blurring (privacy)

**How-to:**

1. Apply `Motion Tracker` to the clip.
2. Draw a bounding box around the target in the preview monitor.
3. Choose a tracking algorithm (KCF is a good default; MOSSE is faster but less accurate; CSRT handles scale changes better).
4. Click **Analyze** to run the track. Kdenlive will process every frame.
5. Once complete, copy the motion data (right-click → Copy keyframes).
6. Apply a `Transform` effect to the target element (title clip, shape, blur) and paste the keyframes.
7. Adjust offset if the pasted position does not align perfectly.

**Pitfalls:**
- Tracking fails when the target is occluded, leaves the frame, or changes appearance drastically. Break the track into segments and manually bridge gaps.
- The tracker runs on the CPU through OpenCV. Long clips at high resolution take time. Track on proxy clips when possible, then re-track a short verification segment on the full-resolution clip.

**Performance:** High CPU cost during analysis (offline process). Zero cost during playback once keyframes are baked.

---

### Denoising

**Definition:** Reduces random noise (grain, color speckle) from the image. Noise comes from high ISO settings, small camera sensors, or low-light shooting conditions.

**Recommended tools:**
- **3D FFT Denoiser** (`frei0r.hqdn3d`): Temporal + spatial denoising. Analyzes neighboring pixels across multiple frames to separate noise from detail. Best for moderate to heavy noise.
- **Afwtdn** (avfilter): Wavelet-based denoiser. Lighter-weight, good for mild noise or as a secondary pass focused on chroma noise.

**How-to:**

1. Apply the denoiser to the noisy clip.
2. For `3D FFT Denoiser`: start with default settings, then increase **Spatial** and **Temporal** strength gradually. Preview at 100% zoom — noise is invisible at fit-to-window zoom.
3. For chroma-only denoising (color speckle without losing luminance detail): reduce the spatial luma parameter and increase spatial chroma.
4. Keyframe strength if noise varies (e.g., a shot that transitions from well-lit to shadow).

**Pitfalls:**
- Over-denoising creates a waxy, plastic look. Preserve some grain — it looks more natural than zero noise.
- Denoising before color grading is generally preferred (grade amplifies noise). Place the denoiser early in the effect stack.
- Temporal denoising can create ghosting on fast-moving subjects. Reduce temporal strength for action shots.

**Performance:** High. Temporal denoising reads multiple frames. Expect dropped frames during preview — rely on proxies or render a preview segment.

---

### A Note on Deprecated Effects

Kdenlive marks some effects as **Deprecated** in the effects list. These are effects that have been superseded by better alternatives, or whose underlying library implementation has known issues. They still work, but:

- They may be removed in a future version.
- They may have bugs that will never be fixed.
- There is always a recommended replacement listed in the Kdenlive documentation.

Avoid using deprecated effects in new projects. If you open an old project that uses them, consider swapping them for the current equivalent during your next revision pass.

---

## Title Cards and Lower Thirds

Titles in Kdenlive are clips, not overlays. They sit on the timeline just like any video clip and are created with the **Title Clip** editor.

### Creating a Title Card

A **title card** is a full-frame text graphic — typically used for chapter openers, section titles, or end screens.

**How-to:**

1. In the Project Bin, right-click → `Add Title Clip`.
2. The Title Clip editor opens. Click on the canvas to place a text element.
3. Set font, size, color, and alignment in the toolbar.
4. For background color: use the `Background` button and set the fill color.
5. Close the editor. The title clip appears in the Project Bin.
6. Drag it to the timeline like any other clip.
7. Duration is set by trimming in the timeline (default is usually 5 seconds).

**Tips:**
- For YouTube tutorials, keep title cards under 3 seconds unless they are the intro card (where 2--5 seconds is acceptable).
- Use the same font family and color palette throughout your video for brand consistency.
- White text on a dark background outperforms dark text on a light background on most displays.

---

### Lower Thirds

A **lower third** is a text graphic that sits in the lower portion of the frame while the main video plays behind it. Used for speaker names, on-screen labels, step numbers, and supplementary info.

**How-to:**

1. Create a Title Clip with just the text element (no background, or a semi-transparent strip using the background element).
2. Place the title clip on V2, with the main clip on V1 running the same time range.
3. Add a `Composite & Transform` composition to the V2 clip.
4. In the Effect Stack, set the geometry to position the text in the lower portion of the frame.
5. Animate in/out using keyframes: start opacity at 0, ramp to 100% over 8--12 frames, hold, then ramp back down.

**Lower third positioning guidelines:**
- Keep text above the lower 10% of the frame (safe area for titles).
- Leave at least 20% of the frame height between the bottom of the text and the bottom edge.
- For 1920×1080 content, the standard lower third zone is roughly Y: 750--900px.

> **ForgeFrame:** Use `/ff-title-cards-generate` to create title cards and lower thirds from a JSON definition:
>
> ```
> /ff-title-cards-generate
> Input: titles=[
>   {type: "chapter", text: "Step 3: Configure the Settings", duration: 3.0},
>   {type: "lower_third", text: "Caleb Bennett", subtext: "ForgeFrame Demo", at: "00:02:15"}
> ], style="tutorial-clean"
> Output: title clips added to Project Bin, placed on timeline at specified positions
> ```
>
> You can also do this manually: create each Title Clip in the Project Bin editor, then place and composite them on V2 in the timeline.

---

## Keyframe Basics

**Keyframes** let any effect parameter change over time. They are the mechanism behind all animation in Kdenlive — from simple fades to complex motion graphics.

### How Keyframes Work

A keyframe stores the *value of a parameter at a specific point in time*. Kdenlive automatically calculates all the frames between keyframes using interpolation.

**Example:** You want the opacity of a lower-third graphic to fade in over 12 frames.

1. Enable keyframing on the opacity parameter (click the stopwatch/keyframe icon).
2. Move the playhead to frame 0. Set opacity to 0. A keyframe is created.
3. Move the playhead to frame 12. Set opacity to 100. Another keyframe is created.
4. Kdenlive fills in all frames between 0 and 12 with a smooth opacity ramp.

### Interpolation Types

| Type | Behavior | Use for |
|---|---|---|
| **Linear** | Steady, constant rate of change | Most parameters; simple fades |
| **Smooth (Bezier)** | Eases in and out of each keyframe | Position animation; natural-feeling motion |
| **Discrete** | Instant jump to the new value at the keyframe | Frame-accurate visibility toggles; strobe effects |

Right-click any keyframe to change its interpolation type.

### Keyframing Workflow

1. **Enable keyframing** on the parameter you want to animate (look for the keyframe/stopwatch icon next to the parameter).
2. **Position the playhead** where you want the first value.
3. **Set the value.** Kdenlive automatically creates a keyframe at the playhead position.
4. **Move the playhead** to the next change point.
5. **Set the new value.** Repeat.
6. **Preview** the result. If motion feels wrong, drag keyframes left/right to adjust timing, or change the interpolation type.

> [!tip] Less is more with keyframes
> Every keyframe is a decision point. A simple fade-in needs exactly two keyframes — start and end. Adding more keyframes between them usually makes the animation worse, not better. Start with the minimum number of keyframes and add more only if the result needs it.

### Common Keyframe Uses for Tutorial Creators

| Effect | How many keyframes | Where |
|---|---|---|
| Fade in a lower third | 2 | Start (opacity 0) + 12 frames later (opacity 100) |
| Hold, then fade out | 4 | In start, in end, out start, out end |
| Push-in zoom on a still | 2 | Start scale (100%) + end scale (110%) |
| PiP slide-in from bottom | 2 | Off-screen Y position + final Y position |
| Music volume duck | 4 | Before duck, duck start, duck end, after duck |

---

## When Effects Help vs. Hurt

### Effects that almost always help

- **Transform / push-in:** A slow zoom-in on a clip that runs too long re-engages the viewer. Use it during complex explanations.
- **Lower thirds:** Labeling what you are doing on screen orients new viewers and helps skimmers.
- **Noise reduction:** Low-light footage with heavy grain is distracting. Mild denoising is almost always worth it.
- **Stabilization:** Handheld footage on a static shot looks like a camera problem. `vidstab` fixes it quickly.
- **Fade to black:** Signals the end of a segment clearly. Prevents abrupt endings.

### Effects that usually hurt more than they help

| Effect | Why it usually hurts |
|---|---|
| Heavy LUTs on tutorial content | Saturated or stylized color distracts from the screen content viewers came to learn |
| Over-sharpening | Creates a harsh, artificial look; amplifies compression artifacts |
| Vignette | Darkens corners; usually unnecessary on indoor tutorial footage |
| Motion blur (on clips, not camera) | Looks cheap; rarely serves a narrative purpose |
| Glow / bloom | Usually dated; signals amateur post-processing |
| Speed ramp / time stretch on dialogue | Distorts speech; almost never worth it |

### The overprocessed tutorial problem

A common trap for new editors: spending hours on color grading and visual effects for a tutorial where viewers are watching your *screen*, not your face. For screen-recording-heavy tutorials:

1. **Fix problems only.** Correct white balance and exposure on your talking-head clips. Leave the screen recording alone.
2. **Skip creative grades.** A "cinematic teal and orange" look does not help viewers learn software.
3. **Focus time on pacing.** A well-paced tutorial with no color grade beats an overprocessed one that rambles. See [Chapter 11](11-pacing-storytelling-retention.md).

> [!tip] The five-minute rule
> If you have spent more than five minutes on an effect and it still does not look right, either the effect is wrong for the material or it needs to be simpler. Stop, reset, and ask whether the effect is necessary at all.

---

## Color Grading Toolkit

For detailed color correction workflows, scopes usage, and the full five-step correction process, see [Chapter 9](09-color-correction-and-grading.md). This section provides a quick reference for the tools that live in the Effects panel.

### Scope Reference

Never grade by eye alone. Monitors vary. Room lighting changes. Your eyes adapt and deceive you.

| Scope | What It Shows | Use It To |
|---|---|---|
| **Waveform** | Luminance distribution across the frame (left-to-right matches the image) | Set black point and white point; check for clipping |
| **RGB Parade** | Separate waveforms for Red, Green, and Blue channels | Identify and fix per-channel imbalances (color casts) |
| **Histogram** | Distribution of pixel brightness values | Verify overall exposure; spot crushed shadows or blown highlights |
| **Vectorscope** | Hue and saturation plotted on a color wheel | Check skin tone accuracy (should fall on the skin tone line); verify white balance |

Enable scopes via `View → Scopes` in Kdenlive.

### Color Tool Comparison

| Tool | CPU Cost | Visual Impact | Keyframing |
|---|---|---|---|
| `Levels` | Very low | Moderate — exposure and range only | Yes |
| `Curves` / `Bezier Curves` | Very low | High — precise per-channel control | Yes |
| `Lift/Gamma/Gain` | Very low | High — three-way color + brightness | Yes |
| `Color Balance` | Low | Moderate — simpler interface than L/G/G | Yes |
| `Apply LUT` | Low | Very high — wholesale color transform | No |
| `Hue/Saturation/Lightness` | Low | Moderate — targeted hue shifts | Yes |
| `White Balance` | Low | Moderate — temperature and tint | Yes |
| `3D FFT Denoiser` | High | Low-moderate — noise reduction | Yes |

### 10-Bit Pipeline

Starting with **Kdenlive 25.12**, 10-bit color processing is supported end-to-end. This means 1024 brightness levels per channel instead of 256, dramatically reducing banding in gradients and allowing more aggressive grading before artifacts appear.

To use it:
- Set your project profile to a 10-bit codec (e.g., ProRes 422, DNxHR HQX, or FFV1).
- Ensure your source footage is 10-bit (or at least high-quality 8-bit — upsampling 8-bit does not create new data).
- Preview may fall back to 8-bit for performance; final render will use the full pipeline.
