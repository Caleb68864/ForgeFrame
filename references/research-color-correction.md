# Color Correction & Grading Research -- For Handbook Ch.09

## Core Concepts (30-Second Version)

**White balance** makes whites actually white -- if your footage looks orange (tungsten light) or blue (shade), this fixes it. **Exposure** is overall brightness. **Contrast** is the difference between darks and lights. **Saturation** is color intensity.

## Reading Kdenlive's Scopes

- **Waveform (most useful)**: Brightness from bottom (0=black) to top (255=white). Keep between 16-235 for broadcast-safe. Face at 70-80 IRE for talking head.
- **Histogram**: Same brightness as a bar chart. Healthy = spread across range without slamming walls.
- **Vectorscope**: Color distribution. Centered dot = neutral. Skin tones along 10 o'clock line.

## Correction vs Grading

**Correction** = fixing problems (always first). **Grading** = creative look (usually skip for tutorials).

## Practical Workflow Order

1. **Exposure/Lift** -- brightness first (Lift/Gamma/Gain effect)
2. **White balance** -- remove color casts
3. **Contrast** -- Gain (highlights) and Lift (shadows)
4. **Saturation** -- small adjustments only (-5 to +15)
5. **Skin check** -- vectorscope skin tone line

Lift/Gamma/Gain handles 90% of correction.

## Common Mistakes

1. Over-saturating skin (sunburned look)
2. Crushing blacks for "cinematic" look (loses detail on phones)
3. Grading before correcting
4. Same correction on every clip without checking scopes
5. Heavy LUTs on poorly-exposed footage

## LUTs vs Manual

Apply LUTs only AFTER manual correction. For tutorials, usually unnecessary.

## BT.709

Default HD color space. Don't change it. Consumer cameras already BT.709.

## What "Good" Looks Like for YouTube Tutorials

Invisible color work. Accurate skin tones, clean whites, visible shadow detail. Slightly warm = friendly. Best investment is lighting, not grading.
