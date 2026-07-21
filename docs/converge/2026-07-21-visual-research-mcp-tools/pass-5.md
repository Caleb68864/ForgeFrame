# Converge Pass 5 — standard scan (edge cases + constraints angle)

- Mode: standard (fresh Explore subagent)
- Result: 2 gaps → both fixed in-pass
- Gaps:
  1. Bounded-overwrite protected-path guard untested — and `handshake._prepare_output_dir` (generate path) lacked the protected-path half entirely (only the export tools had it).
  2. VFR warning passthrough untested (adapter records `metadata["vfr_warning"]`; no test asserted it survives the envelope).
- Fixes:
  - `handshake._prepare_output_dir` now refuses overwrite under `media/raw`/`projects/source` (mirrors the shell guard).
  - 4 new tests: protected-path refusal via `research_run` (tool layer) and `generate_handshake` (pipeline layer); `is_vfr` present in probe envelope; monkeypatched VFR probe → `vfr_warning` in extract_frame envelope. All 4 pass; touched-file regression run 36 passed; scoped ruff clean.
- All 7 Constraints Must-Nots verified holding (incl. zero pyproject/uv.lock changes in diff, SCHEMA_VERSION=1 constant, no source-media mutation).
- Met%: 22/24 before fixes; both gaps closed and verified.
- clean_streak: 0 (reset)
