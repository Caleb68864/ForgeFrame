---
type: redteam-report
generated: 2026-07-21
target: docs/specs/2026-07-21-visual-research-mcp-tools.md
findings_count: 7
critical: 3
advisory: 4
fixes_applied: 7
---

# Red Team Review: 2026-07-21-visual-research-mcp-tools.md

All 9 roles reviewed the spec (5 sub-specs, 17+ acceptance criteria). 3 CRITICAL and 4 ADVISORY findings; all 7 patched directly into the spec.

## CRITICAL Findings (3) — all fixed

**C-1: `research_run` signature could not satisfy its own AC** (QA Tester)
- Location: SS-04 scope vs. first [BEHAVIORAL] criterion
- Issue: AC required a time-window run but the signature had no range parameters.
- Fix applied: added `start_seconds`/`end_seconds`, mapped to `research_video(timestamp_ranges=[(start, end)])`.

**C-2: `selections` read by SS-04 but never written by SS-03** (Integration Architect)
- Location: SS-03 scope / SS-04 second [BEHAVIORAL] criterion
- Issue: cross-sub-spec contract mismatch — `select_from_handshake` never committed to persisting chosen IDs.
- Fix applied: SS-03 now states selections are persisted into `candidates.json` before export.

**C-3: unbounded `overwrite=True` was a destructive-path risk** (Security Auditor)
- Location: SS-04 criteria / Edge Cases
- Issue: replacing an arbitrary agent-supplied directory could delete non-research data; CLAUDE.md forbids touching `media/raw/`, `projects/source/`.
- Fix applied: overwrite honored only when the target contains `manifest.json`/`candidates.json` and never under protected dirs; otherwise `invalid_input` regardless of flag.

## ADVISORY Findings (4) — all fixed

- **A-1** (Developer): SS-02 promised a `score` that `TranscriptRepository.search` (unscored, `transcript_repository.py:21`) doesn't produce → dropped; results in transcript order.
- **A-2** (Developer): "SS-03's rehydration helpers" unnamed → committed public `load_handshake(candidates_dir) -> dict`.
- **A-3** (End User): `candidate_ids` plurality ambiguous → committed: list of one or more; each selected candidate becomes one capture.
- **A-4** (SRE): generate's output-dir collision unspecified → same refuse-unless-overwrite rule applied to `research_generate_candidates`.

## Role Scorecards
Developer: 2 | QA: 1 | End User: 1 | Architect: 1 | Scope Realist: 0 (no defer-rate history — expected) | Security: 1 | SRE: 1 | Data: 0 | Product: 0

## Construction-Site Check
0 findings — the registration seam is the existing `pkgutil.iter_modules` auto-discovery in `edit_mcp/server/tools/__init__.py` (concrete symbol + file), verified present.
