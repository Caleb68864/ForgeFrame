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
- `kdenlive-title-card-pattern.md` — editable titles (`kdenlivetitle` + `xmldata`)
- `kdenlive-cross-dissolve-pattern.md` — stacked-track dissolves; `a_track < b_track` always; direction via `reverse`
- `kdenlive-image-and-qtblend-pattern.md` — image producers + Ken Burns transform filter (entry-local keyframes)
- `kdenlive-clip-speed-pattern.md` — clip speed via timewarp producer (`PlaylistEntry.speed`)
- `kdenlive-bin-loader-source-pointers.md` — exact Kdenlive C++ files/lines for load checks
- `kdenlive-not-all-avfilter-shapes-registered.md` — `avfilter.crop`, `avfilter.curves`, `avfilter.boxblur` are NOT in Kdenlive's effect registry; substitute native MLT or frei0r equivalents
- `kdenlive-frei0r-curves-all-numbered-props.md` — `frei0r.curves` reads numbered props 1-15 at render time; setting only the ones referenced by `kdenlive:curve` flatlines the curve to white
- `kdenlive-color-producer-pattern.md` — MLT `color` producer needs `resource=0xRRGGBBAA` hex; named colours render as black
- `kdenlive-producer-length-must-cover-all-uses.md` — when one media producer is reused at multiple in-points (audio crossfade, multi-region selects), `length` must cover the largest out-point or Kdenlive silently drops the over-range entry
- `kdenlive-lumakey-threshold-tuning.md` — lumakey threshold must straddle a luma boundary actually present in the source clip
- `kdenlive-smoke-test-visible-values.md` — smoke parameter values must produce an unambiguously visible effect, not just a technically-correct subtle one
- `kdenlive-smoke-verification-checklist.md` — manual-review checklist for every smoke output (what to look for in Kdenlive 25.08.3)
- `golden-fixture-testing.md` — testing strategy without launching Kdenlive

### Hard rules (read before editing the serializer)

1. **`kdenlive:uuid` belongs ONLY on the main sequence tractor.** Putting it on a `<chain>` or `<producer>` makes Kdenlive's bin loader skip the entry. Use `kdenlive:control_uuid` for media instead. The main sequence carries *both* `kdenlive:uuid` and `kdenlive:control_uuid` (same value).
2. **Every avformat media file emits two `<chain>` elements** — a timeline twin (`mlt_service=avformat-novalidate`) referenced by playlist entries, and a bin twin (`mlt_service=avformat`, `kdenlive:kextractor=1`, `kdenlive:monitorPosition=0`) referenced by `main_bin`. They share `kdenlive:control_uuid` and `kdenlive:id`. Both twins carry `kdenlive:kextractor=1`.
3. **Each track is its own `<tractor>`** wrapping a content playlist plus an empty `*_kdpair` playlist. Audio track tractors carry `volume`/`panner`/`audiolevel` filters with `internal_added=237`.
4. **Profile names must be canonical** when they exist (`atsc_1080p_2997` for 1920×1080 @ 30000/1001). Anonymous names trigger a "non standard framerate" warning.
5. **`<entry>` `out` attribute on `main_bin` references must be `length-1`**, not `0`. Zero-span entries are rejected.
6. **Resource paths use forward slashes** even on Windows. Backslashes confuse Kdenlive's bin loader.
7. **Every timeline `<entry>` carries `<property name="kdenlive:id">N</property>`** matching the bin clip's integer id. Without it the timeline parser can't resolve the entry to its bin clip.
8. **The sequence's `<track producer="black_track">` has NO `hide` attribute.** Adding `hide="video"` makes Kdenlive consider the sequence unrecoverable.
9. **User clip `kdenlive:id` integers start at 4.** 2 is reserved for the "Sequences" bin folder, 3 for the project's main sequence; collisions corrupt the project.
10. **Title cards use `mlt_service=kdenlivetitle`** with an `xmldata` property holding a `<kdenlivetitle>` document; `kdenlive:clip_type=2` (not 6); `font=` must name a font installed on the host (Windows: `Segoe UI`, Linux: `DejaVu Sans`).
11. **Effect-prefix dispatch is not uniform.** Kdenlive's effect registry recognises *most* `avfilter.X` services but not all — `avfilter.crop`, `avfilter.curves`, and `avfilter.boxblur` are flagged as missing on load and removed. Substitute native MLT (`crop`, `box_blur`) or frei0r (`frei0r.curves`) equivalents. When in doubt, find the upstream `*.kdenlive` test fixture and copy the service id and full property set verbatim — do not assume an `avfilter.X` will work just because adjacent ones do.
12. **`avfilter.huesaturation` has a silent gate**: `av.strength` defaults to 0 and gates ALL hue/saturation/intensity output. Set `av.strength=1` explicitly or the filter loads, the panel displays your values, and playback shows zero effect.
13. **`frei0r.curves` reads numbered props 1-15 at render**, not the `kdenlive:curve` string. Setting only the props your curve string references (e.g. 8/9/10/11) flatlines the curve to white because the unset higher-numbered props are read as zeros. Copy ALL 15 numbered props verbatim from a working upstream reference.
14. **When a media producer is reused at multiple in-points** (audio crossfade, speed ramps, multi-region selects), override `producer.properties["length"]` to cover the maximum out-point of any referencing entry. Otherwise Kdenlive silently drops the over-range entry on load.

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

### Audio adapter rules (`adapters/ffmpeg/audio.py`)

1. **Every audio function must pass `-vn`** to `run_ffmpeg`. Without it, video-input -> audio-output (mp4 -> wav) fails because ffmpeg tries to copy the video stream into a container that can't hold it.
2. **ffmpeg filter syntax uses `=` between the filter name and its first option**, then `:` between subsequent options. `silenceremove=start_periods=1:start_duration=0.5` is correct; `silenceremove:start_periods=1:...` is a parse error.
3. **`normalize_audio` is single-pass loudnorm** and won't hit the LUFS target accurately (typically off by 2-4 LU). For broadcast-conformant normalization, the function needs a two-pass rewrite. See `vault/wiki/ffmpeg-audio-adapter-bugs.md`.

### Testing requirement

Any new ffmpeg adapter function MUST have an integration test in `tests/integration/test_audio_ffmpeg_smoke.py` (or analogous) that:
- Runs against a real fixture (audio fixtures live in `tests/fixtures/media_generated/`).
- Asserts the output exists and is non-empty.
- Where a parameter has a measurable target (LUFS, sample rate, duration), probes the output to confirm the target was hit -- "ffmpeg returned 0" is not sufficient.

The audio fixtures available today are `music_cinematic_short.mp3` (full-band stereo music) and `test_audio_with_silence.mp4` (mono with intentional silence gaps). `greenscreen_reporter_720.mp4` is video-only -- it has NO audio stream and cannot be used as an audio fixture.
