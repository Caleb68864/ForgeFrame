---
title: "ForgeFrame Coverage Gaps Test Plan"
project: "ForgeFrame"
date: 2026-04-09
type: test-plan
tags:
  - test-plan
  - forgeframe
  - coverage-gaps
---

# Test Plan: ForgeFrame Coverage Gaps

## Meta
- Project: ForgeFrame
- Date: 2026-04-09
- Author: Forge
- Spec Source: Codebase scan (gap analysis)
- Scope: All 34 untested modules
- Priority: Pipelines first, then adapters/workspace, then models, then skills
- Edge Cases: Empty/missing inputs, invalid data formats, boundary conditions, subprocess failures
- Test Data: Self-contained (fixtures + tmp_path)

## Prerequisites
- Python 3.12+
- `uv run pytest tests/ -v` for execution
- Existing test fixtures in `tests/fixtures/` (media, projects, transcripts)
- Mock subprocess calls for FFmpeg/yt-dlp (no real external tools needed)

## Scenarios

### Priority 1: Pipelines (9 untested)

| ID | Title | Module | Sequential |
|----|-------|--------|------------|
| PL-01 | Ingest pipeline scan, proxy, transcribe, silence | `pipelines/ingest.py` | No |
| PL-02 | B-roll suggestion detection and formatting | `pipelines/broll_suggestions.py` | No |
| PL-03 | Marker rules default config loading | `pipelines/marker_rules.py` | No |
| PL-04 | Pacing analyzer speech rate and report | `pipelines/pacing_analyzer.py` | No |
| PL-05 | Render pipeline job registry and execution | `pipelines/render_pipeline.py` | No |
| PL-06 | Replay generator highlight reel creation | `pipelines/replay_generator.py` | No |
| PL-07 | Review timeline marker ranking and chapters | `pipelines/review_timeline.py` | No |
| PL-08 | Selects timeline filtering and export | `pipelines/selects_timeline.py` | No |
| PL-09 | YouTube analytics channel and video analysis | `pipelines/youtube_analytics.py` | No |

### Priority 2: Adapters & Workspace (6 untested)

| ID | Title | Module | Sequential |
|----|-------|--------|------------|
| AD-01 | Render executor FFmpeg command building | `adapters/render/executor.py` | No |
| AD-02 | Render jobs creation and status tracking | `adapters/render/jobs.py` | No |
| WS-01 | Workspace manager create, open, save lifecycle | `workspace/manager.py` | Yes |
| WS-02 | Workspace folders structure creation and validation | `workspace/folders.py` | No |

### Priority 3: Models (16 untested)

| ID | Title | Module | Sequential |
|----|-------|--------|------------|
| MD-01 | Base model serialization mixin (JSON/YAML) | `models/_base.py` | No |
| MD-02 | Enums serialization and value coverage | `models/enums.py` | No |
| MD-03 | Kdenlive project model construction and validation | `models/kdenlive.py` | No |
| MD-04 | Marker and MarkerConfig model defaults | `models/markers.py` | No |
| MD-05 | MediaAsset field defaults and aliases | `models/media.py` | No |
| MD-06 | ClipLabel model construction | `models/clips.py` | No |
| MD-07 | ColorAnalysis model construction | `models/color.py` | No |
| MD-08 | Pattern/BuildData model construction | `models/patterns.py` | No |
| MD-09 | Planning models (MaterialList, ScriptDraft) | `models/planning.py` | No |
| MD-10 | Project model (VideoProject, RenderJob, Snapshot) | `models/project.py` | No |
| MD-11 | QCReport and TimeRange model construction | `models/qc.py` | No |
| MD-12 | Social models (ClipCandidate, SocialPost) | `models/social.py` | No |
| MD-13 | Timeline intent models (AddClip, AddEffect, etc.) | `models/timeline.py` | No |
| MD-14 | Transcript and segment models | `models/transcript.py` | No |
| MD-15 | Validation models (ValidationItem, ValidationReport) | `models/validation.py` | No |
| MD-16 | Workspace model construction | `models/workspace.py` | No |

### Priority 4: Skills (3 untested)

| ID | Title | Module | Sequential |
|----|-------|--------|------------|
| SK-01 | Outline generation skill | `skills/outline.py` | No |
| SK-02 | Script generation skill | `skills/script.py` | No |
| SK-03 | Shot plan generation skill | `skills/shot_plan.py` | No |

### Priority 5: App Layer (3 untested)

| ID | Title | Module | Sequential |
|----|-------|--------|------------|
| AP-01 | Server entry point and MCP registration | `server.py` | No |
| AP-02 | MCP resource definitions | `edit_mcp/server/resources.py` | No |
| AP-03 | App logging configuration | `app/logging.py` | No |

## Coverage Summary
- Total scenarios: 35
- Pipeline tests: 9
- Adapter tests: 2
- Workspace tests: 2
- Model tests: 16
- Skill tests: 3
- App layer tests: 3
- Sequential scenarios: 1 (workspace manager lifecycle)
- Edge case categories: 4 (empty inputs, invalid formats, boundaries, subprocess failures)

## Next Step

Run `/forge-test-run docs/tests/2026-04-09-coverage-gaps/test-plan.md` to execute all scenarios.
Or use `/forge-run` with a spec generated from this plan.
