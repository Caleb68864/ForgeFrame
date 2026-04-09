---
title: "Kdenlive Fundamentals"
tags:
  - kdenlive
  - editing
  - timeline
  - proxies
  - sequences
---

# Kdenlive Fundamentals

This chapter covers the core editing workflows in Kdenlive: setting up your project, organizing your bin, working on the timeline, and using proxies to keep things fast. It is the reference you will return to most often during the edit.

For transitions and compositing, see Ch.08. For color correction, see Ch.09. For audio production, see Ch.10. For effects and titles, see Ch.12. For export, see Ch.13.

---

## Project Setup and Asset Management

### The Project Settings Contract

When you create a new Kdenlive project, the **Project Settings** dialog is a contract you sign with yourself. Every decision you make here -- resolution, frame rate, aspect ratio, color space -- ripples through the entire edit. Changing these mid-project is possible but painful, so get them right at the start.

The guiding principle is simple: **match what you recorded**.

- **Resolution**: If you shot 1920x1080, your project should be 1920x1080. If you shot 3840x2160, use that. Do not upscale footage in the project settings hoping for "better quality" -- it does not work that way.
- **Frame rate**: Match your camera's recording frame rate exactly. Mixing 24 fps footage in a 30 fps timeline (or vice versa) causes stuttering and dropped frames. If you recorded at 29.97 fps, use 29.97 fps -- not 30.
- **Aspect ratio**: Follows from your resolution. 1920x1080 gives you 16:9; 1080x1920 gives you 9:16 for vertical/short-form content.
- **Color space**: For standard dynamic range (SDR) content -- which covers the vast majority of YouTube, tutorial, and workshop videos -- use **BT.709**. This is the default for HD content and is what web browsers and video players expect. Only deviate from BT.709 if you are working with HDR footage and have a calibrated HDR display.

> **ForgeFrame:** Use `project_setup_profile` to auto-generate a Kdenlive project profile from your footage metadata. The tool reads resolution, frame rate, and codec information from your clips and outputs a matching profile you can load directly in *Project Settings*.
>
> You can also do this manually by opening *Project* > *Project Settings* and matching each field to your footage.

> **ForgeFrame:** Run `project_match_source` after setting up your project to verify your settings match your source footage. The tool compares project resolution, frame rate, and color space against your ingested clips and flags any mismatches before they become problems.
>
> You can also check this manually: right-click a clip in your bin and choose *Clip Properties* to view its native specs, then compare to your *Project Settings*.

### The Project Bin as Single Source of Truth

The **Project Bin** is where every asset in your project lives -- video clips, audio files, images, title clips, color clips, and sequences. Think of it as the single source of truth for your edit.

**Organize early and aggressively:**

- **Folders**: Create folders in the bin for logical groupings -- `B-Roll`, `Interviews`, `Music`, `SFX`, `Graphics`. Right-click in the bin and choose *Create Folder*.
- **Tags**: Kdenlive supports color tags on clips. Use them to mark selects (green), rejects (red), or clips that need review (yellow).
- **Multiple bins**: For complex projects, you can open multiple bin views. This is useful when you need to see your B-roll folder and your music folder simultaneously while assembling a sequence.

Never reference assets from random locations on disk. Import everything into the bin first. If you move source files after importing, Kdenlive will lose track of them and you will spend time relinking clips.

---

## Timeline Editing and Clip Operations

### Rough Cut to Fine Cut

Editing is a process of progressive refinement:

1. **Selects**: Review all footage. Mark your best takes and moments in the project bin.
2. **Rough cut (assembly)**: Lay your selects onto the timeline in narrative order. Do not worry about timing, transitions, or polish. The goal is to get the story structure down.
3. **Fine cut**: Tighten every edit. Trim heads and tails, adjust pacing, remove dead air, and ensure each cut serves the story. This is where you spend the most time.

Resist the urge to add transitions, effects, or color work during the rough cut. Those are polish steps that become wasted effort if you restructure the edit later.

### 3-Point Editing

Three-point editing is the fastest way to place clips precisely on the timeline. The concept is simple: you define three of the four possible points (source IN, source OUT, timeline IN, timeline OUT), and Kdenlive calculates the fourth.

**The workflow:**

1. **Load a clip** in the Clip Monitor (double-click it in the bin).
2. **Set IN and OUT points** on the source clip using `I` and `O` keys. This defines the portion of the clip you want.
3. **Position the timeline playhead** where you want the clip to land (this is your timeline IN point).
4. **Choose the target track** by activating the track's target indicator (the colored boxes on the track header).
5. **Insert** (`V` key) or **Overwrite** (`B` key) the clip onto the timeline.

- **Insert** pushes existing clips to the right to make room.
- **Overwrite** replaces whatever is on the timeline at that position.

### Trimming and Clip Operations

Once clips are on the timeline, these are the operations you use constantly:

- **Trim** (drag a clip edge): Shortens or extends a clip by moving its IN or OUT point. Only works within the clip's available handle frames.
- **Ripple trim** (`Shift`+drag edge): Same as trim, but automatically closes or opens gaps to keep clips packed together.
- **Roll edit** (`Ctrl`+drag a cut point): Moves the cut between two adjacent clips without changing the overall duration. Makes clip A shorter and clip B longer (or vice versa).
- **Slip** (`Shift`+drag clip body): Moves the clip's content window without changing its position on the timeline. Changes what frames you see, not where the clip sits.
- **Slide** (`Ctrl+Shift`+drag clip body): Moves the clip along the timeline, automatically adjusting adjacent clips to close or fill gaps.

**Keyboard shortcuts for editing:**

| Action | Key |
|--------|-----|
| Set source IN | `I` |
| Set source OUT | `O` |
| Insert to timeline | `V` |
| Overwrite to timeline | `B` |
| Razor cut at playhead | `X` |
| Delete selected, leave gap | `Delete` |
| Lift (delete, close gap) | `Backspace` |
| Toggle track lock | `L` (click track header) |

### Keyframe Handling

Keyframes let you change any property over time -- position, opacity, volume, effect parameters. You will encounter them in two places:

- **Timeline keyframes**: Visible directly on clips in the timeline (commonly used for audio volume rubber-banding). Click on the clip's keyframe line to add a point, drag it to adjust.
- **Effect panel keyframes**: Inside the effect stack, each keyframeable parameter has a small diamond icon. Click it to add a keyframe at the current playhead position. Use the keyframe navigation arrows to jump between keyframes.

**Tips for working with keyframes:**

- Add keyframes *only* where a value changes. Two keyframes define a transition between states.
- Right-click a keyframe to choose interpolation: **Linear** (constant rate of change), **Discrete** (instant jump), or **Smooth** (eased curves).
- To remove a keyframe, right-click it and choose *Delete Keyframe*.

### Sequences (Nested Timelines)

Sequences are one of Kdenlive's most powerful organizational features. A sequence is a timeline that can be nested inside another timeline, just like a clip.

**Why sequences matter:**

- **Modular editing**: Build your intro, individual chapters, and outro as separate sequences. Then assemble them into a master sequence. Changes to a chapter sequence automatically propagate to the master.
- **Reusable elements**: A branded intro sequence can be dropped into every project without rebuilding it.
- **Performance**: Working in a short sequence is faster than scrubbing through a massive single timeline.

**To create a sequence:**

1. Go to *Project* > *Add Sequence* (or use the bin's right-click menu).
2. Edit the sequence in its own timeline tab.
3. Drag the sequence from the bin onto another timeline to nest it.

> [!tip] Sequences for tutorial production
> If you are producing tutorials or educational content, sequences map beautifully to your script structure. Each script section or chapter becomes its own sequence. You can edit, review, and revise each section independently, then assemble the final video by stacking sequences in a master timeline.

---

## Proxies and Performance

Proxy editing is a **first-class workflow skill**, not a hidden checkbox to find when things get slow. The concept: Kdenlive creates lower-resolution, simpler-codec copies of your footage for editing, then swaps in the originals at render time. You get smooth playback during editing without sacrificing final output quality.

**When to use proxies:**

- Your footage is 4K or higher and playback stutters
- You are editing on an older machine or one without dedicated GPU decoding
- Your source codec is computationally expensive (H.265/HEVC, high-bitrate H.264, ProRes on Linux)

**Enable proxies early:**

- Go to *Project* > *Project Settings* > *Proxy* tab.
- Choose a proxy profile (the default is usually fine).
- Enable proxy generation for clips above a certain resolution threshold.
- Kdenlive will generate proxies in the background. A progress bar appears in the bin.

**Camera proxies**: Some cameras (especially cinema cameras) generate their own low-res proxy files alongside the full-resolution originals. Kdenlive can use these directly, saving you the proxy generation step.

> [!warning] Variable frame rate (VFR) footage
> Footage from smartphones and screen recorders often uses **variable frame rate** -- the time between frames is not constant. VFR footage causes sync drift, audio desync, and timeline glitches in *every* NLE, not just Kdenlive. **Always transcode VFR footage to constant frame rate (CFR) before importing.** Use FFmpeg: `ffmpeg -i input.mp4 -vsync cfr -r 30 output.mp4` (replace `30` with your target frame rate). This single step prevents hours of debugging sync issues.

---

## Where to Go Next

- **Ch.01** -- The Video Production Pipeline -- how editing fits the larger workflow
- **Ch.05** -- Filming Your Tutorial -- camera settings, VFR prevention, and gear
- **Ch.07** -- Your First Edit -- apply these fundamentals to a guided beginner project
- **Ch.08** -- Transitions and Compositing -- cuts, dissolves, wipes, and picture-in-picture
- **Ch.09** -- Color Correction and Grading -- scopes, white balance, and Lift/Gamma/Gain
- **Ch.10** -- Audio Production -- loudness normalization and the processing chain
- **Ch.12** -- Effects, Titles, and Graphics -- effect stack, title cards, and lower thirds
- **Ch.13** -- Formats, Codecs, and Export -- render profiles and delivery specs
