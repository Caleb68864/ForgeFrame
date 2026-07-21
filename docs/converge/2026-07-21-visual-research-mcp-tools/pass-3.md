# Converge Pass 3 — standard scan (wiring/reachability + envelope fidelity angle)

- Mode: standard (fresh Explore subagent; live registry probe, shell code-read, SS-04 spot-run)
- Result: 1 gap → fixed in-pass
- Gap: R2 thin-shell purity — `_top_scored_candidate_ids` (~30 lines of FrameScorer selection logic) lived in `server/tools/research_package.py` instead of the pipeline layer, straining R2's "only new logic module is handshake.py".
- Fix: moved verbatim to `pipelines/visual_research/handshake.py` as public `top_scored_candidate_ids(manifest)`; shell now imports it. Verified: `test_research_package_tools.py` + `test_research_handshake.py` = 18 passed; scoped ruff clean.
- Everything else clean: 10/10 tools registered via live probe (211 total in registry); envelope fidelity (no bare dicts, no silent success, causes preserved via from_exception); selections written to disk BEFORE export (handshake.py select flow); bounded overwrite verified at both call sites.
- Flake note: `test_research_run_nonempty_dir_without_overwrite_is_invalid_input` failed once in a combined run immediately after the refactor, then passed in isolation AND in the same combined order twice — transient (suspected Windows file-lock during rmtree), not reproducible, not related to the refactor diff.
- Met% this pass: 23/24 before fix; fix verified.
- clean_streak: 0 (reset by the gap)
