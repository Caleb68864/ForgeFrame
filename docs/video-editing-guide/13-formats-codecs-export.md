---
title: "Formats, Codecs & Export"
part: "Part V — Output"
chapter: 13
tags:
  - export
  - codecs
  - formats
  - rendering
  - ffmpeg
---

# Chapter 13: Formats, Codecs & Export

## Containers vs Codecs

A **container** is the box -- the file format that holds everything together (`.mp4`, `.mov`, `.mkv`). A **codec** is the language spoken inside that box -- the algorithm that compresses and decompresses the actual video and audio data (`H.264`, `ProRes`, `AAC`).

The same codec can live inside different containers, and the same container can hold different codecs. When someone says "I exported an MP4," they have told you the box but not the language. You need both pieces to understand what you are working with.

## Distribution Exports vs Mezzanine Masters

There are two fundamentally different reasons to render a file, and they call for different settings:

- **Distribution exports** are optimized for upload and playback. They use lossy compression tuned for a specific platform (YouTube, Vimeo, social media). Small file size and compatibility matter most.
- **Mezzanine masters** are optimized for editing, archiving, and handoff to other editors or colorists. They use high-quality intermediate codecs (ProRes, DNxHR) that preserve detail for further processing. File size is large, but quality headroom is the priority.

Always keep a mezzanine master if you might revisit the project. Distribution exports are disposable -- you can always re-render one from the master or the project file.

## Export Preset Comparison Table

| Target | Container | Video | Audio | Quality Targets | Notes |
|---|---|---|---|---|---|
| YouTube SDR 1080p (24/25/30) | MP4 | H.264 progressive, High Profile, 4:2:0 | AAC-LC 48 kHz | ~8 Mbps | BT.709 color; enable Fast Start |
| YouTube SDR 1080p (50/60) | MP4 | H.264 progressive, High Profile | AAC-LC 48 kHz | ~12 Mbps | Higher bitrate compensates for motion |
| YouTube SDR 4K (24/25/30) | MP4 | H.264 progressive, High Profile | AAC-LC 48 kHz | ~35--45 Mbps | BT.709 color; enable Fast Start |
| YouTube SDR 4K (50/60) | MP4 | H.264 progressive, High Profile | AAC-LC 48 kHz | ~53--68 Mbps | High bitrate; consider upload time |
| Vimeo standard web | MP4 | H.264 High Profile | AAC-LC 48 kHz, ~320 kb/s | CFR, VBR preferred | Vimeo re-encodes; quality in = quality out |
| Vimeo high-quality | MOV / MP4 | ProRes 422 HQ | AAC-LC 48 kHz | Near-lossless | Large files; use wired upload |
| Broadcast-style master (EU loudness) | MOV | ProRes 422 HQ or DNxHR HQX | PCM or high-quality AAC | -23 LUFS, max true peak -1 dBTP | EBU R 128 compliant; archival grade |

## Fast Start for MP4

YouTube recommends that the `moov` atom (the metadata index) sit at the front of the MP4 file so playback can begin before the entire file downloads. In FFmpeg this is the `-movflags +faststart` flag. In Kdenlive, you add this to your render profile parameters.

> [!important]
> Always enable Fast Start (`-movflags +faststart`) for any MP4 destined for web streaming. Without it, the player must download the entire file before it can begin playback, which causes buffering delays and can trigger platform re-processing.

## Color Space Defaults for SDR

BT.709 (Rec. 709) is the standard color space for SDR content. YouTube explicitly recommends BT.709 for standard dynamic range uploads, and virtually all consumer monitors and web players expect it.

Unless you are working in HDR (BT.2020 / PQ / HLG), default every project and every export to BT.709. Mixing color spaces without explicit conversion is one of the most common causes of washed-out or oversaturated exports.

## When to Use AV1 / HEVC

| Codec | Pros | Cons | Best For |
|---|---|---|---|
| **H.264** | Maximum compatibility, fast encode, universal platform support | Older compression efficiency | Default choice; safe for everything |
| **HEVC (H.265)** | ~30--50% better compression than H.264, good hardware decode support | Licensing complexity, not universally supported in browsers | When file size matters and you control the playback environment |
| **AV1** | Best compression efficiency, royalty-free, growing platform support | Very slow software encode, limited hardware encode support | Future-proofing; platforms that accept it (YouTube, Netflix) |

**Recommendation:** Start with H.264 for everything. Move to AV1 or HEVC only when you have a specific reason -- smaller file size requirements, platform recommendation, or hardware encoder support.

## Audio Loudness for Delivery

Loudness is measured in **LUFS** (Loudness Units relative to Full Scale) using the BS.1770 algorithm.

| Standard | Integrated Loudness | Max True Peak | Context |
|---|---|---|---|
| EBU R 128 | -23.0 LUFS | -1 dBTP | European broadcast |
| YouTube / web (common target) | -14 to -16 LUFS | -1 dBTP | No hard requirement; normalization applied |

- Always use a **BS.1770-compliant** loudness meter for measurement (Kdenlive's audio scopes or external tools like `ffmpeg -af loudnorm`).
- For broadcast delivery, EBU R 128 compliance is mandatory.
- For web delivery, target -14 LUFS for a loud, competitive mix or -16 LUFS for more dynamic range.

> [!info]
> Loudness targeting is a standards-based workflow for broadcast and professional delivery. YouTube and most web platforms apply their own normalization after upload -- they will turn you down if you are too loud, but they will **not** turn you up. Targeting -14 to -16 LUFS is a practical convention, not a universal web requirement.

## Understanding Kdenlive Render Profiles

Kdenlive render presets are thin wrappers around FFmpeg command-line instructions. Each profile defines the codec, container, bitrate, and flags that Kdenlive passes to FFmpeg at render time.

### Custom Profile Locations

| Platform | Path |
|---|---|
| Linux | `~/.local/share/kdenlive/export/customprofiles.xml` |
| Windows | `%LocalAppData%\kdenlive\export\customprofiles.xml` |

### Working with Custom Profiles

- Profiles are stored in XML format inside `customprofiles.xml`.
- You can create new profiles directly in Kdenlive's render dialog or by editing the XML file.
- Community-contributed profiles are downloadable from the [[https://store.kde.org|KDE Store]].

> [!warning]
> When importing third-party render profiles, you may see warnings about `profile` vs `mlt_profile` parameters. This is a naming inconsistency between MLT versions. If the profile renders correctly, the warning is cosmetic. If it fails, try renaming the parameter in the XML to match your Kdenlive version's expectation.

## ForgeFrame Render Profiles

ForgeFrame ships five named render profiles that cover the most common export scenarios. Each profile is a pre-tested FFmpeg parameter set. You never need to remember bitrate numbers or flag names -- just pick the right profile for your destination.

| Profile Name | Container | Video Codec | Video Bitrate | Audio | Key Flags | Use For |
|---|---|---|---|---|---|---|
| `youtube-1080p` | MP4 | H.264 High Profile | 8 Mbps VBR | AAC-LC 384 kbps 48 kHz | `-movflags +faststart`, `yuv420p` | YouTube uploads at 1080p/30fps |
| `youtube-4k` | MP4 | H.264 High Profile | 35 Mbps VBR | AAC-LC 384 kbps 48 kHz | `-movflags +faststart`, `yuv420p` | YouTube uploads at 4K/30fps |
| `vimeo-hq` | MOV | ProRes 422 HQ | Rate-controlled (~300 Mbps) | AAC-LC 320 kbps | `yuv422p10le` | Vimeo high-quality delivery |
| `master-prores` | MOV | ProRes 422 HQ | Rate-controlled | PCM 24-bit | `yuv422p10le` | Archival master, re-edits, colorist handoff |
| `master-dnxhr` | MOV | DNxHR HQX | Rate-controlled | PCM 24-bit | `yuv422p10le` | Broadcast delivery, Avid handoff |

> [!tip]
> When in doubt, start with `youtube-1080p`. It is the most widely compatible export for tutorial content. Use `master-prores` or `master-dnxhr` any time you want to keep a version for future re-editing -- you can always re-render a distribution export from the master, but you cannot recover quality from a compressed file.

### Listing and Using Profiles with ForgeFrame

> **ForgeFrame:** Use `/ff-render-list-profiles` to see all available render profiles and their settings:
>
> ```
> render_list_profiles
> ```
>
> This prints the full parameter set for each profile so you know exactly what FFmpeg flags will be used. You can also do this manually by opening Kdenlive's render dialog and reading the profile details in the sidebar.

> **ForgeFrame:** Use `/ff-render-final` to render your timeline using a named profile:
>
> ```
> render_final profile="youtube-1080p" output="my-tutorial-final.mp4"
> ```
>
> ForgeFrame validates that the output file is created, checks that `-movflags +faststart` is set for MP4 targets, and logs the render duration. You can also do this manually by selecting the profile in Kdenlive's render dialog and clicking **Render to File**.

## Fast Start and `movflags` Explained

The Fast Start section above mentions `-movflags +faststart`. Here is what it actually does and why it matters.

An MP4 file contains two major sections: the **media data** (the compressed video and audio frames) and the **`moov` atom** (the index that tells the player where every frame lives). By default, FFmpeg writes the `moov` atom at the **end** of the file, after all the media data.

This is a problem for streaming:

```
Without Fast Start:  [media data .............. 500MB] [moov atom -- tiny]
                      ← player must download ALL of this → ↑ then it can start
```

With `-movflags +faststart`, FFmpeg rewrites the file after encoding to move the `moov` atom to the front:

```
With Fast Start:     [moov atom -- tiny] [media data .............. 500MB]
                      ↑ player reads this  → can start playing immediately
```

**Why this matters for YouTube:** YouTube re-encodes every upload, but it still needs to read your file's metadata before it can queue the transcode. Files without Fast Start can trigger longer processing times or re-upload prompts on slow connections.

**The practical rule:** Always use `-movflags +faststart` for any MP4 going to a web platform. The ForgeFrame `youtube-1080p` and `youtube-4k` profiles include it automatically.

## What Comes Next

Once you have exported your file, the next step is quality control before upload. See **Chapter 14: Quality Control** for the pre-publish checklist and automated QC checks that catch problems before your viewers do.
