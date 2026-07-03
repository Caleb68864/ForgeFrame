---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: real subtitle track + burn-in"
author: analysis agent
tags: [kdenlive-mcp, research, subtitles, whisper, burn-in]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcripts:
  - "vault/Transcripts/Kdenlive Tutorials/Speech to Text in Kdenlive - How to Configure Whisper for Subtitles in 5 Minutes.md"
  - "vault/Transcripts/Kdenlive Tutorials/How to Set Up Speech-to-Text in Kdenlive (Whisper AI Tutorial).md"
---

# Whisper Subtitles → Real Subtitle Track → MCP Tool Surface Mapping

Drives **§3 High "Real subtitle track"**: subtitles land as SRT files in
`reports/`; nothing attaches them to the project, no styling, no burn-in. This
analysis verifies *how modern Kdenlive (24/25/26) stores a subtitle track in the
project*, against the KDE source, then documents the build. Unlike the guides
cluster (a document-property discrepancy), the subtitle work turned out to be
**render-provable headless** — melt applies the same subtitle filter Kdenlive
attaches, so the attach is not GUI-only.

Two tutorials analysed (Whisper speech-to-text → subtitles):
- *Photolearningism*, "Speech to Text in Kdenlive" (`hoc_cmwptl0`, 6:46,
  Kdenlive ~23.x) — the original speech-recognition feature; Project → Subtitles
  → Speech Recognition on a timeline zone produces a subtitle track.
- *Resolve4u*, "How to Set Up Speech-to-Text in Kdenlive (Whisper AI Tutorial)"
  (`hBdrewHR9Gs`, 25:55, **Kdenlive 25.0.4.1**) — dependency install on Windows,
  then Edit Subtitle tool → Speech Recognition → a subtitle track appears; the
  tutorial then **styles** it (subtitle style: bold, text colour red) and notes
  "in the next class we will learn how to customize subtitle." Confirms the
  25.x workflow: subtitle track + per-style colour/weight, editable inline.

---

## How modern Kdenlive stores subtitles — VERDICT (verified against KDE source)

Confirmed from `src/bin/model/subtitlemodel.cpp` and `src/doc/kdenlivedoc.cpp`
(kdenlive master, invent.kde.org) and cross-checked against a live `melt 7.40`
(bundled with the local Kdenlive **26.04.2**). Subtitles are **three linked
pieces**: a sidecar file, a timeline-tractor filter, and document/sequence
properties.

### 1. Sidecar file — ASS

- Internal storage format is **ASS** (Advanced SubStation Alpha). SRT/VTT/SBV are
  **import-only**; on save Kdenlive writes `.ass`
  (`bool assFormat = outFile.endsWith(".ass");`).
- Path is derived from the project file: `subTitlePath(timelineUuid, ix, ...)`
  builds `QStringLiteral("%1.ass").arg(info.fileName())` — i.e. for
  `project.kdenlive` the primary sidecar is `project.kdenlive.ass` next to it,
  with per-track indices appended for multiple subtitle tracks.

### 2. Timeline filter — `avfilter.subtitles` on the tractor

Kdenlive attaches an MLT filter to the **main timeline tractor**
(`m_timeline->tractor()->attach(*m_subtitleFilter)`), created as
`Mlt::Filter(profile, "avfilter.subtitles")`. Properties it carries:

| property | value | purpose |
|---|---|---|
| `mlt_service` | `avfilter.subtitles` | libass renderer (FFmpeg `subtitles` filter) |
| `av.filename` | path to the `.ass` (or `.srt`) sidecar | the subtitle source |
| `av.force_style` | ASS style-override string | live styling from the GUI |
| `av.alpha` | `1` | process alpha so text composites over video |
| `internal_added` | `237` | Kdenlive-managed-filter marker |
| `disable` | `0`/`1` | show/hide the track |
| `kdenlive:locked` | lock state | GUI lock |

`av.force_style` is a comma-separated libass override list, e.g.
`FontSize=48,PrimaryColour=&H0000FFFF,Outline=2` — colours in ASS **ABGR**
`&HAABBGGRR` order (alpha `00` = opaque).

### 3. Document / sequence properties

- `kdenlive:activeSubtitleIndex` — active subtitle track index, default `"0"`,
  read via `getSequenceProperty(uuid, "kdenlive:activeSubtitleIndex", "0")`, so
  it is a **sequence** (tractor) property in multi-sequence 23.08+ docs.
- The subtitle-track list is serialised by `subtitlesFilesToJson()` as a JSON
  **array of objects** `{"name":<str>, "id":<int>, "file":<path>}` (read back via
  `multiSubtitlePath(timelineUuid) → QMap<pair<int,QString>,QString>`). It is
  stored on the sequence tractor (`kdenlive:sequenceproperties.subtitlesList`)
  and, for pre-sequence/legacy docs, the `kdenlive:docproperties.*` equivalent on
  `main_bin` — the same doc-vs-sequence split the guides work documented. (The
  exact literal key was not quotable from the excerpts fetched; we emit it on
  **both** main_bin docproperties and the tractor sequenceproperties, mirroring
  how the guides serializer hedges, so whichever a given Kdenlive build reads is
  present.)

Categories/style palettes are stored inside the `.ass` `[V4+ Styles]` section
(not a separate doc property like guidesCategories).

### melt capability check (this machine, `melt 7.40.0`, Kdenlive 26.04.2)

- `melt -query filters` lists **`avfilter.subtitles`** (libass) **and** a native
  Meltytech **`subtitle`** filter (`resource` = SRT path) and a `subtitle_feed`
  producer.
- `melt -query "filter=avfilter.subtitles"` → schema present; params `av.filename`,
  `av.force_style`, `av.alpha`, `av.charenc`, `av.original_size`, ...

---

## Headless render proof (the important finding)

The plan hedged that subtitle properties "may be Kdenlive-app-rendered" and thus
invisible to melt. **That is false for `avfilter.subtitles`.** A hand-built MLT
project (grey `color:` background + `avfilter.subtitles av.filename=sub.srt` on
the tractor), rendered with `melt proj.mlt in=50 out=50 -consumer avformat:png`:

| render | frame luma mean | stdev | max | reading |
|---|---|---|---|---|
| control (no filter) | 70.0 | **0.00** | 70 | solid grey, no text |
| default subtitle | 70.2 | **8.5** | **244** | white text pixels present |
| styled (`FontSize=48,PrimaryColour=&H0000FFFF,Outline=2`) | 72.2 | **25.05** | 232 | larger text, R/G≫B → yellow |

So the **attach path is render-provable**, not GUI-only: melt applies the exact
filter Kdenlive attaches, and `av.force_style` (size / ABGR colour / outline) is
honoured. This is stronger than the guides outcome (which is GUI-only), and it is
what the external oracle suite now asserts.

The burn-in path (`ffmpeg -vf subtitles=`/`ass=`) is the belt-and-suspenders
render guarantee — it bakes pixels into a delivered file regardless of any
project-format drift.

---

## Capability mapping

| Step | MCP tool | Status (before → after) | Notes |
|---|---|---|---|
| Generate SRT from transcript | `subtitles_generate(workspace_path)` | existed | writes `reports/{stem}.srt` |
| List exported SRTs | `subtitles_export(workspace_path)` | existed | `reports/*.srt` |
| **Attach an SRT as a real project subtitle track** | `subtitles_attach(workspace_path, project_file, srt_path="", style=None)` | **missing → BUILT** | default srt = latest `reports/*.srt`; converts SRT→ASS (style baked); writes `{project}.ass` sidecar; adds `avfilter.subtitles` on tractor + `subtitlesList`/`activeSubtitleIndex` props; melt-render-proven |
| **Burn subtitles into a delivered file** | `subtitles_burn_in(workspace_path, project_file_or_media, srt_path, style=None, output_name="")` | **missing → BUILT** | ffmpeg `subtitles`/`ass` filter → `media/processed/`; renders project via melt first if a `.kdenlive` is passed; pixel-proven |
| Subtitle **styling** (font/size/colour/outline/position) | `style=` param on both tools | **missing → BUILT** | SubtitleStyle → ASS `[V4+ Styles] Default` line (portable) |
| `AddSubtitleRegion` intent degrading to a guide | (unchanged) | pre-existing limitation | superseded by the real track; left as-is |
| Multiple subtitle tracks / per-sequence targeting | — | partial | model supports a list; tools attach one track (index appended) |

---

## Built artifacts (this work)

- **Model** `core/models/kdenlive.py`: new `SubtitleTrack{id,name,file,style}`
  and `KdenliveProject.subtitles: list[SubtitleTrack]`.
- **Serializer** `adapters/kdenlive/serializer.py`: emits, per subtitle track, a
  nested `<filter mlt_service="avfilter.subtitles">` on the tractor
  (`av.filename`, `av.alpha=1`, `internal_added=237`, `disable=0`, `kdenlive:id`,
  optional `av.force_style`), plus `kdenlive:docproperties.subtitlesList` +
  `kdenlive:activeSubtitleIndex` on `main_bin` and
  `kdenlive:sequenceproperties.subtitlesList` on the tractor.
- **Parser** `adapters/kdenlive/parser.py`: reads the tractor
  `avfilter.subtitles` filter back into `KdenliveProject.subtitles` (rather than
  an opaque element), so attached tracks round-trip losslessly.
- **Pipeline** `pipelines/subtitle_track.py` (pure): `SubtitleStyle`,
  `hex_to_ass_color`, `build_ass_style_line`, `srt_to_ass`, `cues_to_ass`,
  `subtitles_list_json`, `attach_subtitle`, `latest_srt`, `ass_timestamp`.
- **Bundle** `server/bundles/subtitle_track.py`: `subtitles_attach`,
  `subtitles_burn_in` (auto-discovered; snapshot-before/after; `{"status":...}`).

### Round-trip / GUI honesty

- **Attach round-trips** through our parser/serializer (SubtitleTrack survives)
  **and** through `melt file.kdenlive -consumer null` (accepts) **and** renders
  the subtitle pixels headless (proven above). The sidecar `.ass` is written next
  to the project as `{project}.ass`, matching Kdenlive's own `subTitlePath`.
- The `subtitlesList` doc/sequence properties give the Kdenlive **GUI** its
  Subtitles panel entry; the `avfilter.subtitles` tractor filter gives the
  **render** its pixels — we emit both, so a user opening the project in Kdenlive
  24/25/26 sees a real subtitle track *and* an exported render carries it.

### Colour convention

Input hex `#RRGGBB` → ASS `&H00BBGGRR` (AABBGGRR, opaque). Verified end-to-end:
yellow `#FFFF00` → `&H0000FFFF` rendered yellow text by melt.

---

## Raw summary

- **Storage (verified):** sidecar **`.ass`** next to the project
  (`{project}.ass`); an **`avfilter.subtitles`** filter on the **timeline
  tractor** with `av.filename` (+ `av.force_style`, `av.alpha=1`,
  `internal_added=237`, `disable`, `kdenlive:locked`); doc/sequence properties
  **`subtitlesList`** (JSON array of `{name,id,file}`) and
  **`kdenlive:activeSubtitleIndex`** (default `"0"`).
- **Render proof:** melt applies `avfilter.subtitles` headless — attach is NOT
  GUI-only (control stdev 0.0 → subtitle stdev 8.5, styled 25.05).
- **Built tools:** `subtitles_attach`, `subtitles_burn_in` (+ SubtitleStyle,
  SRT→ASS, docproperties assembly).
- **Not-modelled:** multiple simultaneous subtitle tracks in one attach call;
  `guidesCategories`-style palettes; `kdenlive:locked` GUI lock; the exact
  doc-vs-sequence key literal (both emitted defensively).
