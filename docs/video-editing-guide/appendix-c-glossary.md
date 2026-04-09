---
title: "Glossary"
part: "Appendices"
tags:
  - glossary
  - terminology
  - reference
---

# Appendix C: Glossary

Terms used throughout this handbook, defined in plain language for tutorial creators. Technical definitions are simplified for practical use — links to formal standards are provided where precision matters.

---

## A

**A-Roll**
The primary footage of a speaker on camera, narrating or demonstrating. In tutorial videos, A-roll is typically the talking-head segments. Contrast with B-roll.

**AAC**
Advanced Audio Coding. The dominant audio codec for web delivery. Used in YouTube's streaming pipeline. A good-quality stereo AAC encode at 192-320 kbps is transparent for voice and music at typical listening levels.

**AV1**
Open, royalty-free video codec developed by the Alliance for Open Media. Achieves significantly smaller files than H.264 at the same quality. YouTube and most browsers support playback. Encoding is slow on current hardware but improving.

---

## B

**B-Roll**
Supplementary footage that covers narration or provides visual context — closeups of hands at work, product shots, environment shots, process footage. The ratio of B-roll to A-roll determines much of a tutorial's visual pace. See Ch.11 for pacing guidance.

**BT.709** (also: Rec. 709)
The color space standard for HDTV and standard web video (YouTube, Vimeo, streaming). Defines the color primaries (the range of colors that can be represented), white point (D65, 6500K), and gamma transfer function (approximately 2.2). Almost all tutorial footage should be tagged and exported as BT.709. See Ch.09.

**Bitrate**
The amount of data used per second of video or audio, measured in Mbps (megabits per second) for video and kbps (kilobits per second) for audio. Higher bitrate = higher quality and larger file size. YouTube recommends 8 Mbps for 1080p60 uploads.

---

## C

**CFR** (Constant Frame Rate)
Video where each frame occupies exactly the same duration. All professional editing workflows assume CFR. Contrast with VFR.

**CRF** (Constant Rate Factor)
A quality-based encoding mode used by x264 and x265 encoders. Lower numbers = higher quality and larger files. The range is 0-51; 18-23 is typical for good-quality H.264. Counterintuitively, lower CRF numbers mean higher quality — the opposite of what most people expect.

**Codec**
A software algorithm for compressing and decompressing video or audio. Short for "coder-decoder." Common video codecs: H.264, H.265/HEVC, AV1, ProRes, DNxHR. Common audio codecs: AAC, Opus, PCM (uncompressed). Codecs are distinct from containers (MP4, MOV, MKV).

**Color Grading**
Applying creative looks or stylistic color treatments after primary color correction. Grading is optional and subjective — correction is corrective and objective. For tutorial creators, grading usually means adding subtle warmth or contrast to match a "look." See Ch.09.

**Compression (audio)**
Dynamic range compression reduces the volume difference between quiet and loud parts of an audio signal. It makes quiet words louder and loud words quieter. For voice, a ratio of 3:1 to 4:1 with 3-6 dB of gain reduction is typical. Contrast with lossy compression (codec compression).

**Container**
A file format that packages video, audio, and metadata tracks together. Common containers: MP4, MOV, MKV, AVI. A container does not determine quality — it determines what codecs and features (chapters, subtitles, multiple audio tracks) can be stored inside.

---

## D

**dBFS** (Decibels Full Scale)
A measurement of audio level relative to the digital maximum. 0 dBFS is the highest possible level before clipping. Typical voice recording targets -12 to -18 dBFS peaks to leave headroom for processing.

**dBTP** (Decibels True Peak)
A measurement of the actual peak audio level, accounting for inter-sample peaks that can occur during digital-to-analog conversion. YouTube's delivery spec is -1 dBTP maximum. True peak differs from sample peak — a signal that measures -2 dBFS by sample can still clip at the DAC. Use a true peak limiter, not just a peak limiter.

**De-esser**
An audio effect that reduces harsh sibilance — the harsh "ssss" and "tsss" sounds produced by certain consonants, especially when recording close to a microphone. Applied after compression in the signal chain. Part of the `ff-audio-cleanup` processing pipeline.

**DNxHD / DNxHR**
Avid's professional intermediate codecs. DNxHR is the 4K successor to DNxHD. Both offer multiple quality tiers (LB, SQ, HQ, HQX, 444). Used as high-quality editing intermediates; not typically used for delivery. See Ch.13.

---

## E

**EBU R 128**
The European Broadcasting Union's loudness normalization standard. Specifies -23 LUFS integrated target for broadcast, with permitted deviation. Streaming platforms (YouTube, Spotify, etc.) adapted this to their own targets (YouTube: -14 LUFS integrated). The measurement algorithm is defined by ITU-R BS.1770. See Ch.10.

**Export Profile**
A preset in Kdenlive's Render dialog that specifies container, codec, bitrate or quality settings, and audio parameters. ForgeFrame provides named profiles (`youtube-1080p`, `youtube-4k`, `master-prores`, etc.) for common delivery targets. See Ch.13.

---

## F

**FFmpeg**
The open-source multimedia framework that powers most of Kdenlive's encoding, decoding, and processing. Required by ForgeFrame. Most troubleshooting commands in Ch.17 use FFmpeg or its companion tool `ffprobe`.

**FFprobe**
A command-line tool included with FFmpeg for inspecting media files. Used to detect VFR, check color metadata, verify codec parameters, and diagnose playback issues.

**Frame Rate**
The number of frames displayed per second. Common rates: 24fps (cinematic), 30fps (standard for tutorials), 60fps (smooth motion). Must be constant (CFR) for reliable editing. See VFR for the common problem with phone footage.

---

## G

**Gain**
The amount of amplification applied to a signal. At the recording stage, gain controls how sensitive the microphone is to incoming sound. At the output stage, gain controls volume. Setting gain too high during recording causes clipping; setting it too low results in poor signal-to-noise ratio. Target -12 dBFS peaks for voice recording.

**Grading** → See *Color Grading*

---

## H

**H.264** (also: AVC, MPEG-4 Part 10)
The most widely supported video codec. Used for most web video and camera recordings. Long-GOP structure makes it efficient for delivery but difficult to edit directly — use proxy clips or transcode to an editing-friendly intermediate. See Ch.13.

**H.265** (also: HEVC)
The successor to H.264. Achieves comparable quality at roughly half the bitrate. Widely supported for playback; encoding is slower than H.264 on software encoders. Patent licensing is more complicated than AV1 alternatives.

**High-Pass Filter** (HPF)
An audio filter that attenuates frequencies below a cutoff frequency. In voice processing, a high-pass at 80 Hz removes low-frequency rumble, desk noise, and air conditioning hum without affecting voice clarity. The first step in the `ff-audio-cleanup` chain. See Ch.10.

---

## I

**IRE**
A unit of measurement for analog video signal levels, named after the Institute of Radio Engineers. In the context of digital scopes (waveform monitors), IRE is used informally to indicate luma (brightness) level: 0 IRE = black, 100 IRE = white. Properly exposed footage should have its darkest darks at 0-5 IRE and brightest whites at 90-100 IRE (slightly below digital clipping). See Ch.09 for scope reading.

**Intermediate Codec**
A codec designed for editing rather than delivery. High quality, intraframe only (every frame is independently compressed, no inter-frame dependencies), large file sizes. Examples: ProRes, DNxHR, MJPEG. Use as an intermediate after transcoding VFR footage; return to a delivery codec (H.264, AV1) for the final export.

**Intraframe Codec**
A codec where each frame is compressed independently, with no reference to adjacent frames. Kdenlive can seek to any frame instantly, and transcoding is reliable at any cut point. All intermediate codecs are intraframe. Contrast with Long-GOP.

---

## J-K-L

**J-K-L Editing**
A three-key playback control system used in professional editing. J = play backward, K = stop/pause, L = play forward. Pressing J or L multiple times increases speed (2x, 4x, 8x). This is the fastest way to scrub through footage in Kdenlive. See Appendix B for the full shortcut list.

---

## L

**Lift / Gamma / Gain**
The three primary controls for tonal adjustment in color correction:
- **Lift**: Adjusts the shadow/black levels (low end of the tonal range)
- **Gamma**: Adjusts midtones without affecting shadows or highlights
- **Gain**: Adjusts the highlight/white levels (high end of the tonal range)

Together these three controls handle 90% of primary color correction. Available in Kdenlive as the "Lift/Gamma/Gain" effect. See Ch.09.

**Long-GOP**
A compression structure where only some frames are fully encoded (keyframes/I-frames); other frames store only the differences from nearby keyframes (P-frames and B-frames). Efficient for delivery (H.264, H.265), but creates problems during editing: seeking is slow, and editing at non-keyframe positions can cause artifacts. Use proxy clips or transcode to an intraframe intermediate for editing.

**LUFS** (Loudness Units Full Scale)
The unit of integrated loudness measurement, as defined by ITU-R BS.1770 and used in EBU R 128. Measures perceptual loudness across the duration of a program (integrated) rather than instantaneous peaks. YouTube normalizes uploads to -14 LUFS integrated. See Ch.10.

**LUT** (Look-Up Table)
A file that maps input color values to output color values, used to apply a consistent color transformation or look. Technical LUTs convert between color spaces (e.g., log-to-BT.709). Creative LUTs apply stylistic grading looks. Always apply LUTs AFTER primary correction, not before. ForgeFrame uses `.cube` LUT files via the `color_apply_lut` tool. See Ch.09.

---

## M

**MCP** (Model Context Protocol)
The protocol used by Claude Code to communicate with external tools and services. ForgeFrame exposes its 88 tools over MCP, which is what allows Claude to run render jobs, analyze audio, check VFR, and perform other production tasks from within the conversation.

**MLT Framework**
The open-source media processing framework that powers Kdenlive and Shotcut. MLT handles the actual video decoding, effect processing, and encoding — Kdenlive is essentially a graphical interface for MLT. Understanding MLT helps when troubleshooting edge cases in Kdenlive, especially for effects that use LADSPA or frei0r plugins.

**MYOG** (Make Your Own Gear)
A maker community acronym for handmade outdoor gear (backpacks, shelters, sleeping bags) from technical fabrics. `ff-pattern-brain` was designed specifically for MYOG tutorial workflows — extracting materials lists, measurements, and build steps from tutorial transcripts.

---

## N

**NLE** (Non-Linear Editor)
A video editing application that allows access to any frame in any order at any time (unlike tape-based "linear" editing). Kdenlive, Premiere Pro, DaVinci Resolve, and Final Cut Pro are all NLEs. The term distinguishes modern software editors from tape decks and early hardware editing systems.

**Normalization**
Adjusting audio levels to a target standard. Loudness normalization targets an integrated LUFS value. Peak normalization targets a maximum sample peak. Use loudness normalization (not peak) for YouTube delivery — targeting -14 LUFS integrated, -1 dBTP true peak. See Ch.10.

---

## P

**Proxy Clips**
Low-resolution, editing-friendly versions of source footage created for use during editing. Kdenlive uses proxies to enable smooth playback of high-resolution, high-bitrate source files (4K H.264, 8K RAW). The original files are used for the final render. Enable via *Project Settings > Proxy*. See Ch.06.

**ProRes**
Apple's family of professional intermediate codecs. Quality tiers from lowest to highest: ProRes Proxy, ProRes LT, ProRes 422, ProRes 422 HQ, ProRes 4444, ProRes 4444 XQ. ProRes 422 HQ is a common editing intermediate — high quality, intraframe, fast to decode and encode. Supported by FFmpeg on Linux. See Ch.13.

---

## Q

**QC** (Quality Control)
The process of verifying a finished export before delivery or upload. Includes checking for black frames, audio dropouts, clipping, loudness compliance, subtitle timing, and file integrity. ForgeFrame's `qc_check` tool automates the technical checks. A human watch pass is still required. See Ch.14 and Ch.17.

---

## R

**Render Profile**
→ See *Export Profile*

**Rough Cut**
The first assembled edit, before detailed trimming, color, audio processing, or titles. A rough cut establishes structure — the order of scenes and approximate timing — but is not polished. `ff-auto-editor` produces a rough cut; `ff-rough-cut-review` evaluates it.

---

## S

**Signal Chain** (audio)
The sequence of processing stages applied to audio, in order. Order matters because each stage affects what subsequent stages receive. The correct signal chain for tutorial voice audio: recording → noise reduction → high-pass filter → EQ → compression → de-esser → loudness normalization → peak limiter. See Ch.10.

**Slug**
A URL-safe, lowercase, hyphenated identifier for a project or video. Derived from the title. Used as the project folder name and Obsidian note filename. Example: "Making a Walnut Cutting Board" → `making-a-walnut-cutting-board`.

**sRGB**
The standard color space for most monitors and web imagery. For video, BT.709 uses essentially the same color primaries as sRGB but a different gamma encoding for the transfer function. For tutorial creators, "set your project to BT.709" and "set your project to sRGB" produce similar results for SDR YouTube delivery.

---

## T

**Timeline**
The main editing workspace in an NLE. Clips are arranged on tracks in the timeline to form the edit. In Kdenlive, the timeline shows video tracks above the center line and audio tracks below. All editing operations (cuts, trims, transitions, effects) happen in the timeline.

**Transcript**
A text transcription of the spoken audio in a video, with timestamps. ForgeFrame uses Whisper (via `faster-whisper`) to generate transcripts from raw audio. Transcripts power the `ff-pacing-meter`, `ff-voiceover-fixer`, `ff-broll-whisperer`, `ff-rough-cut-review`, and `ff-social-clips` skills.

**True Peak** → See *dBTP*

---

## V

**VFR** (Variable Frame Rate)
Video where frames do not all occupy the same duration — the frame rate varies over time. Most phones and screen recorders produce VFR. Video editing engines (including MLT, which powers Kdenlive) assume CFR; VFR causes audio drift, sync problems, and incorrect cut positions. Always transcode phone and screen-capture footage to CFR before editing. See Ch.14, Ch.17.

**Vectorscope**
A video scope that displays color saturation and hue in a circular plot. Fully saturated colors appear at the edge of the circle; neutral gray appears at the center. Used to verify white balance (the plot should cluster near center for neutral scenes) and to check that skin tones fall on the "skin tone line" (a diagonal from bottom-left to upper-right). See Ch.09.

---

## W

**Waveform Monitor**
A video scope that displays the luma (brightness) values of a video signal across the frame, plotted as a function of horizontal position. Used to verify exposure (blacks should sit near 0 IRE, whites near 90-100 IRE) and to match exposure between shots during color correction. See Ch.09.

**White Balance**
The color temperature calibration of a video signal so that white objects appear neutral (not blue or orange). Incorrect white balance is the most common color problem in amateur tutorial footage. Fix it in the camera (manual WB), during color correction with Lift/Gamma/Gain adjustments, or with the `color_analyze` tool. See Ch.09.

**WPM** (Words Per Minute)
A measure of speaking pace. Tutorial narration should target 140-160 WPM for comfortable comprehension. Below 100 WPM sounds slow and viewers disengage. Above 180 WPM feels rushed. `ff-pacing-meter` measures WPM per 30-second segment. See Ch.11.

---

## X

**x264 / x265**
Open-source software encoders for H.264 and H.265 respectively. Used by FFmpeg and Kdenlive to encode delivery files. Quality is controlled by CRF value (see CRF). x265 produces smaller files at the same quality but is slower to encode than x264. See Ch.13.

---

## Y

**YAML Frontmatter**
Structured metadata at the top of a markdown file, delimited by `---`. Used in Obsidian vault notes and ForgeFrame skill files. The `ff-obsidian-video-note` skill writes and maintains frontmatter fields (title, slug, status, tags, etc.) while preserving any custom fields the user adds.
