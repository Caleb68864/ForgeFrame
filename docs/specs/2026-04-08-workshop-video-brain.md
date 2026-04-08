---
title: "Workshop Video Brain -- Master Spec"
project: ForgeFrame
repo: Caleb68864/ForgeFrame
date: 2026-04-08
author: Caleb Bennett
quality_scores:
  outcome: 5
  scope: 4
  edges: 4
  criteria: 5
  decomposition: 4
  total: 22
---

# Workshop Video Brain -- Master Spec

## Outcome

When this spec is fully implemented, ForgeFrame is a working Claude Code plugin marketplace that installs Workshop Video Brain -- a local-first video production assistant. Users run `/plugin marketplace add Caleb68864/ForgeFrame` and `/plugin install workshop-video-brain@forgeframe` to get 5 Production Brain skills and a Kdenlive Edit MCP server. The system can take a rough tutorial idea through Obsidian planning, media ingest, auto-marking, review timeline generation, and Kdenlive project output -- all locally, all on copies, all explainable.

## Context

This spec was produced from a brainstorm session that unified three source documents:
- [Original PRD](../reference/original/PRD.md) -- product vision, user profile, workflows, requirements
- [Original Technical Spec](../reference/original/SPEC.md) -- architecture, data models, adapter design, MCP surface
- [Original Task File](../reference/original/TASKS.md) -- 60+ tasks across 14 phases

Reference documentation for implementation:
- [Claude Code Skills Guide](../reference/claude-code/skills-complete-guide.md) -- how to build SKILL.md files
- [Claude Code Skills Docs](../reference/claude-code/skills-docs.md) -- frontmatter reference, distribution
- [Claude Code MCP Docs](../reference/claude-code/mcp-docs.md) -- MCP server installation, .mcp.json format
- [Claude Code Plugin Marketplaces](../reference/claude-code/plugin-marketplaces-docs.md) -- marketplace.json schema, plugin.json, distribution
- [Kdenlive Introduction](../reference/kdenlive/introduction.md) -- features, formats, tech stack (C++, MLT, Qt)
- [Kdenlive Documentation Workgroup](../reference/kdenlive/documentation-workgroup.md) -- project file format, feature list

The unified design document with all resolved decisions: [Design Plan](../plans/2026-04-08-workshop-video-brain-design.md)

**Key resolved decisions:**
1. Kdenlive parser: opaque passthrough -- parse only what you manipulate
2. Production Brain: Claude Code skills + CLI, not MCP (v1)
3. Subtitles: SRT canonical format
4. Speaker diarization: fully deferred to v2
5. Review timeline UX: Kdenlive guide markers + external markdown report
6. Transitions: direct apply to working copy, snapshots for rollback
7. Distribution: Claude Code plugin marketplace from day 1
8. OTIO: skip for v1
9. Whisper model: `small` default, configurable
10. Obsidian folders: configurable with sensible defaults

**Technology stack:** Python 3.12+, FastMCP/mcp-python, FFmpeg/ffprobe, faster-whisper, Pydantic, Jinja2, pytest, pyproject.toml + uvx

## Requirements

1. The ForgeFrame repo MUST be a valid Claude Code plugin marketplace (`.claude-plugin/marketplace.json`)
2. The `workshop-video-brain` plugin MUST install via `/plugin install workshop-video-brain@forgeframe`
3. Installation MUST provide 5 Claude Code skills: `/ff-video-idea-to-outline`, `/ff-tutorial-script`, `/ff-shot-plan`, `/ff-obsidian-video-note`, `/ff-rough-cut-review`
4. Installation MUST start a Kdenlive Edit MCP server via `.mcp.json`
5. The MCP server MUST expose workspace, media, transcript, markers, timeline, project, transitions, subtitles, and render tool namespaces
6. The MCP server MUST expose read-only resources for workspace state, media catalog, transcripts, markers, timelines, validation, and render logs
7. All project mutations MUST target working copies, never originals
8. Snapshots MUST be created before every write operation on project files
9. The workspace model MUST support the standard folder layout (media/raw, media/proxies, transcripts, markers, projects/working_copies, projects/snapshots, renders, reports, logs)
10. Obsidian notes MUST use HTML comment boundaries (`<!-- wvb:section:name -->`) for safe section replacement
11. Frontmatter updates MUST merge, never overwrite unrelated fields
12. Media scanning MUST use ffprobe and handle bad files gracefully (isolate errors, don't crash batch)
13. Proxy generation MUST be automatic by default with configurable thresholds
14. Transcript generation MUST use faster-whisper first, Whisper fallback, offline-capable
15. Auto-markers MUST include confidence score, source method, and rationale for every marker
16. Review timelines MUST support best-guess-first ranking and chronological fallback
17. The Kdenlive adapter MUST preserve unknown XML elements via opaque passthrough
18. Generated .kdenlive projects MUST open in Kdenlive 25.12-era without errors
19. Each skill MUST produce dual output: human-readable markdown + machine-readable JSON
20. A CLI MUST mirror all core MCP capabilities for local use without MCP

## Sub-Specs

### Sub-Spec 1: Bootstrap + Plugin Scaffold
**Scope:** Repository structure, plugin marketplace manifest, dependency setup, config loader, MCP server skeleton.

**Files:**
- `.claude-plugin/marketplace.json`
- `workshop-video-brain/plugin.json`
- `workshop-video-brain/.mcp.json`
- `workshop-video-brain/src/workshop_video_brain/__init__.py`
- `workshop-video-brain/src/workshop_video_brain/server.py`
- `workshop-video-brain/src/workshop_video_brain/app/config.py`
- `workshop-video-brain/src/workshop_video_brain/app/logging.py`
- `workshop-video-brain/src/workshop_video_brain/app/paths.py`
- `workshop-video-brain/skills/ff-*/SKILL.md` (5 stub skills)
- `pyproject.toml`
- `.env.example`
- `README.md`
- `docs/adr/001-python-stack.md`
- `docs/adr/002-file-based-integration.md`
- `docs/adr/003-copy-first-safety.md`
- `docs/adr/004-two-module-architecture.md`

**Acceptance criteria:**
- [ ] `.claude-plugin/marketplace.json` validates against Claude Code marketplace schema
- [ ] `plugin.json` declares all 5 skills and is valid JSON
- [ ] `.mcp.json` points to a runnable Python MCP server command
- [ ] `pyproject.toml` includes dependency groups: runtime, dev, test
- [ ] Config loader reads `.env` / environment variables for: vault path, workspace root, ffmpeg path, whisper model
- [ ] Config loader reports missing optional tools (ffmpeg, whisper) without crashing
- [ ] MCP server starts and responds to a `ping` tool call
- [ ] 5 stub SKILL.md files exist with valid frontmatter (name, description)
- [ ] 4 ADRs written in `docs/adr/`
- [ ] README.md includes project description and installation instructions

**Dependencies:** none

### Sub-Spec 2: Core Models + Workspace + Obsidian
**Scope:** Shared Pydantic data models, path utilities, structured logging, snapshot safety, workspace folder conventions, Obsidian vault integration with note CRUD and templates.

**Files:**
- `workshop-video-brain/src/workshop_video_brain/core/models/*.py` (MediaAsset, Transcript, TranscriptSegment, Marker, MarkerGroup, ShotPlan, Shot, ScriptDraft, ReviewNote, TimelineIntent, TransitionIntent, SubtitleCue, RenderJob, SnapshotRecord, VideoProject, Workspace, enums)
- `workshop-video-brain/src/workshop_video_brain/core/utils/paths.py`
- `workshop-video-brain/src/workshop_video_brain/core/utils/naming.py`
- `workshop-video-brain/src/workshop_video_brain/app/logging.py` (expand from stub)
- `workshop-video-brain/src/workshop_video_brain/workspace/manager.py`
- `workshop-video-brain/src/workshop_video_brain/workspace/manifest.py`
- `workshop-video-brain/src/workshop_video_brain/workspace/snapshot.py`
- `workshop-video-brain/src/workshop_video_brain/workspace/folders.py`
- `workshop-video-brain/src/workshop_video_brain/production_brain/notes/frontmatter.py`
- `workshop-video-brain/src/workshop_video_brain/production_brain/notes/writer.py`
- `workshop-video-brain/src/workshop_video_brain/production_brain/notes/updater.py`
- `workshop-video-brain/src/workshop_video_brain/production_brain/notes/templates/*.md`
- `templates/obsidian/*.md` (6 templates)
- `tests/unit/test_models.py`
- `tests/unit/test_paths.py`
- `tests/unit/test_snapshot.py`
- `tests/unit/test_frontmatter.py`
- `tests/unit/test_note_updater.py`
- `tests/fixtures/vault/` (sample vault structure)

**Acceptance criteria:**
- [ ] All Pydantic models serialize to JSON and YAML, round-trip cleanly
- [ ] Enums for status (idea, outlining, scripting, filming, ingesting, editing, review, rendering, published, archived), marker categories, job status documented
- [ ] Path utilities produce collision-safe filenames, handle illegal chars, support versioned naming
- [ ] Structured logging writes per-job log files with machine-readable format
- [ ] `workspace.create()` produces all standard folders (media/raw, media/proxies, transcripts, markers, projects/source, projects/working_copies, projects/snapshots, renders/preview, renders/final, reports, logs)
- [ ] `workspace.yaml` manifest round-trips with all required fields
- [ ] `snapshot.create()` copies project file + manifest state before mutation
- [ ] `snapshot.restore()` recovers to prior state
- [ ] No code path exists that overwrites a file in `media/raw/` or `projects/source/`
- [ ] Obsidian note writer creates notes with valid YAML frontmatter and markdown body
- [ ] Obsidian note updater merges frontmatter without clobbering unrelated fields
- [ ] Section-bounded updates replace only the bounded section, leaving everything else intact
- [ ] Unbounded sections are appended to, never overwritten
- [ ] Re-running updater with same content doesn't duplicate sections
- [ ] 6 Obsidian templates exist: idea, in-progress, shot plan, transcript, edit review, publish checklist

**Dependencies:** Sub-Spec 1

### Sub-Spec 3: Media Pipeline + Transcripts
**Scope:** Media inventory scanning via ffprobe, automatic proxy generation, transcript generation via faster-whisper, silence detection, loudness analysis.

**Files:**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/probe.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/proxy.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/ffmpeg/silence.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/stt/whisper_engine.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/ingest.py`
- `tests/unit/test_probe.py`
- `tests/unit/test_proxy.py`
- `tests/integration/test_ingest_pipeline.py`
- `tests/fixtures/media/` (small sample media files)

**Acceptance criteria:**
- [ ] `probe.py` extracts: path, container, video/audio codec, duration, fps, width, height, aspect ratio, channels, sample rate, bitrate, creation time, file size, hash
- [ ] Scanner handles mixed media folders with video, audio, images, and corrupt files without crashing
- [ ] Bad files produce isolated error entries, not pipeline crashes
- [ ] `proxy.py` generates proxies when: resolution > threshold, codec in heavy list, bitrate > threshold
- [ ] Proxy thresholds are configurable via workspace config
- [ ] Proxies map back to source assets deterministically (naming convention)
- [ ] Existing valid proxies are not regenerated on re-run
- [ ] `whisper_engine.py` produces: full text transcript, timestamped segments, SRT export, JSON export
- [ ] Whisper model size configurable (default: `small`)
- [ ] Engine falls back gracefully if faster-whisper unavailable (try whisper, then error)
- [ ] `silence.py` detects silence gaps > configurable threshold and stores them per asset
- [ ] All analysis artifacts stored in workspace under `transcripts/` and `markers/`
- [ ] Ingest pipeline is idempotent: re-running skips already-processed assets

**Dependencies:** Sub-Spec 2

### Sub-Spec 4a: Auto-Marking + Review Ranking
**Scope:** Marker taxonomy, transcript-to-marker heuristics, confidence scoring, clip ranking, selects list abstraction.

**Files:**
- `workshop-video-brain/src/workshop_video_brain/core/models/markers.py` (expand marker enums/taxonomy)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/auto_mark.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/review_timeline.py` (ranking logic only)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/selects_timeline.py` (abstraction only)
- `tests/unit/test_auto_mark.py`
- `tests/unit/test_ranking.py`
- `tests/fixtures/transcripts/` (sample transcript JSON)

**Acceptance criteria:**
- [ ] 14 marker categories defined: intro_candidate, hook_candidate, materials_mention, step_explanation, measurement_detail, important_caution, mistake_problem, fix_recovery, broll_candidate, closeup_needed, dead_air, repetition, ending_reveal, chapter_candidate
- [ ] Every generated marker includes: category, confidence_score (0.0-1.0), source_method, reason (human-readable), clip_ref, time_range (start_seconds, end_seconds)
- [ ] Marker generation from transcript uses keyword/rule-based matching (configurable keyword lists)
- [ ] Marker generation from silence detection flags gaps > threshold as dead_air
- [ ] Nearby segments (< configurable gap) are grouped into marker ranges
- [ ] Best-guess-first ranking scores markers by: confidence * category_weight
- [ ] Category weights are configurable (defaults: chapter_candidate=1.0, step_explanation=0.9, mistake_problem=0.8, etc.)
- [ ] Chronological fallback ordering available as alternate sort
- [ ] Selects list outputs as JSON with per-clip time ranges, reason, and estimated usefulness score
- [ ] Selects list also exports as human-readable markdown
- [ ] Marker generation is deterministic for same inputs and config
- [ ] Unit tests cover: single-speaker tutorial, multi-clip footage, empty transcript, all-silence input

**Dependencies:** Sub-Spec 3

### Sub-Spec 4b: Kdenlive Adapter + Timelines + Subtitles
**Scope:** Kdenlive project model, XML parser with opaque passthrough, writer producing versioned copies, project validator, timeline intent model, selects timeline generator, chapter markers, subtitle handoff (SRT).

**Files:**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/parser.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/serializer.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/validator.py`
- `workshop-video-brain/src/workshop_video_brain/core/models/kdenlive.py` (internal project model)
- `workshop-video-brain/src/workshop_video_brain/core/models/timeline.py` (timeline intent model)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/review_timeline.py` (complete: ranked → Kdenlive)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/selects_timeline.py` (complete: selects → Kdenlive)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/subtitle_pipeline.py`
- `tests/unit/test_kdenlive_parser.py`
- `tests/unit/test_kdenlive_writer.py`
- `tests/unit/test_validator.py`
- `tests/integration/test_kdenlive_roundtrip.py`
- `tests/fixtures/projects/*.kdenlive` (sample Kdenlive project files)

**Acceptance criteria:**
- [ ] Kdenlive internal model covers: project metadata, media references (bins), tracks, clips with in/out points, gaps, markers/guides, subtitle references, transition/composition stubs, render profile references
- [ ] Parser reads `.kdenlive` XML into internal model
- [ ] Unknown XML elements/attributes are preserved as opaque nodes (not discarded)
- [ ] Parser captures Kdenlive document version
- [ ] Parser fails gracefully on unsupported constructs (returns validation warning, not crash)
- [ ] Writer outputs versioned `.kdenlive` files to `projects/working_copies/`
- [ ] Writer creates snapshot before writing
- [ ] Written project opens in Kdenlive without errors (manual QA step)
- [ ] Validator checks: media path existence, clip range validity, track integrity, marker range validity, required metadata presence
- [ ] Validator returns structured report with severity levels: info, warning, error, blocking_error
- [ ] Timeline intent model supports operations: add_clip, trim_clip, insert_gap, add_marker, add_subtitle_region, add_transition, create_track
- [ ] Review timeline generator creates a Kdenlive project with clips ordered by ranking score
- [ ] Review timeline includes Kdenlive guide markers with labels explaining why each segment was included
- [ ] External markdown review report generated alongside the project
- [ ] Selects timeline generator creates a filtered Kdenlive project from approved marker ranges
- [ ] Chapter marker generator identifies chapter_candidate markers and exports to Kdenlive guides + note
- [ ] Subtitle pipeline converts transcript segments to SRT with configurable max line length and duration
- [ ] SRT files import cleanly into Kdenlive (manual QA step)

**Dependencies:** Sub-Spec 4a

### Sub-Spec 5: Production Brain Skills + Transitions + Render
**Scope:** Complete SKILL.md files for all 5 skills, Python skill engine implementations, rough-cut review generator, transition abstraction and helpers, render profiles and job launcher.

**Files:**
- `workshop-video-brain/skills/ff-video-idea-to-outline/SKILL.md` (complete)
- `workshop-video-brain/skills/ff-tutorial-script/SKILL.md` (complete)
- `workshop-video-brain/skills/ff-shot-plan/SKILL.md` (complete)
- `workshop-video-brain/skills/ff-obsidian-video-note/SKILL.md` (complete)
- `workshop-video-brain/skills/ff-rough-cut-review/SKILL.md` (complete)
- `workshop-video-brain/src/workshop_video_brain/production_brain/skills/outline.py`
- `workshop-video-brain/src/workshop_video_brain/production_brain/skills/script.py`
- `workshop-video-brain/src/workshop_video_brain/production_brain/skills/shot_plan.py`
- `workshop-video-brain/src/workshop_video_brain/production_brain/skills/video_note.py`
- `workshop-video-brain/src/workshop_video_brain/production_brain/skills/review.py`
- `workshop-video-brain/src/workshop_video_brain/core/models/transitions.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/kdenlive/patcher.py` (extend with transition application)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/render/profiles.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/render/jobs.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/render/executor.py`
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/render_pipeline.py`
- `templates/render/*.yaml` (preview, draft-youtube, final-youtube profiles)
- `tests/unit/test_skills.py`
- `tests/unit/test_transitions.py`
- `tests/unit/test_render_profiles.py`

**Acceptance criteria:**
- [ ] Each SKILL.md has valid frontmatter with name (kebab-case) and description (includes trigger phrases)
- [ ] SKILL.md descriptions under 250 chars, include WHAT and WHEN, no XML tags
- [ ] `/ff-video-idea-to-outline` produces: viewer promise, materials list, teaching beats, pain points, chapter structure, open questions
- [ ] `/ff-tutorial-script` produces: intro hook, project overview, materials section, ordered steps, common mistakes, conclusion
- [ ] `/ff-shot-plan` produces: A-roll, overhead bench, detail closeups, measurement shots, inserts, glamour B-roll, pickup list
- [ ] `/ff-obsidian-video-note` creates new note from template OR updates existing note preserving manual edits
- [ ] `/ff-rough-cut-review` identifies: pacing drags, repetition, missing inserts, overlay opportunities, chapter breaks
- [ ] All skill Python implementations emit dual output: markdown string + structured dict/JSON
- [ ] Transition model supports: crossfade, dissolve, fade_in, fade_out, audio_crossfade
- [ ] Each transition instruction includes: type, track_ref, left_clip_ref, right_clip_ref, duration_frames, reason
- [ ] Crossfade helper calculates overlap and falls back safely if overlap is insufficient
- [ ] Duration presets: short (12 frames), medium (24 frames), long (48 frames)
- [ ] Transitions applied directly to working copy Kdenlive project (with pre-snapshot)
- [ ] Render profiles defined in YAML: preview (720p fast), draft-youtube (1080p medium), final-youtube (1080p high)
- [ ] Render job launcher executes via Kdenlive CLI / melt, captures logs
- [ ] Render job model tracks: job_id, workspace_id, project_path, profile, output_path, status, timestamps, log_path
- [ ] Render artifact registry records what was rendered from which project version

**Dependencies:** Sub-Spec 4b

### Sub-Spec 6: MCP Tools + CLI + Integration Testing + Docs
**Scope:** Full MCP tool and resource surface, CLI entrypoints, end-to-end testing, documentation.

**Files:**
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (complete all tools)
- `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/resources.py` (complete all resources)
- `workshop-video-brain/src/workshop_video_brain/app/cli.py`
- `tests/integration/test_mcp_tools.py`
- `tests/integration/test_obsidian_lifecycle.py`
- `tests/integration/test_kdenlive_roundtrip.py` (expand)
- `tests/integration/test_end_to_end.py`
- `docs/developer-setup.md`
- `docs/user-workflow.md`
- `docs/ai-handoff.md`

**Acceptance criteria:**
- [ ] MCP tools registered and callable: workspace_create, workspace_status, media_ingest, media_list_assets, proxy_generate, transcript_generate, transcript_export, markers_auto_generate, markers_list, timeline_build_review, timeline_build_selects, project_create_working_copy, project_validate, project_summary, transitions_apply, transitions_batch_apply, subtitles_generate, subtitles_import, subtitles_export, render_preview, render_final, render_status, snapshot_list, snapshot_restore
- [ ] Each MCP tool validates inputs and returns structured JSON output
- [ ] MCP resources readable: workspace://current/summary, workspace://{id}/media-catalog, workspace://{id}/transcript-index, workspace://{id}/markers, workspace://{id}/timeline-summary, workspace://{id}/validation, workspace://{id}/render-logs, system://capabilities
- [ ] CLI commands mirror MCP: `wvb workspace create`, `wvb media ingest`, `wvb transcript generate`, `wvb markers auto`, `wvb timeline review`, `wvb timeline selects`, `wvb project validate`, `wvb render preview`, `wvb plan outline`, `wvb plan script`, `wvb plan shots`
- [ ] `wvb prepare-tutorial-project <media-folder>` runs full pipeline: init workspace → scan → proxies → transcribe → mark → note → selects → Kdenlive project
- [ ] End-to-end test: ingest sample media → auto-proxy → transcribe → mark → rank → selects → update Obsidian note → generate Kdenlive project → validate → all artifacts present and coherent
- [ ] Developer setup guide covers: Python 3.12+ install, FFmpeg, faster-whisper model download, vault config, running tests, running server
- [ ] User workflow guide covers: plugin install, workspace creation, note workflow, marker review, opening Kdenlive project, what's automated vs manual
- [ ] AI handoff notes cover: module boundaries, dangerous areas (Kdenlive XML, Obsidian merge), assumptions, extension ideas, known limitations

**Dependencies:** Sub-Spec 5

## Edge Cases

1. **Media folder contains no video files** -- Scanner completes with empty inventory, markers pipeline skips, review timeline is empty. User sees clear message: "No video files found in {path}."
2. **FFmpeg not installed** -- Config loader reports "ffmpeg not found." Media scanning, proxy generation, and silence detection disabled. Transcript generation still attempts (whisper extracts audio internally). MCP tools return structured error.
3. **Whisper not installed** -- Config loader reports "faster-whisper not found, whisper not found." Transcript tools return error. Marker generation falls back to silence-only if ffmpeg available, or skips entirely.
4. **Corrupt .kdenlive file** -- Parser returns validation report with blocking_error. No working copy created. User sees specific parse error.
5. **Obsidian vault path doesn't exist** -- Config warns at startup. Note-related skills and tools return error with suggestion to set WVB_VAULT_PATH. Media/edit pipeline still works.
6. **Re-running pipeline on already-processed workspace** -- Idempotent. Existing proxies, transcripts, markers skipped. Only new/changed media processed.
7. **Working copy .kdenlive opened in Kdenlive while pipeline runs** -- File locking not implemented v1. Documented as "close Kdenlive before running pipeline mutations." Snapshots provide recovery.
8. **Extremely long video (>2 hours)** -- Whisper processes in segments. Proxy generation may take time. Progress reported via structured logging. No in-memory loading of full file.

## Out of Scope

- Speaker diarization / labeling (v2)
- OTIO integration (v2, if multi-editor needed)
- Production Brain as MCP tools (v2)
- Advanced Kdenlive effects, color grading, keyframe authoring
- GUI automation (xdotool, OCR)
- Cloud/paid STT services
- Multi-user collaboration
- Thumbnail generation pipeline
- Social media auto-reframing
- Live bridge to running Kdenlive session
- Music/beat-sync editing

## Verification

End-to-end verification that the whole system works:

1. Clone ForgeFrame repo
2. Run `/plugin marketplace add ./` -- marketplace loads without errors
3. Run `/plugin install workshop-video-brain@forgeframe` -- skills appear in `/` menu, MCP server starts
4. Run `/ff-video-idea-to-outline "I want to make a tutorial about sewing a zippered pouch for bikepacking"` -- produces structured outline
5. Run `wvb workspace create --title "Zippered Pouch" --media-root ./sample-footage/` -- workspace created with all folders
6. Run `wvb media ingest` -- media scanned, proxies generated for large files
7. Run `wvb transcript generate` -- transcripts produced with timestamps
8. Run `wvb markers auto` -- markers generated with confidence scores and rationale
9. Run `wvb timeline review` -- Kdenlive project created in working_copies/
10. Open the generated .kdenlive in Kdenlive -- project loads, guide markers visible, media plays
11. Run `/ff-obsidian-video-note` -- note created/updated in vault with outline, shot plan, transcript summary
12. Run `wvb project validate` -- validation report shows no blocking errors
13. Run `wvb render preview` -- preview video rendered to renders/preview/
