---
type: phase-spec
master_spec: "../2026-04-08-workshop-video-brain.md"
sub_spec: 2
title: "Core Models + Workspace + Obsidian"
dependencies: [1]
date: 2026-04-08
---

# Sub-Spec 2: Core Models + Workspace + Obsidian

## Scope

Shared Pydantic data models with JSON/YAML serialization, path utilities with collision-safe naming, structured logging with per-job files, snapshot/copy-first safety layer, workspace folder conventions and initializer, Obsidian vault integration (note CRUD, frontmatter merge, section-aware updates), 6 Obsidian note templates, unit tests.

## Interface Contracts

### Provides (to Sub-Spec 3+)

- **All shared models** in `core/models/` -- importable Pydantic v2 models:
  - `MediaAsset(id, path, relative_path, media_type, container, video_codec, audio_codec, duration, fps, width, height, aspect_ratio, channels, sample_rate, bitrate, created_at, file_size, hash, proxy_path, proxy_status, transcript_status, analysis_status)`
  - `Transcript(id, asset_id, engine, model, language, segments: list[TranscriptSegment], raw_text, created_at)`
  - `TranscriptSegment(start_seconds, end_seconds, text, confidence, words: list[WordTiming] | None)`
  - `Marker(id, category: MarkerCategory, confidence_score: float, source_method: str, reason: str, clip_ref: str, start_seconds: float, end_seconds: float, suggested_label: str)`
  - `ShotPlan(shots: list[Shot])`, `Shot(type: ShotType, description, beat_ref, priority)`
  - `ScriptDraft(sections: dict[str, str], tone, target_length)`
  - `ReviewNote(pacing_notes, repetition_flags, insert_suggestions, overlay_ideas, chapter_breaks)`
  - `RenderJob(id, workspace_id, project_path, profile, output_path, mode, status: JobStatus, started_at, completed_at, log_path)`
  - `SnapshotRecord(id, workspace_id, timestamp, project_file_path, manifest_snapshot, description)`
  - `VideoProject(id, title, slug, status: ProjectStatus, content_type, created_at, updated_at)`
  - `Workspace(id, project: VideoProject, media_root, vault_note_path, config: dict)`

- **Enums**: `ProjectStatus`, `MarkerCategory` (14 categories), `JobStatus`, `ShotType`, `ProxyStatus`, `TranscriptStatus`, `AnalysisStatus`, `ValidationSeverity`

- **Path utilities** in `core/utils/`:
  - `safe_filename(name: str) -> str` -- strip illegal chars, truncate, ensure uniqueness
  - `versioned_path(base: Path, extension: str) -> Path` -- append version number if exists
  - `workspace_relative(absolute: Path, workspace_root: Path) -> str`

- **Workspace manager** in `workspace/`:
  - `WorkspaceManager.create(title: str, media_root: Path, config: Config) -> Workspace`
  - `WorkspaceManager.open(path: Path) -> Workspace`
  - `WorkspaceManager.save_manifest(workspace: Workspace) -> None`
  - `SnapshotManager.create(workspace: Workspace, description: str) -> SnapshotRecord`
  - `SnapshotManager.restore(workspace: Workspace, snapshot_id: str) -> None`
  - `SnapshotManager.list(workspace: Workspace) -> list[SnapshotRecord]`

- **Obsidian note manager** in `production_brain/notes/`:
  - `NoteWriter.create(vault_path: Path, template: str, frontmatter: dict, sections: dict) -> Path`
  - `NoteUpdater.update_frontmatter(note_path: Path, updates: dict) -> None`
  - `NoteUpdater.update_section(note_path: Path, section_name: str, content: str) -> None`
  - `NoteUpdater.append_section(note_path: Path, section_name: str, content: str) -> None`
  - `FrontmatterParser.read(note_path: Path) -> dict`
  - `FrontmatterParser.write(note_path: Path, frontmatter: dict, body: str) -> None`

### Requires (from Sub-Spec 1)

- Config loader at `app/config.py`
- Logging setup at `app/logging.py`
- Package structure with `__init__.py` files

## Patterns to Follow

- **Pydantic v2**: Use `model_dump()` / `model_validate()` / `model_dump_json()`. Add `to_yaml()` / `from_yaml()` methods using `pyyaml`.
- **Enums**: `class ProjectStatus(str, Enum)` with `model_config = {"use_enum_values": True}` on models.
- **Frontmatter**: Parse with `yaml.safe_load()` between `---` delimiters. Merge by updating dict, not replacing.
- **Section boundaries**: `<!-- wvb:section:name -->` ... `<!-- /wvb:section:name -->`. Regex: `r'<!-- wvb:section:(\w[\w-]*) -->(.*?)<!-- /wvb:section:\1 -->'` with `re.DOTALL`.
- **Snapshot**: Copy file to `projects/snapshots/{timestamp}-{description}/`, save manifest YAML alongside.

## Implementation Steps

### Step 1: Create enum definitions

**Create** `core/models/enums.py` with all enums: `ProjectStatus`, `MarkerCategory` (14 values), `JobStatus` (queued/running/succeeded/failed/cancelled), `ShotType`, `ProxyStatus`, `TranscriptStatus`, `AnalysisStatus`, `ValidationSeverity` (info/warning/error/blocking_error).

### Step 2: Create core data models

**Create** individual model files in `core/models/`:
- `media.py` -- MediaAsset, MediaTechnicalProfile
- `transcript.py` -- Transcript, TranscriptSegment, WordTiming
- `markers.py` -- Marker, MarkerGroup
- `planning.py` -- ShotPlan, Shot, ScriptDraft, ReviewNote, MaterialList
- `timeline.py` -- TimelineIntent, TransitionIntent, SubtitleCue
- `project.py` -- VideoProject, Workspace, RenderJob, SnapshotRecord
- `validation.py` -- ValidationReport, ValidationItem

Each model: Pydantic BaseModel with `to_yaml()`, `from_yaml()`, `to_json()`, `from_json()` methods. Include `id` (UUID default factory), timestamps where appropriate.

**Create** `core/models/__init__.py` re-exporting all models.

### Step 3: Create path utilities

**Create** `core/utils/paths.py`:
- `safe_filename()` -- strip `<>:"/\|?*`, replace spaces with hyphens, truncate to 200 chars
- `versioned_path()` -- if file exists, append `-1`, `-2`, etc.
- `workspace_relative()` -- return path relative to workspace root
- `ensure_dir()` -- create directory if missing, return path

**Create** `core/utils/naming.py`:
- `slugify()` -- lowercase, hyphens, strip special chars
- `timestamp_prefix()` -- `YYYY-MM-DD-HHMMSS` prefix

### Step 4: Create structured logging

**Expand** `app/logging.py`:
- JSON log formatter for structured output
- `setup_logging(workspace_path=None, job_id=None)` -- configures root logger + optional file handler at `{workspace}/logs/{job_id}.jsonl`
- Log record includes: timestamp, level, module, message, job_id (if set)

### Step 5: Create workspace folder conventions

**Create** `workspace/folders.py`:
- `WORKSPACE_FOLDERS` constant listing all required directories
- `create_workspace_structure(root: Path) -> None` -- creates all folders
- `validate_workspace_structure(root: Path) -> list[str]` -- returns missing folders

Standard folders: `media/raw`, `media/proxies`, `media/derived_audio`, `transcripts`, `markers`, `projects/source`, `projects/working_copies`, `projects/snapshots`, `renders/preview`, `renders/final`, `reports`, `logs`

### Step 6: Create workspace manifest

**Create** `workspace/manifest.py`:
- `WorkspaceManifest` Pydantic model with all fields from spec (workspace_id, project_title, slug, status, created_at, updated_at, content_type, vault_note_path, media_root, proxy_policy, stt_engine, etc.)
- `read_manifest(workspace_root: Path) -> WorkspaceManifest`
- `write_manifest(workspace_root: Path, manifest: WorkspaceManifest) -> None`
- YAML format in `workspace.yaml`

### Step 7: Create snapshot manager

**Create** `workspace/snapshot.py`:
- `SnapshotManager` class
- `create(workspace_root, file_to_snapshot, description) -> SnapshotRecord` -- copies file to `projects/snapshots/{timestamp}-{slug}/`, saves metadata YAML
- `restore(workspace_root, snapshot_id) -> None` -- copies snapshot file back
- `list_snapshots(workspace_root) -> list[SnapshotRecord]`

### Step 8: Create workspace manager

**Create** `workspace/manager.py`:
- `WorkspaceManager` class tying together folders, manifest, and snapshots
- `create(title, media_root, config) -> Workspace` -- creates structure, writes initial manifest
- `open(path) -> Workspace` -- reads existing manifest, validates structure
- `update_status(workspace, new_status) -> None`

### Step 9: Create frontmatter parser

**Create** `production_brain/notes/frontmatter.py`:
- `parse_note(path: Path) -> tuple[dict, str]` -- returns (frontmatter_dict, body_text)
- `write_note(path: Path, frontmatter: dict, body: str) -> None` -- writes YAML frontmatter + body
- `merge_frontmatter(existing: dict, updates: dict) -> dict` -- deep merge, updates win on conflict, existing keys preserved

### Step 10: Create note writer

**Create** `production_brain/notes/writer.py`:
- `NoteWriter` class
- `create(vault_path, folder, filename, template_name, frontmatter, sections) -> Path`
- Uses Jinja2 to render templates from `templates/obsidian/`
- Ensures directory exists, won't overwrite existing files

### Step 11: Create note updater

**Create** `production_brain/notes/updater.py`:
- `NoteUpdater` class
- `update_frontmatter(note_path, updates)` -- reads, merges, writes
- `update_section(note_path, section_name, content)` -- finds `<!-- wvb:section:name -->` boundaries, replaces content between them
- `append_section(note_path, section_name, content)` -- if section boundaries exist, appends inside them; if not, appends at end of file
- Handles missing boundaries gracefully (append, don't error)

### Step 12: Create 6 Obsidian templates

**Create** in `templates/obsidian/`:
- `video-idea.md` -- minimal frontmatter (title, slug, status=idea, content_type, viewer_promise), sections: Summary, Viewer Promise, Materials and Tools, Teaching Beats
- `in-progress.md` -- full frontmatter, all sections from spec
- `shot-plan.md` -- shot-focused template with A-roll, overhead, closeups, inserts, pickups sections
- `transcript.md` -- transcript metadata frontmatter, sections: Full Transcript, Key Segments, Speaker Notes
- `edit-review.md` -- review-focused: Pacing Notes, Repetition, Missing Inserts, Chapter Ideas
- `publish-checklist.md` -- publish-focused: Title, Description, Tags, Chapters, Thumbnail, Social

### Step 13: Write unit tests

**Create** tests:
- `tests/unit/test_models.py` -- serialize/deserialize round-trip for each model, enum value coverage
- `tests/unit/test_paths.py` -- safe_filename with special chars, versioned_path collision handling, workspace_relative
- `tests/unit/test_snapshot.py` -- create/restore/list snapshots (use tmp_path fixture)
- `tests/unit/test_frontmatter.py` -- parse, write, merge (preserves unrelated keys, updates conflicts)
- `tests/unit/test_note_updater.py` -- section update (bounded), section append (unbounded), no duplication on re-run

## Verification Commands

```bash
# Run all unit tests
uv run pytest tests/unit/ -v

# Verify model round-trip
uv run python -c "
from workshop_video_brain.core.models import MediaAsset, Marker, MarkerCategory
m = MediaAsset(path='/test.mp4', media_type='video', duration=120.0)
assert MediaAsset.from_json(m.to_json()).path == '/test.mp4'
print('Model round-trip: PASS')
"

# Verify workspace creation
uv run python -c "
from pathlib import Path
from workshop_video_brain.workspace.folders import create_workspace_structure
import tempfile
with tempfile.TemporaryDirectory() as td:
    create_workspace_structure(Path(td))
    assert (Path(td) / 'media/raw').exists()
    assert (Path(td) / 'projects/snapshots').exists()
    print('Workspace structure: PASS')
"
```

## Acceptance Criteria

- [ ] All Pydantic models serialize to JSON and YAML, round-trip cleanly
- [ ] Enums for status, marker categories, job status documented
- [ ] Path utilities produce collision-safe filenames, handle illegal chars, support versioned naming
- [ ] Structured logging writes per-job log files with machine-readable format
- [ ] `workspace.create()` produces all standard folders
- [ ] `workspace.yaml` manifest round-trips with all required fields
- [ ] `snapshot.create()` copies project file + manifest state before mutation
- [ ] `snapshot.restore()` recovers to prior state
- [ ] No code path exists that overwrites a file in `media/raw/` or `projects/source/`
- [ ] Obsidian note writer creates notes with valid YAML frontmatter and markdown body
- [ ] Obsidian note updater merges frontmatter without clobbering unrelated fields
- [ ] Section-bounded updates replace only the bounded section, leaving everything else intact
- [ ] Unbounded sections are appended to, never overwritten
- [ ] Re-running updater with same content doesn't duplicate sections
- [ ] 6 Obsidian templates exist
