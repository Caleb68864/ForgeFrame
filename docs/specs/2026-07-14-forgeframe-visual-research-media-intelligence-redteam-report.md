---
type: redteam-report
generated: 2026-07-14
target: 2026-07-14-forgeframe-visual-research-media-intelligence.md
findings_count: 5
critical: 3
advisory: 2
patched: 5
---

# Red Team Review: 2026-07-14-forgeframe-visual-research-media-intelligence.md

9-role adversarial review of the master spec. All findings verified against the
filesystem before flagging. All 5 findings auto-patched; path validation re-run clean
(35 files, 12 sub-specs).

## CRITICAL Findings (3) — all patched

**C-1: Test & fixture paths pointed at the wrong root** (Developer, QA)
- Location: every sub-spec `Files (new)` test/fixture/evidence entry; SS-02/SS-10/SS-11 AC prose.
- Issue: paths used `workshop-video-brain/tests/…`, but tests live at repo-root `tests/`
  (`[tool.pytest.ini_options] testpaths=["tests"]` in root `pyproject.toml`; fixture is
  `tests/fixtures/media_generated/greenscreen_reporter_720.mp4`). Source paths under
  `workshop-video-brain/src/…` were correct; only tests are at root.
- Evidence: `find` located `./tests/unit`, `./tests/integration`,
  `./tests/fixtures/media_generated/greenscreen_reporter_720.mp4`; root `pyproject.toml`
  `pythonpath=["workshop-video-brain/src"]`.
- Fix applied: rewrote all `workshop-video-brain/tests/` → `tests/`.

**C-2: AC commands used the wrong working directory** (Developer, SRE)
- Location: every `[MECHANICAL]` AC.
- Issue: commands were `cd workshop-video-brain && uv run pytest …`, but uv/pytest run
  from repo root (root `pyproject.toml` governs; `forge-project.json` test_command is
  `uv run pytest tests/ -v`). The `cd` targeted a non-existent nested `tests/`.
- Fix applied: dropped `cd workshop-video-brain &&` from all pytest/python/uv-sync ACs.

**C-3: SS-12 edited the wrong `pyproject.toml`** (Data Steward, Developer)
- Location: SS-12 Files (modify) + ACs.
- Issue: optional-deps extra targeted `workshop-video-brain/pyproject.toml`, but `uv sync`
  installs from the root `pyproject.toml`; the extra would be invisible.
- Fix applied: retargeted SS-12 to root `pyproject.toml`; the tomllib AC now reads root.

## ADVISORY Findings (2) — patched

**A-1: Integration fixture alignment** (QA)
- Location: SS-04 / SS-10 / SS-11.
- Issue: the `sample.json` transcript fixture must contain a segment matching the
  integration query ("reporter on camera") within the video duration, or the E2E test
  resolves zero regions.
- Fix applied: added the constraint to SS-04 Decisions.

**A-2: FFmpeg timeout hygiene** (SRE)
- Location: SS-02 / SS-03.
- Issue: new adapters must keep the repo's `timeout=` + `TimeoutExpired` discipline
  (`CLAUDE.md`).
- Fix applied: added the requirement to SS-02 and SS-03 Decisions.

## Role Scorecards
Developer: 2 | QA: 2 | End User: 0 | Architect: 0 | Scope Realist: 0 | Security: 0 | SRE: 2 | Data: 1 | Product: 0

## Post-patch verification
- Path validation re-run: 35 files across 12 sub-specs resolve cleanly ✓.
- Source paths (`workshop-video-brain/src/…`) confirmed correct and unchanged.
- Modify targets (source files + root `pyproject.toml`) confirmed tracked.
