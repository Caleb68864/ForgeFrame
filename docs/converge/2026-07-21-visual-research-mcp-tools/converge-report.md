# Converge Report — visual-research-mcp-tools

**Outcome:** CONVERGED
**Passes used:** 16 / 20 (3 consecutive clean passes, the 3rd adversarial)
**Reference:** `docs/specs/2026-07-21-visual-research-mcp-tools.md`
**Base:** main · **Branch:** `2026/07/21-2028-caleb-feat-visual-research-mcp-tools`

## Met% per pass
| Pass | Mode | Result | Gaps found | Fixed |
|------|------|--------|-----------|-------|
| 1 | standard | 3 gaps | SS-03 docstring trips its own grep checks; full-suite gate; (Windows collection crash surfaced) | 3 |
| 2 | standard | CLEAN | — | — |
| 3 | standard | 1 gap | R2 selection logic in shell not pipeline | 1 |
| 4 | standard | CLEAN | (advisory: dup import) | 1 |
| 5 | standard | 2 gaps | protected-path guard missing on generate + untested; VFR passthrough untested | 2 |
| 6 | standard | CLEAN | — | — |
| 7 | standard | 1 gap | spec-internal schema sketch named nonexistent `quality_scores` | 1 |
| 8 | standard | CLEAN | — | — |
| 9 | standard | CLEAN | (scope/negative-space audit — no creep) | — |
| 10 | **adversarial** | 1 gap | **G1: unbounded overwrite in select's export path (data loss)** | 1 |
| 11 | standard | CLEAN | (G1 fix exploit-verified) | — |
| 12 | standard | CLEAN | — | — |
| 13 | **adversarial** | 1 gap | **schema_version never validated on load; empty candidate_ids accepted** | 2 |
| 14 | standard | CLEAN | — | — |
| 15 | standard | CLEAN | (doc-coherence audit — all 4 artifacts true) | — |
| 16 | **adversarial** | CLEAN | (hardening: equal-dir self-destruct) | 1 (post) |

Convergence achieved at pass 16 (passes 14–15 standard clean, 16 adversarial clean = 3 consecutive). The 3rd, adversarial, pass ran four verification modalities (full 53-test fresh run, 11 self-designed hostile tool-drives, cold-import reachability, scope/frozen-claim audit) and found zero spec gaps.

## What the adversarial passes caught (the value of the loop)
Two of the three real correctness/safety gaps were found ONLY by adversarial passes, not standard ones:
- **G1 (pass 10):** `select_from_handshake` did an unconditional `shutil.rmtree` on `overwrite=True` — proven by execution to delete a sentinel file under a `media/raw/` path while other tools correctly refused. The bounded-overwrite rule existed in the export tools but had been omitted from select's own export path.
- **Schema/empty (pass 13):** `load_handshake` never read back `schema_version` despite SS-03 attributing schema validation to it; a hand-edited v2 manifest exported successfully. Empty `candidate_ids` exported an empty package against the "one or more" contract.
- **Equal-dir self-destruct (pass 16, post-convergence):** `output_dir == candidates_dir` with overwrite would rmtree the live handshake state. Flagged as a hardening idea (literal overwrite bound was honored), fixed anyway as a real data-loss footgun.

## Residual gaps
None.

## Frozen (requires-human-review, environment-limited)
- **Full `uv run pytest tests/ -q` exits 0 on this Windows host** — 31 pre-existing failures, every one in a file byte-identical to `main` (ffmpeg/melt-dependent integration + command-shape unit tests sensitive to the local Windows environment). CI Linux is the green gate. Verified across passes by confirming no pre-existing source/test file differs from main except the accepted Windows `skipif` guard. The 53 research-family tests all pass on this host.

## Accepted exclusions (spec Out-of-Scope + operator)
Caching/resumability; vision/OCR providers; CLI changes; timeline/Kdenlive integration; `transcript_search` rename; an `output_dir` parameter for the `extract_frame_burst` adapter (adapter signature change — escalation trigger).

## Deferred hardening (recorded, not actioned — beyond the explicit contract)
- Corrupt/truncated `candidates.json` → generic `operation_failed` backstop (could be `invalid_input`).
- Missing candidate image at export → `ExportError` via backstop (could be a specific error).
- Duplicated `candidate_ids` → duplicate captures of the same frame.
- Half-open `research_run` ranges (start-only / end-only) → coherent empty captures rather than open-ended semantics.
