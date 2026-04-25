# ForgeFrame -- Workshop Video Brain

## Conventions

### Skill Naming
All skills MUST be prefixed with `ff-` (e.g., `ff-video-idea-to-outline`, not `video-idea-to-outline`). This ensures all ForgeFrame skills group together in the `/` autocomplete menu.

### Project Structure
- Plugin marketplace root: `.claude-plugin/marketplace.json`
- Plugin directory: `workshop-video-brain/`
- Skills: `workshop-video-brain/skills/ff-*/SKILL.md`
- Python source: `workshop-video-brain/src/workshop_video_brain/`
- Tests: `tests/unit/`, `tests/integration/`

### Safety Rules
- Never overwrite files in `media/raw/` or `projects/source/`
- Always create snapshots before writing project files
- Obsidian section boundaries: `<!-- wvb:section:name -->` ... `<!-- /wvb:section:name -->`
- Frontmatter updates merge, never overwrite unrelated keys

### Testing
- Run all tests: `uv run pytest tests/ -v`
- Python 3.12+ required

## Kdenlive XML serialization

The `.kdenlive` files this project produces target **Kdenlive 25.x / MLT 7.x**. The format is much stricter than a flat MLT XML — getting it wrong yields silent "Project corrupted. Clip ... not found in project bin" errors.

Detailed notes (one concept per page) live in `vault/wiki/`:
- `kdenlive-25-document-shape.md` — full structural contract
- `kdenlive-uuid-vs-control-uuid.md` — the most important trap (cost 3 iteration rounds)
- `kdenlive-twin-chain-pattern.md` — every avformat clip needs two `<chain>` elements
- `kdenlive-per-track-tractor-pattern.md` — per-track tractor + audio filter wiring
- `kdenlive-bin-loader-source-pointers.md` — exact Kdenlive C++ files/lines for load checks
- `golden-fixture-testing.md` — testing strategy without launching Kdenlive

### Hard rules (read before editing the serializer)

1. **`kdenlive:uuid` belongs ONLY on the main sequence tractor.** Putting it on a `<chain>` or `<producer>` makes Kdenlive's bin loader skip the entry. Use `kdenlive:control_uuid` for media instead.
2. **Every avformat media file emits two `<chain>` elements** — a timeline twin (referenced by playlist entries) and a bin twin with `kdenlive:kextractor=1` (referenced by `main_bin`). They share `kdenlive:control_uuid` and `kdenlive:id`.
3. **Each track is its own `<tractor>`** wrapping a content playlist plus an empty `*_kdpair` playlist. Audio track tractors carry `volume`/`panner`/`audiolevel` filters with `internal_added=237`.
4. **Profile names must be canonical** when they exist (`atsc_1080p_2997` for 1920×1080 @ 30000/1001). Anonymous names trigger a "non standard framerate" warning.
5. **`<entry>` `out` attribute on `main_bin` references must be `length-1`**, not `0`. Zero-span entries are rejected.
6. **Resource paths use forward slashes** even on Windows. Backslashes confuse Kdenlive's bin loader.

### Files

- Serializer: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/serializer.py`
- Parser (handles legacy + v25 shapes): `.../kdenlive/parser.py`
- Patcher (seeds chain properties on clip insert): `.../kdenlive/patcher.py`
- Reference fixture: `tests/fixtures/kdenlive_references/single_clip_kdenlive_native.kdenlive`
- Structural test: `tests/unit/test_kdenlive_v25_shape.py`
- End-to-end smoke: `tests/integration/test_v25_kdenlive_smoke.py`

### When Kdenlive rejects a file

1. Copy the **exact** error message from Kdenlive's dialog.
2. Grep the [KDE/kdenlive source](https://invent.kde.org/multimedia/kdenlive) for the literal English text — it's in an `i18n(...)` call.
3. Read the function emitting the error to find the precise condition.
4. Compare your output's relevant element/property against the reference fixture.
5. Fix, run `tests/unit/test_kdenlive_v25_shape.py`, regenerate the smoke output, re-open in Kdenlive.

This loop is dramatically faster than guessing.

## ffmpeg subprocess hygiene

All ffmpeg subprocess calls in `adapters/ffmpeg/*` and `adapters/stt/whisper_engine.py` must pass `timeout=` to `subprocess.run`. Without timeouts, the MCP server blocks indefinitely on UHD proxy generation or Whisper transcription, and the client RPC times out. Existing timeouts: 600s for proxy/runner, 300s for whisper extraction and silence detection. Catch `subprocess.TimeoutExpired` and clean up partial outputs.
