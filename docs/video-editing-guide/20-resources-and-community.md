---
title: "Resources and Community"
part: "Part VI — Reference"
chapter: 20
tags:
  - resources
  - tutorials
  - community
  - links
---

# Chapter 20: Resources and Community

## Official Kdenlive Documentation

The Kdenlive docs live on the KDE UserBase wiki. Bookmark these entry points:

| Page | Link | Description |
|------|------|-------------|
| Manual root | <https://userbase.kde.org/Kdenlive/Manual> | Top-level table of contents for the full manual. |
| Introduction | <https://userbase.kde.org/Kdenlive/Manual/Introduction> | Project philosophy, feature overview, and what's new. |
| Quick Start | <https://userbase.kde.org/Kdenlive/Manual/QuickStart> | First-project walkthrough: import, cut, export. |
| Tutorials index | <https://userbase.kde.org/Kdenlive/Manual/Tutorials> | Curated list of official and community tutorials. |
| Video Tutorials | <https://userbase.kde.org/Kdenlive/Manual/Tutorials#Video_Tutorials> | Embedded and linked video walkthroughs. |
| Written Tutorials | <https://userbase.kde.org/Kdenlive/Manual/Tutorials#Written_Tutorials> | Step-by-step text guides with screenshots. |
| Effects and Filters | <https://userbase.kde.org/Kdenlive/Manual/Effects> | How the effect stack works, keyframes, presets. |
| Video Effects list | <https://userbase.kde.org/Kdenlive/Manual/Effects/Video> | Per-effect documentation for every bundled video effect. |
| Rendering | <https://userbase.kde.org/Kdenlive/Manual/Rendering> | Render dialog, queue, and job management. |
| Render Profile Parameters | <https://userbase.kde.org/Kdenlive/Manual/Project_Menu/Render/Render_Profile_Parameters> | Deep dive into custom render profile syntax. |
| Download New Render Profiles | <https://userbase.kde.org/Kdenlive/Manual/Settings_Menu/Download_New_Render_Profiles> | How to install community-contributed render presets. |
| Subtitles | <https://userbase.kde.org/Kdenlive/Manual/Subtitles> | Built-in subtitle editor workflow. |
| Speech to Text | <https://userbase.kde.org/Kdenlive/Manual/Speech_to_Text> | Whisper/VOSK integration for automatic subtitling. |
| Project File Details | <https://userbase.kde.org/Kdenlive/Manual/Project_File_Details> | XML structure of `.kdenlive` files (useful for scripting). |
| Installation Troubleshooting | <https://userbase.kde.org/Kdenlive/Manual/Installation_Troubleshooting> | Common install problems and fixes. |
| Windows Issues | <https://userbase.kde.org/Kdenlive/Manual/Windows_Issues> | Windows-specific bugs and workarounds. |
| Credits and License | <https://userbase.kde.org/Kdenlive/Manual/Credits_and_License> | Licensing info and contributor credits. |

## Video Tutorials (Curated Channels)

These channels produce Kdenlive-focused or general open-source editing content that maps well to the concepts in this handbook.

| Channel | Focus | Why Useful | Kdenlive-Specific? |
|---------|-------|-----------|-------------------|
| **Nuxttux** | Kdenlive tutorials, beginner to intermediate | Clear, concise walkthroughs of core features. Good first stop. | Yes |
| **Victoriano de Jesus** | Kdenlive deep dives, effects, tips | Covers advanced effects and lesser-known features in detail. | Yes |
| **Arkengheist 2.0** | Kdenlive workflow and tips | Practical workflow-oriented tutorials with real project examples. | Yes |
| **Linuceum** | Kdenlive and Linux creative tools | Bridges Kdenlive with the broader Linux creative ecosystem. | Yes |
| **Open Source Bug** | Open-source video editing | Comparative tutorials across open-source NLEs; good perspective. | Partial |
| **Peter Thomson** | Kdenlive tutorials | Methodical, step-by-step approach suited for absolute beginners. | Yes |
| **Mint Visual** | Kdenlive and creative workflows | Visual storytelling focus with Kdenlive as the tool. | Yes |
| **TJ FREE** | Open-source creative tools | Broad coverage of FOSS creative software; Kdenlive is a regular topic. | Partial |
| **Geek Outdoors** | Linux desktop and creative apps | Covers Kdenlive in the context of a full Linux creative workstation. | Partial |
| **AllinItis** | Kdenlive tutorials and tips | Quick-hit tutorials on specific Kdenlive tasks and effects. | Yes |
| **Chris' Tutorials** | Video editing fundamentals | NLE-agnostic editing principles that transfer directly to Kdenlive. | No |
| **Tux Designer** | Linux design and video | Creative design workflows with Kdenlive and complementary FOSS tools. | Partial |

## Export and Codec References

### FFmpeg Encoding Guides

- **H.264**: <https://trac.ffmpeg.org/wiki/Encode/H.264> -- CRF, presets, tuning, and two-pass encoding.
- **H.265 (HEVC)**: <https://trac.ffmpeg.org/wiki/Encode/H.265> -- Same structure as H.264 guide, with HEVC-specific options.
- **AV1**: <https://trac.ffmpeg.org/wiki/Encode/AV1> -- SVT-AV1, libaom, and rav1e encoder options.
- **AAC**: <https://trac.ffmpeg.org/wiki/Encode/AAC> -- Audio encoding for web delivery.
- **Filters documentation**: <https://ffmpeg.org/ffmpeg-filters.html> -- Complete reference for every FFmpeg filter (video, audio, subtitle).

### Platform Upload Specs

- **YouTube recommended upload encoding settings**: <https://support.google.com/youtube/answer/1722171> -- Container, codec, bitrate, and colour space recommendations.
- **Vimeo compression guidelines**: <https://vimeo.com/help/compression> -- Vimeo's preferred delivery specs.

## Audio Standards

These standards define how loudness is measured and targeted for broadcast and streaming:

- **EBU R 128**: <https://tech.ebu.ch/docs/r/r128.pdf> -- European loudness normalisation standard (-23 LUFS integrated, with permitted deviation). Widely adopted by streaming platforms.
- **ITU-R BS.1770**: <https://www.itu.int/rec/R-REC-BS.1770> -- The measurement algorithm behind EBU R 128 and ATSC A/85. Defines how LUFS/LKFS values are calculated.

See Ch.10 (Audio Production) for practical application of these standards in Kdenlive.

## Color Correction Resources

These resources go deeper on color theory and practical correction workflows for video creators.

### Scope Reading and Fundamentals

- **Mixing Light — "Understanding Video Scopes"**: Practical video scope tutorials (waveform, vectorscope, parade, histogram) written for working colorists. Searchable archive at mixinglight.com.
- **Cullen Kelly — YouTube**: Free scope-reading tutorials and correction walkthroughs covering Resolve, but the concepts apply directly to any NLE including Kdenlive.
- **Alexis Van Hurkman — "Color Correction Handbook" (Peachpit)**: The definitive practical reference for video colorists. Covers scope reading, correction workflow, matching shots, and finishing. Assumes SDR/BT.709 workflow throughout.

### BT.709 and Color Space References

- **Rec. ITU-R BT.709**: <https://www.itu.int/rec/R-REC-BT.709> — The formal specification for HDTV color primaries, white point, and transfer characteristics. Authoritative but dense; useful if you need to understand what Kdenlive's color settings actually mean.
- **EBU Tech 3213**: The European Broadcasting Union's companion document defining sRGB/BT.709 compliance for production.

### LUT Resources

- **Free BT.709 correction LUTs**: Several colorists distribute free "technical" LUTs for log-to-rec709 conversion and white balance correction. Search for "free rec709 lut" on Mixing Light and Luts.tv.
- **Kdenlive LUT application**: Kdenlive supports `.cube` LUT files natively via the LUT effect in the effect stack. See Ch.09 for the correct application order (always after primary correction, never before).

## Audio Production Resources

These resources cover the practical audio processing concepts taught in Ch.10.

### Loudness and Standards

- **EBU R 128**: <https://tech.ebu.ch/docs/r/r128.pdf> — European loudness normalization standard. Defines integrated LUFS, true peak, and loudness range measurements that YouTube and all streaming platforms use.
- **ITU-R BS.1770**: <https://www.itu.int/rec/R-REC-BS.1770> — The measurement algorithm behind LUFS/LKFS. Defines how integrated loudness is calculated across different channel configurations.
- **YouTube loudness normalization**: YouTube targets -14 LUFS integrated. Content above this is turned down; content below this is turned up. Upload at -14 LUFS and the platform normalization leaves your mix untouched.

### Processing Guides

- **iZotope Learning (izotope.com/learn)**: Free tutorials on dynamics, EQ, noise reduction, and the complete vocal processing chain. Most tutorials use RX or Ozone but the concepts apply universally.
- **In The Mix — YouTube**: Practical mixing tutorials covering compression, EQ, and vocal processing. Clear explanations aimed at music producers but directly applicable to voice-over work.
- **Voice Over Herald — voiceoverherald.com**: Specifically focused on voice recording and processing for commercial and tutorial audio. Covers mic technique, gain staging, and noise floor management.

### FFmpeg Audio References

- **FFmpeg loudnorm filter**: <https://ffmpeg.org/ffmpeg-filters.html#loudnorm> — The filter used for EBU R 128 normalization. The `-print_format json` flag enables measurement-only mode without modifying the file.
- **FFmpeg afftdn (noise reduction)**: <https://ffmpeg.org/ffmpeg-filters.html#afftdn> — FFT-based noise reduction filter. Used internally by the `ff-audio-cleanup` noise reduction stage.

## Pacing and Retention Resources

These resources cover the viewer psychology and structural principles taught in Ch.11.

### Retention Data and Platform Behavior

- **YouTube Creator Academy (creatoracademy.youtube.com)**: Free official courses including audience retention analysis, analytics interpretation, and the "3 Cs" framework (consistency, content, community). Directly applicable to tutorial creators.
- **vidIQ and TubeBuddy blogs**: Both platforms publish regular analysis of YouTube algorithm changes and retention benchmarks. Useful for current data on average viewer retention curves by video length.
- **Derral Eves — "The YouTube Formula" (Wiley)**: Data-driven book on YouTube growth. Chapters on hook structure, retention curves, and watch-time optimization are directly applicable to tutorial content.

### Structural Patterns and Storytelling

- **Brandon Sanderson's "Sanderson's Laws" lectures**: Available free on YouTube (BYU courses). While focused on fantasy writing, his lecture on the "promise" concept directly parallels the viewer promise structure used in `ff-video-idea-to-outline`.
- **Walter Murch — "In the Blink of an Eye" (Silman-James Press)**: Short, readable book on the psychology of film editing. The chapter on why cuts work — and when they don't — applies directly to tutorial pacing.
- **Robert Cialdini — "Influence"**: The chapter on social proof and commitment explains why tutorial creators benefit from showing the finished result early (the "hook formula" covered in Ch.11).

### Speaking Pace Tools

- **Online WPM calculators**: Paste your script text and get word count; divide by target duration in minutes to get WPM. Target 140-160 WPM for tutorial content.
- **Descript**: Desktop app that shows per-sentence WPM in transcript view. Useful for identifying where your narration speeds up or slows down relative to the script.

## Professional Codec References

- **Apple ProRes white paper**: <https://www.apple.com/final-cut-pro/docs/Apple_ProRes_White_Paper.pdf> -- Bandwidth tables, quality tiers (Proxy through 4444 XQ), and design rationale.
- **Avid DNxHR bandwidth specifications**: <https://www.avid.com/alliance-partner-program/avid-dnxhr> -- Data rates per resolution and quality level (LB, SQ, HQ, HQX, 444).

## Community Support

### Bug Reports and Issue Tracking

- **KDE GitLab Issues** (primary): <https://invent.kde.org/multimedia/kdenlive/-/issues> -- File bugs, feature requests, and search existing issues here.
- **bugs.kde.org** (legacy Bugzilla): <https://bugs.kde.org/describecomponents.cgi?product=kdenlive> -- Older bug tracker; still contains historical context but new issues should go to GitLab.

### Discussion Forums

- **KDE Discuss (Kdenlive tag)**: <https://discuss.kde.org/tag/kdenlive> -- The active community forum. Ask questions, share tips, and browse answered threads.
- **r/kdenlive**: <https://www.reddit.com/r/kdenlive/> -- Subreddit with a mix of help requests, showcases, and news.

> [!info] Legacy KDE Forum
> The old KDE Forum (forum.kde.org) has been archived and is read-only. Use KDE Discuss for new conversations.

## CC0/CC-BY Asset Sources

Free assets for practice projects, prototyping, and learning. Always verify the license on the specific asset you download -- libraries may contain mixed licenses.

| Source | License | Best Use | How to Cite |
|--------|---------|----------|-------------|
| [Poly Haven](https://polyhaven.com) | CC0 1.0 | HDRIs, textures, 3D models for backgrounds and compositing. | No attribution required. Credit appreciated. |
| [Kenney](https://kenney.nl) | CC0 1.0 | 2D/3D game assets, UI elements, icons. Great for motion graphics practice. | No attribution required. Credit appreciated. |
| [Freesound](https://freesound.org) | CC0 / CC-BY | Sound effects, ambiences, foley. Check per-sound license. | CC-BY: "Sound by [author] from Freesound.org" |
| [OpenGameArt](https://opengameart.org) | CC0 / CC-BY | Sprites, tilesets, music. Mixed licenses per asset. | CC-BY: credit author and link to asset page. |
| [Blender Foundation -- Sintel](https://durian.blender.org) | CC BY 3.0 | Short film footage for editing practice and colour grading. | "Sintel (c) Blender Foundation, CC BY 3.0" |
| [Wikimedia Commons](https://commons.wikimedia.org) | Mixed (CC0, CC-BY, CC-BY-SA, PD) | Photos, diagrams, historical footage. Verify per file. | Follow license terms on the file's description page. |

See the [[examples/one-minute-tutorial/README|One-Minute Tutorial]] example project for a script that generates synthetic CC-free assets for practice.
