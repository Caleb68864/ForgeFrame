# Chapter 09: Color Correction & Grading

**Part IV — Post-Production**

---

> **The best tip in this chapter, stated upfront:** Good lighting eliminates 80% of color problems before you ever open Kdenlive. If you spend ten minutes improving your lighting setup, you will spend ten seconds on color correction. Keep that in mind as you read.

Color correction is one of those topics that sounds intimidating until you realize most of it is just fixing a handful of common problems. Your footage looks a little orange from a lamp. Your face is too dark. The whites look greenish from fluorescent lighting. These are solvable, and they are solvable quickly once you know what to look for.

This chapter teaches practical correction for tutorial creators — not cinematic grading for filmmakers. By the end, you will know how to spot a color problem, fix it in five steps, and move on with your edit.

---

## What Is Color Correction, Actually?

Before touching any sliders, it helps to understand what the four fundamental properties of video color actually mean. All color correction tools, regardless of software, are ultimately adjusting one or more of these:

### Exposure

Exposure is how bright or dark your footage is overall. An underexposed shot looks muddy and dark, with faces disappearing into shadow. An overexposed shot looks washed out and bright, with detail blown out in the highlights. Correct exposure means your subject is clearly visible and the image has detail from the darkest shadows to the brightest highlights.

For tutorial creators, the most common exposure problem is a face that is too dark — usually because you are backlit by a window or your camera underexposed for the background.

### White Balance

Every light source has a color temperature. Tungsten bulbs (old-style incandescent) cast orange-warm light. Fluorescent tubes cast greenish-cool light. Shade and overcast skies cast blue light. Cameras try to automatically compensate for this, and they often get it wrong.

White balance correction makes whites actually look white, and makes neutral grays look neutral gray. When white balance is off, your skin looks either sunburned (too warm) or like you have been in a cold storage facility for a week (too cool).

A practical test: look at a white wall or a white shirt in your footage. If it looks orange, you have too much warmth. If it looks blue, you have too much cool. If it looks green, the camera picked up fluorescent contamination.

### Contrast

Contrast is the relationship between the darkest and brightest parts of your image. High contrast means deep blacks and bright whites with a punchy look. Low contrast means everything is a bit flat and gray — which is often what unprocessed footage looks like, because cameras capture a "flat" image intentionally to preserve maximum detail for editing.

For tutorials, you want enough contrast that your image looks natural and three-dimensional, without being so high-contrast that you crush detail in shadows or blow out a bright shirt.

### Saturation

Saturation is color intensity. At zero saturation, everything is black and white. At maximum saturation, colors are cartoonishly intense. For tutorials, you want saturation that looks natural — real enough that it does not draw attention to itself. Human skin is the main reference point: if skin tones look believable, saturation is probably in the right range.

The most common mistake is pushing saturation too high trying to make footage look "vibrant." It makes skin look sunburned and distracts viewers from the content.

---

## Reading Kdenlive's Scopes

Kdenlive includes three video scopes — instruments that show you exactly what is in your footage, without relying on your monitor being perfectly calibrated. Learning to read them is the single most important skill for consistent color work. You cannot trust your eyes alone, especially if you are editing on a laptop screen in variable lighting.

Access scopes in Kdenlive via the **View menu → Scopes**, or dock them in a panel. You do not need all three open at once. The waveform is your primary tool.

### The Waveform Monitor (Use This One)

The waveform displays brightness from bottom (0, pure black) to top (100 IRE or 255, pure white). Everything in your image is plotted as a column of dots, left to right matching your image, bottom to top matching brightness.

**What to look for:**

- Signals near the very bottom (0-16) mean crushed blacks — shadow detail lost
- Signals at the very top (235-255) mean blown highlights — bright areas with no detail
- A healthy image has signals spread between roughly 16 and 235, with most of the action in the middle

**The most useful thing the waveform tells you:** where your face sits. For a talking-head tutorial shot, you want the bright areas of your face (forehead, cheek highlights) to sit around 70-80 IRE on the waveform. That range reads as naturally lit and well-exposed on most screens. Below 50, your face disappears on phones in bright sunlight. Above 90, you start looking washed out.

When you look at the waveform for the first time, you will see a cluster of values somewhere. If that cluster is low (face at 40-50 IRE), your image is underexposed. If it is high (face at 90-100), it is overexposed. Your correction job is to move it toward 70-80.

### The Histogram

The histogram shows the same brightness information as the waveform, but as a bar chart instead of a signal trace. Left side is shadows, right side is highlights, height is how many pixels are at that brightness level.

A healthy histogram has a hill somewhere in the middle — not slammed hard against either wall. Slammed against the left wall means underexposed. Slammed against the right wall means overexposed. A histogram with a gap in the middle (called a "comb") usually means over-processing with too-aggressive contrast.

The histogram is easier to glance at for a quick sanity check. The waveform tells you more specific information about where things are in the frame.

### The Vectorscope

The vectorscope shows color distribution. Dots in the center mean neutral (no color cast). Dots spread out toward the edges mean strong colors. Target markers around the perimeter show where pure red, green, blue, yellow, cyan, and magenta should land.

**The most useful thing the vectorscope tells you:** whether skin tones are on the right line. There is a diagonal line in the vectorscope (sometimes called the "fleshtone line" or "skin tone indicator") that runs from roughly 10 o'clock to 4 o'clock. Healthy human skin tones of all shades, from very light to very dark, should cluster along this line when white balance is correct.

If your skin tones are clustered to the left of the skin tone line (toward orange/red), your footage is too warm. If they are to the right (toward green-yellow), your footage is too cool or has a green cast.

You do not need to read the vectorscope in detail. Just check: is the skin tone cluster near the skin tone line? If yes, white balance is reasonable. If no, you need to adjust.

> **ForgeFrame:** Use `/ff-color-analyze` to run `color_analyze` on your clip. It reads the waveform, histogram, and vectorscope values automatically and outputs a plain-English report: "face at 58 IRE (underexposed), skin tone 12° from fleshtone line (slightly warm)." This gives you a starting point before you touch any sliders.
>
> You can also do this manually by opening Kdenlive's scopes panel and reading the values yourself — the callout just speeds up the diagnosis.

---

## Correction vs Grading: Know the Difference

These two terms get used interchangeably, but they mean different things and they happen in a specific order.

**Correction** means fixing problems. Making the exposure accurate. Removing color casts. Normalizing contrast. When you are done with correction, your footage looks like how the scene actually looked in real life — natural, accurate, and neutral. This is always Step 1.

**Grading** means adding a creative look on top of corrected footage. A cool, desaturated look for a corporate video. A warm, golden look for a lifestyle channel. A high-contrast, slightly teal-and-orange look for cinematic content. Grading is always Step 2, and it only makes sense to do after correction — applying a look to badly-corrected footage just makes the problems more visible.

**For tutorial creators, the recommendation is: correct everything, grade almost nothing.**

Your viewers are watching to learn something. Color that draws attention to itself — either because it looks wrong, or because it looks aggressively styled — is color doing its job badly. The goal is footage that looks completely natural and professional, so the viewer can focus on what you are teaching.

There is one exception: a slightly warm color treatment (nudging the temperature a few degrees toward yellow-orange) consistently polls as friendlier and more engaging for tutorial content. It is subtle enough to be invisible but measurably improves viewer perception. You will read more about this in the "What Good Looks Like" section.

---

## The 5-Step Correction Workflow

Work through these steps in order. The order matters: if you adjust contrast before white balance, you will have to readjust contrast again after you fix the color cast. Do it once, in sequence.

For each step, keep the waveform and vectorscope open so you can see what your changes are actually doing.

### Step 1: Exposure

First, get the overall brightness right. Apply the **Lift/Gamma/Gain** effect to your clip (search for it in Kdenlive's Effects panel). This is your primary correction tool — it handles the three zones of brightness independently.

Look at your waveform. Is the signal cluster sitting at 70-80 IRE where your face is? If your face reads around 50-60 IRE (dark), push the Gamma slider slightly to the right. Gamma controls midtones — the middle zone where most facial detail lives — without blowing out highlights or crushing shadows.

Do not overcorrect. A face at 75 IRE is well-exposed. You do not need 90 IRE just because you can get there.

### Step 2: White Balance

Now fix the color cast. While watching the vectorscope, look at the skin tone cluster. Is it near the skin tone line?

In Kdenlive, you can adjust white balance using the **White Balance** effect, or by using the color temperature controls in Lift/Gamma/Gain if your version supports it. Pull the temperature control toward cool (blue) if your footage is too warm (orange), or toward warm (orange/yellow) if your footage is too cool (blue).

A practical shortcut: if you shot something white — a white wall, a piece of paper, a white shirt — in the same conditions as your main footage, you can use Kdenlive's white balance picker and click on that white area. Kdenlive will calculate the correction automatically.

After adjustment, the skin tone cluster in the vectorscope should sit closer to the skin tone line. A perfectly corrected clip will have near-neutral whites when you look at them on screen.

### Step 3: Contrast

With exposure and white balance correct, now shape the contrast. Contrast is the relationship between your darkest darks and your brightest brights.

Back in Lift/Gamma/Gain:
- **Lift** controls shadows (the dark end). Pushing it slightly lower deepens blacks. Raising it lifts shadows, which can reveal blocked-up shadow detail.
- **Gain** controls highlights (the bright end). Pushing it up boosts highlights. Pulling it down brings overexposed areas back into range.

Watch the waveform as you do this. You want the bottom of the signal to sit around 16-20 (not slammed to 0, which means crushed blacks) and the top of the signal to sit around 220-235 (not slammed to 255, which means blown highlights).

A very light contrast push — Lift down just a touch, Gain up just a touch — makes flat footage look natural and three-dimensional. Be conservative. Over-contrasted tutorial footage looks harsh and reads poorly on phone screens in sunlight.

### Step 4: Saturation

Now that the image is correctly exposed, white-balanced, and contrasted, check the saturation. Most well-lit footage needs only a small saturation adjustment, if any.

Add the **Saturation** effect or use the saturation control in your color effect. The safe range for tutorial corrections is roughly -5 (slightly desaturated) to +15 (slightly boosted). Stay in this range.

Look at skin tones specifically. Oversaturated skin looks sunburned or artificially pink. Pull back if skin looks unnatural.

### Step 5: Skin Check

The final check is a deliberate look at skin tones using the vectorscope. The skin tone cluster should be on or near the skin tone line, at a reasonable distance from center (neither washed out nor oversaturated).

Also look at the image on screen: does skin look like a real person? Does it read naturally? Is there any odd color bias — greenish, pinkish, yellowish? Fix it now before moving on.

If you are correcting multiple clips from the same shoot in the same lighting conditions, you can copy the effect settings from your first corrected clip and paste them onto similar clips. In Kdenlive, right-click a clip's effect stack → Copy → paste onto other clips. This is dramatically faster than correcting each clip individually.

---

## Lift/Gamma/Gain: Your Primary Tool

Lift/Gamma/Gain is the industry-standard color correction structure, and it handles approximately 90% of everything a tutorial creator needs to do.

- **Lift** = shadows (the dark third of the tonal range)
- **Gamma** = midtones (the middle third — where most of your subject lives)
- **Gain** = highlights (the bright third)

Each of these can be adjusted as a whole (all channels together, affecting overall brightness) or per-channel (adjusting red, green, and blue independently, which is how you remove color casts).

For most corrections, you will only adjust the overall (master) channel. Per-channel adjustment is for precise color cast removal — for example, pulling down the blue channel in Lift to remove a shadow-area color cast from fluorescent lights.

The reason this tool handles most corrections is that lighting problems are almost always tonal-zone-specific. An orange tungsten cast is mostly in the highlights and midtones. A fluorescent green cast is often concentrated in shadows. Lift/Gamma/Gain lets you address each zone without affecting the others.

---

## LUTs: What They Are and When to Use Them

A LUT (Look-Up Table) is a preset color transformation packaged as a file. You apply it to your footage and it shifts the colors and contrast according to the preset — similar to a photo filter, but mathematically precise.

LUTs come in two types:

**Technical/conversion LUTs** convert footage from one color space to another. For example, if you shoot in a flat "log" profile on a Sony camera, you apply a specific conversion LUT to restore normal colors. Most tutorial creators shooting in standard camera modes do not need these.

**Creative/look LUTs** add a stylistic grade — a warm vintage look, a cool teal-orange cinematic look, a clean corporate look. These are the LUTs sold on marketplaces and bundled with "color grading packs."

**The rule for LUTs:** apply them only after manual correction, never before.

A LUT is designed to work on footage that is already properly exposed and white-balanced. If you apply a LUT to underexposed, color-cast footage, it does not fix the problems — it bakes them in permanently, often making them worse.

For most tutorial creators, LUTs are optional. A properly corrected clip using the 5-step workflow above looks clean and professional without any LUT applied. If you want to experiment with creative looks, apply the LUT as a final step, and check that skin tones still look natural afterward.

> **ForgeFrame:** Use `color_apply_lut` to apply a LUT file to your clip or sequence without manually hunting for the effect in Kdenlive. Specify the LUT path and it will be applied to the correct position in the effect stack.
>
> You can also do this manually: in Kdenlive, apply the **LUT (3D)** effect to a clip and browse to your .cube or .3dl file. Make sure it is below (after) your correction effects in the stack.

---

## BT.709: Don't Touch This

Your footage almost certainly exists in a color space called **BT.709**. This is the standard for HD video — essentially the rules for how colors are encoded and decoded for standard monitors and televisions. Every consumer camera, every streaming platform, every home screen uses BT.709 as the default.

You will see BT.709 mentioned in Kdenlive's project settings and occasionally in export dialogs. The practical instruction is: **do not change it unless you have a specific reason and know exactly what you are doing.** Leave it as BT.709 (or Rec. 709 — same thing).

What happens if you change it accidentally? Your colors will look wrong on most screens because the playback device will interpret your color data differently than it was encoded. This is a surprisingly common source of "why does my video look different on YouTube" problems.

When `color_analyze` reports color space information, it is confirming that your footage is correctly in BT.709. If it reports something different — for example, BT.2020 from a phone that was set to shoot in HDR mode — that is a signal that you may need to do a color space conversion before editing. In most cases, the fix is to change your phone's recording settings to standard HD (see Chapter 05 for camera settings guidance).

---

## What Good Looks Like for YouTube Tutorials

"Good color" for tutorial content is defined by what it is NOT: it is not noticeable. Viewers should not think "wow, this looks great" any more than they should think "wow, this looks off." They should not think about it at all.

Here is what the target looks like, concretely:

**Skin tones look real.** A person with medium skin tone looks medium. No orange glow, no sickly green, no blue shadow. Skin under a desk lamp should not look like a sunset.

**Whites look white.** A white wall, a white shirt, a white coffee mug — these should look white, not cream, not gray, not faintly blue. White balance is correct when your whites are neutral.

**Shadow detail is visible.** You can see the texture of a dark shirt, the edge of a dark object on a dark surface. Shadows are not a black void. This matters especially for mobile viewing, where screens have higher contrast ratios and shadow crushing is immediately visible.

**Slightly warm is better than perfectly neutral.** For human presenters in tutorials, footage that is very slightly warm (a degree or two toward yellow-orange) consistently reads as more welcoming and personable than perfectly neutral footage. The difference is subtle — you are not adding an Instagram filter, you are shifting the color temperature just enough to remove the cool, clinical feeling of a fluorescent-lit space.

**Color supports the content, not the other way around.** If you are showing code on screen, your color correction should make that code easy to read. If you are demonstrating a physical object, the object's real color should be accurately represented.

> **[Tip]** Good lighting is worth more than good color correction. A well-lit shot with zero correction looks better than a badly lit shot with expert color work. Before you spend time learning correction techniques, spend time learning to put a light in the right place. Chapter 05 covers lighting for tutorial creators specifically.

---

## Common Color Mistakes

> **[Sidebar: Mistakes to Avoid]**
>
> **Over-saturating skin.** Pushing saturation because the image "looks flat" almost always goes too far. Skin tones turn orange-red and look sunburned or synthetic. Small saturation adjustments only — you rarely need to go above +15.
>
> **Crushing blacks for a "cinematic" look.** Pulling Lift down hard to get deep, dramatic blacks looks impressive on a calibrated monitor and looks terrible on a phone screen in sunlight. Tutorial viewers watch on every device. Keep shadow detail visible.
>
> **Grading before correcting.** Applying a LUT or stylistic grade on top of uncorrected footage. The LUT makes the cast worse, not better. Always correct first.
>
> **Applying the same correction to every clip without checking.** Different shots from the same camera have different exposures and color temperatures. A shot outdoors in the afternoon needs different correction than a shot indoors with lamps. Check each clip or each lighting condition separately.
>
> **Heavy LUTs on poorly-exposed footage.** A dramatic cinematic LUT on footage that was underexposed and orange does not give you a cinematic look. It gives you a muddy, orange, dark image with a blue tint on top. Fix the underlying problems before applying any creative treatment.
>
> **Correcting on an uncalibrated screen.** If you are editing on a laptop screen in a bright room, what looks "warm" to you might actually be neutral on a properly calibrated monitor. Use the scopes, not your eyes, as your primary reference.

---

## Putting It All Together: A Practical Example

Here is what the correction process looks like on a typical tutorial clip — a medium shot of a person at a desk, shot with a webcam and a desk lamp as the primary light source.

**Before correction:** The waveform shows the face sitting at around 55 IRE. The vectorscope shows the skin tone cluster shifted notably to the orange side of the skin tone line. The whites of the background shelf look cream-colored.

**Step 1 (Exposure):** Push Gamma slightly right. Face moves from 55 to 72 IRE. The image immediately looks more alive.

**Step 2 (White balance):** Cool the temperature slightly. The skin tone cluster moves closer to the skin tone line. The shelf background shifts from cream to closer to white.

**Step 3 (Contrast):** Small Lift reduction — pull shadows down just slightly. Small Gain increase — let highlights open up a bit. Image gains dimensionality.

**Step 4 (Saturation):** Check vectorscope. Skin saturation looks reasonable. No adjustment needed.

**Step 5 (Skin check):** Skin tone cluster is on the skin tone line at a healthy distance from center. Face looks like a real person. Done.

Total time: 3-4 minutes for the first clip. Subsequent clips from the same shoot: copy-paste the effect stack and check on the scope — usually 30 seconds each.

---

## ForgeFrame Tools for Color

### color_analyze

The `color_analyze` tool reads a clip or region of your timeline and returns a scope-based diagnosis:
- Face IRE value (compared to the 70-80 target)
- Color space confirmation (BT.709)
- White balance status (estimated cast, if any)
- Skin tone vector position (distance from fleshtone line)
- Any clipping warnings (blown highlights or crushed blacks)

Use this before starting correction to get a clear picture of what needs fixing. Use it after correction to confirm the result.

**Manual equivalent:** Open Kdenlive's scopes, play through the clip, and read the waveform and vectorscope values manually against the targets described in this chapter.

### color_apply_lut

The `color_apply_lut` tool applies a LUT file to a clip or sequence, inserting it at the correct position in the effect stack (after correction effects, not before). It accepts .cube and .3dl formats.

**Manual equivalent:** Apply the Kdenlive **LUT (3D)** effect and browse to your LUT file. Drag it below your correction effects in the effect stack.

---

## What to Read Next

Color is closely related to two adjacent topics:

- **Chapter 05 (Filming Your Tutorial)** covers how to avoid color problems at the source — lighting setups, white balance settings in-camera, and camera settings that prevent footage from arriving in the edit with severe color problems.
- **Chapter 14 (Quality Control)** covers `qc_check`, which includes automated color space verification and basic exposure checking as part of the pre-publish QC workflow.
- **Appendix C (Glossary)** defines BT.709, LUT, IRE, LUFS, and other technical terms used throughout the handbook.

---

*Chapter 09 is part of Part IV — Post-Production. Previous: Chapter 08 (Transitions & Compositing). Next: Chapter 10 (Audio Production).*
