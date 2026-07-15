# ADR 005: production_brain <-> edit_mcp Boundary

**Status:** Accepted
**Date:** 2026-07-04
**Amends:** ADR 004 (Two-Module Architecture)

## Context

ADR 004 split the package into two top-level modules -- `production_brain/`
(Claude-driven planning: skills, note templates, workflows) and `edit_mcp/`
(FastMCP server, adapters, processing pipelines) -- and asserted that **both**
"depend on `core/` models only". The consistency sweep
(`docs/plans/2026-07-03-codebase-restructuring-opinion.md`, section 3.4) found
that claim is no longer true, and an import-graph audit confirms it:

**Forward edges -- `production_brain` -> `edit_mcp` (2):**

| From | Kind | Target |
|---|---|---|
| `production_brain/skills/broll.py:12` | **module-level** | `edit_mcp.pipelines.broll_suggestions` |
| `production_brain/skills/pattern.py:27` | lazy | `edit_mcp.pipelines.pattern_brain` |

Planning skills consume pure analysis logic from the pipeline layer -- the
`detect_broll_opportunities` / `format_broll_suggestions` and `extract_build_data`
/ `generate_overlay_text` / `generate_build_notes` functions.

**Reverse edges -- `edit_mcp` -> `production_brain` (12, ALL function-local):**

| From | Target |
|---|---|
| `edit_mcp/pipelines/new_project.py` (x7) | `production_brain.skills.{video_note,outline,script,shot_plan}`, `production_brain.notes.updater` |
| `edit_mcp/pipelines/publishing.py` (x2) | `production_brain.notes.frontmatter` |
| `edit_mcp/server/tools/broll.py` | `production_brain.skills.broll` |
| `edit_mcp/server/tools/transcript_markers.py` | `production_brain.skills.voiceover` |
| `edit_mcp/server/tools/assembly_titles.py` | `production_brain.skills.pattern` |

Every reverse edge is a **function-local (lazy) import**. They are lazy *on
purpose*: the forward edge (`production_brain` imports `edit_mcp.pipelines` at
module load) means a module-level reverse import would form an **import-time
cycle**. `new_project`/`publishing` orchestrate skills to generate notes; the
`server/tools/*` shells dispatch to skills. This works today with zero failures.

So the reality is: the coupling **runs both ways**, but it is *shallow* and
*layered* -- the forward edges only touch `edit_mcp.pipelines`, and the reverse
edges are confined to a lazy escape hatch. A full decouple (moving
`new_project`'s note-generation orchestration out of the pipeline layer) is
exactly the feature-domain restructure the opinion rejected as ~40-80 agent-hours
at HIGH risk for marginal gain.

## Decision

**BLESS the coupling with an explicit, enforced direction rule.** Do not
restructure. Amend ADR 004's "core-only" claim to the layering below.

Effective layering (bottom -> top):

```
core  <  edit_mcp.adapters  <  edit_mcp.pipelines
      <  production_brain.{skills,notes}  <  edit_mcp.server  <  app
```

`production_brain` sits **above** the pipeline/adapter layers (it consumes their
analysis) and **below** the server shell (which dispatches to it). Two rules make
that honest and cycle-free:

- **Rule 1 -- reverse edges are lazy-only.** `edit_mcp` may import
  `production_brain` **only** via function-local imports. A module-level
  `edit_mcp -> production_brain` import is forbidden (it would create an
  import-time cycle). The lazy imports in `new_project`, `publishing`, and the
  `server/tools/*` shells are the sanctioned orchestration escape hatch.

- **Rule 2 -- forward edges go down, never to the shell.** `production_brain`
  may import `edit_mcp.pipelines`, `edit_mcp.adapters`, and `core` (the blessed
  "planning consumes analysis" direction, at module level or lazily) but must
  **never** import `edit_mcp.server`. Reaching into the shell layer -- which
  itself imports `production_brain` -- would reintroduce the cycle at the top.

Why bless rather than decouple: the coupling is one-directional at the layer
level (planning depends downward on analysis) with a single, deliberately-lazy
reverse escape hatch for orchestration. Blessing names the true direction and
the true escape hatch; decoupling would move load-bearing orchestration code for
no correctness gain. This is the cheap, honest choice.

## Consequences

**Positive:**
- The dependency map is now accurate; future agents are not misled by the stale
  ADR 004 "core-only" claim.
- The import graph is guaranteed acyclic at module-load time (Rule 1).
- The blessed direction (planning consumes analysis) is documented, so new
  skills can freely import `edit_mcp.pipelines` without ambiguity.

**Negative:**
- The lazy reverse imports remain a mild smell (they exist to dodge a cycle).
  Accepted deliberately: the alternative is a large, low-value restructure.
- Two rules must be kept green as the tree grows -- hence the enforcement test.

## Enforcement

`tests/unit/test_module_boundaries.py` walks the module ASTs of
`production_brain/` and `edit_mcp/` (without importing them) and asserts:

1. No **module-level** `edit_mcp -> production_brain` import (Rule 1).
2. No `production_brain -> edit_mcp.server` import at any level (Rule 2).
3. Every `production_brain -> edit_mcp` edge targets `pipelines`/`adapters`/`core`
   (positive characterization guarding Rule 2's blind spots).

A violation of either rule fails the unit suite.
