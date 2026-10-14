# Kdenlive Automation Architecture and Tool Pairing

Stock Kdenlive has no scripting engine, plugin API or usable external control surface, so generating and patching `.kdenlive` / MLT XML and rendering with `melt` remains the right architecture for ForgeFrame's MCP server.

- **Date:** 2026-10-13
- **Method:** deep-research workflow (5 search angles, 21 sources fetched, 99 claims extracted, 25 verified by 3-vote adversarial check: 21 confirmed, 4 refuted)
- **Scope:** (1) XML manipulation vs. Kdenlive scripting/automation, (2) roadmap features, (3) tools that pair with Kdenlive + ffmpeg + whisper + Obsidian

## Decisions (2026-10-13)

| Item | Decision |
|---|---|
| Direct `.kdenlive` XML editing + `melt` render | **Keep** as the core architecture |
| PySceneDetect | **Build** (scene/cut detection for B-roll, chapters, selects) |
| auto-editor | **Build** (silence/motion rough-cut step; test its Kdenlive export against our shape rules) |
| MLT Python bindings (`python3-mlt`) | **Build** (render/preview/inspection layer alongside the serializer) |
| Harvest from `12bijaya/MCP_Server_Kdenlive` | **Do** — pull useful features/code (check licence first) |
| Broaden into a general media-editing MCP | **Goal** — raw video files, text, other media, not only Kdenlive projects |
| OpenTimelineIO | **Undecided** — revisit whether interchange with Resolve etc. is useful |
| WhisperX | **Not now** |
| Speaker diarization | **Not now** (solo creator) |

## 1. Architecture: XML manipulation vs. scripting

### Kdenlive has no scripting/plugin API (high confidence, 3-0)
- Python scripting API request [#2047](https://invent.kde.org/multimedia/kdenlive/-/work_items/2047) and "Standardized communication API" #2137 (Qt Remote Objects; framed as app-to-app interop with Shotcut/Glaxnimate) are both **open and unimplemented** (last updated 2026-03-25).
- MR !763 "Draft: Add initial DBus API for external automation" was **closed unmerged** in Nov 2025.
- Issue #1615 asks for a `--render` CLI flag on the main binary — there is no supported CLI render entry point.

### Stock D-Bus surface is too small (medium confidence, 2-1 / 3-0)
- The main window exposes ~6 `Q_SCRIPTABLE` slots, mostly for the render subprocess to report back (`setRenderingProgress`, `setRenderingFinished`, `addProjectClip`, `addTimelineClip`, `addEffect`, `scriptRender`). None reads the timeline, trims clips or sets parameters (checked against `mainwindow.h` in KDE LXR).
- Sources: [D-Ogi/mcp-kdenlive listing](https://glama.ai/mcp/servers/D-Ogi/mcp-kdenlive), [kdenlive MCP listing](https://glama.ai/mcp/servers/d26yen403c), [D-Ogi Kdenlive fork](https://github.com/D-Ogi/kdenlive).

### Existing Kdenlive MCP servers (medium confidence)
- **[D-Ogi/mcp-kdenlive](https://github.com/D-Ogi/mcp-kdenlive)** — live control over D-Bus (`org.kde.kdenlive-{PID}`), but **requires a patched Kdenlive fork** adding 108 `Q_SCRIPTABLE` methods.
- **[12bijaya/MCP_Server_Kdenlive](https://github.com/12bijaya/MCP_Server_Kdenlive)** — reads/writes `.kdenlive` XML directly and renders with `melt`; does "not remote-control a running Kdenlive window". **Same design as ForgeFrame**; the only approach that works on stock Kdenlive.
- Also seen: [Va1bhav512/kdenlive-mcp-server](https://glama.ai/mcp/servers/Va1bhav512/kdenlive-mcp-server) (not analysed).

### Kdenlive's own render path is melt/MLT (high confidence)
- `kdenlive_render` is an internal helper ([man page](https://www.mankier.com/1/kdenlive_render): "not meant to be called directly by users"). Delivery mode runs melt on MLT XML; preview chunks use the MLT library in-process (verified against current `renderer/kdenlive_render.cpp`). ffmpeg alone cannot render a `.kdenlive` project.

### Update 2026-10-13: Kdenlive 26.08 command-line options (tested locally)
The "no CLI render entry point" finding above is **outdated for Kdenlive 26.x**:
- `kdenlive --render [--render-preset P] [--render-async] project.kdenlive out.mp4`
  exists in 26.08.2. `main.cpp` loads the project headlessly
  (`Core::build(..., true)` + `pCore->initHeadless`), builds `RenderRequest` jobs
  and runs `kdenlive_render`. Works under `xvfb-run -a` (rc 0, correct
  frame count on ForgeFrame-generated projects).
- It is **not a validator**: a ForgeFrame project with its `main_bin` entry
  deliberately removed (the "clip not found in project bin" class of bug)
  still rendered with rc 0 and identical logs.
- Kdenlive `master` adds **`--verify-file`** ("Verify whether a Kdenlive project
  file is valid, print details, and exit"): headless load, then
  `KdenliveDoc::checkConsistency()`. It prints `SUCCESS: Project file is valid:`
  or `Verification failed: ...` and exits 0/1. Not in 26.08.2. When it ships,
  it is the ideal automated oracle for ForgeFrame's serializer (CI + a
  `project_validate` backend). Source: `src/main.cpp` on invent.kde.org master.

### Alternatives
- **OpenTimelineIO** (high confidence, 3-0): Kdenlive has **native C++ OTIO import/export since 25.04** ([release notes](https://kdenlive.org/news/releases/25.04.0/)); the old Python integration was removed and [`otio-kdenlive-adapter`](https://pypi.org/project/otio-kdenlive-adapter) is deprecated/unmaintained (0.0.3, Jan 2026). Kdenlive's OTIO export **drops effects, filters and transitions**, so OTIO can only be a secondary interchange layer (cut structure to/from Resolve), never the primary edit format. Transitions/mixes listed as WIP.
- **[otio-mlt-adapter](https://pypi.org/project/otio-mlt-adapter)**: write-only (`.mlt` for melt), cannot parse `.mlt`/`.kdenlive`, unmaintained (OTIO 0.12/0.13 era).
- **MLT Python bindings** ([`python3-mlt`](https://packages.debian.org/sid/python3-mlt), SWIG over mlt++, Debian 7.42.0 in sid): programmatic MLT build/render. Will **not** emit Kdenlive-specific structures (twin chains, `control_uuid`, `main_bin`), so they supplement render/preview/inspection but cannot replace the serializer.

### Takeaway
The 25.x-vs-26.04 shape breakage is the inherent cost of XML generation and no alternative avoids it. Invest in the validator and native-saved golden fixtures; resolve the 25.x vs 26.04 contract (see roadmap). Watch #2047 / #2137 — if one ships, consider a hybrid: live control for preview/review, XML generation as the source of truth.

## 2–3. Features and tool pairing

- **PySceneDetect** (high, 3-0): one `detect(path, ContentDetector())` call returns `(start, end)` `FrameTimecode` pairs ([API docs](https://www.scenedetect.com/docs/_sources/api.rst.txt)). Good for B-roll segmentation, chaptering, selects.
- **[auto-editor](https://github.com/wyattblue/auto-editor)** (high, 3-0): mature CLI that cuts mainly by audio loudness (optionally motion); `--export kdenlive` plus Premiere, Resolve, FCP, Shotcut, clip exports. No filler-word detection. Its `.kdenlive` output must be tested against our strict shape — may be better to consume its cut list instead.
- **[WhisperX](https://github.com/m-bain/whisperx)** (medium): wav2vec2 forced alignment for accurate word timestamps (useful for text-based editing / filler cuts). **Not** a faster-whisper drop-in (that claim was refuted 0-3). Whisper often omits "um/uh"; filler removal may need a verbatim model such as CrisperWhisper (unverified). Diarization via pyannote needs a HF token + gated model.
- **Diarization**: evidence supports keeping it deferred for a solo creator.

### Not covered by verified claims (hypotheses to research next)
Auto-reframe for vertical, caption burn-in, multicam sync by audio, Demucs (voice/noise separation), Gyroflow, OBS, yt-dlp, ComfyUI, Remotion, MoviePy, Blender, and other NLEs' scripting APIs (Resolve, Blender VSE, Shotcut, Olive). Most promising for workshop videos (judgement, unverified): multicam audio sync, caption burn-in from existing transcripts, Demucs for shop noise, auto-reframe on top of `ff-social-clips`.

## Refuted claims
- "Kdenlive plans a native C++ OTIO adapter" (#1916) — 0-3 (it already shipped in 25.04).
- "kdenlive-opentimelineio repo still in preparation" — 1-2.
- "otio-mlt-adapter supports transitions, nesting, gaps but not markers/effects/speed" — 0-3.
- "WhisperX uses faster-whisper, so it is a drop-in upgrade" — 0-3.

## Open questions
- Does auto-editor's `--export kdenlive` open cleanly in Kdenlive 25.x/26.04, or should ForgeFrame consume only its cut list (JSON / timeline v3)?
- How lossy is a round trip through Kdenlive's native OTIO (markers, guides, speed, mixes)? Is an OTIO export tool worth it?
- Which ASR handles verbatim fillers with word timestamps best: WhisperX, CrisperWhisper, or faster-whisper `word_timestamps`?
- If #2137 (QtRO) or a D-Bus automation API ships, adopt a live-preview hybrid?

## Caveats
D-Bus/MCP evidence leans on secondary MCP directory listings and single-author anecdotes (main points checked against primary repos and Kdenlive source). The `kdenlive_render` man page dates from 2008 (only the architectural conclusion was confirmed against current source). All findings are time-sensitive.

Related: [[kdenlive-25-document-shape]], [[kdenlive-bin-loader-source-pointers]], [[external-kdenlive-examples-survey]], [[golden-fixture-testing]]
