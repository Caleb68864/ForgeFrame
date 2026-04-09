---
title: "Scripts, Shot Plans & Capture Prep"
part: "Part II — Preproduction"
tags:
  - preproduction
  - script
  - shot-list
  - capture
  - b-roll
---

# Chapter 04: Scripts, Shot Plans & Capture Prep

**Part II — Preproduction**

You have an outline. Now turn it into production documents: a script you can speak from, a shot list you can take to the set, and a checklist that means nothing gets forgotten before you press record.

This chapter covers the three documents that bridge planning and filming.

---

## Script Structure

For tutorial and explainer content, you don't need a Hollywood screenplay. But you do need enough written structure that you can speak clearly without wandering, and your future editor knows what you intended each segment to be.

### Choosing Your Format

#### Full Script

Write every word you plan to say. Best when precision matters — technical explainers, narrated walkthroughs, or any content where saying the wrong thing causes real problems.

```
## HOOK (0:00-0:30)

[ON CAMERA — workshop bench with finished piece]

This is what a properly fitted hand-cut dovetail looks like.
No gaps, no rocking, no glue needed to close it up.
By the end of this video, you'll be cutting these yourself —
starting from a board, not a kit.

---

## MATERIALS & TOOLS (0:30-1:30)

[ON CAMERA — overhead bench with tools laid out]

You'll need: a marking gauge, a dovetail saw, a coping saw or
fret saw, and two chisels — a 1/4" and a 3/4". That's the
whole kit. Nothing exotic.
```

#### Bullet Outline

Write the key points per section and ad-lib during recording. Best for conversational talking-head content where sounding natural matters more than saying every word exactly.

```
- Hook: Show finished dovetail, state who this is for
- Tools: Marking gauge, dovetail saw, coping saw, 2 chisels
- Step 1: Mark the tails — gauge setting, knife wall, angle
  - Gotcha: don't use a pencil line to cut to
- Step 2: Saw the tails — kerf on waste side, stop at gauge line
- Step 3: Chop waste — work from both faces, pare to line
- Step 4: Transfer to pins — registration, marking sequence
- Step 5: Saw and chop pins — same technique, patience
- Fit and finish: test without glue first, adjust, then glue
- CTA: "Try it in pine before you try it in walnut"
```

Either way, **time each section mentally**. Speak the beats aloud and count the seconds. If your target is 5 minutes and your outline has 12 sections, each section gets 25 seconds — likely not enough for anything technical. Adjust before you film, not after.

### Script Sections That Every Tutorial Needs

Regardless of format, a tutorial script has four load-bearing sections:

**Hook (0:00–0:30):** Show the result. State who the video is for. Never open with "Hi everyone, welcome to my channel." Start with the thing the viewer came for. 30 seconds maximum.

**Materials & Tools:** List exactly what is needed — with specs, not vague categories. "A 3/4" chisel" is useful. "A chisel" is not. This section also functions as a filter: viewers who don't have the tools know immediately whether to watch now or come back.

**Steps (the core):** Each step covers one coherent action. Include on-camera direction notes: what to show, from what angle, at what moment. Also note the common mistake for each step — viewers remember the mistakes more than the instructions.

**Conclusion:** Show the finished result. Give one tip for what to try next. A brief call to action is fine — keep it genuine, not formulaic.

> **ForgeFrame:** Use `/ff-tutorial-script` to generate a full production script
> from your outline. Describe your project or pass in the outline from
> `/ff-video-idea-to-outline`, and the skill writes each section with on-camera
> direction lines, key talking points per step, and a voiceover notes section for
> the editor.
>
> You can also do this manually: take each teaching beat from your outline and
> write it out as a script section using the four-section structure above.
> The skill automates the drafting — but the structure is the same.

---

## Shot List: Seven Categories

A shot list is the production document that tells you (or your camera operator) exactly what to capture. The goal is to arrive on set with a checklist, not a vague sense of "film the steps."

Use these seven categories for every shot in your list. Every shot belongs in one category.

### A-Roll (Talking Head)

The presenter on camera, explaining or narrating. These are your primary continuity shots — the backbone of the edit. Film these after the work is done so you can hold or reference the finished piece.

| # | Beat | Description | Priority | Notes |
|---|------|-------------|----------|-------|
| A1 | Intro | Host on camera, finished piece in hand | must-have | Eye-level, rule of thirds |
| A2 | Step 3 | Explain glue-up technique at bench | must-have | Hold finished piece |
| A3 | Outro | CTA and thanks | should-have | Same framing as A1 |

### Overhead / Bench

Camera mounted above or angled steeply down at the work surface. Used for assembly steps, layout, measurements — anything where the spatial relationship between parts matters. Often the workhorse of a workshop video.

### Detail Closeups

Tight shots of surfaces, joints, grain, texture, or any feature the viewer needs to see clearly. Not measurement-related — measurement shots get their own category.

### Measurement / Cutting

Shots showing dimensions, marks, tape measure readings, saw fence settings, angles. These must be legible in the final video. Note if text overlay will be added in post so you leave enough frame space.

### "Don't Forget" Inserts

One- or two-second cutaways that editors often miss during shooting but wish they had: applying finish, wiping excess, tightening a fastener, checking with a square. Scan your script for verbs like *wipe*, *apply*, *tighten*, *check*, *measure* — each one is an insert candidate.

### Glamour / Result B-Roll

Beauty shots of the finished piece. Shot at the end of the filming day, multiple angles, different lighting if possible. Used in the intro hook, chapter thumbnails, and conclusion. Include at least one "product in use" shot — not just a display shot.

### Likely Pickup Shots

Shots you probably cannot get during the main shoot: wrong time of day, need a second take, require moving the camera between setups. Flag these explicitly so you plan a separate pickup session rather than discovering the gap in the edit.

### Shot Count Summary

Once you've built the full list, summarize it:

| Category | Must-Have | Should-Have | Nice-to-Have | Total |
|----------|-----------|-------------|--------------|-------|
| A-Roll | 3 | 1 | 0 | 4 |
| Overhead | 5 | 2 | 1 | 8 |
| Closeup | 4 | 3 | 2 | 9 |
| Measurement | 3 | 0 | 0 | 3 |
| Inserts | 4 | 2 | 0 | 6 |
| Glamour | 2 | 2 | 2 | 6 |
| Pickups | 1 | 1 | 0 | 2 |

This summary gives you a realistic estimate of how long the shoot will take and tells you exactly which shots are optional if you run out of time.

> **ForgeFrame:** Use `/ff-shot-plan` to generate a complete shot list from your
> script or outline. The skill organizes every shot into the seven categories
> above, assigns priority (must-have / should-have / nice-to-have), links each
> shot to the teaching beat it covers, and produces a summary table with an
> estimated shooting time.
>
> You can also do this manually: read through your script once, and for each
> teaching beat, ask "what does the camera need to show here?" Write down each
> answer in the appropriate category column.

---

## B-Roll Planning

B-roll is any footage that isn't A-roll. It covers cuts, illustrates points, adds visual interest, and carries the viewer through sections where talking-head footage would be static or slow.

For tutorial content, B-roll falls into two kinds:

**Planned B-roll** — shots you know you need before filming starts, because the script explicitly describes an action or detail. If your script says "apply a thin bead of glue to one mating surface only," you need an overhead shot of that action. That goes on your shot list as a planned shot.

**Reactive B-roll** — shots you identify after the fact, from a transcript or rough cut, where the narration describes something the camera didn't show. "The glue sets in about 5 minutes" — did you film the clock or a close-up of squeeze-out appearing? If not, those are pickup shots.

### How Much B-Roll Do You Need?

For a talking-head tutorial, aim for enough B-roll to cover 40-70% of the final runtime. If your video runs 5 minutes and you're on camera the whole time, viewers will disengage. Process shots, tool close-ups, and result reveals give the edit visual rhythm.

The most common B-roll mistake: only filming the final result, not the process. The result looks great, but you have nothing to cut to during the explanation.

> **ForgeFrame:** After filming, use `/ff-broll-whisperer` to analyze your
> transcript and surface specific B-roll moments you might have missed. The skill
> reads your transcript, identifies every moment where a process shot, material
> close-up, tool shot, result reveal, or measurement shot would strengthen the
> edit, and gives you a prioritized shot list grouped by category.
>
> You can also do this manually: read your script or transcript and highlight
> every sentence that describes a physical action or visual detail. Each
> highlighted sentence is a candidate B-roll moment. If you don't have footage
> for it, it goes on your pickup list.

---

## Locking In Technical Specs Before You Shoot

Lock in your technical specs before you record a single frame. Changing resolution or frame rate in post leads to resampling artifacts, sync problems, and wasted render time.

### Default Recommendation

For most tutorial content destined for YouTube or Vimeo:

| Parameter | Value | Why |
|-----------|-------|-----|
| Resolution | 1920×1080 (1080p) | Universally compatible, fast to edit |
| Frame rate | 30 fps | Works for tutorials, talking head, demos |
| Color space | SDR / BT.709 | Standard for web delivery |

### When to Deviate

| Choose this | When |
|-------------|------|
| **4K (3840×2160)** | You need to punch in or reframe in post, or your audience watches on 4K displays |
| **24 fps** | You want a cinematic look and your content has no screen recordings or fast motion |
| **60 fps** | Recording gameplay, fast hand movements, or anything where motion clarity matters |

> [!warning] Keep native frame rate — don't upconvert
> If your camera shoots 30 fps, edit and deliver at 30 fps. "Upconverting" 30 fps footage to 60 fps does not add real motion information — it just doubles frames or creates interpolation artifacts. Match your project frame rate to your source material.

> [!warning] Variable Frame Rate (VFR) causes sync problems
> Many phones and some cameras default to Variable Frame Rate (VFR), which records at a fluctuating frame rate rather than a constant one. VFR footage can appear to work fine until you add audio — then lip sync drifts. Check your camera settings before filming. See Chapter 14 (Quality Control) for how to detect and fix VFR footage after the fact.

---

## Pre-Shoot Checklist

### Camera Setup

- [ ] Resolution set to target (default: 1920×1080)
- [ ] Frame rate set to target (default: 30 fps)
- [ ] Frame rate mode: **Constant Frame Rate (CFR)** — not Variable (VFR)
- [ ] White balance set manually (not auto-WB — it shifts during a shot)
- [ ] Shutter speed set to ~2× frame rate (60/s for 30 fps, 50/s for 25 fps)
- [ ] ISO set to lowest clean setting for your lighting
- [ ] Storage card formatted and confirmed empty

### Audio Setup

| Mic type | Best for | Trade-offs |
|----------|----------|------------|
| USB condenser (e.g., AT2020 USB) | Voiceover, desk recording | Picks up room noise; needs quiet environment |
| Lavalier / lapel | On-camera, moving around | Less room noise; can rustle on clothing |
| Shotgun (e.g., Rode NTG) | On-camera at a distance | Very directional; needs boom or camera mount |
| Built-in laptop / phone mic | Absolute last resort | Noisy, thin, echoey — avoid if possible |

**Before rolling:**
- [ ] Mic connected and input level checked (target: peaks around -12 dBFS, never hitting 0)
- [ ] Test recording played back through headphones — not speakers
- [ ] Room checked: fans off, AC off, windows closed
- [ ] Record 10 seconds of room tone (silence) before your first take — for noise reduction in post

### Lighting Setup

Three scenarios for tutorial content:

**Talking head (facing camera):** Key light at 45° to your face, fill or bounce on the other side to reduce shadows. Avoid overhead-only lighting — it creates unflattering shadows under eyes.

**Overhead bench shot:** Soft, even lighting from above with no harsh shadows on the work surface. Two diffused lights at 45° angles works better than one overhead light.

**Detail / closeup shot:** Directional light from the side to reveal texture and depth. A small LED panel at low angle shows grain, surface quality, and material detail better than flat frontal lighting.

- [ ] Lights positioned for your first setup
- [ ] No clipped highlights (overexposed bright areas) in test frame
- [ ] Background is appropriate — not distracting, not too dark

### Sync Strategy

If you record audio separately from camera (e.g., USB mic into Audacity while camera rolls), you need a sync point.

> [!tip] Clap method for sync
> At the start of every take, give a single sharp clap on camera. The clap creates a visible spike in the audio waveform and a visual frame where your hands meet. Line those two up in the timeline and your audio is synced. This takes five seconds and saves twenty minutes of frustration.

If you record audio directly through the camera or screen recorder, sync is automatic — but check it in the editor before committing to an edit.

- [ ] Sync method decided (on-camera audio vs. separate recorder)
- [ ] If separate: clap or slate ready for start of each take
- [ ] If screen recording: confirm audio routed correctly before hitting record

---

> **ForgeFrame:** Use `/ff-capture-prep` to generate a personalized pre-shoot
> checklist from your shot plan. The skill reads your shot plan, optimizes the
> shooting order to minimize setup changes (all overhead shots together, then
> all A-roll, then closeups), and produces a checklist customized to your target
> resolution, frame rate, and any gear constraints you mention.
>
> You can also use the manual checklist above as-is — it covers the same ground.
> The skill adds shot-order optimization and connects directly to your project
> workspace, but the pre-shoot requirements are identical either way.

---

## Before You Shoot

By the end of this chapter, you should have:

- [ ] A script (full or outline format) with section timing
- [ ] A shot list organized by the seven categories, with priorities
- [ ] B-roll candidates identified and marked on the shot list
- [ ] Technical specs locked (resolution, frame rate, CFR confirmed)
- [ ] Pre-shoot checklist completed

With these documents, your shoot has a plan. You'll know when you're done because you can physically check off every shot. Your editor (future you) will thank you.

---

*Next: [Chapter 05 — Filming Your Tutorial](05-filming-your-tutorial.md)*
*Back: [Chapter 03 — From Idea to Outline](03-from-idea-to-outline.md)*
