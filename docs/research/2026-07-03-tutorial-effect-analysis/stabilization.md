---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: video stabilization (vidstab)"
author: analysis agent
tags: [kdenlive-mcp, research, stabilization, vidstab, ffmpeg, fixing-footage]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_tutorial: "vault/Research/Kdenlive Tutorial Landscape - Uncovered Effects.md (row 18)"
source_transcript: "vault/Transcripts/Kdenlive Tutorials/Stabilizing Video easily with Vidstab - No Commandline thanks to kdenlive! (windows & linux).md"
video: https://www.youtube.com/watch?v=eo7HSqKsd70
---

# Stabilization Tutorial → MCP Tool Surface Mapping

Tutorial #18 in the Kdenlive landscape survey — *"Stabilizing Video easily with
Vidstab — No Commandline"* (Maebbie, 2020, ~4:45). Mapped against the
workshop-video-brain MCP surface (`edit_mcp/adapters/ffmpeg/`,
`edit_mcp/pipelines/`, `edit_mcp/server/tools.py`, `server/bundles/`) and the two
source specs that call for it:

- **Plan §3 Medium** (`docs/plans/2026-07-03-kdenlive-mcp-improvements.md`):
  *"Stabilization (vidstab), lens correction, motion tracking (opencv.tracker)
  wrappers — common workshop-footage needs."*
- **FFmpeg research** (`vault/Research/FFmpeg for Video Production Automation.md`):
  tool #10 `media_stabilize` — *"Two-pass `vidstabdetect`+`vidstabtransform`
  (with `deshake` fallback), `media/processed/` output."*

The tutorial is tagged **REINFORCE** — the capability was already scoped; this
note verifies it and ships the file-level route as `media_stabilize`.

## Two routes to stabilization

There are two independent ways to stabilize footage, and they are **not**
interchangeable. This note builds the second one.

| Route | Where it runs | Artifact | Automatable here? |
|---|---|---|---|
| **A. Kdenlive clip-job vidstab** | Inside the Kdenlive editor — right-click a bin clip → *Jobs* → *Stabilize* (the transcript's "no command line" workflow). Kdenlive shells out to `libvidstab` itself, runs the two passes, stores a `.trf` transforms file beside the media, and produces a **new stabilized child clip** in the project bin. | `<clip>.trf` + a stabilized producer referenced by `kdenlive:clip_type`/analysis; lives *in the project*, not a standalone media file. | **No (not here).** Would require writing Kdenlive's clip-job/analysis producer XML and driving the bin. Out of scope; the project's file-processing tools all operate on standalone media instead. |
| **B. File-level ffmpeg vidstab** (this build) | A standalone two-pass `ffmpeg` render outside any project, exactly like the audio `audio_enhance`/`audio_denoise` tools. | A fully-rendered stabilized file in `media/processed/`. | **Yes.** Shipped as `media_stabilize`. |

Route A is what the *video* demonstrates (clip job, audio-not-included caveat,
`.trf` beside the clip). Route B is what the **FFmpeg research + plan** actually
ask `media_stabilize` to be, and it fits the repo's existing
"fix footage → write to `media/processed/`" pattern (`_cfr`, `_proxy`)
one-to-one. We build B and document A as the editor-native alternative.

---

## Technique breakdown (from the tutorial, route A)

The transcript is an auto-translated German→English caption dump and is largely
garbled, but the demonstrated workflow is unambiguous and matches the standard
Kdenlive vidstab clip-job:

1. **[00:00]** Vidstab ships as a clip job in modern Kdenlive — no command line
   needed. (Older builds needed a separate `libvidstab`/transcode step.)
2. **[00:45]** Select a clip in the **project bin**; open the **clip jobs** menu.
3. **[01:32]** Choose **Stabilize** (vidstab). Kdenlive runs the two analysis +
   transform passes and adds a new stabilized clip.
4. **[02:20]** Caveat called out explicitly: the stabilized job clip **does not
   include audio by default** — you must right-click the clip and re-enable the
   audio stream (or use the original for sound).
5. **[03:10]** Drop the stabilized clip on the timeline; compare against the
   shaky original; export via the render dialog (H.264/MP4 discussed).

Kdenlive exposes the vidstab knobs (accuracy, shakiness, stepsize, mincontrast,
smoothing, zoom, optzoom, and the render codec) through the job's settings
dialog — the same parameters `vidstabdetect`/`vidstabtransform` accept.

### Route B recipe (what we automate)

From `vault/Research/FFmpeg for Video Production Automation.md` §"Two-pass
stabilization":

```bash
# Pass 1 — analyse motion → transforms.trf
ffmpeg -i shaky.mov -vf vidstabdetect=shakiness=6:result=transforms.trf -f null -
# Pass 2 — apply the smoothed transform + recover sharpness
ffmpeg -i shaky.mov -vf \
  vidstabtransform=input=transforms.trf:smoothing=30:zoom=0,unsharp=5:5:0.8 \
  -c:v libx264 -crf 18 -c:a copy stable.mp4
```

---

## Kdenlive features / ffmpeg filters named

Clip-job **Stabilize** (vidstab); the `libvidstab` `vidstabdetect` /
`vidstabtransform` pair; `.trf` transforms file; accuracy / shakiness /
smoothing / zoom parameters; audio-not-included-in-job caveat; render dialog
(H.264/MP4). Fallback (research): single-pass `deshake`.

## Capability mapping

| Step (route) | MCP tool | Status | Why |
|---|---|---|---|
| Two-pass vidstab → standalone stabilized file (B) | **`media_stabilize`** | **exists (new)** | Built here: `vidstabdetect` → `.trf` in a tempdir → `vidstabtransform` → `media/processed/`. |
| Single-pass fallback when `libvidstab` absent (B) | `media_stabilize` (auto) | **exists (new)** | Falls back to `deshake=edge=1`; result reports `method="deshake"` + a note. |
| Shakiness / smoothing / accuracy / zoom knobs | `media_stabilize(shakiness, smoothing, accuracy, zoom)` | exists (new) | Clamped to vidstab ranges (1–10 / 0–100 / 1–15 / −100–100). |
| Never overwrite `media/raw` source | `media_stabilize` | exists (new) | Writes `{stem}_stabilized{ext}` to `media/processed/`; refuses an `output_name` that resolves back onto the raw source. |
| Preserve audio through the render | `media_stabilize` (pass 2 `-c:a copy`) | exists (new) | Improves on route A, whose clip job drops audio. |
| Kdenlive clip-job stabilize (A) — bin job + `.trf` producer | — | **not built (out of scope)** | Would need clip-job/analysis producer XML in the project bin; no such primitive exists. |
| Lens correction | — | **missing** | Named alongside stabilization in plan §3 Medium; not built. |
| Motion tracking (`opencv.tracker`) | — | **missing** | Plan §3 Medium / §5; absent from the whole codebase (see `compositing-effects.md`). |

## Availability verdict (this machine)

`ffmpeg -filters | grep vidstab` →

```
vidstabdetect     V->V   Extract relative transformations, pass 1 of 2 …
vidstabtransform  V->V   Transform the frames, pass 2 of 2 …
```

**`libvidstab` IS present.** The integration test asserts `method == "vidstab"`
on this build and actually renders the two passes. The `deshake` fallback path
is still built and tested (`force_deshake=True`) so the tool degrades gracefully
on builds compiled without `--enable-libvidstab`.

## Bundle tool spec — `media_stabilize` (built)

```
media_stabilize(
  workspace_path: str,
  source: str = "",          # video in workspace; empty → latest in media/raw/
  shakiness: int = 5,        # vidstabdetect, 1–10
  smoothing: int = 15,       # vidstabtransform frames, 0–100
  accuracy: int = 15,        # vidstabdetect, 1–15
  zoom: int = 0,             # vidstabtransform %, −100–100
  output_name: str = "",     # default {stem}_stabilized{ext}
) -> dict   # {status, data:{input, output, method, params, steps_count, note?}}
```

Pure logic lives in `edit_mcp/pipelines/stabilize.py`
(`clamp_params`, `build_detect_filter`, `build_transform_filter`,
`build_deshake_filter`, `vidstab_available`, `stabilized_output_path`,
`stabilize_file`), executing via the shared
`adapters/ffmpeg/runner.run_ffmpeg`. Registration is in
`edit_mcp/server/bundles/stabilize.py` (auto-discovered by
`server/bundles/__init__.py`), mirroring the audio file-processing tools exactly
(workspace resolve → `media/raw` safety → `media/processed/` output →
`_ok`/`_err` result dict).

**No new primitives required** — this is a self-contained file-processing tool
on top of ffmpeg, unlike the compositing bundles which are blocked on
`motion_track` and the §1.1 filter-placement fix.

---

## Raw summary

- **Tutorial:** #18 *Stabilizing Video with Vidstab (no command line)*
  (eo7HSqKsd70, ~4:45, Maebbie 2020) — REINFORCE.
- **Effect name / tool:** `media_stabilize` (file-level two-pass vidstab).
- **Two routes:** (A) Kdenlive clip-job vidstab — in-editor bin job, writes
  `.trf`, drops audio — **not automated (out of scope)**; (B) file-level ffmpeg
  two-pass — **built**, writes to `media/processed/`.
- **Availability verdict:** `libvidstab` **present** on this machine →
  `method="vidstab"`; single-pass `deshake` fallback built + tested for builds
  without it.
- **Missing/adjacent (not built):** Kdenlive clip-job producer, lens correction,
  motion tracking (`opencv.tracker`).
- **Bundle tool:** `media_stabilize(workspace_path, source="", shakiness=5, smoothing=15, accuracy=15, zoom=0, output_name="")`.
- **No §1.1 dependency** — pure media processing, no project-XML filter placement.
