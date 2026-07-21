# Converge Pass 7 — standard scan (spec-text drift angle)

- Mode: standard (fresh Explore subagent)
- Result: 1 gap → fixed in-pass
- Drift audit: all ten tool signatures MATCH the spec (params, defaults, no renames); docstring Args all accurate; candidates.json write matches schema v1 except one spec-internal contradiction:
- Gap: spec's schema sketch named `candidates[].quality_scores`, a field that doesn't exist on `FrameCandidate`. The spec's own governing clause ("the entry shape is the model's shape") makes the model canonical; renaming a model field would violate the spec's non-additive-change must-not. Fix: corrected the spec sketch to the real serialized fields (`metrics`, `metadata`). Code unchanged.
- Live re-runs this pass: `test_research_candidate_tools.py` + `test_research_tools_e2e.py` = 9 passed.
- Met%: 23/24 before fix; contradiction resolved in the reference.
- clean_streak: 0 (reset)
