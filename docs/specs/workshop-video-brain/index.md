---
type: phase-spec-index
master_spec: "../2026-04-08-workshop-video-brain.md"
date: 2026-04-08
sub_specs: 7
---

# Workshop Video Brain -- Phase Specs

Refined from [2026-04-08-workshop-video-brain.md](../2026-04-08-workshop-video-brain.md).

| Sub-Spec | Title | Dependencies | Phase Spec |
|----------|-------|--------------|------------|
| 1 | Bootstrap + Plugin Scaffold | none | [sub-spec-1-bootstrap.md](sub-spec-1-bootstrap.md) |
| 2 | Core Models + Workspace + Obsidian | 1 | [sub-spec-2-core-models.md](sub-spec-2-core-models.md) |
| 3 | Media Pipeline + Transcripts | 2 | [sub-spec-3-media-pipeline.md](sub-spec-3-media-pipeline.md) |
| 4a | Auto-Marking + Review Ranking | 3 | [sub-spec-4a-auto-marking.md](sub-spec-4a-auto-marking.md) |
| 4b | Kdenlive Adapter + Timelines + Subtitles | 4a | [sub-spec-4b-kdenlive-adapter.md](sub-spec-4b-kdenlive-adapter.md) |
| 5 | Production Brain Skills + Transitions + Render | 4b | [sub-spec-5-skills-transitions-render.md](sub-spec-5-skills-transitions-render.md) |
| 6 | MCP Tools + CLI + Integration Testing + Docs | 5 | [sub-spec-6-mcp-cli-docs.md](sub-spec-6-mcp-cli-docs.md) |

## Execution

Run `/forge-run docs/specs/2026-04-08-workshop-video-brain.md` to execute all phase specs.
Run `/forge-run docs/specs/2026-04-08-workshop-video-brain.md --sub 1` to execute a single sub-spec.
