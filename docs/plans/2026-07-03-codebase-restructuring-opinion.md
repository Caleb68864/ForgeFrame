---
date: 2026-07-03
topic: "Codebase Restructuring Opinion -- layer-first vs feature-domain"
author: Caleb Bennett
status: draft
tags:
  - planning
  - restructuring
  - architecture
  - consistency-pass-5
---

# Codebase Restructuring Opinion

Consistency Pass 5 of 5. Synthesis only -- no code was changed to produce this
document. This is the one-pager the project owner reads to decide whether to
restructure `workshop-video-brain/src/workshop_video_brain/`.

**Bottom line up front:** Do **not** restructure to feature-domain packages. The
layer-first layout plus the `bundles/` auto-discovery pattern already minimizes
the binding constraint (shared-file contention for agent fleets). Spend ~4-6
agent-hours on three surgical cleanups instead, then stop.

---

## 1. State of the structure

Post-buildout map, walked from the source tree (244 modules, ~59.8k LOC):

| Layer / package | Modules | LOC | Role |
|---|--:|--:|---|
| `core/models` (+utils, validators) | 30 | 1,463 | Pydantic data models -- the shared spine (ADR 004) |
| `edit_mcp/adapters/{ffmpeg,kdenlive,render,stt,youtube}` | 21 | 6,095 | External-tool boundary (ffprobe, MLT XML, melt, whisper) |
| `edit_mcp/pipelines` (+`effect_wrappers`) | 104 | 28,608 | Pure logic -- the bulk of the codebase |
| `edit_mcp/server` (`server.py` hub, `errors`, `resources`, `tools_helpers`) | 5 | ~1,700 | MCP registration hub + shared kernel |
| `edit_mcp/server/tools` | 16 | 8,885 | Grouped multi-tool I/O shells (~133 re-exported names) |
| `edit_mcp/server/bundles` | 38 | 8,947 | One-tool-per-file I/O shells, auto-discovered |
| `production_brain/{skills,notes}` | 14 | 2,438 | Claude-driven planning (ADR 004 second module) |
| `app` | 6 | 2,982 | Click CLI wiring |
| `workspace` | 5 | 348 | Workspace scaffolding |
| **tests** (`unit` 151 / `integration` 76 / `external` 19) | 246 | 55,497 | Test-type-first, not feature-first |

**Registration topology (matters for the whole argument).** `server.py`
(FastMCP hub) imports four things for their decorator side effects:
`server.tools` (explicit re-export in `tools/__init__.py`), `server.resources`,
`pipelines.effect_wrappers` (generated, explicit imports), and `server.bundles`
(**`pkgutil.iter_modules` auto-discovery** -- its `__init__` docstring states the
intent literally: *"auto-discovers submodules so adding a new bundle never edits
shared files"*). Live registry: **201 tools**.

**What the 4 passes already fixed** (evidence, not vibes):
- Pass 1: drained ~1,187 LOC of duplication into shared helpers; created
  `pipelines/_common.py`; slimmed the 22 generated effect wrappers 1956→802 LOC
  via a byte-identical regen template.
- Pass 2: fixed the real `_v10 < _v2` lexicographic version bug in two bundles;
  unified time-conversion onto one half-up `seconds_to_frames`; censused the
  signature conventions (177/201 lead with `workspace_path`) and found **0**
  renames warranted.
- Pass 3: layering enforcement -- pushed every inline `ET`/ffprobe leak out of
  the shell layer down into `pipelines/_common` and `adapters/ffmpeg/probe`, each
  with a byte-identity assertion. The shell layer is now near-pure.
- Pass 4: built `tests/_testkit.py` (309 LOC) killing ~40 copy-pasted unwrap
  blocks; found the CPU-pinning orphaned-render flake root cause (environmental,
  not a product bug) and halved suite time (417s→218s).

**Friction that remains, with evidence from the notes:**

1. `server/tools_helpers.py` (357 LOC) is a **multi-domain kernel** -- workspace
   validation, response envelopes, latest-project selection, project load/save,
   filter-XML building (`_build_filter_xml`), effect application, media finders,
   playlist resolution, catalog lookup. Flagged in Pass 1, Pass 3 ("doubly a
   mixed kernel"). Every tool imports it, so it is a genuine hot shared file.
2. **One stranded XML builder.** `_build_filter_xml` (id-normalizing, server
   layer) is the last filter builder not living beside its three siblings in
   `pipelines/_common` (Pass 3 carry-forward). Imported by
   `tools/effects_bundles.py` and re-exported in `tools/__init__` (one of the 133
   names), so moving it is churn, not a no-op.
3. **`clip` vs `clip_index`** (56 vs 18 params) is the single real cross-cutting
   naming dup left standing (Pass 2). Documented, not renamed -- positional break.
4. **bundles/ vs tools/ is not a logic-vs-shell boundary** (Pass 3): both are thin
   shells now. The only difference is auto-discovered-single-tool vs
   explicit-grouped-multi-tool.
5. **`_common.py` (156 LOC) shows early multi-domain drift** (time, xml, text,
   dsp) -- the same shape that bloated `tools_helpers` (Pass 3 watch).
6. **ADR 004 has quietly eroded** (found this pass, not previously logged):
   `production_brain/skills/broll.py` and `pattern.py` import
   `edit_mcp.pipelines.*` at **module level**, and `edit_mcp` reaches back into
   `production_brain.skills`/`notes` via **function-local (lazy)** imports in
   `new_project.py`, `publishing.py`, `assembly_titles.py`. ADR 004 asserts both
   modules "depend on `core/` models only" -- that is no longer true.

The structure is **healthy**. Nothing here is a fire. The question is whether a
big-bang reorg buys enough to justify its cost.

---

## 2. The central question: layer-first vs feature-domain vs hybrid

The dominant development mode is **agent fleets**, and the binding constraint all
day has been **shared-file contention** (two agents editing the same file) and
**context-per-task** (how much an agent must load to do one feature). Weigh each
layout against *those two* axes, not aesthetics.

### Option A -- Layer-first (today)

`core/models`, `pipelines/*`, `adapters/*`, `server/tools`, `server/bundles`,
`production_brain`. A feature vertical is three same-named files in three
directories: `pipelines/titles.py` + `server/bundles/titles.py` +
`tests/.../test_titles*.py`.

- **Pros for THIS codebase:** The pipeline(logic)/bundle(shell) seam is
  consistently applied and was *reinforced* by Pass 3 -- it is a proven, healthy
  boundary. Critically, **the growth path already has near-zero shared-file
  contention**: adding a feature = a new `pipelines/x.py` + a new
  `bundles/x.py`, both brand-new files, auto-discovered by `pkgutil` -- no shared
  `__init__` edit. Context-per-task is already low because verticals share a
  basename across layers; an agent globs `**/titles*` and gets the whole vertical
  in three hits. Adapters and core stay cleanly reusable across all verticals.
- **Cons:** The `tools/` package (16 grouped modules, `__init__` re-exports 133
  names) is the **one real contention point** -- multiple tools per file, and a
  shared re-export surface two agents can collide on. `tools_helpers`/`_common`
  are hot shared kernels. A newcomer navigates three dirs per feature (ADR 004
  already conceded this).
- **Migration cost:** 0 (status quo).

### Option B -- Feature-domain packages

`features/titles/{pipeline.py, tool.py, tests.py}`, `features/audio/...`, ~55
verticals; keep `core`/`adapters` shared.

- **Pros:** Maximal locality -- one folder per feature, minimal context to load,
  and two agents on two features never share a file (including no shared
  `tools/__init__`). This is the theoretical best on both axes.
- **Cons for THIS codebase:** The benefit is **largely already captured** by (i)
  `bundles/` auto-discovery and (ii) same-basename-across-layers naming -- so the
  marginal gain is small. It **collapses or nests the proven pipeline/shell
  seam**: either you merge logic+shell into one file (losing the Pass-3 boundary
  and the "pure logic is unit-testable headlessly" property) or you recreate
  `features/titles/{pipeline,shell}` -- same file count, deeper paths, no net win.
  **Tests would not follow cleanly**: the suite is organized by *execution tier*
  (unit / integration / external-oracle) and gating marks (`render_retry`,
  `melt_bin`), which are orthogonal to feature -- so `features/titles/tests.py`
  fights the external-oracle architecture Pass 4 just consolidated. And every one
  of the ~55 verticals' pipelines is referenced by cross-cutting modules
  (`_common`, `probe`, generated wrappers, `assembly`) -- the import surface to
  rewrite is enormous.
- **Migration cost:** See §migration calibration -- **~40-80 agent-hours, HIGH
  risk.**

### Option C -- Hybrid (keep `adapters`+`core` as layers, group the ~55 verticals)

- **Pros:** Keeps the reusable layers where layering genuinely pays (a probe or a
  model is shared by everyone), groups only the feature verticals.
- **Cons for THIS codebase:** Still collapses/nests the pipeline/shell seam for
  the grouped part; still orphans the test-tier organization; still a large
  import rewrite. It is Option B's cost with a slightly smaller blast radius, and
  the same "benefit already captured by auto-discovery + naming" objection
  applies. The one thing it would *genuinely* fix -- the `tools/__init__`
  contention -- is fixable far more cheaply by making `tools/` auto-discover like
  `bundles/`, without moving a single feature.
- **Migration cost:** ~25-45 agent-hours, MEDIUM-HIGH risk.

### Migration calibration (from the proven splits)

- **patcher split** (`e7037c4`): 1,756 LOC → 80-line shim + 2 modules, ~50 import
  sites preserved via re-export, zero behavior change, one commit. Call it ~3-4
  agent-hours for a single well-bounded module.
- **tools split** (`86c22c5`): 139 top-level statements → 16 modules via
  byte-identical AST-span extraction, `__init__` re-exports 133 names, verified
  201 tools + full suite identical. One package, one big commit -- call it ~5-8
  agent-hours.

A full feature-domain reorg is **every package + every import site + the test
tree at once**: conservatively 10-15x the tools-split surface, and unlike the
tools split it cannot be byte-identical because files change directories and the
pipeline/shell seam is being merged or nested. Hence the ~40-80h / HIGH-risk
estimate for Option B. **What it buys concretely:** a marginal locality
improvement on top of an already-low-contention growth path -- i.e. it pays down
a debt that the `bundles/` pattern already mostly retired.

---

## 3. The smaller structural questions (carry-forward verdicts)

**3.1 Merge `server/bundles` into `server/tools/` domains?**
**Verdict: NO -- keep the split, but re-document its real rationale.** The
original justification ("bundles/ is where logic hid") was drained by Pass 3.
But the split now earns its keep for a *better* reason: `bundles/` is the
**only zero-shared-file-edit registration path in the codebase** (pkgutil
auto-discovery). Merging it into `tools/` would *force* every new feature to edit
`tools/__init__`'s 133-name re-export -- manufacturing exactly the shared-file
contention the agent fleet must avoid. If anything, the arrow points the other
way: make `tools/` auto-discover too (a cheap, separate win -- see §4 phase B,
optional). Document: `bundles/` = auto-discovered single-tool shells (the
sanctioned growth path); `tools/` = legacy grouped shells retained for cohesion.

**3.2 Split `tools_helpers`' multi-domain kernel?**
**Verdict: YES, low priority -- it is the cleanest real win.** 357 LOC spanning
≥5 domains, imported by nearly every tool. Convert to a `tools_helpers/` package
(`_workspace`, `_responses`, `_effects`, `_projects`, `_xml`) with
`tools_helpers/__init__.py` re-exporting every current name -- the exact
patcher-split shim pattern, byte-identical, import-churn-free for callers.
Fold the stranded `_build_filter_xml` into `pipelines/_common` at the same time
(keep a re-export in `tools_helpers`/`tools` so the 133-name surface is intact).

**3.3 `_common` growth policy?**
**Verdict: policy, not a split (yet).** At 156 LOC it is still cohesive
("pipeline-layer primitives"). Set an explicit trigger: split into a `_common/`
package (`_time`, `_xml`, `_text`, `_dsp`) **when it exceeds ~250 LOC or a 5th
domain lands**. Same test applies to `tests/_testkit.py`. Write the trigger down;
do not pre-split.

**3.4 `production_brain`'s relationship to `edit_mcp`?**
**Verdict: ADR 004 is partially violated -- amend the ADR, do not restructure.**
`production_brain` now module-level-imports `edit_mcp.pipelines.*`, and
`edit_mcp` lazily reaches into `production_brain.skills`/`notes`. The lazy
(function-local) imports on the `edit_mcp` side are load-bearing -- they exist to
dodge a circular import, which is the smell. This works today and there is no
failure, so the right move is to **write ADR 005 amending ADR 004**: acknowledge
that `production_brain.skills` depends on `edit_mcp.pipelines` (planning consumes
analysis), and that `new_project`/`publishing` orchestrate `production_brain` via
lazy imports. Formalize the intended direction rather than pretending the
two-module wall still stands. No code move required.

**3.5 Should tests mirror whatever structure wins?**
**Verdict: NO -- tests stay tier-first.** The suite is organized by execution
tier (unit / integration / external-oracle) plus gating marks -- concerns
orthogonal to feature. Pass 4 just consolidated the external-oracle tier and
`_testkit`. Forcing `features/x/tests.py` would fight that architecture. This is
itself a **third independent argument against Option B**: the winning src layout
would not propagate to tests, so feature-domain buys locality on only 2 of the 3
layers it claims to unify.

---

## 4. Recommendation

**DO** the three surgical cleanups below (~4-6 agent-hours, low risk).
**DON'T** do the feature-domain (Option B) or hybrid (Option C) restructure.

**Rejected -- Option B feature-domain: "not worth it because"** the marginal
locality gain sits on top of an already-low-contention growth path
(auto-discovery + same-basename naming already give agents the whole vertical),
while the cost is ~40-80 agent-hours at HIGH import-surface and test-churn risk,
it collapses the proven Pass-3 pipeline/shell seam, and it cannot even propagate
to the tier-organized test tree.

**Rejected -- Option C hybrid: "not worth it because"** it carries most of
Option B's cost and seam-collapse for a smaller blast radius, and the one thing
it uniquely fixes (the `tools/__init__` contention) is fixable for ~2 agent-hours
by making `tools/` auto-discover -- no feature needs to move.

**"Do nothing more" -- evaluated honestly.** This is a *defensible* choice. The 4
passes captured the large majority of the available value: the duplication is
drained, the version bug is fixed, the shell layer is pure, the flake is
diagnosed, the test kit exists. Every remaining item is cosmetic or a
documentation gap. If agent-hours are scarce, stopping here loses almost nothing
concrete. The only reason to prefer the tiny cleanup over pure do-nothing is that
`tools_helpers` is a genuinely *hot* shared file (every tool imports it) and the
ADR-004 drift is an undocumented correctness-of-the-map issue that will confuse
future agents -- both cheap to retire.

**Recommended sequenced phases (all independently shippable, each its own
commit, suite-gated):**

- **Phase A (~2-3h) -- split `tools_helpers` + land the stranded builder.**
  `tools_helpers/` package with full re-export shim; move `_build_filter_xml`
  into `pipelines/_common` with re-export. Patcher-split pattern.
- **Phase B (~1h, optional) -- retire the one real contention point.** Make
  `tools/__init__.py` auto-discover its submodules (mirror `bundles/`) so new
  grouped tools stop touching the 133-name re-export. Keep the explicit
  re-export block only for names external code imports directly, or generate it.
- **Phase C (~1h) -- documentation, no code.** Write ADR 005 (production_brain ↔
  edit_mcp coupling); add the `_common`/`_testkit` >250-LOC split trigger and the
  bundles-vs-tools rationale to `CLAUDE.md` or a `docs/reference/structure.md`.

Explicitly **not** doing: the `clip`/`clip_index` rename (positional break, no
churn-justifying payoff -- keep documented per Pass 2); any feature-folder move.

---

## 5. If-we-do-it safety protocol

For Phases A-B (and any future split), reuse the exact patterns the patcher and
tools splits proved:

1. **Shim / re-export strategy.** The origin module becomes a thin package
   `__init__` (or shim module) that re-exports **every** public *and* private
   name external code touches -- the patcher shim deliberately re-exported private
   helpers like `_iter_clip_filters`; the tools `__init__` re-exports private
   `_build_filter_xml`. All ~50 (patcher) / 133 (tools) import sites stayed
   **unchanged**. Same rule: no caller edits, no monkeypatch-target moves.
2. **Byte-identity verification.** Carve by **AST-span extraction** (as the tools
   split did: 139 statements moved verbatim) so the moved code is byte-identical.
   For any relocated XML/logic builder, assert output byte-identity against the
   original before running the suite -- the discipline Pass 3 used for the three
   `make_filter_element_xml` builders.
3. **Suite gates.** Baseline `uv run pytest tests/ -q` and record
   pass/skip counts **and** the live tool count (`mcp.list_tools()` == 201)
   before and after; require identical totals (the tools split gated on "201
   before/after, suite identical"). Run the full suite **twice** to unmask
   load-flakes (Pass 4 protocol). Before any run, sweep
   `pgrep -fa 'melt|ffmpeg.*-loop'` and kill stragglers, and **never `kill -9`
   the suite** -- Pass 4 proved a single orphaned render pins a core and
   resurrects the flake.
4. **One concern per commit.** Each phase is pure movement with zero behavior
   change, message stating "pure code movement, zero behavior change" + the
   before/after tool count + suite totals, matching the patcher/tools precedent.
