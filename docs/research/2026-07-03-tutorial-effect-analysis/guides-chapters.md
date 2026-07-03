---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: project guides & YouTube chapters"
author: analysis agent
tags: [kdenlive-mcp, research, guides, chapters, publishing]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcript: "vault/Transcripts/Kdenlive Tutorials/2025 Kdenlive Tutorial - Using Guides to add YouTube Chapters.md"
---

# Guides → YouTube Chapters Tutorial → MCP Tool Surface Mapping

One tutorial analysed against the workshop-video-brain MCP surface, driving two
plan items: **§3 High "Project guides as first-class tools"** and **§3 Medium
"chapter export from guides"**. Unlike the compositing cluster, this workflow was
**buildable today** — the `Guide` model + `AddGuide` intent already existed and
just needed an MCP surface. This analysis documents the tutorial, the build, and
the one real blocker: our serializer writes a **legacy guide format that modern
Kdenlive does not read**.

Tutorial #22 in `vault/Research/Kdenlive Tutorial Landscape - Uncovered
Effects.md`. Note: the landscape table attributes this to *TJ Free*; the actual
downloaded video is **Victoriano de Jesus**, "2025 Kdenlive Tutorial - Using
Guides to add YouTube Chapters" (`LiKnPfPidKU`, 5:02, Kdenlive 24.12.3).

---

## Video — "Using Guides to add YouTube Chapters" (LiKnPfPidKU, 5:02)

### a) Technique breakdown

1. **[00:00]** Goal: add chapters to a video and carry them into YouTube on
   upload. Kdenlive 24.12.3 on Ubuntu 24.04; three 1080p/24fps clips from Pexels.
2. **[00:46]** Drag clips to the timeline (accept the 1080p24 profile switch).
   Guides are Kdenlive's built-in way to organise/annotate the timeline **and**
   can be exported as YouTube chapters. Enable the **Guides** toolbox via
   **View → Guides** (if unchecked you won't see the panel).
3. **[01:33]** Add a guide: move the **playhead**, right-click → **Add/Remove
   Guide** (shortcut **G**), type a label, OK. It appears in the Guides toolbox.
4. **[02:18]** Preferred workflow: navigate precisely with **Alt+Arrow** (jump to
   clip endpoints/cuts), press **G** at each cut, label them: *Intro*,
   *Chapter One*, *Chapter Two*, *End*. Guides render as colored markers on the
   timeline ruler.
5. **[03:07]** Clicking a guide jumps the playhead there. Guides have editable
   **categories** (colors) and their **position** can be fine-tuned by editing
   the guide.
6. **[03:54]** Export: **hamburger menu → Export** (Export Guides) → the dialog
   shows the **time codes + labels**; **Copy to Clipboard**.
7. **[03:54]** In YouTube Studio, paste the copied lines into the video
   **Description**; on save, YouTube auto-generates clickable chapters, provided
   the first entry is at **0:00**.

### b) Kdenlive features named

Guides / Guides toolbox (View → Guides); Add/Remove Guide (shortcut G); playhead
navigation (Alt+Arrow to clip endpoints); guide labels; guide categories
(colors); guide position editing; Export Guides dialog → "copy to clipboard";
YouTube Studio description chapters.

### c) Capability mapping

| Step | MCP tool | Status (before → after this work) | Notes |
|---|---|---|---|
| Add a guide at a timeline position | `guide_add(project_file, at_seconds, label, category=None)` | **missing → BUILT** | Model `Guide` + `AddGuide` intent existed; no tool. Now writes via `patch_project(AddGuide)`. |
| See all guides in a project | `guide_list(project_file)` | **missing → BUILT** | Returns frame + seconds + timecode + label + category. |
| Delete a guide (by time or label) | `guide_remove(project_file, at_seconds_or_label)` | **missing → BUILT** | Numeric arg matches by frame; string matches by label (case-insensitive). |
| Export guides as YouTube chapters | `publish_chapters(project_file_or_workspace, min_gap_seconds=10)` | **missing → BUILT** | Enforces 0:00-first + 10s-min rules; writes `reports/chapters.txt`; also pulls `chapter_candidate` markers. |
| Guides actually **show up in Kdenlive** | serializer | **BROKEN** | We write legacy top-level `<guide>` elements; modern Kdenlive reads the `docproperties/sequenceproperties.guides` JSON. See verdict below. |
| Editable guide **categories** (colors) | — | **partial** | We store `category` as a string and emit it as the `type` int in the docproperties JSON; the `guidesCategories` color palette is not modelled. |
| Guide **position** as timecode not frames | `publish_chapters` / `guide_list` | **exists** | Both surface `MM:SS`/`H:MM:SS` timecodes. |

---

## Guides-format discrepancy — VERDICT

**Our serializer writes a legacy format that Kdenlive 24.x/25.x does not read at
runtime.** Concretely:

- **What we write** (`adapters/kdenlive/serializer.py:332-339`, READ ONLY — not
  modified): top-level `<guide position="{frames}" comment="{label}"
  type="{category}"/>` elements as direct children of `<mlt>`.
- **What our parser reads** (`adapters/kdenlive/parser.py:127-138`): the same
  legacy `<guide>`/`<kdenlive:guide>` elements. So guides **round-trip cleanly
  through our own tools** (verified by the integration tests) — but only within
  our own ecosystem.
- **What real Kdenlive 24.x/25.x expects** (confirmed from KDE source —
  `markerlistmodel.cpp`, `kdenlivedoc.cpp`, `documentvalidator.cpp`): guides are
  a JSON array stored in a `<property>` element, keyed `pos` (frames, **not**
  seconds/timecode), `comment` (label), `type` (integer category index), plus an
  optional `duration` (frames). Location:
  - Modern multi-sequence docs (23.08+): `kdenlive:sequenceproperties.guides`
    as a property on that sequence's `<tractor>`.
  - Pre-sequence / legacy docs: `kdenlive:docproperties.guides` in the
    `<playlist id="main_bin">`.
  - The legacy top-level `<guide>` elements we emit are honoured **only** by a
    one-time upgrade path for documents with `version < 0.97`
    (`documentvalidator.cpp`) — after which Kdenlive rewrites them into the JSON
    property. A freshly-written 24.x/25.x project ignores them.
  - Categories are a **document-level** property `kdenlive:docproperties.
    guidesCategories` in `main_bin`: JSON objects `{index, comment, color}`
    (default install ships 9 categories, index 0–8).

**Consequence:** guides written by `guide_add`/`title_cards_generate` will **not
appear in a modern Kdenlive GUI** until the serializer emits the JSON property.
This is honest and documented, not silently broken.

**Mitigation shipped now:** the guides pipeline exposes
`guides_docproperties_json(project)` producing the exact JSON Kdenlive expects
(`[{"pos":<frames>,"comment":<label>,"type":<int>}]`), and both `guide_add` and
`guide_list` return it in their result payload (`docproperties_guides_json`). So
the data is available; only the serializer wiring is missing.

**Filed for the placement-fix agent (owns serializer.py):** in the Guides block
of `serialize_project`, in addition to (or instead of) the legacy `<guide>`
elements, write
`<property name="kdenlive:docproperties.guides">{guides_docproperties_json}</property>`
onto the `main_bin` playlist (and/or `kdenlive:sequenceproperties.guides` on the
active sequence tractor for multi-sequence docs), and add
`kdenlive:docproperties.guidesCategories` when non-default categories are used.
The pipeline function `pipelines/guides.guides_docproperties_json` produces the
value verbatim. Positions are **frames** = `round(seconds * fps)` — the same
convention `Guide.position` already uses, so no unit change is needed.

### Chapter-export format (Kdenlive's own)

Kdenlive's Export Guides dialog (`exportguidesdialog.cpp`) defaults to
`{{timecode}} {{comment}}` where the timecode uses **colons**, omits hours when
zero, and does **not** zero-pad minutes below an hour (`0:00`, `5:30`,
`1:05:30`). It shows a YouTube reminder when the default format is used:
(1) a chapter must start at 0:00, (2) at least three timestamps, (3) each chapter
≥ 10 seconds. `publish_chapters` mirrors these rules; it uses the slightly
stricter `MM:SS` (zero-padded minutes) form the plan spec requested (`00:00
Intro`), which YouTube also accepts.

---

## d) Built tools (this work)

New pure pipeline `edit_mcp/pipelines/guides.py` and new bundle
`edit_mcp/server/bundles/guides.py` (auto-discovered; snapshot-before-write;
`{"status": ...}` dicts). Patcher/serializer/tools.py/server.py **untouched**.

```
guide_add(project_file, at_seconds, label, category=None)
    -> add a guide via AddGuide + patch_project; snapshot; serialize.
guide_list(project_file)
    -> read-only; guides with frame + seconds + timecode + docproperties JSON.
guide_remove(project_file, at_seconds_or_label)
    -> numeric matches by frame, string by label (case-insensitive); snapshot.
publish_chapters(project_file_or_workspace, min_gap_seconds=10)
    -> collect guides (+ chapter_candidate markers from markers/*.json via
       publishing._read_chapters_from_workspace), enforce 0:00-first + min-gap,
       write reports/chapters.txt, return text + count + YouTube warnings.
```

Pure helpers (unit-tested in isolation): `seconds_to_frames`,
`frames_to_seconds`, `format_timestamp`, `add_guide`, `list_guides`,
`remove_guide`, `guides_docproperties_json`, `collect_project_guide_chapters`,
`merge_min_gap`, `prepare_chapters`, `format_chapter_lines`,
`youtube_chapter_warnings`.

### Design notes / decisions

- **Snapshot resolution:** the task's signatures take only `project_file` (no
  `workspace_path`), so the bundle derives the workspace root by walking up to
  the nearest `workspace.yaml`; if found, it snapshots before + after writing
  (consistent with the effect wrappers). Outside a workspace it still writes but
  skips snapshotting.
- **Chapter sourcing:** `publish_chapters` unions project guides with
  `chapter_candidate` markers, reusing `publishing._read_chapters_from_workspace`
  (no edit to publishing.py) so it dovetails with the existing publish_* tools —
  which also emit a `reports/publish/chapters.txt`. This tool writes the
  top-level `reports/chapters.txt` the plan item calls for.
- **min-gap merge = YouTube min-length rule:** consecutive chapters closer than
  `min_gap_seconds` are dropped (first always kept), which both de-noises marker
  spam and satisfies YouTube's 10s-minimum-chapter constraint.

---

## Raw summary

- **Workflow:** project guides ↔ YouTube chapters (organise timeline; export
  timecoded chapters into the YouTube description).
- **Built tools:** `guide_add`, `guide_list`, `guide_remove`,
  `publish_chapters` (module `edit_mcp/server/bundles/guides.py`; pure functions
  in `edit_mcp/pipelines/guides.py`).
- **Format discrepancy verdict:** our serializer emits **legacy top-level
  `<guide>` elements**, which **modern Kdenlive (24.x/25.x) ignores** at runtime
  — it reads `kdenlive:sequenceproperties.guides` (per-sequence tractor) or
  legacy `kdenlive:docproperties.guides` (main_bin) as JSON `{pos(frames),
  comment, type(int)}`, with categories in `kdenlive:docproperties.
  guidesCategories`. Guides written here round-trip through our own
  parser/serializer but will not display in a real Kdenlive GUI until the
  serializer writes the JSON property. `guides_docproperties_json()` produces the
  exact value; wiring it in is filed for the placement-fix agent (serializer
  owner).
- **Missing / not-modelled:** `guidesCategories` color palette (we carry only the
  category index); guide `duration` (range guides); per-sequence guide targeting
  for multi-sequence documents (single-tractor parser, plan §3 Low).
- **§1.1 relationship:** unlike the effect/compositing cluster, guides are
  **not** filter placement — they are document properties, so the §1.1
  root-vs-entry filter bug does not apply. The analogous bug here is the
  serializer's legacy-vs-JSON guide format (above), which is the guide-specific
  parallel and should land with the same serializer wave.
```
