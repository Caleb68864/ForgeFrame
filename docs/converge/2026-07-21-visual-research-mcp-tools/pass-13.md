# Converge Pass 13 — ADVERSARIAL confirmation #2 (streak was 2)

- Mode: adversarial (fresh subagent, no prior context; ~25 hostile live tool-drives, state corruption, destructive-path hunt, 50-test fresh run, cold-import registry, scope audit)
- Result: 1 gap → fixed in-pass, plus one spec-anchored hardening item also fixed
- Gap G1: `load_handshake` never validated `schema_version` (SS-03 scope: "rehydrate + validate schema/fingerprint") — a hand-edited v2 manifest exported successfully. Fix: `SchemaVersionError` raised on mismatch; both shells map it to `invalid_input` with a re-generate suggestion.
- Also fixed (spec-anchored: "candidate_ids is a list of one or more IDs"): empty `candidate_ids` no longer exports an empty package — `EmptySelectionError` → `invalid_input`.
- Regression tests: 3 new (schema-v2 via select, schema-v2 via export, empty selection). Suites: 32 passed; scoped ruff clean.
- Hardening ideas recorded, NOT actioned (beyond explicit contract): corrupt/truncated candidates.json falls to `operation_failed` backstop (could be `invalid_input`); missing candidate image at export surfaces ExportError via backstop; duplicated candidate_ids yield duplicate captures; extract_frame default output path writes beside source (adapter design, operator-escalated for burst).
- Confirmed by execution: all hostile inputs produced coherent envelopes (no tracebacks/fake success beyond G1), fingerprint/unknown-id/second-select paths correct, tree stayed clean, no undeclared scope, frozen-R7 logic re-verified independently.
- clean_streak: 0 (reset)
