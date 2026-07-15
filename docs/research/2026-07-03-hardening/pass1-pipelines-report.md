# Hardening Pass 1 — Pipelines & Adapters (non-Kdenlive plumbing)

Scope: `edit_mcp/pipelines/` (~80 modules), `edit_mcp/adapters/{ffmpeg,render,stt,youtube}/`,
`workspace/` snapshot machinery. Excluded (sibling-owned): `adapters/kdenlive/`,
`tools_helpers.py`, `server/tools/`, `server/bundles/`, `errors.py`.

Layer rule applied: pure pipeline/adapter functions raise **typed, message-rich
exceptions** (gold standard: `ProjectParseError`, `EngineUnavailable`,
`TrackerUnavailable`); the tool layer converts them to the error-contract dict.
Nothing here returns error dicts.

## Baseline / final test numbers

- **Baseline (start of run):** 3836 passed, **56 failed**, 2 skipped. All 56
  failures in `test_serializer_bin.py` (16), `test_nle_operations.py` (4),
  `test_proxy_wiring.py` (4) + roundtrip cascades — a concurrent Kdenlive-
  serializer agent's in-flight work, entirely outside this domain.
- **Affected-area targeted run (my domain):** 542 passed, 0 failed
  (probe, probe_extended, proxy, whisper, youtube, render_executor,
  render_final, snapshot, title_cards, social_clips, publishing, stack_presets,
  new_project, broll_library, review_loop, silence, denoise, stabilize,
  loudnorm, ingest).
- **New tests:** `tests/unit/test_hardening_pipelines.py` — **20 tests, all green.**
- **Final full suite:** 3950 passed, 9 failed (transient). The 9 were a snapshot
  during a sibling authoring `test_integration/test_hardening_tools.py`; re-run
  in isolation → **all pass**. Residual genuine failures
  (`test_effect_presets::test_sr17_fade…` qtblend keyframes,
  `external/test_transition_renders`) are Kdenlive-effects / external-render
  domains — **not this domain, not caused by these changes.**

## Subprocess-runner hardening

Introduced typed exceptions in `adapters/ffmpeg/runner.py` (shared vocabulary):
`FFmpegNotFound` (binary missing, carries install hint), `FFmpegTimeout`
(names command + elapsed), `FFmpegCommandError` (nonzero exit, carries stderr
**tail**, ~10 lines, not full dump). Plus `_stderr_tail()` helper and a
`FFmpegResult.stderr_tail` property.

| Module | Change |
|---|---|
| `adapters/ffmpeg/runner.py` (**linchpin** — covers denoise, stabilize 2-pass vidstab, loudnorm, qc_check, rewind) | timeout param (default **3600s**); `FileNotFoundError`→`FFmpegNotFound`+hint; `TimeoutExpired`→`FFmpegTimeout`(elapsed); nonzero exit still returns `success=False` (command failure caller inspects) but now logs the stderr tail; `stderr_tail` property |
| `adapters/ffmpeg/probe.py` `probe_media` | timeout **120s**; missing input → `FileNotFoundError(path)`; ffprobe missing → `FFmpegNotFound`; `CalledProcessError`→`FFmpegCommandError` w/ tail+path |
| `adapters/ffmpeg/probe.py` `scan_directory` | now **re-raises** `FFmpegNotFound`/`FFmpegTimeout` (env error, not per-file) instead of swallowing into empty list; per-file media errors still best-effort+logged (documented) |
| `adapters/ffmpeg/probe.py` `measure_loudness` | `FileNotFoundError`/`TimeoutExpired` given specific WARNINGs; broad fallback retained (documented best-effort → `None`) but now logs the actual cause; unparseable-JSON narrowed+logged |
| `adapters/ffmpeg/proxy.py` `generate_proxy` | timeout **1800s**; missing source → `FileNotFoundError`; FNF/Timeout/CalledProcessError → typed w/ tail |
| `adapters/ffmpeg/silence.py` `detect_silence` | timeout **1800s**; FNF→`FFmpegNotFound`; Timeout→`FFmpegTimeout` |
| `adapters/stt/whisper_engine.py` `extract_audio` | timeout **1800s**; missing source → `FileNotFoundError`; FNF/Timeout/CalledProcessError → typed w/ tail. Documented that in-process `transcribe()` (faster-whisper/whisper libs) **cannot** take a subprocess timeout — extract_audio is the guarded step. |
| `adapters/render/executor.py` | already had timeout + FNF/Timeout handling (compliant); tightened redundant `except (FileNotFoundError, TimeoutExpired, Exception)` in codec probe into distinct logged handlers; FNF render message now carries an install hint; failure log switched from stderr **head** to **tail** |
| `pipelines/render_final.py` (final render) | added timeout **3600s**; FNF→`RuntimeError`+hint; Timeout→`TimeoutError`(named); nonzero exit message switched from stderr head to **tail** |
| `adapters/youtube/fetcher.py` | wrapped both `extract_info` calls (channel + single video); yt-dlp `DownloadError` et al. → `RuntimeError` naming the URL, cause type, and a network/URL suggestion (was raw traceback) |

Timeouts added where previously **none**: runner (3600), probe_media (120),
proxy (1800), silence (1800), whisper extract (1800), render_final (3600).

## Filesystem / media-raw write-guard audit

- `workspace/snapshot.py` `_assert_not_protected` correctly blocks
  `media/raw` and `projects/source` (exact match or prefix). `restore()` calls
  it before writing back; `create()` only writes under `projects/snapshots/`.
  **Verdict: guard is sound; no path can write into `media/raw`.** Added tests
  proving the guard blocks `media/raw` + `projects/source`, allows
  `media/processed`, and that `restore()` of a record pointing at `media/raw`
  raises and never creates the file.
- All `media/raw` references elsewhere are **reads only** (`ingest`,
  `replay_generator`, `scan_directory`). Processing pipelines (denoise,
  stabilize, silence_segment, ai_mask, motion_track) target `media/processed/`
  per their docstrings — confirmed.

## Swallow-pattern census

~50 `except…: pass|continue|return None/{}/[]` sites examined across pipelines +
adapters (grep + per-site read).

- **BUG-silent (hides real failure, degrades primary output) — 4 found, 4 fixed:**
  `title_cards.py:76` & `:78` (corrupt marker file / malformed marker →
  silently zero title cards), `social_clips.py:578` (unreadable transcript
  dropped from clip-finding), `publishing.py:67` (unreadable transcript dropped
  from description/tag corpus). All now narrowed to `(OSError, ValueError)` +
  WARNING naming the file.
- **LEGIT-needs-log (best-effort but silent) — fixed the high-value ones:**
  `new_project.py:41` (corrupt `~/.forgeframe/config.json` silently → `{}`),
  `broll_library.py:38` (corrupt config silently → no vault),
  `review_loop.py:163` (manifest read fail → fresh `uuid4()` that breaks
  render↔workspace correlation), `social_clips.py:588` (manifest title),
  `snapshot.py:124` (corrupt snapshot metadata skipped). Each now logs WARNING
  with path/cause and a docstring/comment noting best-effort intent.
- **LEGIT-already-logs / narrow-appropriate — ~30, left as compliant:** e.g.
  `scan_directory` per-file, `clip_search`/`clip_labeler`/`transcript_index`
  malformed-entry skips, `effect_catalog_gen` optional network/JSON,
  `review_loop` font-fallback + unlink cleanups (narrow `OSError`),
  `overlay_looks`/`image_overlay` optional-import fallbacks. These already log
  at WARNING/DEBUG or are narrow, documented best-effort paths.

## Weak-raise fixes

Pipelines were overwhelmingly strong already (nearly every `ValueError`/
`RuntimeError` interpolates the offending value + expected range). Only genuinely
weak ones fixed:

- `stack_presets.py:161` `"Markdown file has no YAML frontmatter block"` → now
  names the source file + expected block shape.
- `stack_presets.py:164` `"Frontmatter did not parse to a mapping"` → now names
  the file + actual parsed type (`got {type}`). Threaded a `source` arg through
  the two call sites.

## Top 5 defect patterns

1. **No subprocess timeout** on genuinely long-running ffmpeg work (the runner
   itself + render_final + proxy + silence + whisper extract) — a wedged process
   could hang the server forever. Fixed with generous ceilings.
2. **Binary-missing indistinguishable from command-failure** — a missing ffmpeg/
   ffprobe raised a raw `FileNotFoundError` (or was swallowed) instead of a
   typed, install-hinted error. Now `FFmpegNotFound` everywhere.
3. **Full stderr dumps instead of the diagnosable tail** — failure messages/logs
   pushed the whole ffmpeg log (or the useless head). Standardized on last ~10
   lines via `_stderr_tail`.
4. **Swallow-and-continue that degrades the primary output** — corrupt transcript/
   marker files silently produced empty results (title cards, clip candidates,
   descriptions). Now narrowed + logged.
5. **Silent config/manifest fallback** — corrupt `~/.forgeframe/config.json` or a
   missing workspace manifest silently swapped in defaults / a random id. Now
   logged loudly.

## Referred to sibling (tool-layer) agents

- Tool wrappers over these pipelines must map the new typed exceptions to the
  contract: `FFmpegNotFound`/yt-dlp import errors → `missing_binary` /
  `missing_dependency`; `FFmpegTimeout`/`TimeoutError` → `operation_failed`;
  `FileNotFoundError`(path) → `missing_file`; `FFmpegCommandError` /
  `probe` failures → `media_unreadable` / `operation_failed`. The `tool_guard`
  backstop already catches anything unmapped.
