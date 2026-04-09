---
title: "Quality Control"
part: "Part V — Output"
chapter: 14
tags:
  - quality-control
  - qc
  - loudness
  - vfr
  - export
---

# Chapter 14: Quality Control

You have exported your video. Before you upload, run QC. A two-minute check now prevents a bad experience for every viewer who watches before you catch it.

This chapter covers two types of QC: a quick visual spot-check you do with your eyes, and an automated check that catches technical problems your eyes would miss.

## Why QC Before Upload

Once a video is live on YouTube, any significant quality problem requires re-uploading. Re-uploads reset your view count, lose any scheduled premiere, and break external links. More importantly, the first hours of a video's life matter most for algorithm reach. A bad first impression is expensive.

The most common problems QC catches:
- Silent sections from a dropped audio track
- Black frames from a missed cut or missing source media
- Audio clipping from a gain stage set too hot
- Loudness that is too quiet (viewers turn away) or too loud (YouTube turns it down anyway)
- VFR (variable frame rate) footage that survived to export and causes sync drift

## Pre-Publish QC Checklist

Work through this checklist on every export before uploading.

### Visual Spot-Check (Manual -- ~2 minutes)

- [ ] **Watch the first 30 seconds at full speed.** Does it start cleanly? No black frames, no audio pop, no wrong music?
- [ ] **Scrub to the middle.** Any obvious visual glitches, jump cuts that should not be there, or missing B-roll?
- [ ] **Watch the last 30 seconds.** Does the outro play correctly? Does audio fade out rather than cut?
- [ ] **Check the title card and any lower thirds.** Spelling correct? Text readable on a phone-sized screen?
- [ ] **Check chapter marker timestamps** (if using chapters in the description). Do they land on the right sections?

### Automated QC Check (ForgeFrame -- ~30 seconds)

> **ForgeFrame:** Use `/ff-qc-check` to run automated technical checks on your export:
>
> ```
> qc_check file="my-tutorial-final.mp4"
> ```
>
> ForgeFrame will report pass/fail for each check and flag specific timestamps for any issues found. You can also do this manually using the tools listed in the table below.

## What Each QC Check Catches

| Check | What It Detects | Example of a Real Problem | Manual Alternative |
|---|---|---|---|
| **Black frames** | Contiguous frames at or below 0.01 luma | Missed source clip left a 2-second black gap at 4:32 | Scrub timeline at 2x speed |
| **Silence** | Audio RMS below -60 dBFS for >0.5 seconds | Narration track accidentally muted for 8 seconds | Listen through at 2x speed |
| **Loudness** | Integrated LUFS below -18 or above -10 | Mix is too quiet (viewers skip); mix is too loud (YouTube normalizes down, dynamic range collapses) | `ffmpeg -i file.mp4 -af loudnorm=print_format=json -f null -` |
| **Clipping** | True peak samples at or above -0.5 dBTP | Mic peaked during a loud explanation; sounds distorted on good speakers | Kdenlive audio meter; any sample above 0 dBFS is clipping |
| **File size** | File significantly smaller or larger than expected for the profile | 2-hour render at 8 Mbps came out 50 MB -- encoding failed silently; or 30-min tutorial is 18 GB -- wrong profile used | `ls -lh output.mp4` |

### Loudness Targets

- **Target integrated loudness:** -14 LUFS
- **Maximum true peak:** -1 dBTP

These are the practical targets for YouTube tutorial content. YouTube applies its own loudness normalization, but if you submit at -14 LUFS your audio will pass through normalized at nearly the same level, which means your mix sounds as you intended. If you submit louder than -14 LUFS, YouTube will turn you down and the compression artifacts become more noticeable.

If your export is louder than -14 LUFS, go back to Chapter 10 (Audio Production) and lower your master fader, then re-export. If it is quieter, you have room to increase gain before the limiter.

> [!info]
> True peak is different from peak. True peak accounts for inter-sample peaks that occur during D/A conversion, which can clip even if your digital meters show headroom. The -1 dBTP ceiling prevents this. The ForgeFrame `qc_check` uses BS.1770-4 measurement, the same algorithm YouTube uses internally.

## VFR Detection and Correction

Variable frame rate (VFR) is the single most common technical problem that survives QC on casual exports. Phones, screen recorders, and many webcams default to VFR mode -- they vary the frame rate to save power or bandwidth. Inside Kdenlive, VFR footage may look fine. In the rendered export, audio and video drift apart progressively over a long clip.

See Chapter 05 (Filming Your Tutorial) for how to prevent VFR at capture time. If you already have a VFR file, use the workflow below.

### Detecting VFR

> **ForgeFrame:** Use `media_check_vfr` to detect variable frame rate in a source file:
>
> ```
> media_check_vfr file="screen-recording.mp4"
> ```
>
> ForgeFrame reports the minimum, maximum, and average frame interval. If min and max differ by more than 1ms, the file is VFR. You can also do this manually:
>
> ```bash
> ffprobe -v error -select_streams v:0 \
>   -show_entries packet=pts_time,duration_time \
>   -of csv=p=0 input.mp4 | awk -F, '{print $2}' | sort -u
> ```
>
> Multiple distinct values in the output confirm VFR.

### Transcoding to CFR

> **ForgeFrame:** Use `media_transcode_cfr` to convert a VFR file to constant frame rate before importing into Kdenlive:
>
> ```
> media_transcode_cfr file="screen-recording.mp4" fps=30 output="screen-recording-cfr.mp4"
> ```
>
> Use 30fps for screen recordings and talking-head footage. Use 60fps only if the source was captured at 60fps. You can also do this manually:
>
> ```bash
> ffmpeg -i screen-recording.mp4 -vf fps=30 -vsync cfr screen-recording-cfr.mp4
> ```

> [!warning]
> Always transcode VFR to CFR **before** importing into Kdenlive. Transcoding after editing (on the Kdenlive timeline or the final render) does not fix the timing relationship between audio and video that was established at import.

## What to Do When QC Fails

| QC Failure | Root Cause | Go Back To |
|---|---|---|
| Black frames | Missing source clip, failed composite, or bad transition | **Chapter 07** (Your First Edit) -- check clip bins and timeline for gaps |
| Silence > 2 seconds | Muted audio track, missing narration clip, or cut that removed audio | **Chapter 07** -- check audio tracks in timeline |
| Loudness too quiet (below -18 LUFS) | Master fader too low, noise gate over-triggering, or narration track missing | **Chapter 10** (Audio Production) -- recheck gain staging and normalization |
| Loudness too loud (above -10 LUFS) | Gain staging set too hot upstream of the limiter | **Chapter 10** -- lower input gain before the limiter |
| Clipping | Gain was increased after limiter, or limiter is bypassed | **Chapter 10** -- check signal chain order |
| File size wrong (too small) | Render failed silently, wrong profile used, or source was missing | Re-render using the correct ForgeFrame profile (see **Chapter 13**) |
| VFR detected in export | VFR source footage was not converted before import | **Chapter 05** (Filming) for prevention; re-transcode source with `media_transcode_cfr` and re-edit |

## After QC Passes

When all checks are green, your file is ready to upload. See **Chapter 15: Publishing to YouTube** for title, description, thumbnail, and chapter marker guidance to maximize reach after you upload.
