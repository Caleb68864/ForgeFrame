---
title: "Hardware and Software"
part: "Part VI — Reference"
chapter: 18
tags:
  - hardware
  - software
  - budget
  - alternatives
---

# Chapter 18: Hardware and Software

## Hardware Tiers

The table below maps common editing workloads to reasonable hardware targets. These are guidelines, not minimums -- you can always start with what you have and upgrade the bottleneck you actually hit.

| Tier | Typical Workload | CPU | RAM | GPU | Storage | Budget (USD) |
|------|-----------------|-----|-----|-----|---------|-------------|
| **Entry** | 1080p SDR, light effects, simple cuts | 6-8 cores | 16 GB | Integrated OK | 1 TB SSD | ~$600-1000 |
| **Mid** | 4K SDR with proxies, heavier effects, colour grading | 8-16 cores | 32 GB | Discrete GPU (4 GB+ VRAM) | 1-2 TB NVMe + archive HDD | ~$1000-2500 |
| **Pro** | Multi-cam, 4K/6K+, higher bit depth, HDR | 16+ cores | 64 GB+ | Strong GPU (8 GB+ VRAM) | NVMe scratch + RAID/NAS for projects | ~$2500+ |

### Evidence Notes

- **CPU**: Kdenlive delegates encoding to MLT/FFmpeg, which distributes work across threads. Codecs like H.264 and H.265 scale well to 8-16 threads; beyond that you hit diminishing returns on encode speed but still benefit during preview rendering and effects processing.
- **Storage**: ProRes 422 HQ runs roughly 220 Mbps at 1080p 29.97 fps; DNxHR SQ is comparable. A single 4K ProRes stream can saturate a SATA SSD, so NVMe matters once you move past 1080p or stack multiple streams on a timeline.
- **GPU**: GPU acceleration in Kdenlive/MLT is situational. It helps with specific encode paths (e.g., VAAPI/NVENC hardware encoding, some OpenGL-accelerated scopes) but is not a blanket performance multiplier for every operation. Spend on CPU and storage first.

## Disproportionately Helpful Add-Ons

> [!tip] Audio first
> A USB condenser microphone ($50-100) paired with basic acoustic treatment (moving blankets, foam panels) improves perceived production quality more than a camera upgrade. Audiences tolerate mediocre video far longer than mediocre audio.

- **Second display**: With two monitors you can keep the timeline, scopes, and project bin visible simultaneously. Kdenlive's dockable UI panels make this especially effective -- drag the clip monitor and effect stack onto the second screen and reclaim timeline real estate on the primary.
- **Shuttle/jog controller**: Optional but useful for long-form edits. Kdenlive supports configurable keyboard shortcuts that map well to shuttle dials.
- **UPS / battery backup**: Protects long renders from power interruptions. Cheap insurance.

## Software Ecosystem

Kdenlive is built on the **MLT Framework**, which acts as a media processing pipeline. Understanding the layer cake helps when you hit edge cases:

```
MLT core
  └── FFmpeg / libavfilter   (decode, encode, many filters)
        └── frei0r            (additional video effects)
        └── LADSPA            (audio effects / plugins)
              └── packaging-dependent extras
```

Effect availability depends on what your distribution packages. On Flatpak installs, some frei0r or LADSPA plugins may be missing compared to native packages. Check `Settings > Configure Kdenlive > Environment` to see which plugin paths are active.

> [!warning] Codec licensing
> Some codecs (notably H.264 and H.265/HEVC) are covered by patent pools. FFmpeg includes decoders/encoders but redistribution and commercial use may carry licensing obligations depending on jurisdiction. For public or commercial projects, be aware of MPEG-LA and Access Advance licensing terms, or consider royalty-free codecs like AV1 and VP9 for distribution.

## Monitor Calibration for Color Work

> [!tip] Color work sidebar
> If you do any color correction or grading, your monitor is a precision instrument -- not just a display. An uncalibrated monitor will mislead you about the actual appearance of your footage on viewer screens.

### What "calibrated" means

A calibrated monitor has been adjusted so that:
- **White point is D65** (6500K, the standard for sRGB and BT.709 content)
- **Gamma is 2.2** (standard for SDR content on Windows and Linux)
- **Color primaries match BT.709** -- the color space used by virtually all YouTube and streaming content

If your monitor runs at a warmer white point (yellowish whites), you will add too much blue when correcting. If it runs cool (bluish whites), you will overcorrect the other direction. Either way, your corrections look right on your screen but wrong on everyone else's.

### Minimum setup for tutorial creators

You do not need a professional reference monitor. You need:
1. **A monitor that can display sRGB/BT.709 accurately** -- most modern IPS panels can; TN panels are less consistent
2. **A hardware calibration profile applied** -- use your OS display settings or a free tool to load the manufacturer's ICC profile
3. **Kdenlive's color scopes** -- use the Waveform and Parade scopes to verify exposure and white balance by the numbers, not just by eye (see Ch.09 for scope reading)

### Free calibration steps (no calibration hardware)

1. **Load the manufacturer ICC profile** -- Download from the monitor vendor's site, install under *System Settings > Color* (Linux) or *Display > Color Profile* (Windows). This corrects for your specific panel's factory measurements.
2. **Adjust brightness to ~80-100 nits** -- Too bright or too dim shifts your perception of contrast.
3. **Set color temperature to 6500K** -- Use your monitor's OSD menu. Avoid "warm" or "cool" presets; those are usually 5000K and 8000K respectively.
4. **Use a reference image** -- Display a known-good BT.709 reference image (a standard color chart or a trusted "calibration test image") and compare against a known-good screen (e.g., your phone in sRGB mode).

### When to invest in a hardware calibrator

A hardware colorimeter (Datacolor Spyder, X-Rite i1Display) is worth it if:
- You are doing paid work where color accuracy matters
- You are grading on a different monitor than you edit on
- You notice consistent color complaints from viewers despite your corrections looking right

For tutorial creators publishing to YouTube, a properly profiled mid-range IPS monitor is sufficient. Focus on mastering the scopes first (Ch.09) before spending on calibration hardware.

See Ch.09 (Color Correction & Grading) for how to read waveforms and vectorscopes to verify your corrections independently of your monitor's accuracy.

## Alternatives Comparison

All tools below are free and open-source unless noted.

| Tool | License | Strength for Learners | ForgeFrame Notes |
|------|---------|----------------------|-----------------|
| **[[18-hardware-and-software#Software Ecosystem\|Kdenlive]]** | GPL-3.0 | Broad NLE feature set: subtitles, speech-to-text, sequences, extensive render presets. Good "teachable mapping" to professional concepts. | Primary target for ForgeFrame automation. |
| **Shotcut** | GPL-3.0 | Also MLT-based -- same engine, different UI philosophy. Filter-centric workflow. | Same render pipeline; ForgeFrame render profiles are mostly compatible. |
| **Flowblade** | GPL-3.0 | Linux-focused, strong classic insert/overwrite editing model, simpler UI. | Good alternative if Kdenlive feels overwhelming at first. |
| **OpenShot** | GPL-3.0 | Very beginner-friendly, curve-based keyframes, drag-and-drop titles. | Solid starter NLE; fewer advanced features to grow into. |
| **Olive** | GPL-3.0 | Modern node-based UX, GPU-accelerated. Currently alpha/unstable. | Watch this space -- promising architecture but not production-ready yet. |
| **Blender VSE** | GPL-2.0+ | Video editing + VFX + motion graphics in one suite. | Heavier learning curve; best if you already use Blender for 3D/motion work. |
