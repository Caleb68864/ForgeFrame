---
title: "Example: One-Minute Tutorial"
tags:
  - example
  - project
  - beginner
---

# Example: One-Minute Tutorial

This is a self-contained beginner project that walks you through editing a short "one-minute tutorial" video from scratch. It uses procedurally generated assets so you can start immediately without downloading stock footage or recording anything.

## What You'll Build

A ~60-second screencast-style tutorial with:

- A title card over a solid colour background
- A test-pattern "screen recording" with timecode overlay
- A tone-based audio track (standing in for narration)
- A simple lower-third text overlay
- An export to H.264 for YouTube upload

The result won't win any awards, but it exercises every stage of the editing pipeline: import, arrange, trim, add effects, mix audio, and render.

## Generate Sample Assets

All assets are created locally by a shell script. Nothing is downloaded, and the generated files are CC-free (procedurally generated via FFmpeg).

```bash
cd docs/video-editing-guide/examples/one-minute-tutorial/scripts
chmod +x generate-assets.sh
./generate-assets.sh
```

This creates files in the `assets-generated/` folder. See [[#Folder Structure]] below.

> [!info] Assets are generated locally, not distributed
> The `assets-generated/` directory is git-ignored. Each person working through this example generates their own copies. This keeps the repository lightweight and avoids any licensing concerns -- every asset is synthesized from FFmpeg test sources.

## Folder Structure

After running the generation script, the project directory looks like this:

```
one-minute-tutorial/
├── README.md              ← you are here
├── scripts/
│   └── generate-assets.sh ← asset generator
└── assets-generated/      ← created by the script (git-ignored)
    ├── synthetic_testsrc_1080p30.mp4
    ├── synthetic_tone_48k.wav
    ├── silent_48k.wav
    ├── title_bg_0x1a1a2e.png
    ├── title_bg_0x16213e.png
    ├── title_bg_0x0f3460.png
    ├── title_bg_0x533483.png
    └── overlay_001.png ... overlay_060.png
```

## Step-by-Step Instructions

Work through these steps in order. Each links back to the relevant handbook chapter for deeper explanation.

### 1. Set Up Your Project

1. Open Kdenlive and create a new project: `File > New`.
2. Set the project profile to **HD 1080p 29.97 fps** (see [[../../06-kdenlive-fundamentals|Kdenlive Fundamentals]] for why this matters).
3. Save the project file inside this example folder.

### 2. Import Assets

1. Drag the files from `assets-generated/` into the Kdenlive **Project Bin**.
2. Verify the clip properties match expectations: right-click a clip and choose `Clip Properties` (see [[../../06-kdenlive-fundamentals|Kdenlive Fundamentals]] for details on clip management).

### 3. Build the Timeline

1. Place `title_bg_0x1a1a2e.png` on **V2** (video track 2) for the first 3 seconds -- this is your title card background.
2. Add a **Title Clip** (`Project > Add Title Clip`) with your tutorial title. Place it on **V3** above the background.
3. Place `synthetic_testsrc_1080p30.mp4` on **V1** starting at the 3-second mark.
4. Trim the test video to ~7 seconds so the total timeline is roughly 10 seconds.

See [[../../06-kdenlive-fundamentals|Kdenlive Fundamentals]] for trimming and track management.

### 4. Add Audio

1. Place `synthetic_tone_48k.wav` on **A1** (audio track 1), aligned with the test video.
2. Lower its volume to around -18 dB -- this simulates background music at an appropriate level.
3. Place `silent_48k.wav` on **A2** as a placeholder for where narration would go.
4. Apply a fade-out to the tone track over the last 2 seconds.

See [[../../10-audio-production|Audio Production]] for gain staging and loudness targeting.

### 5. Add an Overlay

1. Import a few of the `overlay_*.png` frames and place them on **V3** during the screencast section.
2. Use the **Composite & Transform** transition to blend the overlay with the video below.
3. Adjust opacity to taste.

See [[../../08-transitions-and-compositing|Transitions and Compositing]] for compositing and effect stacking.

### 6. Add Transitions

1. Add a **Dissolve** transition between the title card and the screencast clip.
2. Adjust the transition duration to ~0.5 seconds.

See [[../../12-effects-titles-graphics|Effects, Titles & Graphics]] for transition best practices.

### 7. Export

1. Open the render dialog: `Project > Render`.
2. Choose **MP4 / H.264** with a quality-based (CRF) preset.
3. Render the project and review the output.

See [[../../13-formats-codecs-export|Formats, Codecs & Export]] for codec selection and platform-specific settings.

### 8. Review

Play back the rendered file. Check:

- [ ] Title card displays cleanly for ~3 seconds
- [ ] Dissolve transition is smooth
- [ ] Audio fades out before the end
- [ ] No black frames or gaps in the timeline
- [ ] File plays correctly in VLC or mpv

Congratulations -- you've completed a full edit-to-export cycle in Kdenlive.
