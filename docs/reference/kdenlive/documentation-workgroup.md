# Kdenlive Documentation Workgroup

> Source: https://community.kde.org/Kdenlive/Workgroup/Documentation
> Saved: 2026-04-08

## Manual infrastructure

The Kdenlive Manual (docs.kdenlive.org) is based on Sphinx and lives in a git repository. Moved from the wiki in November 2021.

## Screenshot conventions

- Use Breeze Dark Theme (Settings > Color Theme > Breeze Dark)
- Use Breeze Icons (Settings > Force Breeze Icon Theme)
- Preferred format: lossless webp
- Animated gifs via ezgif.com for demonstrations
- Naming: `<chapter>-<kdenlive_feature>-<kdenlive_main_release>.webp`

## Key features documented (relevant to ForgeFrame)

### Timeline features
- Tools, Modes, Timeline Guides, Selection, Mixes
- Change Speed, Tracks, Master Track
- Composition Mode, Zoombar, Thumbnails, Snapping
- Align Audio, Remove Space

### Project features
- Project Settings, Project Notes
- Archive Project, Backup/Autosave
- Cache Management

### Media features
- Proxy Clips
- Subclips, Clip Guides
- Detect Scene Job, Speedchange Job, Stabilization Job

### Export/Import
- Rendering
- OpenTimelineIO
- DVD Wizard, Transcode Clip

### Audio
- Audio Mixer, Audio Spectrum

### Subtitles
- Subtitles feature
- Speech-to-Text (AI-supported)

### Effects
- Effect/Composition Stack
- Rotoscoping, LUT
- Scopes

## Technical references migrated

- MLT concepts and basic producers → `dev-docs/mlt-intro.md`
- Kdenlive project file format → `community.kde.org/Kdenlive/Development/File_format`
