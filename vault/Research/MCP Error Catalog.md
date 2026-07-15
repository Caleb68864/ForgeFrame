---
title: MCP Error Catalog
date: 2026-07-03
type: reference
tags: [forgeframe, errors, reference]
---

# MCP Error Catalog

Every ForgeFrame MCP tool fails the same way: it returns a structured **error
dict**, never a raw traceback and never a fake success. This catalog is the
user-facing reference for those errors — what each one means, why it happens,
and exactly what to do next.

Every error dict has this shape:

```json
{
  "status": "error",
  "message": "<plain sentence: what broke, with the concrete subject>",
  "error_type": "<stable machine key, see taxonomy>",
  "suggestion": "<what to do next, in plain language, naming a real tool>",
  "cause": "<optional one-line underlying cause, never a traceback>",
  "path": "…", "given": "…", "valid_range": "…"   // optional echoed input
}
```

`status` is always present. `message` is always present. The rest are added when
they help. Read `suggestion` first — it tells you the fix.

---

## Error-type taxonomy

`error_type` is a stable machine key you can branch on. There are ten.

| `error_type` | Meaning | Typical causes | Remediation |
|---|---|---|---|
| `missing_file` | A path that had to exist doesn't. | Wrong path, typo, file moved/renamed, no working copy yet. | Check the path (it resolves under the workspace root unless absolute); create the missing artefact (e.g. `project_create_working_copy`). |
| `missing_binary` | A required external program isn't on `PATH`. | `melt`, `ffmpeg`, or `ffprobe` not installed. | Install the tool and make sure it's on `PATH` (message names it and how). |
| `missing_dependency` | A required Python package isn't importable. | Optional extra not installed (`rembg`, `opencv`, `faster-whisper`, numpy…). | Install it with the pip/uv command in the suggestion, or pick a lighter engine. |
| `invalid_input` | An argument is empty, the wrong type, or out of domain. | Blank required string, bad enum value, `duck_db` positive, non-finite float. | Re-read the argument description; pass a valid value (suggestion gives the shape). |
| `invalid_index` | A track/clip/angle index is outside what the project actually has. | Guessing an index; project has fewer tracks/clips than assumed. | Pass an index inside the stated range; use `project_summary` to see the real counts. |
| `bad_json_param` | A string parameter that must contain JSON didn't parse or had the wrong structure. | Hand-written JSON with a typo; wrong shape (object vs list). | Provide valid JSON in the shape shown by the example in the suggestion. |
| `corrupt_project` | A `.kdenlive` file couldn't be parsed. | Truncated/corrupt file, not actually a Kdenlive project, interrupted write. | Restore a snapshot (`snapshot_list` → `snapshot_restore`), or reopen and re-save in Kdenlive. |
| `media_unreadable` | A media file exists but can't be probed/decoded. | Truncated download, unsupported/exotic codec, audio-only where video is required. | Confirm the file plays and `ffprobe` can open it; re-export or re-ingest it. |
| `not_found` | A *named* thing (effect, profile, preset, cue, snapshot) doesn't exist. | Typo in a name; asking for something never created. | List the available items (`effect_list_common`, `render_list_profiles`, `snapshot_list`, `effect_stack_list`) and pick one. |
| `operation_failed` | An unexpected error escaped the tool. | A bug, or an external command failing for an unclassified reason. | Read `cause`; if it's not self-explanatory, report it — the full traceback is in the server log. |

Legacy/simple errors may omit `error_type`; they still carry `status` and a
plain `message`. New tooling should always set one.

---

## The ~15 errors you'll actually hit while editing

Each entry shows the **message** you'll see and the **fix**.

### 1. melt / ffmpeg not installed
- **Message:** `Required binary 'melt' was not found on PATH.` or `ffmpeg is not available on PATH.`
- **error_type:** `missing_binary`
- **Fix:** Install it. `melt`: `apt install melt` (Debian/Ubuntu) or `brew install mlt` (macOS). `ffmpeg`: your package manager (`sudo pacman -S ffmpeg`, `apt install ffmpeg`, `brew install ffmpeg`) or <https://ffmpeg.org/download.html>. Rendering, previews, proxies, audio processing, and transcription all need one of these.

### 2. No working copy yet
- **Message:** `No projects/working_copies/ directory found in this workspace.` or `No .kdenlive files found in projects/working_copies/`
- **error_type:** `missing_file`
- **Fix:** Run **`project_create_working_copy`** to make an editable copy of your project. ForgeFrame never edits the source project in place; all clip/effect/transition tools operate on a working copy.

### 3. Project file couldn't be parsed (corrupt project) + recovery
- **Message:** `Project file could not be parsed: <path>`
- **error_type:** `corrupt_project`
- **Fix:** The `.kdenlive` file is corrupt, truncated, or not a Kdenlive project. Recover it:
  1. `snapshot_list` — every mutating tool writes a snapshot before it changes anything.
  2. `snapshot_restore` with the id from just before things broke.
  Alternatively reopen and re-save the project in Kdenlive. Because ForgeFrame writes projects atomically (see *How tools fail*), a parse failure means an *older* file was already bad — not a half-written one from this session.

### 4. The clip's media moved or was renamed
- **Message:** `Source media not found: <path>` (or `Could not resolve the source media for clip N on track T.`)
- **error_type:** `missing_file`
- **Fix:** The file a clip points at is gone. Restore/rename it back, or re-ingest with `media_ingest`. Run **`project_validate`** to find every dangling media reference at once. `render_final` failures very often trace back to this.

### 5. Track / clip / angle index out of range
- **Message:** `track 7 out of range (project has 4 tracks)` or `clip_index 12 out of range (0-8).`
- **error_type:** `invalid_index`
- **Fix:** Pass an index inside the stated range (tracks and clips are 0-based). Run **`project_summary`** to see how many tracks and clips the project actually has. A negative index is also rejected — it would silently wrap to the last element.

### 6. Bad keyframe / params / points JSON
- **Message:** `Invalid keyframes JSON: <detail>` or `params must decode to a JSON object`
- **error_type:** `bad_json_param`
- **Fix:** Provide valid JSON in the shape the suggestion shows, e.g. keyframes `[{"frame": 0, "value": 1.0}]`, effect params `{"opacity": 0.5}`, polygon points `[[0, 0], [0.5, 0.5]]`. A trailing comma or single-quotes will trip the parser.

### 7. rembg / segmentation engine not installed (AI mask)
- **Message:** `<engine> is not installed …`
- **error_type:** `missing_dependency`
- **Fix:** Install the requested segmentation engine as shown in the message, **or pass `engine='rembg'`** — the lightest CPU/no-torch option. Heavier engines (SAM etc.) pull in torch.

### 8. opencv / tracker backend not installed (motion track)
- **Message:** `<backend> is not installed …`
- **error_type:** `missing_dependency`
- **Fix:** Install the tracker backend, or pass **`engine='opencv'`** after `pip install opencv-contrib-python-headless`.

### 9. faster-whisper not installed (transcription)
- **Message:** `faster-whisper is not installed.`
- **error_type:** `missing_dependency`
- **Fix:** `pip install faster-whisper` (or `uv add faster-whisper`), then run `transcript_generate` again.

### 10. No media to work on
- **Message:** `No video file found. Provide source or add files to media/raw/.` / `media/raw/ does not exist in this workspace: <path>`
- **error_type:** `invalid_input` / `missing_file`
- **Fix:** Pass `source` pointing at a file, or drop a clip into **`media/raw/`** so the tool picks it up automatically. Many tools auto-discover the newest file in `media/raw/`.

### 11. Refusing to overwrite media/raw
- **Message:** `Refusing to overwrite your original source in media/raw/; media/raw/ is read-only by design.`
- **error_type:** *(none / plain)*
- **Fix:** Pass a different `output_name`. `media/raw/` holds your originals and is never written to; processed output goes to `media/processed/`.

### 12. Snapshot couldn't be written before an edit
- **Message:** `Snapshot failed: <detail>`
- **error_type:** *(plain)*
- **Fix:** A safety snapshot must be written before a destructive edit. Make sure `projects/snapshots/` is writable (disk space, permissions), then retry. The edit was **not** applied.

### 13. Effect not in the generated catalog
- **Message:** `Effect service '<svc>' is not in the generated catalog.` / `The effect catalog has not been generated yet.`
- **error_type:** *(plain)* / `not_found`
- **Fix:** Regenerate it: `uv run workshop-video-brain catalog regenerate`. Use **`effect_list_common`** to see known effects, or `effect_info <name>` to check one.

### 14. Named thing not found (effect / profile / preset / snapshot)
- **Message:** `Effect not found: <name>. Try 'effect_list_common' for the registry.` / `Snapshot '<id>' not found …`
- **error_type:** `not_found` / `missing_file`
- **Fix:** List and pick a real one: `effect_list_common`, `render_list_profiles`, `effect_stack_list`, `snapshot_list`.

### 15. Vault / config not set up
- **Message:** `Vault root not configured.` / `Vault path not configured.` / `projects_root is not set in ~/.forgeframe/config.json.`
- **error_type:** *(plain)*
- **Fix:** Set `vault_root` in `forge-project.json` (or `personal_vault` in `~/.claude/forge.json`), set `WVB_VAULT_PATH`, or run `wvb init`. Needed for B-roll library, preset promotion, and vault notes.

### Bonus: a partial multi-step op failed
- **Message:** `partial failure after N filters: <detail>`
- **Fix:** Some steps applied before one failed. Restore the pre-op snapshot with **`snapshot_restore`** to return to a clean state, fix the offending input, and retry.

---

## How tools fail (the guarantees)

- **Every failure is a structured dict.** `status == "error"`, always with a
  human `message`. You never get a Python traceback in the payload and never a
  string that isn't JSON-shaped. Full tracebacks go to the server log
  (`workshop_video_brain.edit_mcp.tools`), not to you.
- **No fake successes.** A no-op precondition (empty timeline, nothing matched,
  no changes applied) returns a loud error or an explicit skipped-intents
  result — never a green "done" that did nothing.
- **Projects are never left half-written.** Mutating tools take a snapshot
  *before* they touch anything and write the project atomically. If a write
  fails midway, the on-disk project is still the previous good version, and a
  `corrupt_project` you hit later is always an *older* problem, not damage from
  the current call. Recovery is always `snapshot_list` → `snapshot_restore`.
- **`media/raw/` is read-only.** Originals are never modified or overwritten;
  derived output lands in `media/processed/`.
- **`cause` is one line.** When present it's `ExceptionType: first line` — safe
  to show, never the stack.
