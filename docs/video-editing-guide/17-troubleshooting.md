---
title: "Troubleshooting and QC"
part: "Part VI — Reference"
chapter: 17
tags:
  - troubleshooting
  - qc
  - performance
  - debugging
---

# Chapter 17: Troubleshooting and QC

This page follows a consistent format: **symptom**, **likely cause**, **test**, and **fix**.

## Performance / Playback Stutters

**Symptom:** Timeline playback drops frames, stutters, or freezes entirely.

**Likely cause:** You are editing high-resolution, long-GOP codecs (H.264, HEVC) directly on the timeline without proxies. Other contributors include slow storage (spinning disk, USB 2.0), heavy real-time effects stacking, and insufficient RAM.

**Test:** Check your clip properties -- if your source files are H.264 `.mp4` from a camera or phone and you have no proxy clips enabled, this is almost certainly the problem. Monitor CPU usage during playback.

**Fix:**
1. **Enable proxy clips** -- Kdenlive can generate lightweight editing proxies automatically. Go to *Project > Project Settings > Proxy* and enable proxy generation.
2. **Reduce preview scaling** -- In the monitor toolbar, lower the preview resolution to half or quarter.
3. **Simplify effects** -- Temporarily disable effects on clips to isolate the bottleneck.
4. **Use fast storage** -- Edit from an SSD or NVMe drive, not a spinning disk or network share.

## Audio Clips / Distorts

**Symptom:** Audio sounds distorted, crunchy, or harsh on loud sections.

**Likely cause:** Audio levels are exceeding 0 dBFS (digital clipping). Once audio hits the digital ceiling, the waveform is literally chopped flat.

**Test:** Watch the audio meters during playback. If they hit red / 0 dB, you are clipping.

**Fix:**
1. Enable clipping indicators on the master audio meter.
2. Lower the gain on the offending track or clip.
3. Apply a **limiter** on the master bus as a safety net (set ceiling to -1 dBTP).
4. Normalize with intent -- do not just slam everything to 0 dB. Target your delivery loudness (see [[13-formats-codecs-export#Audio Loudness for Delivery]]).

## Subtitle Generation Fails

**Symptom:** Subtitle generation or import produces errors, empty tracks, or misaligned timing.

**Likely cause:** Workflow edge cases around subtitle track creation and import in Kdenlive. The subtitle system expects a subtitle track to exist before import, and temporary file paths can disappear between sessions.

**Test:** Check whether a subtitle track exists in the timeline. Verify your SRT file is saved to a persistent location (not `/tmp`).

**Fix:**
1. **Create the subtitle track first** -- In the timeline, add a subtitle track before attempting to import an SRT file.
2. **Save SRT files outside temp paths** -- Store subtitle files in your project directory, not in system temp folders that get cleaned up.
3. Re-import the SRT after ensuring the track exists and the file path is stable.

## Variable Frame Rate / Sync Issues

**Symptom:** Audio drifts out of sync with video over time, or cuts appear at wrong positions.

**Likely cause:** Your source footage uses Variable Frame Rate (VFR). Most phones and screen recorders produce VFR files. Video editing engines (including MLT, which powers Kdenlive) assume Constant Frame Rate (CFR). When they encounter VFR, timing calculations break down progressively.

**Test:** Use `ffprobe` or MediaInfo to check if your source file has variable frame rate. Look for `Variable` in the frame rate mode field.

> [!danger]
> Variable Frame Rate is the number one beginner trap with phone footage. If you record on a phone and edit in Kdenlive (or most NLEs), you **must** transcode to CFR first. There is no reliable fix after the fact -- the sync errors compound over the entire timeline.

**Fix:**
1. **Transcode to CFR before editing** -- Use FFmpeg to convert VFR sources to a constant frame rate intermediate:
   ```bash
   ffmpeg -i input_vfr.mp4 -vsync cfr -r 30 -c:v prores_ks -profile:v 1 output_cfr.mov
   ```
2. Make this a standard step in your ingest workflow for any phone or screen-capture footage.

> **ForgeFrame:** Use `media_check_vfr` to detect VFR sources automatically across your entire workspace, then `media_transcode_cfr` to convert them in one step. This runs FFprobe on every clip in `media/raw/` and flags any file with variable frame rate before you start editing.
> You can also do this manually: run `ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate,avg_frame_rate -of default=noprint_wrappers=1 input.mp4` and compare `r_frame_rate` vs `avg_frame_rate` -- if they differ, the file is VFR.

See Ch.14 (Quality Control) for the automated QC workflow that catches VFR files before they reach the timeline.

## Audio Sounds Muffled, Harsh, or Inconsistent

**Symptom:** Recorded audio has constant background hiss, volume that jumps between sentences, harsh "s" and "t" sounds (sibilance), or overall levels that are too quiet for comfortable listening.

**Likely cause:** Unprocessed raw audio almost always needs a processing chain applied: noise reduction, dynamic compression, de-essing, and loudness normalization. Raw recordings from a USB mic or lavalier rarely sound broadcast-ready without at least some processing.

**Test:** Check your integrated LUFS level using FFmpeg's loudnorm filter in analysis mode. YouTube targets -14 LUFS integrated. A raw recording might be at -23 to -30 LUFS -- audible but far too quiet after YouTube's normalization step.

**Fix:**
1. Apply the standard voice processing chain in order:
   - **Noise reduction** -- sample a silent section and remove constant background hiss
   - **High-pass filter** -- cut everything below 80 Hz (eliminates rumble, desk vibration)
   - **EQ** -- cut mud at 200-400 Hz, boost presence at 2-5 kHz
   - **Compression** -- even out volume swings (3:1-4:1 ratio, 3-6 dB gain reduction)
   - **De-esser** -- tame harsh sibilance if present
   - **Loudness normalization** -- target -14 LUFS integrated, -1 dBTP true peak
   - **Limiter** -- final safety net at -1 dBTP ceiling

2. Kdenlive can apply these as a chain using LADSPA and MLT audio filters. Stack them in the Clip Properties audio tab.

> **ForgeFrame:** Use `/ff-audio-cleanup` to apply the full processing chain automatically. It analyzes your raw audio, selects the right preset (`youtube_voice`, `podcast`, or `raw_cleanup`), runs all six stages, and reports before/after LUFS so you can see exactly what changed.
> You can also do this manually: Kdenlive's audio effect stack supports individual noise reduction (SoX), EQ (LADSPA), and normalization steps -- apply them in the order listed above.

See Ch.10 (Audio Production) for a full explanation of each processing stage and why the order matters.

## Export Quality Slider Confusion

**Symptom:** Changing the quality slider produces unexpected results -- higher numbers look worse, or the slider seems to do nothing.

**Likely cause:** Quality scales differ by codec and are not consistent across Kdenlive render profiles. For x264, MPEG-2, and VPx codecs, **lower numbers mean higher quality** (they map to CRF or quantizer values). This is the opposite of what most people expect.

**Test:** Render a short test clip at two different quality values and compare file size and visual quality.

**Fix:**
1. Use codec-specific guidance rather than trusting the slider label:
   - **x264/x265:** Quality = CRF. Range 0--51. Use 18--23 for good quality.
   - **VP9:** Quality = CQ. Range 0--63. Use 15--35.
   - **MPEG-2:** Quality = qscale. Range 1--31. Use 2--5.
2. Always verify with a short test export before committing to a full render.

## Missing Codec / Red Cross on Render Preset

**Symptom:** A render preset shows a red cross or error icon, and rendering fails with codec-related errors.

**Likely cause:** The required codec libraries are not installed on your system. This is common on minimal Linux installations or when using distribution packages that split codec support into separate packages.

**Test:** Try rendering with a basic H.264/MP4 preset. If that works but others fail, you are missing specific codec packages.

**Fix:**
1. Install the missing codec packages for your distribution (e.g., `ffmpeg`, `libx264`, `libx265`, `libvpx`).
2. **Rerun the Kdenlive configuration wizard** after installing codecs -- Kdenlive detects available codecs at startup or during the wizard, and it will not pick up newly installed codecs until you do this.

> [!tip]
> The Kdenlive **AppImage** bundles most codecs and their dependencies. If you are fighting codec issues on Linux, switching to the AppImage can resolve them in one step.

## Color Looks Wrong After Export

**Symptom:** Exported video looks washed out, oversaturated, or has shifted colors compared to the timeline preview.

**Likely cause:** Colorspace metadata issues during the transcode pipeline. Common scenarios include mixing BT.601 and BT.709 sources, incorrect tagging in the export profile, or player-side misinterpretation of color metadata.

**Test:** Compare the export in multiple players (VLC, browser, mpv). If it looks different in each, the metadata tagging is ambiguous. Use `ffprobe` to check the `color_space`, `color_transfer`, and `color_primaries` fields.

**Fix:**
1. Verify that your project and export settings are both set to **BT.709** for SDR content (see [[13-formats-codecs-export#Color Space Defaults for SDR]]).
2. If you transcoded source footage before editing, check that the transcode preserved or correctly set color metadata.
3. Consult the Kdenlive "Color Hell" documentation for edge cases involving MLT's color pipeline.

## QC Checklist

Run through this checklist before delivering or uploading any final export:

- [ ] Watch the full export at 1x speed (no skipping)
- [ ] Check the first and last 5 seconds for black frames or audio pops
- [ ] Verify audio levels -- no clipping, consistent loudness across the piece
- [ ] Check subtitle timing and readability (if applicable)
- [ ] Test on the target platform (do a private/unlisted upload test)
- [ ] Compare against source material for color accuracy and framing
- [ ] Verify file size is reasonable for the target bitrate and duration
