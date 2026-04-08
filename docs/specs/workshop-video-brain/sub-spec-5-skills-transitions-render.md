---
type: phase-spec
master_spec: "../2026-04-08-workshop-video-brain.md"
sub_spec: 5
title: "Production Brain Skills + Transitions + Render"
dependencies: ["4b"]
date: 2026-04-08
---

# Sub-Spec 5: Production Brain Skills + Transitions + Render

## Scope

Complete all 5 SKILL.md files with full instructions (not stubs), Python skill engine implementations producing dual output (markdown + JSON), rough-cut review generator, transition model and crossfade helpers, transition application in Kdenlive output, render profiles in YAML, render job launcher and artifact registry.

## Interface Contracts

### Provides (to Sub-Spec 6)

- **Complete skills** in `workshop-video-brain/skills/*/SKILL.md` -- full instructions, not stubs
- **Skill engines** in `production_brain/skills/`:
  - `outline.generate_outline(idea, project_type, audience, constraints) -> tuple[str, dict]` -- (markdown, structured_data)
  - `script.generate_script(outline, tone, target_length) -> tuple[str, dict]`
  - `shot_plan.generate_shot_plan(outline_or_script, gear_constraints) -> tuple[str, dict]`
  - `video_note.create_or_update_note(workspace, vault_path, data) -> Path`
  - `review.generate_review(transcript, markers, edit_notes) -> tuple[str, dict]`

- **Transition system**:
  - `TransitionType` enum: crossfade, dissolve, fade_in, fade_out, audio_crossfade
  - `TransitionInstruction(type, track_ref, left_clip, right_clip, duration_frames, reason)`
  - `calculate_crossfade(left_clip, right_clip, preset) -> TransitionInstruction`
  - Patcher method to apply transitions to Kdenlive project

- **Render system**:
  - `RenderProfile` model loaded from YAML
  - `launch_render(workspace, project_path, profile) -> RenderJob`
  - `RenderArtifactRegistry` tracking what was rendered from what

### Requires (from Sub-Spec 4b)

- Kdenlive project model, parser, serializer, patcher
- Workspace and Obsidian note infrastructure
- Transcript, marker, and selects models

## Implementation Steps

### Step 1: Complete SKILL.md files

Replace the 5 stub files with full instructions. Each SKILL.md should be 100-300 lines with:
- Valid frontmatter (name, description under 250 chars)
- Clear step-by-step instructions for Claude
- Examples of user queries and expected outputs
- Output format specification (markdown + JSON sidecar)
- References to the Python engine for data processing

Key: skills are PROMPT instructions, not executable code. They tell Claude HOW to use the tools and format output. The Python engine does the data manipulation.

### Step 2: Create outline skill engine

**Create** `production_brain/skills/outline.py`:
- `generate_outline(idea, project_type=None, audience=None, constraints=None) -> tuple[str, dict]`
- Returns markdown with sections: Viewer Promise, What We're Making, Materials & Tools, Teaching Beats, Pain Points, Chapter Structure, Open Questions
- Also returns structured dict with same data for consumption by other modules
- This is a template engine, not an LLM call -- the SKILL.md prompts Claude, the engine structures the output

### Step 3: Create script skill engine

**Create** `production_brain/skills/script.py`:
- `generate_script(outline_data, tone="practical", target_length=None) -> tuple[str, dict]`
- Sections: Hook, Project Overview, Materials, Step-by-Step, Common Mistakes, Conclusion
- Structured output maps each section to its content

### Step 4: Create shot plan skill engine

**Create** `production_brain/skills/shot_plan.py`:
- `generate_shot_plan(outline_or_script_data, gear_constraints=None) -> tuple[str, dict]`
- Categories: A-roll, Overhead/Bench, Detail Closeups, Measurement, Inserts, Glamour B-roll, Pickup Shots
- Each shot has: type, description, beat_ref, priority

### Step 5: Create video note skill engine

**Create** `production_brain/skills/video_note.py`:
- `create_or_update_note(workspace, vault_path, data) -> Path`
- Uses NoteWriter and NoteUpdater from Sub-Spec 2
- Creates new note from template if doesn't exist
- Updates sections via bounded section markers if note exists
- Frontmatter sync from workspace manifest
- Returns path to created/updated note

### Step 6: Create review skill engine

**Create** `production_brain/skills/review.py`:
- `generate_review(transcript, markers, edit_notes=None) -> tuple[str, dict]`
- Analyzes: pacing (long segments without cuts), repetition (similar text segments), missing visually (segments mentioning detail without closeup marker), overlay opportunities (measurements, lists), chapter breaks (natural topic shifts)
- Output: markdown review note + structured findings

### Step 7: Create transition model

**Create** `core/models/transitions.py`:
- `TransitionType` enum: crossfade, dissolve, fade_in, fade_out, audio_crossfade
- `TransitionPreset` enum: short (12 frames), medium (24 frames), long (48 frames)
- `TransitionInstruction` Pydantic model: type, track_ref, left_clip_ref, right_clip_ref, duration_frames, audio_link_behavior, reason

### Step 8: Create crossfade helper

**Add to** patcher or new file `edit_mcp/adapters/kdenlive/transitions.py`:
- `calculate_crossfade(left_clip, right_clip, preset=TransitionPreset.MEDIUM) -> TransitionInstruction`
- Checks if clips are adjacent, calculates overlap
- Falls back to shorter duration if overlap is insufficient
- Returns instruction with reason explaining the choice

### Step 9: Extend Kdenlive patcher with transitions

**Extend** `edit_mcp/adapters/kdenlive/patcher.py`:
- Handle `AddTransition` intent
- Apply transition XML to the Kdenlive project (same-track mix elements)
- Create snapshot before applying

### Step 10: Create render profiles

**Create** `templates/render/`:
- `preview.yaml`: 720p, fast encoding, low bitrate
- `draft-youtube.yaml`: 1080p, medium quality, standard YouTube settings
- `final-youtube.yaml`: 1080p, high quality, optimized for YouTube

**Create** `edit_mcp/adapters/render/profiles.py`:
- `RenderProfile` Pydantic model: name, width, height, fps, codec, bitrate, audio_codec, audio_bitrate, extra_params
- `load_profile(name) -> RenderProfile` -- loads from YAML templates
- `list_profiles() -> list[str]`

### Step 11: Create render job launcher

**Create** `edit_mcp/adapters/render/jobs.py`:
- `RenderJob` model (already in core models -- use it)
- `launch_render(workspace, project_path, profile, mode="preview") -> RenderJob`
- Runs `melt` or `kdenlive-render` CLI with profile settings
- Output path: `renders/{mode}/{title}_{timestamp}.mp4`
- Captures stdout/stderr to log file

**Create** `edit_mcp/adapters/render/executor.py`:
- Subprocess execution wrapper
- Progress parsing from melt output if available
- Timeout handling

### Step 12: Create render artifact registry

**Create** `edit_mcp/pipelines/render_pipeline.py`:
- `RenderArtifactRegistry`: tracks renders in workspace manifest
- `register_render(workspace, job) -> None` -- adds to manifest
- `list_renders(workspace) -> list[RenderJob]`
- Each entry: job_id, source project path + version, profile, output path, timestamp

### Step 13: Write tests

- `tests/unit/test_skills.py` -- each engine returns (markdown_str, dict), dict has expected keys
- `tests/unit/test_transitions.py` -- crossfade calculation, preset durations, insufficient overlap fallback
- `tests/unit/test_render_profiles.py` -- YAML loading, profile field validation

## Verification Commands

```bash
uv run pytest tests/unit/test_skills.py tests/unit/test_transitions.py tests/unit/test_render_profiles.py -v

# Verify skill files have valid frontmatter
python -c "
import yaml
for skill in ['video-idea-to-outline', 'tutorial-script', 'shot-plan', 'obsidian-video-note', 'rough-cut-review']:
    with open(f'workshop-video-brain/skills/{skill}/SKILL.md') as f:
        content = f.read()
        assert content.startswith('---')
        fm = content.split('---')[1]
        data = yaml.safe_load(fm)
        assert 'name' in data
        assert 'description' in data
        assert len(data['description']) <= 250
        print(f'{skill}: PASS')
"
```

## Acceptance Criteria

- [ ] Each SKILL.md has valid frontmatter with name (kebab-case) and description (includes trigger phrases, under 250 chars)
- [ ] All 5 skills produce expected output sections
- [ ] All skill engines emit dual output: markdown string + structured dict/JSON
- [ ] `/obsidian-video-note` creates new or updates existing, preserving manual edits
- [ ] Transition model supports: crossfade, dissolve, fade_in, fade_out, audio_crossfade
- [ ] Crossfade helper calculates overlap and falls back safely
- [ ] Duration presets: short (12), medium (24), long (48 frames)
- [ ] Transitions applied directly to working copy with pre-snapshot
- [ ] Render profiles defined in YAML for preview, draft-youtube, final-youtube
- [ ] Render job launcher executes and captures logs
- [ ] Render artifact registry records source project version
