---
date: 2026-04-08
topic: "Workshop Video Brain -- Unified Build Plan"
author: Caleb Bennett
status: draft
tags:
  - design
  - workshop-video-brain
  - forgeframe
  - mcp
  - kdenlive
  - obsidian
---

# Workshop Video Brain -- Unified Build Plan

## Summary

Workshop Video Brain is a local-first video production assistant for a solo Linux creator making MYOG, camping, garage/shop, and DIY tutorial videos. It combines an Obsidian-centered planning layer (Production Brain) with a Kdenlive-aware media/edit automation layer (Kdenlive Edit MCP), distributed as a Claude Code plugin marketplace from the ForgeFrame GitHub repository.

This document is the single source of truth for implementation. It unifies the PRD, technical spec, and task file into one actionable plan with all design decisions resolved.

## Approach Selected

**Phased execution specs** -- the original PRD and tech spec are preserved as reference docs. This plan organizes work into 6 dark-factory-sized execution phases, each independently buildable and testable.

## Reference Documents

- [Original PRD](../reference/original/PRD.md)
- [Original Technical Spec](../reference/original/SPEC.md)
- [Original Task File](../reference/original/TASKS.md)
- [Claude Code Skills Guide](../reference/claude-code/skills-complete-guide.md)
- [Claude Code Skills Docs](../reference/claude-code/skills-docs.md)
- [Claude Code MCP Docs](../reference/claude-code/mcp-docs.md)
- [Claude Code Plugin Marketplaces](../reference/claude-code/plugin-marketplaces-docs.md)
- [Kdenlive Introduction](../reference/kdenlive/introduction.md)
- [Kdenlive Documentation Workgroup](../reference/kdenlive/documentation-workgroup.md)

---

## Resolved Design Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Kdenlive parser preservation | Opaque passthrough -- parse only what you manipulate, preserve everything else as raw XML | Safest approach; won't break features the parser doesn't understand |
| 2 | Production Brain surface | Claude Code skills + CLI only for v1. MCP deferred to v2. | Keeps MCP server focused on edit operations. Skills are simpler to build and test. |
| 3 | Canonical subtitle format | SRT | Simple, universal, Kdenlive imports natively, easy to hand-edit |
| 4 | Speaker diarization | Fully deferred to v2. Data model has the field, no engine runs. | Solo creator = one speaker. Complexity not justified for v1. |
| 5 | Review timeline explanations | Kdenlive guide markers + external markdown report | In-editor context via markers, detailed explanations in report file |
| 6 | Transition application | Direct apply to working copy. Snapshots provide rollback. | Keeps workflow simple. Copy-first safety already handles risk. |
| 7 | Distribution model | Claude Code plugin marketplace from day 1 | Real distribution path that exists today. One install gets skills + MCP. |
| 8 | OTIO role | Skip entirely for v1. Native Kdenlive adapter handles everything. | OTIO adds complexity without value until multi-editor support is needed. |
| 9 | Whisper model default | `small` (configurable). Tuned after first real use. | Good speed/quality balance for clear tutorial speech. |
| 10 | Obsidian folder naming | Configurable with sensible defaults (`Videos/Ideas/`, etc.) | Not hardcoded. Users organize differently. |

---

## Architecture

### Repository Structure (Plugin Marketplace)

```
ForgeFrame/  (GitHub: Caleb68864/ForgeFrame)
│
├── .claude-plugin/
│   └── marketplace.json              ← Marketplace manifest
│
├── workshop-video-brain/             ← The plugin directory
│   ├── plugin.json                   ← Plugin manifest (skills + MCP)
│   ├── skills/
│   │   ├── video-idea-to-outline/
│   │   │   └── SKILL.md
│   │   ├── tutorial-script/
│   │   │   └── SKILL.md
│   │   ├── shot-plan/
│   │   │   └── SKILL.md
│   │   ├── obsidian-video-note/
│   │   │   └── SKILL.md
│   │   └── rough-cut-review/
│   │       └── SKILL.md
│   ├── .mcp.json                     ← MCP server definition
│   └── src/
│       └── workshop_video_brain/
│           ├── __init__.py
│           ├── server.py             ← MCP server entrypoint
│           ├── app/
│           │   ├── config.py         ← Config loading, tool discovery
│           │   ├── logging.py        ← Structured logging
│           │   └── paths.py          ← Path resolution
│           ├── core/
│           │   ├── models/           ← All shared data models
│           │   ├── validators/       ← Shared validation logic
│           │   └── utils/            ← Path helpers, naming, versioning
│           ├── workspace/
│           │   ├── manager.py        ← Workspace CRUD + state
│           │   ├── manifest.py       ← workspace.yaml read/write
│           │   ├── snapshot.py       ← Snapshot/restore
│           │   └── folders.py        ← Folder convention enforcement
│           ├── production_brain/
│           │   ├── skills/           ← Skill engine implementations
│           │   │   ├── outline.py
│           │   │   ├── script.py
│           │   │   ├── shot_plan.py
│           │   │   ├── video_note.py
│           │   │   └── review.py
│           │   └── notes/
│           │       ├── templates/    ← Jinja or string templates
│           │       ├── frontmatter.py
│           │       ├── writer.py
│           │       └── updater.py    ← Section-aware merge
│           └── edit_mcp/
│               ├── server/
│               │   ├── mcp_server.py
│               │   ├── tools.py      ← Tool definitions
│               │   └── resources.py  ← Resource definitions
│               ├── adapters/
│               │   ├── kdenlive/
│               │   │   ├── parser.py
│               │   │   ├── serializer.py
│               │   │   ├── patcher.py
│               │   │   └── validator.py
│               │   ├── ffmpeg/
│               │   │   ├── probe.py
│               │   │   ├── proxy.py
│               │   │   └── silence.py
│               │   ├── stt/
│               │   │   └── whisper_engine.py
│               │   └── render/
│               │       ├── profiles.py
│               │       ├── jobs.py
│               │       └── executor.py
│               └── pipelines/
│                   ├── ingest.py
│                   ├── auto_mark.py
│                   ├── review_timeline.py
│                   ├── selects_timeline.py
│                   ├── subtitle_pipeline.py
│                   └── render_pipeline.py
│
├── docs/
│   ├── reference/
│   │   ├── original/                 ← PRD.md, SPEC.md, TASKS.md
│   │   ├── claude-code/              ← Skills, MCP, marketplace docs
│   │   └── kdenlive/                 ← Kdenlive docs
│   ├── plans/                        ← This design doc
│   └── adr/                          ← Architecture decision records
│
├── templates/
│   ├── obsidian/                     ← Note templates
│   └── render/                       ← Render profile YAML
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│       ├── media/
│       ├── projects/                 ← Sample .kdenlive files
│       └── vault/                    ← Sample Obsidian vault
│
├── pyproject.toml
├── LICENSE
└── README.md
```

### Installation Flow

```bash
# User adds the ForgeFrame marketplace
/plugin marketplace add Caleb68864/ForgeFrame

# User installs Workshop Video Brain
/plugin install workshop-video-brain@forgeframe

# This gives them:
#   5 Production Brain skills (/video-idea-to-outline, etc.)
#   Kdenlive Edit MCP server (auto-starts via .mcp.json)
#   Obsidian note templates
#   Render profile presets
```

### Component Responsibilities

| Component | Owns | Does NOT Own |
|---|---|---|
| `core/models` | All shared data models, enums, serialization | Business logic, file I/O |
| `core/utils` | Path helpers, collision-safe naming, versioned output naming | Config, logging |
| `app/` | Config loading, structured logging, CLI entrypoint, path resolution | Domain logic |
| `workspace/` | Workspace creation, manifest YAML, folder conventions, snapshot/restore | Media processing, Kdenlive XML |
| `production_brain/skills/` | Outline, script, shot plan, rough-cut review logic | MCP exposure, media analysis |
| `production_brain/notes/` | Obsidian note CRUD, frontmatter merge, section-aware updates, templates | Vault discovery, file watching |
| `edit_mcp/server/` | MCP protocol, tool/resource registration, request routing | Business logic behind tools |
| `edit_mcp/adapters/kdenlive/` | `.kdenlive` XML parsing, opaque passthrough, patching, validation | Timeline semantics, marker generation |
| `edit_mcp/adapters/ffmpeg/` | Media probing, proxy transcoding, silence detection | Transcript generation |
| `edit_mcp/adapters/stt/` | Whisper/faster-whisper engine, transcript segment output | Speaker diarization (deferred) |
| `edit_mcp/pipelines/` | Multi-step workflow orchestration | Low-level adapter details |
| `skills/` (plugin dir) | Claude Code skill SKILL.md files for Production Brain prompts | Python execution |

**Boundary rule:** Pipelines call adapters. Adapters don't call each other. The workspace manager mediates all state.

### Data Flow

**Flow A: Idea → Obsidian Note (Production Brain)**
```
User idea → skill: /video-idea-to-outline → structured outline (JSON + markdown)
  → production_brain/notes/writer → Obsidian vault note (frontmatter + sections)
  → /tutorial-script → appended
  → /shot-plan → appended
```

**Flow B: Footage → Marked Review Timeline (Edit MCP)**
```
Media folder → pipeline/ingest → ffmpeg/probe + ffmpeg/proxy + stt/whisper + ffmpeg/silence
  → pipeline/auto_mark → markers with confidence + rationale
  → pipeline/review_timeline → ranked segments → kdenlive/serializer → working copy .kdenlive
```

**Flow C: Bridge (Brain ↔ Edit)**
```
Production Brain artifacts (outline, shot plan, keywords)
  → workspace/manifest (shared JSON/YAML)
    → Edit MCP reads for marker generation and coverage comparison

Edit MCP artifacts (transcript, markers, chapter candidates)
  → workspace/manifest
    → Production Brain reads for rough-cut review and note updates
```

### Error Handling

1. **Missing tools (FFmpeg/Whisper):** Config loader detects at startup, reports clearly, adapters have `check_available()`, pipelines skip unavailable steps.
2. **Kdenlive XML parse failure:** Opaque passthrough preserves unknowns. Validation report with severity levels. Working copy never written if blocking errors.
3. **Obsidian note merge conflict:** Generated sections bounded by `<!-- wvb:section:name -->` comments. Missing boundaries → append, never destroy. Every update logged.
4. **Failed batch jobs:** Each asset independent. Failed assets get `failed` status. Re-run skips completed (idempotent).
5. **Workspace manifest corruption:** Snapshots before every write. Schema validation on read. `workspace restore-snapshot` for recovery.

---

## Execution Phases

### Phase 1: Bootstrap + Plugin Scaffold
**Goal:** Repo structure, plugin marketplace manifest, dependency setup, config loader, hello-world MCP server.

**Tasks (from original task file):** 0.1, 0.2, 0.3, 10.1 (skeleton only)

**Deliverables:**
- `.claude-plugin/marketplace.json` with plugin entry
- `workshop-video-brain/plugin.json` with skill and MCP declarations
- `workshop-video-brain/.mcp.json` pointing to the Python MCP server
- `pyproject.toml` with dependency groups
- `.env.example` with all config paths
- Config loader that detects FFmpeg, Whisper, vault path
- MCP server skeleton with health check / ping tool
- 4 initial ADRs (Python stack, file-based integration, copy-first safety, two-module architecture)

**Acceptance criteria:**
- `/plugin marketplace add ./` works locally
- `/plugin install workshop-video-brain@forgeframe` installs skills + starts MCP
- `claude mcp list` shows the server
- Ping tool responds

### Phase 2: Core Models + Workspace + Obsidian
**Goal:** Shared data models, workspace folder conventions, snapshot safety, Obsidian note CRUD.

**Tasks:** 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4

**Deliverables:**
- All shared Pydantic models with JSON/YAML serialization (MediaAsset, Transcript, Marker, ShotPlan, etc.)
- Path utilities with collision-safe naming and versioned outputs
- Structured logging framework with per-job log files
- Snapshot/copy-first safety layer (no in-place overwrite path exists)
- Workspace initializer creating all standard folders
- Obsidian vault integration: note create, read, frontmatter merge, section-aware update
- 6 Obsidian note templates (idea, in-progress, shot plan, transcript, edit review, publish checklist)
- Note lifecycle actions (create from idea, status transitions, append content)

**Acceptance criteria:**
- Models serialize/deserialize round-trip cleanly
- Workspace initializer creates all folders
- Obsidian notes survive create → update → update without data loss
- Frontmatter merges preserve unrelated fields
- Section updates don't duplicate content on re-run
- Snapshot operations tested

### Phase 3: Media Pipeline + Transcripts
**Goal:** Media scanning, automatic proxies, local transcript generation, analysis helpers.

**Tasks:** 3.1, 3.2, 3.3, 3.5

**Deliverables:**
- Media inventory scanner using ffprobe (path, codec, duration, fps, resolution, size, hash)
- Automatic proxy generation with configurable thresholds
- Proxy status tracking on asset model
- Transcript generation pipeline (faster-whisper first, Whisper fallback)
- Timestamped segments, plain text export, JSON export, SRT export
- Silence detection, loudness analysis
- All analysis output stored per asset in workspace

**Acceptance criteria:**
- Mixed media folder scans without crashing on bad files
- Proxies generated to correct folder, mapped to source assets
- Transcripts produced offline with segment timestamps
- Silence gaps detected and stored
- Re-running skips already-processed assets

**Note:** Task 3.4 (speaker labeling) deferred to v2 per Decision 4.

### Phase 4: Auto-Marking + Review Timelines + Kdenlive Adapter
**Goal:** Marker taxonomy, transcript-to-marker heuristics, review/selects timelines, Kdenlive parser/writer, validation.

**Tasks:** 4.1, 4.2, 4.3, 4.4, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4

**Deliverables:**
- Marker taxonomy (14 categories: intro candidate, hook, step explanation, chapter candidate, dead air, etc.)
- Transcript-to-marker heuristics with confidence scoring and rationale
- Best-guess-first ranking + chronological fallback
- Selects list abstraction (JSON/Markdown with per-clip time ranges and reasons)
- Kdenlive project model (internal representation, not raw XML in business logic)
- Kdenlive parser with opaque passthrough for unknown elements
- Kdenlive writer producing versioned working copies
- Project validator returning structured severity-leveled reports
- Timeline intent model for editorial operations
- Selects timeline generator → Kdenlive project with guide markers
- Chapter marker generator with confidence/rationale
- Subtitle handoff (transcript → SRT, per-project export)

**Acceptance criteria:**
- Markers generated deterministically for same inputs
- Every marker has confidence, rationale, and source method
- Review timeline opens in Kdenlive with visible guide markers
- Selects available in both ranked and chronological order
- Sample .kdenlive files parse and write back; output opens in Kdenlive
- Validator catches missing media, invalid clip ranges, bad transitions
- Subtitle SRT imports cleanly into Kdenlive

### Phase 5: Production Brain Skills + Transitions + Render
**Goal:** All 5 Production Brain skills, transition helpers, render pipeline.

**Tasks:** 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 8.1, 8.2, 8.3, 9.1, 9.2, 9.3

**Deliverables:**
- `/video-idea-to-outline` skill: viewer promise, materials, teaching beats, pain points, chapters
- `/tutorial-script` skill: hook, overview, materials, steps, mistakes, final thoughts
- `/shot-plan` skill: A-roll, overhead, closeups, inserts, glamour, pickups
- `/obsidian-video-note` skill: create/update with frontmatter sync and section merge
- `/rough-cut-review` skill: pacing, repetition, insert suggestions, chapter breaks
- Rough-cut review generator (markdown output, appendable to Obsidian note)
- Transition abstraction (crossfade, dissolve, fade in/out, audio crossfade)
- Crossfade helper with overlap calculation and duration presets
- Transition application in Kdenlive output (direct apply, per Decision 6)
- Render profile config (preview, draft YouTube, final YouTube)
- Render job launcher with logging and status tracking
- Render artifact registry

**Acceptance criteria:**
- Each skill produces dual output: human-readable markdown + machine-readable JSON
- Skills insert correctly into Obsidian notes
- Re-running /obsidian-video-note doesn't duplicate content
- Basic transitions appear and behave correctly in Kdenlive
- Preview render works end-to-end from working copy
- Render metadata stored with source project version

### Phase 6: MCP Tools + Integration + Testing + Docs
**Goal:** Full MCP tool/resource surface, CLI entrypoints, end-to-end testing, documentation.

**Tasks:** 10.2, 10.3, 10.4, 11.1, 11.2, 12.1-12.6, 13.1-13.3

**Deliverables:**
- MCP resources: workspace summary, media inventory, transcript summary, markers report, project summary, render status, validation report
- MCP tools: workspace_initialize, media_scan, proxy_generate, transcript_generate, markers_generate, selects_build, project_generate, project_validate, subtitles_export, transition_apply, render_preview, snapshot_list
- Production Brain tools (optional MCP exposure or CLI-only): video_idea_to_outline, tutorial_script, shot_plan, obsidian_video_note, rough_cut_review
- CLI entrypoints mirroring all core capabilities
- `prepare-tutorial-project` guided workflow command
- Unit tests for models, path helpers, serialization
- Integration tests for media pipeline, Obsidian notes, Kdenlive parser/writer
- MCP tool contract tests
- End-to-end workflow test (ingest → proxies → transcript → markers → selects → note → Kdenlive project → validate)
- Developer setup guide
- User workflow guide
- AI handoff notes

**Acceptance criteria:**
- All MCP tools return structured, validated output
- CLI mirrors MCP capabilities with helpful --help text
- `prepare-tutorial-project` produces a usable workspace from a media folder
- End-to-end test passes: all artifacts inspectable and coherent
- Generated .kdenlive project opens in Kdenlive with markers, proxies, subtitles visible

---

## Plugin Marketplace Configuration

### `.claude-plugin/marketplace.json`

```json
{
  "name": "forgeframe",
  "owner": {
    "name": "Caleb Bennett"
  },
  "metadata": {
    "description": "Kdenlive MCP and Video Production Skills for tutorial creators",
    "version": "0.1.0"
  },
  "plugins": [
    {
      "name": "workshop-video-brain",
      "source": "./workshop-video-brain",
      "description": "Local-first video production assistant: Obsidian planning + Kdenlive edit automation for tutorial makers",
      "version": "0.1.0",
      "author": "Caleb Bennett",
      "license": "MIT",
      "keywords": ["kdenlive", "video", "mcp", "obsidian", "tutorial", "production"],
      "category": "media"
    }
  ]
}
```

### `workshop-video-brain/plugin.json`

```json
{
  "name": "workshop-video-brain",
  "version": "0.1.0",
  "description": "Local-first video production assistant combining Obsidian planning with Kdenlive edit automation for MYOG, camping, garage, and DIY tutorial videos",
  "author": "Caleb Bennett",
  "license": "MIT",
  "skills": {
    "video-idea-to-outline": {
      "path": "skills/video-idea-to-outline"
    },
    "tutorial-script": {
      "path": "skills/tutorial-script"
    },
    "shot-plan": {
      "path": "skills/shot-plan"
    },
    "obsidian-video-note": {
      "path": "skills/obsidian-video-note"
    },
    "rough-cut-review": {
      "path": "skills/rough-cut-review"
    }
  }
}
```

### `workshop-video-brain/.mcp.json`

```json
{
  "mcpServers": {
    "workshop-video-brain": {
      "command": "uvx",
      "args": ["--from", "${CLAUDE_PLUGIN_ROOT}/src", "workshop-video-brain-server"],
      "env": {
        "WVB_VAULT_PATH": "${WVB_VAULT_PATH:-}",
        "WVB_WORKSPACE_ROOT": "${WVB_WORKSPACE_ROOT:-}"
      }
    }
  }
}
```

---

## Skill Specifications

### `/video-idea-to-outline`

```yaml
---
name: video-idea-to-outline
description: Turn a rough video idea into a structured tutorial outline with viewer promise, materials list, teaching beats, pain points, and chapter structure. Use when user says "plan a video", "outline a tutorial", "video idea", or describes a project they want to film.
---
```

### `/tutorial-script`

```yaml
---
name: tutorial-script
description: Generate a practical tutorial script from an outline or project note. Produces intro hook, materials section, step-by-step build instructions, common mistakes, and conclusion. Use when user says "write a script", "draft the tutorial", or "script this video".
---
```

### `/shot-plan`

```yaml
---
name: shot-plan
description: Generate a production shot list from a tutorial outline or script. Covers A-roll, overhead bench shots, detail closeups, measurement shots, inserts, glamour B-roll, and likely pickup shots. Use when user says "shot list", "plan the shots", "what do I need to film", or "shooting plan".
---
```

### `/obsidian-video-note`

```yaml
---
name: obsidian-video-note
description: Create or update an Obsidian video project note with frontmatter, outline, script, shot plan, transcript, edit notes, and publish checklist. Preserves manual edits. Use when user says "create video note", "update the note", "obsidian note", or "project note".
---
```

### `/rough-cut-review`

```yaml
---
name: rough-cut-review
description: Review a rough cut using transcript and edit notes. Identifies pacing issues, repetition, missing inserts, overlay opportunities, and chapter break candidates. Use when user says "review the cut", "rough cut feedback", "pacing review", or "what should I fix".
---
```

---

## MCP Tool Surface

### Namespaces

| Namespace | Tools |
|---|---|
| `workspace` | create, open, status, snapshot_list, restore_snapshot |
| `media` | ingest, list_assets, generate_proxies |
| `transcript` | generate, export |
| `markers` | auto_generate, list |
| `timeline` | build_review, build_selects |
| `project` | create_working_copy, validate, summary, apply_patch |
| `transitions` | apply, batch_apply |
| `subtitles` | generate_from_transcript, import, export |
| `render` | preview, final, status |

### MCP Resources

| Resource URI | Description |
|---|---|
| `workspace://current/summary` | Current workspace state |
| `workspace://{id}/media-catalog` | Media inventory |
| `workspace://{id}/transcript-index` | Transcript summaries |
| `workspace://{id}/markers` | Marker report |
| `workspace://{id}/timeline-summary` | Review/selects timeline info |
| `workspace://{id}/validation` | Project validation report |
| `workspace://{id}/render-logs` | Render job status and logs |
| `system://capabilities` | Available tools and adapters |

---

## Shared Workspace Model

Each video project has a local workspace:

```
VideoProject/
  workspace.yaml           ← Manifest (ID, title, status, paths, config)
  media/
    raw/                   ← Source media (never modified)
    proxies/               ← Auto-generated proxies
    derived_audio/         ← Extracted audio for STT
  transcripts/             ← JSON + text + SRT per asset
  markers/                 ← Marker JSON per asset + aggregated
  projects/
    source/                ← Original .kdenlive (if provided)
    working_copies/        ← Generated/patched copies (versioned)
    snapshots/             ← Pre-mutation snapshots
  renders/
    preview/
    final/
  reports/                 ← Validation, review, marker reports
  logs/                    ← Per-job structured logs
```

---

## Obsidian Note Structure

### Frontmatter

```yaml
title: "Zippered Bikepacking Pouch"
slug: zippered-bikepacking-pouch
status: idea  # idea|outlining|scripting|filming|ingesting|editing|review|rendering|published|archived
content_type: myog-tutorial
viewer_promise: "Build a durable zippered pouch for bikepacking in under 2 hours"
target_runtime: "12-15 min"
materials: ["X-Pac VX21", "#5 YKK zipper", "Gutermann thread"]
tools: ["Juki DU-1181N", "rotary cutter", "cutting mat"]
workspace_path: "/path/to/workspace"
transcript_path: ""
edit_state: not_started
publish_state: not_started
```

### Section boundaries (for safe automated updates)

```markdown
<!-- wvb:section:viewer-promise -->
## Viewer Promise
Build a durable zippered pouch...
<!-- /wvb:section:viewer-promise -->

<!-- wvb:section:shot-plan -->
## Shot Plan
- A-roll: talking head intro...
<!-- /wvb:section:shot-plan -->
```

Unbounded sections are never overwritten -- only appended to.

---

## Technology Stack

| Component | Technology | Notes |
|---|---|---|
| Language | Python 3.12+ | Type hints, Pydantic models |
| MCP Framework | FastMCP or mcp-python | Python MCP server |
| Media Analysis | FFmpeg/ffprobe | Probing, proxies, silence detection |
| Transcription | faster-whisper (primary), Whisper (fallback) | Local, free, offline after model download |
| Note Templates | Jinja2 or string.Template | Obsidian note generation |
| Config | YAML + env vars | `.env` for paths, YAML for workspace manifests |
| Testing | pytest | Unit + integration + fixtures |
| Packaging | pyproject.toml + uvx | For MCP server execution |
| Distribution | Claude Code plugin marketplace | `/plugin marketplace add Caleb68864/ForgeFrame` |

---

## Open Questions (Non-Blocking)

1. **Kdenlive version compatibility** -- Adapter targets 25.12-era. Fixture tests per version when breakage occurs.
2. **Whisper model size default** -- Start with `small`, tune after first real use.
3. **Obsidian vault folder naming** -- Configurable with defaults. Not hardcoded.
4. **Plugin .mcp.json command** -- Exact `uvx` invocation may need tuning based on how plugin paths resolve at runtime.

---

## Approaches Considered

### Approach A: Monolithic Unified Spec
Merge all three docs into one giant spec. Single source of truth but ~30K words, hard to navigate, context limit risk for agents.

**Not selected:** Too large for dark factory execution.

### Approach B: Phased Execution Specs (Selected)
PRD + spec as reference. One unified plan with 6 phases. Each phase independently buildable.

**Selected because:** Practical for incremental dark factory execution. Preserves original docs. Clear handoff points.

### Approach C: Component Specs
Independent specs per component. Maximum parallelism but integration risk.

**Not selected:** Solo builder, no parallelism benefit. Linear dependencies between components.

---

## Next Steps

- [ ] Run `/forge docs/plans/2026-04-08-workshop-video-brain-design.md` to generate Phase 1 execution spec
- [ ] Execute Phase 1 via dark factory
- [ ] Validate plugin installation works locally
- [ ] Proceed to Phase 2
