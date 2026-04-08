# Kdenlive Introduction

> Source: https://docs.kdenlive.org/en/getting_started/introduction.html
> Saved: 2026-04-08

**Kdenlive** is an acronym for KDE **N**on-**Li**near **V**ideo **E**ditor.

Free software (GPL licensed) primarily aimed at Linux, also works on BSD and Windows. Through the MLT framework Kdenlive integrates many effects for video and audio processing. Features include a title editor, subtitling with AI-supported speech-to-text, nested timelines, and Glaxnimate animation support.

## Video editing features

- Multitrack editing with virtually unlimited video and audio tracks
- Split audio and video from a clip in multiple tracks
- 3-point editing
- Non-blocking rendering (keep working while rendering)
- Dozens of effects and transitions, saveable as custom effects
- Keyframeable effects with linear or smooth curves
- Color clips, text clips, image clips
- Automatic slideshow creation from image directories
- Configurable keyboard shortcuts, toolbars, interface layouts
- Audio and video scopes
- Proxy editing for 4K+ footage
- Themable interface supporting dark themes

## Supported formats and codecs

No need to import or convert footage prior to editing.

- **Low resolution:** DV (Raw/AVI), MPEG4-ASP/MP3, VOB (DVD), 4:3/16:9, PAL/NTSC
- **High/Ultra-high resolution:** MPEG-2, MP4, Matroska, WebM, Apple ProRes 422, H264/H265, HDV 720/1080
- **Modern codecs:** SNOW lossless, Ogg vorbis, LOTTIE/RAWR animations
- **Mixed sources:** Any resolution (auto-adapted), any frame rate (15-60+ fps)
- **Image formats:** PNG, GIF, JPEG, TGA, TIFF, SVG, WEBP, AVIF, HEIF, HEIC, JPEG XL
- **Export:** Any ffmpeg-supported format including DVD, MPEG-2, MP4 (HD/UHD/4K), Matroska-H264/H265, animated GIF, image sequences, lossless formats, video with alpha

## Technology Stack (Developer Info)

- Written in C++
- **Core Framework:** MLT for video editing functionality
- **GUI Framework:** Qt and KDE Frameworks 6
- **Additional Libraries:** frei0r (video effects), LADSPA (audio effects)
- Project files are XML based on MLT structures
- Development happens on KDE Invent (GitLab)
- Developer Matrix channel: `#kdenlive-dev:kde.org`

## Key references for ForgeFrame

- Build instructions: `dev-docs/build.md`
- Architecture: `dev-docs/architecture.md`
- Coding guidelines: `dev-docs/coding.md`
- MLT Introduction: `dev-docs/mlt-intro.md`
- Project file format: `community.kde.org/Kdenlive/Development/File_format`
