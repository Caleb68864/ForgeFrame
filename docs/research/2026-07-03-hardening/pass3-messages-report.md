# Hardening Pass 3b — Error-message Quality Sweep

Date: 2026-07-03
Scope: STRING CONTENT ONLY (message/suggestion literals) in error paths across
`workshop-video-brain/src`. No control flow, signatures, `error_type` values, or
dict keys changed. Propagation behavior owned by the sibling agent.

## Sites reviewed

- **709** error call sites extracted via AST (`err`/`_err`/`invalid_input`/
  `missing_*`/`invalid_index`/`bad_json_param`/`corrupt_project`/`media_unreadable`/
  `not_found`/`operation_failed`) across `edit_mcp/server/{tools,bundles}` and
  `edit_mcp/pipelines`.
- Graded against the 4-point bar: (a) concrete subject interpolated, (b) actionable
  suggestion naming a real tool/command, (c) plain sentence / no internal jargon,
  (d) no divergent phrasing across tools for the same situation.
- Dominant defect at entry: **252** raw `err()`/`_err()` sites with a message but
  **no `suggestion`** (fails bar (b)). Plus a handful of jargon and family-drift cases.

## Fixed — count by defect class

| Defect class | Sites fixed | How |
|---|---|---|
| No suggestion (added actionable `suggestion=`) | ~150 | Converted bare `_err(msg)` → `err(msg, suggestion=…)` and enriched `err()` calls that lacked one. |
| Internal jargon in message ("playlist") | 3 | `transitions.py`, `clips_nle.py`: "no video playlist found" → "this project has no video track". |
| Family drift — missing source/media | ~14 | Normalized capitalization + one suggestion voice ("…resolves under the workspace root unless absolute"). |
| Family drift — no working copy | 4 | Unified to "Run project_create_working_copy first…" across `timeline_project`, `render`. |
| Family drift — missing binary (ffmpeg/melt/whisper) | 5 | Split inline hint into `suggestion`; consistent "install …" voice. |
| Family drift — media/raw write guard | 4 | Unified "…media/raw/ is read-only by design." + "Pass a different output_name…". |
| Family drift — snapshot write guard | ~8 | "Snapshot failed: <cause>" + "…projects/snapshots/ is writable…". |
| Family drift — missing catalog service | ~6 | "Effect service '<svc>' is not in the generated catalog." + regenerate hint. |
| Bad JSON (params/tags/points/hints/keyframes) | ~8 | Message states shape; suggestion carries a concrete JSON example. |
| Effect-wrapper generator (22 generated files) | 22 | Edited the generator template + regenerated in place; "Project file not found" now carries a working-copy suggestion. |
| No-op precondition ("no changes applied", "partial failure") | ~18 | Kept the concrete reason; added "each reason above says why… fix and retry / restore snapshot". |

**Total error sites edited: ~230** (message and/or suggestion). Remaining bare
`_err()` call sites: **3** — the `effect_info` not-found/empty/catalog paths that
tests assert by **exact dict** (`==`), deliberately left unchanged per the contract.

## Normalized families (one phrasing each, established as the house voice)

1. **Missing workspace / media/raw** — "media/raw/ does not exist in this workspace: <path>" + "Create media/raw/ and copy your source recordings into it…".
2. **Missing project / no working copy** — "Run project_create_working_copy first…".
3. **Missing source media** — "Source … not found: <path>" + "…resolves under the workspace root unless absolute."
4. **Bad JSON** — "<param> is not valid JSON" / "… must be a JSON <shape>" + example in suggestion.
5. **Missing binary** — "<name> is not available on PATH." + "Install …".
6. **Index out of range** — preserves the substring `out of range`; adds real counts + a `0-N` range + "Use project_summary…".
7. **media/raw write guard** — "…media/raw/ is read-only by design." + "Pass a different output_name…".
8. **Snapshot guard** — "Snapshot failed: <cause>" + "…projects/snapshots/ is writable…".

## Assertions updated (with justification)

Only where the new wording was strictly clearer; all others preserved by keeping
pinned substrings.

1. `tests/integration/test_stack_presets_mcp_tools.py::test_promote_no_vault_returns_err`
   — message shortened to "Vault root not configured."; the config keys
   `vault_root` / `personal_vault` moved into the actionable `suggestion`. Assertions
   for those two substrings retargeted from `message` to `suggestion`.
2. `tests/integration/test_clip_dupes_mcp_tool.py::TestSignatureMethod::test_gating_error_when_filter_absent`
   — the "phash" actionable alternative moved from `message` into `suggestion`
   (message now states only what's missing). Assertion for `phash` retargeted to
   `suggestion`. (`signature` substring still asserted on `message`, preserved.)

No `error_type` values, dict keys, control flow, or signatures were changed.

## Tests

- Baseline: **4159 passed, 1 skipped**.
- Per-batch: each edited file group's tests run green before moving on.
- Two transient failures in the first full run (`external`-marked
  `test_clip_place_render` render test and an order-sensitive
  `test_corrupt_project_is_named_by_every_downstream_tool`) **pass in isolation**;
  attributable to parallel/stateful flakiness, not the string edits. The one real
  break — the clip_dupes `phash` assertion — is fixed above.
- Final full suite: **4179 passed, 1 skipped** (`uv run pytest tests/ -q`). The
  +20 vs the 4159 baseline are propagation tests added concurrently by the sibling
  agent; all green. The first run's two flaky failures were confirmed clean on re-run.

## Deliverables

- User-facing catalog: `vault/Research/MCP Error Catalog.md`
  (taxonomy of all 10 `error_type`s; the ~15 most common concrete errors with exact
  message + fix; a "how tools fail" guarantees section).
- Developer style guide: appended to
  `docs/research/2026-07-03-hardening/error-contract.md` ("Message style guide" section).
