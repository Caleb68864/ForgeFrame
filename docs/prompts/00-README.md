# ForgeFrame fix and feature prompts

Self-contained task prompts for a smaller AI model. Do them **in file-name
order**: later prompts assume earlier ones are merged. Start a **new, empty
session for each prompt**. Hand the model this file plus the prompt file:

> Read `docs/prompts/00-README.md`, then do the task in
> `docs/prompts/NN-....md`. Report back when done.

Review the model's report and diff after each prompt, then commit it yourself
(or tell the model to commit) before starting the next.

## Order

| # | Prompt | Source | Needs |
|---|---|---|---|
| 01 | `01-kdenlive-differential-test.md` | roadmap "Kdenlive 26.08 fixes" step 1 | -- |
| 02 | `02-audio-on-insert.md` | step 2 | 01 |
| 03 | `03-effects-kdenlive-identity.md` | step 3 | 01 |
| 04 | `04-bin-clip-ids-and-ranges.md` | step 5 | 01 |
| 05 | `05-entry-ids-and-speed-variant.md` | step 5 | 04 |
| 06 | `06-gui-pass-and-hard-rules.md` | step 6 (**you** open Kdenlive) | 02-05 |
| 07 | `07-verify-file-validator.md` | step 7 (only once Kdenlive ships `--verify-file`) | 06 |
| 08 | `08-reliability-runtime-validation.md` | roadmap "Reliability" follow-up | -- |
| 10 | `10-pyscenedetect-engine.md` | expansion Phase 1 | -- |
| 11 | `11-pyscenedetect-tools.md` | Phase 1 | 10 |
| 12 | `12-auto-editor-silence.md` | Phase 2 | -- |
| 13 | `13-jump-cut-timeline-and-profiles.md` | Phase 2 | 02, 12 |
| 14 | `14-mlt-worker-and-load-check.md` | Phase 3 | -- |
| 15 | `15-mlt-thumbnails-and-progress.md` | Phase 3 | 14 |
| 16 | `16-mlt-service-registry.md` | Phase 3 | 14 |
| 17 | `17-undo-redo-and-batch.md` | Phase 4 (harvest) | -- |
| 18 | `18-melt-render-progress.md` | Phase 4 | -- |
| 19 | `19-applied-effect-editing.md` | Phase 4 | 03 |
| 20 | `20-trim-tools.md` | Phase 4 | 02 |
| 21 | `21-easing-and-camera-moves.md` | Phase 4 | 03 (effect ids) |
| 22 | `22-snapshot-diff.md` | Phase 4 | -- |
| 23 | `23-beat-sync.md` | Phase 4 | 20, 21 |
| 24 | `24-chain-per-placement-experiment.md` | Phase 4 | 05 |
| 30 | `30-media-foundation-trim-concat.md` | Phase 5 (bare-file foundation, trim, concat) | -- |
| 31 | `31-media-speed-rotate-convert-audio.md` | Phase 5 | 30 |
| 32 | `32-media-gif-thumbnail.md` | Phase 5 | 30 |
| 33 | `33-media-reframe-and-social-render.md` | Phase 5 | 30 |
| 34 | `34-audio-mix-music-and-fade-files.md` | Phase 5 | 30 |
| 35 | `35-audio-loudness-and-waveform-files.md` | Phase 5 | 30 (34 if present) |
| 36 | `36-transcribe-file.md` | Phase 5 | 30 |
| 37 | `37-subtitle-file-ops.md` | Phase 5 | 30, 36 |
| 38 | `38-text-based-editing.md` | Phase 5 | 02, 12, 13, 30, 36 |
| 39 | `39-image-file-tools.md` | Phase 5 | 30 |

Gaps in the numbering are deliberate (room to insert prompts). Prompt 06
may produce follow-up prompts numbered `09-...` for code changes the GUI
pass reveals; run those before 10.

Any prompt that writes a Kdenlive effect or filter (19, 21, 23, and any new timeline effect tool) must
use the effect-id resolver added by prompt 03: an unknown `kdenlive_id`
crashes `kdenlive --render`. Run 03 before them.

Background documents the prompts refer to:
- `CLAUDE.md` (repo root): mandatory conventions. Every prompt assumes it.
- `docs/plans/2026-04-08-feature-roadmap.md`: the "Next Step: Kdenlive 26.08
  Compatibility Fixes" section.
- `docs/plans/2026-10-13-media-mcp-expansion.md`: Phases 1-5.
- `docs/testing/2026-10-13-kdenlive-2608-differential.md`: the
  Kdenlive-vs-melt evidence.
- `vault/Research/Kdenlive Automation Architecture and Tool Pairing.md`.

## Shared rules (every prompt)

### Machine and shell
- Repo: `/home/caleb/Projects/ForgeFrame`, Linux (Arch), zsh.
- **Never use `cd`.** In this shell it runs `eza` and hangs. Use absolute paths
  and `git -C /home/caleb/Projects/ForgeFrame ...`.
- zsh does not word-split unquoted variables. Use arrays or literal arguments.
  A word starting with `=` (e.g. `echo ====`) is an error.
- Python runs through uv:
  `uv run --project /home/caleb/Projects/ForgeFrame <cmd>`.
  - The venv is CPython 3.12.
  - The system Python is 3.14. It is the only one with the MLT bindings
    (`import mlt7`).
- Anything that renders with melt needs a display: prefix the command with
  `xvfb-run -a`.
- Installed: ffmpeg, ffprobe, melt (MLT 7.42), Kdenlive 26.08.2
  (`kdenlive --render` works headless under `xvfb-run -a`), uv 0.13.
- `pytest-xdist` is NOT installed, so never pass `-n`.

### Tests
- Unit tests:
  `uv run --project /home/caleb/Projects/ForgeFrame pytest /home/caleb/Projects/ForgeFrame/tests/unit -q -p no:cacheprovider`
- Full suite (about 7 min):
  `xvfb-run -a uv run --project /home/caleb/Projects/ForgeFrame pytest /home/caleb/Projects/ForgeFrame/tests -q -p no:cacheprovider`
  - Baseline after commit `38fe0e1`: **4806 passed, 20 skipped**. The skips are
    host-specific fixtures and are expected.
  - Report the new numbers. Any new failure is yours to fix.
- Dead-code lint on the files you touched:
  `uvx ruff check --select F401,F841 <files>`. It must be clean.
- A test that shells out to ffmpeg, ffprobe, melt or kdenlive needs the
  matching `requires_*` mark from `tests/_testkit.py`.
- Every `melt ... -consumer null:` call needs `terminate_on_pause=1`.

### Code
- Follow the `CLAUDE.md` "Authoring a New MCP Tool" checklist:
  - logic goes in `edit_mcp/pipelines/` or `edit_mcp/adapters/`;
  - the tool is a thin shell in `edit_mcp/server/bundles/<x>.py` or
    `edit_mcp/server/tools/<x>.py`, with `@mcp.tool()` and then `@tool_guard`
    directly under it;
  - errors use the specific `server/errors.py` constructors;
  - results use the `_ok`/`_err` envelope;
  - a timeline-affecting tool needs an external melt render proof.
- New tools use the `clip_index` parameter name, not `clip`.
- Every blocking `subprocess` call needs `timeout=`, using the shared
  constants in `adapters/ffmpeg/runner.py`.
- Paths inside ffmpeg filtergraphs go through
  `pipelines/_common.escape_filter_path`. Use `os.devnull`, never
  `"/dev/null"`.
- Never write into `media/raw/` or `projects/source/`.
- Do not edit any `__init__.py` to register tools; discovery is automatic.
  Do not "fix" the intentional F401 re-export block in
  `adapters/kdenlive/patcher.py`.
- Optional Python dependencies:
  - add an extra to **both** `pyproject.toml` (root) and
    `workshop-video-brain/pyproject.toml`;
  - add a row to `app/doctor.py`;
  - use a lazy import with the `EngineUnavailable` pattern from
    `edit_mcp/pipelines/ai_mask` (`ENGINES`, `resolve_engine`);
  - add a `requires_<x>` skip mark in `tests/_testkit.py`, using
    `importlib.util.find_spec`.
- After adding or renaming tools or skills, regenerate `docs/capabilities.md`.
  Find the generator with `grep -rn "capabilities.md" /home/caleb/Projects/ForgeFrame/workshop-video-brain/src`.
- Document user-visible behaviour in the vault (`vault/wiki/` for Kdenlive or
  ffmpeg facts, the video-editing guide notes for tools).

### Scope discipline
- Do only what the prompt asks. If you find another bug, list it in the
  report; do not fix it.
- Do not commit unless the prompt says to.
- If a step's assumption turns out to be false (a file moved, a function was
  renamed, behaviour differs), stop and report what you found rather than
  improvising a large change.

### Report format (end of every task)
1. Files changed (one line each, saying what changed).
2. Test results: unit, full suite and ruff, with counts.
3. Verification numbers the prompt asked for (dB, PSNR, frame counts...).
4. Anything skipped, any assumption that was wrong, any bugs noticed.
