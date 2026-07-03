---
title: "From Day to Night - kdenlivetutorials Blog"
url: https://www.kdenlivetutorials.com/2014/11/from-day-to-night/
channel: Kdenlive Tutorials (Luca Tringali)
type: reference
tags: [kdenlive, tutorial, reference, color-grading, compositing, day-to-night]
---
# From Day to Night - kdenlivetutorials Blog

Distilled from the kdenlivetutorials.com "From day to night" VFX tutorial (Luca Tringali, Nov 2014). Technique: fake a night shot from day footage using digital color correction, then add a starry sky and distance-based brightness. Example result: https://www.youtube.com/watch?v=Qru3PH0IWBM

## The night look (what we are simulating)
- Highlights go **blue** (eyes are most sensitive to blue).
- Other colors, **red especially, are strongly desaturated** and barely recognizable.
- Both **shadows and midtones must be quite dark**; only the highlights keep a fair brightness.
- Objects **closest to the camera are slightly brighter** than distant ones (light falls off with distance).
- Best source footage: shot on a **cloudy day / around noon** (fewer harsh shadows), buildings rather than trees/countryside (moving leaves glow and are hard to fix).

## Stage 1 - Prepare the clip
1. Import the day clip into a new Kdenlive project on a video track (e.g. Movie3 / a working track).
2. Add two color effects to the clip up front (values set later): **Saturation** and **Hue Shift**.

## Stage 2 - Shades of blue (the grade)
1. **Levels** effect on channel **Luma**: raise the incoming **black** level to about **120** to darken the image without overdoing it.
2. A second **Levels** effect on the **Red** channel: increase red-channel contrast - incoming black around **125**, incoming white around **915**.
3. Return to the **Saturation** and **Hue Shift** effects: set **Saturation below 100** (e.g. **80**); set **Hue Shift** so the image takes on a **blue** tone.
4. Render this first stage to a high-quality file (e.g. ~44000 kb/s MP4). Colors are now correct but the image is still too bright - this rendered file is the base for the next stage.

## Stage 3 - Turn off the light, turn on the stars (sky overlay compositing)
1. Prepare a **starry sky** image (photograph a night sky, retouch in GIMP if needed).
2. New project with two clips: the **sky image on the track ABOVE** (e.g. Video2) and the Stage-2 rendered movie **below** (e.g. Movie3).
3. Between the two clips add a **Darken** transition/blend, extended along their full length.
4. On the lower track (Video1) place the rendered movie again and apply a **Lighten** transition for the movie's full duration.
5. Add an **Invert** effect to the Video1 clip so the starry sky becomes visible.
6. Apply a **Box Blur** ("blurred cube") to that clip: blur factor **5**, vertical multiplier **~3**, horizontal multiplier **1** - stretches/softens the stars.

## Stage 4 - Brightness by distance (rotoscope)
1. Render the current project to a new high-quality file.
2. New project: load that file onto **two overlapping tracks** (e.g. Movie3 and Video2) with a **Composite** transition along their whole length.
3. On the upper clip (Video2) apply the **Curves** effect on channel **Luma**: draw the curve to keep shadows and midtones very low while highlights stay high enough (darker version).
4. Add a **Rotoscoping** effect to the Video2 clip and mask it so only the **foreground/close objects** show through from the brighter lower clip - use continuous keyframes to track object movement frame by frame.
5. Render the result. Optionally fine-tune final brightness with **Curves** effects on the **Luma** and **Blue** channels.

## Notes on effect names
The blog is machine-translated from Italian; the actual Kdenlive effects referenced are: **Saturation**, **Hue Shift**, **Levels** (translated "Layers"), **Curves** (translated "Bends"), **Box Blur** (translated "Blurred cube"), **Invert**, **Rotoscoping**, and the **Darken / Lighten / Composite** compositions (transitions/blend modes).
