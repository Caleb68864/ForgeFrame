# Hardening Pass 2 — Kdenlive adapter (adversarial fault injection)

Date: 2026-07-03
Scope owned: `edit_mcp/adapters/kdenlive/{parser,serializer,validator,patcher_intents,effect_stack}.py`
plus new tests + fixtures. Did NOT touch `server/tools|bundles`, `errors.py`, or non-kdenlive
pipelines.

Deferred pass-1 item (adapter audit, held while the serializer got the E-shape rewrite in
`ca167dd`) is closed here together with a fault-injection corpus.

## TL;DR verdict

| Question | Verdict |
|---|---|
| Baseline green first? | Yes — 3273 unit / 54 external+1 skip **before** changes |
| Old pre-E-shape ForgeFrame projects still parse? | **Yes** (backward compat intact) |
| …and upgrade to valid E-shape on re-serialize? | **Yes** — no media `kdenlive:uuid`, 1 sequence tractor (pt=17), 1 `projectTractor`, `main_bin xml_retain=1`, melt-accepts |
| Round-trip idempotence on real fixtures? | **Yes** — `serialize(parse(x))` structurally == the second round-trip, all 5 real fixtures |
| Any adversarial input crash with a raw KeyError/RecursionError/etc.? | **No longer** — every input yields a correct parse or a typed error |
| Failed serialize can write a partial/broken file? | **No** — validated-before-write survived the E-shape rewrite, and the write is now atomic (temp + `os.replace`) |

## Breaks found & fixed

Empirically probed (not guessed) against the live adapter. Six real defects:

1. **Deep nesting → raw `RecursionError`.** `ET.parse` is iterative, but `ET.tostring`
   (used to snapshot unknown elements as `OpaqueElement`) recurses in Python; a document
   ~2000 levels deep raised a bare `RecursionError` mid-parse — a mandate violation.
   **Fix (parser):** iterative `_max_depth()` guard, cap `_MAX_NESTING_DEPTH = 256` (real
   files nest <20), raising `ProjectParseError("document nesting too deep")`.

2. **Billion-laughs / entity expansion.** `xml.etree.ElementTree` (expat) **expands internal
   general entities** — a nested-`<!ENTITY>` DOCTYPE inflated a title to arbitrary size (DoS).
   **Fix (parser):** reject any document carrying a `<!DOCTYPE` (byte-scan before expat). A
   legitimate `.kdenlive` never declares a DOCTYPE (confirmed: zero DOCTYPE/CDATA across all
   real + legacy + smoke fixtures, so no false-positive risk — a literal `<!DOCTYPE` can only
   appear as real markup, never as escaped property text).

3. **XXE (external entity).** expat already *rejects* external `SYSTEM` entities
   (`ParseError: reference to external entity`), so no file read ever occurred — now
   **documented** and additionally covered by the blanket DOCTYPE guard. No network/file
   disclosure path exists.

4. **Wrong root element silently accepted.** `<html>`, `<fcpxml>`, etc. parsed into a
   near-empty project (a downstream tool would then overwrite the source with an empty
   timeline). **Fix (parser):** require the root localname to be `mlt`, else
   `ProjectParseError("root element is <X>, expected <mlt>")`.

5. **Serializer silently emitted broken documents.** Three model inconsistencies were
   written verbatim:
   - playlist entry referencing a **ghost producer** (id defined nowhere);
   - clip entry with **out_point < in_point** (`<entry in="50" out="10">`);
   - **negative / non-positive blank length** (`<blank length="-5">`).
   **Fix (serializer):** new typed `ProjectSerializeError` + `_assert_serializable()` guard
   that runs **before any I/O** and raises with playlist / track / entry-index context.
   Critically, "known producer ids" includes ids preserved as `<producer>`/`<chain>`
   OpaqueElements — real Kdenlive `<chain>` clips carry timecode `out=` attributes the chain
   parser cannot int-cast, so they round-trip through the opaque store while still being
   referenced by entries; those references are valid, not ghosts. This is why the guard does
   **not** false-fire on the real corpus.

6. **Non-atomic write.** A crash mid-write could truncate an existing project.
   **Fix (serializer):** write to a sibling `.tmp` then `os.replace()` (atomic on POSIX);
   cleanup on any exception. Combined with the pre-existing (and confirmed-intact)
   well-formedness check, the target is only ever replaced by a fully-written valid document.

## Audit fixes (weaker spots, no crash but context-poor)

- Malformed-element skip logs (`<producer>`, `<chain>`, `<playlist>`, `<tractor>`) now name
  the element **id** instead of only echoing the exception. Previously "Skipping malformed
  `<playlist>`: invalid literal for int()" — now includes `id=...`.
- Confirmed `effect_stack.py` already raises `IndexError` **with range context** for
  out-of-range `track_index`/`clip_index` (no change needed).
- Confirmed the parser's per-section broad `except Exception` catches keep malformed
  sub-elements as OpaqueElements (round-trip-safe), so no raw `KeyError`/`ValueError`
  escapes; the whole-file paths raise `ProjectParseError`.
- Residual (out of fault-injection scope, left as-is): `patcher_intents.py` has a few
  `int(source.properties["length"])` accesses in the mutation-tool path that would `KeyError`
  on a producer lacking `length`; these are reached only via MCP edit intents (bounds-validated
  upstream), not via the parse→serialize fault path, so not modified here.

## Adversarial corpus

`tests/fixtures/projects/adversarial/` — **19 committed** inputs; 2 more (10k-clip large
project, 5000-deep tree) generated in-test to avoid committing big/pathological blobs.

Parse-must-fail (→ `ProjectParseError`): `empty`, `not_xml`, `truncated_prolog`,
`truncated_deep`, `wrong_root_html`, `wrong_root_fcpxml`, `xxe_external`, `billion_laughs`,
`doctype_plain`.
Serialize-must-fail (→ `ProjectSerializeError`): `ghost_producer`, `negative_blank`,
`out_lt_in`, `negative_in`.
Parseable-but-odd (parse + serialize to valid XML): `zero_tracks`, `filter_no_service`,
`bad_entry_int`, `bad_blank_int`, `bad_chain_out`, `hybrid_legacy_single_tractor`.

`tests/fixtures/projects/legacy/` — 3 real pre-E-shape ForgeFrame working copies
(`smoke_test_full`, `review-timeline_v3`, `selects-timeline_v3`) committed so the
backward-compat + E-shape-upgrade test is self-contained.

## Legacy-compat proof (the CRITICAL check)

Real pre-E-shape smoke files (`smoke_test_full.kdenlive`, `review-timeline_v3.kdenlive`,
`test_project.kdenlive`) each: **parse** to real content → **serialize** to E-shape with
`media_with_uuid=[]`, `seq_tractors=1`, `project_tractors=1`, `main_bin xml_retain=1` →
**melt-accepts** (`rc=0`, zero structural-fatal lines). The `hybrid_legacy_single_tractor`
fixture (a legacy flat single-tractor doc whose media producer deliberately carries the
poison `kdenlive:uuid`) upgrades correctly — the uuid is dropped on re-serialize.

## Idempotence proof

For all 5 `tests/fixtures/projects/real/*.kdenlive`:
`serialize(parse(x))` and `serialize(parse(serialize(parse(x))))` produce **byte-structurally
identical** trees (element-tag + sorted-attrib signature equal; tag counts equal:
304/304, 1418/1418, 341/341, 698/698, 290/290).

## Performance bounds observed (10k-clip synthetic)

| metric | observed | test bound |
|---|---|---|
| parse | 0.24–0.27 s | < 20 s |
| serialize | 2.7–2.8 s | < 40 s |
| peak memory (tracemalloc) | ~104 MB | < 800 MB |
| output size | 4.8 MB | — |

(The generated 10k-clip source is ~1.8 MB; heavier per-clip metadata would approach the
"50 MB" framing but the time/memory profile is the load-bearing signal and is comfortably
within bounds.)

## Test counts

- New permanent suite `tests/unit/test_faults_adapter.py`: **69 tests**, all green.
- Full unit suite: **3342 passed** (was 3273 baseline + 69 new; net +69), 2 warnings.
- External suite: **54 passed, 1 skipped** (unchanged from baseline).
- One test-data fix: `tests/unit/test_serializer_bin.py::_make_project` now references the
  first supplied producer in its default playlist (three metadata tests were overriding
  `producers` while the default timeline still pointed at the old `prod0` — a latent silent
  broken-document that the new serializer guard correctly surfaced).

## Changed files

- `edit_mcp/adapters/kdenlive/parser.py` — DOCTYPE guard, wrong-root check, depth guard,
  richer skip-log context.
- `edit_mcp/adapters/kdenlive/serializer.py` — `ProjectSerializeError`, `_assert_serializable`,
  atomic temp+`os.replace` write.
- `tests/unit/test_faults_adapter.py` (new), `tests/fixtures/projects/adversarial/*` (new),
  `tests/fixtures/projects/legacy/*` (new), `tests/unit/test_serializer_bin.py` (fixture fix).

Committed nothing (per instruction).
