# AI Handoff Notes

Notes for any AI agent (or human developer) picking up this project. Covers
module boundaries, dangerous areas, key assumptions, extension ideas, and
known limitations.

---

## Module Boundaries

### `production_brain` vs. `edit_mcp`

These two subsystems are deliberately separated:

| Subsystem | Responsibility | Entry Point |
| --- | --- | --- |
| `production_brain` | Pre-production planning and note management. Content structuring, scripting, shot planning. Obsidian vault interaction. No video processing. | `production_brain/skills/`, `production_brain/notes/` |
| `edit_mcp` | Post-production automation. Media ingestion, transcription, marker generation, timeline building, Kdenlive project management, rendering. | `edit_mcp/pipelines/`, `edit_mcp/adapters/` |
| `workspace` | Workspace lifecycle: create, open, manifest I/O, snapshots. Used by both subsystems. | `workspace/manager.py`, `workspace/snapshot.py` |
| `server.py` | MCP server entry point. Imports the `server/tools` and `server/bundles` packages, which `pkgutil`-auto-discover their submodules so every `@mcp.tool()` registers on import. A new tool is a new file in either package -- no shared-file edit (see CLAUDE.md "Authoring a New MCP Tool"). 201 live tools. | `server.py` |
| `app/cli.py` | Click CLI. Mirrors MCP tool capabilities for command-line use. | `app/cli.py` |

**Rule (see [ADR 005](adr/005-production-brain-boundary.md) -- supersedes the old
two-way wall):** the layering is `core < edit_mcp.adapters < edit_mcp.pipelines <
production_brain.{skills,notes} < edit_mcp.server < app`. Concretely:
`production_brain` **may** import `edit_mcp.pipelines`/`adapters`/`core` (planning
consumes analysis) but **never** `edit_mcp.server`. `edit_mcp` **may** import
`production_brain` **only via function-local (lazy) imports** (the orchestration
escape hatch in `new_project`/`publishing`/`server/tools`), never at module level.
Enforced by `tests/unit/test_module_boundaries.py`.

---

## Dangerous Areas

### 1. Kdenlive XML Opaque Passthrough

**The rule:** Any XML element inside a `.kdenlive` file that the parser does not explicitly handle is stored as an `OpaqueElement` with its raw XML string intact. This is by design for round-trip safety.

**The danger:** 
- Do NOT strip opaque elements before serializing. Kdenlive stores its own metadata (fade effects, compositing settings, bin organization) as opaque XML.
- Do NOT attempt to "clean up" or deduplicate opaque elements without understanding their semantics.
- The serializer re-inserts opaques verbatim. If you modify `opaque_elements` list order, Kdenlive may not load the file correctly.

**Safe pattern:**
```python
patched = patch_project(original, intents)  # preserves opaques automatically
serialize_project(patched, output_path)      # re-inserts opaques verbatim
```

### 2. Obsidian Section Boundaries

The `<!-- wvb:section:name -->` / `<!-- /wvb:section:name -->` boundary pattern is used for idempotent section updates. 

**The dangers:**
- Never manually write or edit these boundaries in notes. The `updater.py` functions handle them.
- `update_section` **replaces** content between boundaries. `append_section` **adds** to existing content and is idempotent.
- If section boundaries are malformed (unbalanced tags), the updater will create a new section at the end of the file rather than crashing. This can create duplicate section wrappers.
- Re-running `append_section` with identical content is safe (idempotent). Changing content even slightly will add a duplicate.

### 3. Snapshot Before Writes

The serializer automatically creates a snapshot of any existing file before overwriting it. The patcher creates a snapshot before applying `AddTransition` intents.

**The danger:** Snapshots are stored in `projects/snapshots/`. On long projects this directory can grow large. There is no automatic cleanup. If disk space is a concern, periodically prune old snapshots.

**Never delete `projects/source/` or `media/raw/`** — these are protected paths. The snapshot manager enforces this via `_PROTECTED_PREFIXES`.

### 4. Ingest Idempotency

Ingest skips assets that already have a transcript JSON. This means:
- Deleting a transcript JSON and re-running ingest will re-transcribe (expected).
- The transcript JSON is the idempotency key — not the media file itself.
- If transcription produces a corrupt JSON, the file exists but is unreadable. Manually delete and re-run.

---

## Assumptions

1. **Single user, local Linux.** No multi-user support. File paths are assumed absolute and local. No network file systems tested.

2. **Kdenlive 25.12.** The `.kdenlive` XML format is derived from Kdenlive 25.12. Earlier versions use different element names for guides (`<kdenlive:guide>` vs `<guide>`). The parser handles both but the serializer always writes `<guide>`.

3. **FFmpeg on PATH.** The ingest pipeline calls `ffmpeg` as a subprocess. The path can be overridden via `WVB_FFMPEG_PATH` but defaults to `ffmpeg`.

4. **faster-whisper for STT.** The primary transcription backend. Falls back to `openai-whisper` if available. If neither is installed, transcription is skipped gracefully.

5. **Workspace = one project.** A workspace maps to exactly one `VideoProject`. There is no support for multi-project workspaces or shared media pools.

6. **25fps default.** All timeline calculations default to 25fps. Frame-accurate operations at other frame rates require passing the correct fps to profile/guide calculations.

7. **Transcript JSON format.** The transcript JSON is the `Transcript.to_json()` output (Pydantic model serialization). Do not write transcript JSON by hand — use `Transcript.from_json()` to read it.

---

## Extension Ideas

### High Value

- **Speaker diarization.** Integrate `pyannote.audio` or similar to identify individual speakers in transcripts. This would enable per-speaker markers and better chapter detection.

- **OTIO export.** Export timelines as [OpenTimelineIO](https://opentimelineio.readthedocs.io/) for use in Premiere, Resolve, Avid, etc. The `KdenliveProject` model already has enough structure for this.

- **Production Brain MCP.** The `production_brain` skills currently have no MCP tools. Adding `outline_generate`, `script_generate`, `shot_plan_generate` tools would expose planning to MCP clients.

- **Live Kdenlive bridge.** Kdenlive supports DBus automation. A bridge could watch for guide/marker changes in a running Kdenlive instance and sync them back to the workspace markers.

### Lower Priority

- **Diarization-aware markers.** Once diarization is available, mark speaker transitions and solo speaker segments for better clip selection.

- **YouTube chapter export.** Export guides as YouTube chapter timestamps (`0:00 Intro`, `1:32 Materials`, etc.).

- **Thumbnail suggestion.** Flag frames at high-confidence markers as thumbnail candidates.

- **B-roll matching.** Cross-reference `broll_candidate` markers against a local stock footage library.

---

## Known Limitations

1. **No GUI automation.** There is no way to automate actions within a running Kdenlive instance. All project generation is file-based.

2. **No multi-user support.** Workspace paths are absolute and local. No locking mechanism — concurrent access to a workspace is unsafe.

3. **No cloud STT.** Transcription requires a local Whisper installation. There is no integration with cloud speech-to-text services (AWS Transcribe, Google STT, etc.).

4. **Effect coverage is per-service, not general.** Effects, colour grades, compositing, masks and transitions *are* applied programmatically (the `bundles/` and `tools/` packages carry ~74 effect/mask/composite/clip tools). What is not general is the *service vocabulary*: Kdenlive's effect registry recognises most `avfilter.X` services but not all — `avfilter.crop`, `avfilter.curves` and `avfilter.boxblur` are silently dropped at load, and several services have silent gates (`avfilter.huesaturation`'s `av.strength`, `frei0r.curves`' numbered props 1-15). A new effect service must be verified against a real Kdenlive load, not assumed from an adjacent one. See CLAUDE.md "Hard rules" 11-13 and `vault/wiki/kdenlive-not-all-avfilter-shapes-registered.md`.

5. **Proxy policy is conservative.** The default proxy policy only generates proxies for files above 4K resolution. Very high-framerate files (120fps+) are not specifically handled.

6. **Whisper hallucinations.** faster-whisper occasionally hallucinates text, especially on silence or background noise. Markers generated from hallucinated text may not correspond to actual speech.

7. **English-centric marker keywords.** The default `MarkerConfig` rules use English keywords. Other languages require custom `MarkerRule` configurations.

8. **No render queue.** Render jobs are executed synchronously. Long renders block the process. A proper render queue with background workers is a future enhancement.

9. **No auth or sandboxing.** The MCP server has no authentication. It should only be run locally and trusted with local file access.

10. **melt exits 0 on footage it cannot open**, and the guard against that is a precondition with a deliberately narrow guarantee. melt does not fail when a producer's file is gone: it logs a warning, renders that clip as blank frames, and returns 0. Nothing downstream can tell that from a good render. `adapters/render/media_check` is the one implementation that closes it — it parses the XML about to be rendered and refuses, naming each absent file — and it is reached by every path that hands melt a *project*: `execute_render` (so every render and preview), `pipelines/render_final`, `bundles/subtitle_track`'s burn-in, and `pipelines/review_loop`'s project thumbnails. `adapters/kdenlive/validator.validate_project` answers the same question through the same code, so the advisory report and the hard refusal cannot disagree (`tests/unit/test_media_check_reconciled.py` is the case table that pins it).

    What it does **not** cover, by design or by omission:
    - Only producers whose `mlt_service` is a known file-backed service (`avformat`, `avformat-novalidate`, `qimage`, `pixbuf`, `timewarp`, `xml`) are checked. It is an allowlist, never a deny-list, because a timeline legitimately contains producers with no file at all (every Kdenlive project carries `producer_black`). A file-backed producer that somehow carries no `mlt_service` is therefore *not* checked — the price of never refusing a render that would have worked.
    - Remote resources (`http://`, `smb://`, …) and image sequences (`%04d`, `.all.`, `glob:`) are skipped: `Path.exists()` cannot settle either.
    - **File references that are not producer resources are not checked at all**: luma mattes (`pipelines/masked_wipes`, `pipelines/compositing`), the `shape` alpha mask, and the `av.filename` subtitle sidecar. Those still fail silently the way missing footage used to.
    - `pipelines/motion_track.run_melt_tracker` is handed one media file rather than a timeline, so it stats that file itself rather than using this module. Same reason, different check.

11. **A round-trip re-bases relative resources.** `parse_project` now keeps the `<mlt root>` attribute (`KdenliveProject.root`), and everything resolving media resolves against it — but `serialize_project` still writes the *output file's own directory* as `root` on every save. Importing a project whose resources are relative and saving it elsewhere therefore silently re-points them. Use absolute resources for anything this repo writes; treat a relative-resource import as read-mostly.
