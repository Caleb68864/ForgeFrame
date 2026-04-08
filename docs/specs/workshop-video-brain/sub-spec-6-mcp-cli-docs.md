---
type: phase-spec
master_spec: "../2026-04-08-workshop-video-brain.md"
sub_spec: 6
title: "MCP Tools + CLI + Integration Testing + Docs"
dependencies: [5]
date: 2026-04-08
---

# Sub-Spec 6: MCP Tools + CLI + Integration Testing + Docs

## Scope

Complete MCP tool and resource registration on the server, CLI entrypoints mirroring all capabilities, end-to-end guided workflow command, integration tests for all major pipelines, end-to-end workflow test, developer setup guide, user workflow guide, AI handoff notes.

## Interface Contracts

### Provides

- **Complete MCP server** with all tools and resources registered
- **CLI** at `wvb` command with subcommands for every operation
- **`wvb prepare-tutorial-project`** guided workflow
- **Documentation** for developers, users, and future AI agents

### Requires (from Sub-Spec 5)

- All pipeline functions (ingest, auto_mark, review_timeline, selects_timeline, subtitle, render)
- All adapter functions (ffmpeg, whisper, kdenlive, render)
- All skill engines
- Workspace manager, snapshot manager
- Obsidian note writer/updater
- All core models

## Implementation Steps

### Step 1: Register MCP tools

**Expand** `edit_mcp/server/tools.py` -- register all tools using `@mcp.tool()`:

```python
@mcp.tool()
def workspace_create(title: str, media_root: str, vault_path: str | None = None) -> dict:
    """Create a new video project workspace."""
    ...

@mcp.tool()
def media_ingest(workspace_path: str) -> dict:
    """Scan media folder and catalog all assets."""
    ...
```

Full tool list:
- `workspace_create`, `workspace_status`, `workspace_snapshot_list`, `workspace_restore_snapshot`
- `media_ingest`, `media_list_assets`, `proxy_generate`
- `transcript_generate`, `transcript_export`
- `markers_auto_generate`, `markers_list`
- `timeline_build_review`, `timeline_build_selects`
- `project_create_working_copy`, `project_validate`, `project_summary`
- `transitions_apply`, `transitions_batch_apply`
- `subtitles_generate`, `subtitles_import`, `subtitles_export`
- `render_preview`, `render_final`, `render_status`

Each tool: validates inputs, calls the appropriate pipeline/adapter, returns structured JSON dict with status and results.

### Step 2: Register MCP resources

**Expand** `edit_mcp/server/resources.py`:

```python
@mcp.resource("workspace://current/summary")
def workspace_summary() -> str:
    """Current workspace state and status."""
    ...

@mcp.resource("workspace://{id}/media-catalog")
def media_catalog(id: str) -> str:
    """Media inventory for the workspace."""
    ...
```

Resources: workspace summary, media catalog, transcript index, markers, timeline summary, validation report, render logs, system capabilities.

### Step 3: Build CLI

**Expand** `app/cli.py` using Click groups:

```python
@main.group()
def workspace():
    """Workspace management."""

@workspace.command()
@click.argument("title")
@click.option("--media-root", required=True)
def create(title, media_root):
    """Create a new workspace."""
    ...

@main.group()
def media():
    """Media operations."""

@media.command()
def ingest():
    """Scan and catalog media."""
    ...
```

Groups: `workspace`, `media`, `transcript`, `markers`, `timeline`, `project`, `render`, `plan`

Under `plan`: `outline`, `script`, `shots`, `note`, `review`

### Step 4: Build guided workflow command

**Add** `prepare-tutorial-project` command:

```python
@main.command()
@click.argument("media_folder")
@click.option("--title", prompt=True)
@click.option("--vault-path")
def prepare_tutorial_project(media_folder, title, vault_path):
    """Full pipeline: workspace → scan → proxy → transcribe → mark → note → selects → Kdenlive project."""
    ...
```

Steps: create workspace → run ingest → generate markers → build selects → build review timeline → create/update Obsidian note → validate project → report summary.

### Step 5: Write MCP tool contract tests

**Create** `tests/integration/test_mcp_tools.py`:
- Test each tool with valid inputs, verify structured output
- Test each tool with invalid inputs, verify error response
- Test resource reads return valid content
- Use temporary workspace fixtures

### Step 6: Write Obsidian lifecycle integration test

**Create** `tests/integration/test_obsidian_lifecycle.py`:
- Create note from idea template
- Update frontmatter
- Append section content
- Update bounded section
- Re-run update (verify no duplication)
- Verify final note is valid markdown with correct frontmatter

### Step 7: Expand Kdenlive round-trip integration test

**Expand** `tests/integration/test_kdenlive_roundtrip.py`:
- Parse fixture .kdenlive
- Add guides via patcher
- Serialize to new file
- Parse the new file
- Verify guides preserved
- Verify opaque elements preserved
- Verify clip structure intact

### Step 8: Write end-to-end integration test

**Create** `tests/integration/test_end_to_end.py`:
- Create workspace with fixture media
- Run ingest pipeline
- Run auto-mark
- Build review timeline
- Build selects
- Generate Kdenlive project
- Validate project
- Verify all artifacts exist: workspace.yaml, transcripts/, markers/, projects/working_copies/*.kdenlive, reports/

### Step 9: Write developer setup guide

**Create** `docs/developer-setup.md`:
- Prerequisites: Python 3.12+, uv, FFmpeg, Kdenlive (optional for manual QA)
- Clone and setup: `git clone`, `uv sync --group dev --group test`
- Install faster-whisper model: `python -c "from faster_whisper import WhisperModel; WhisperModel('small')"`
- Configure: copy `.env.example` to `.env`, set paths
- Run tests: `uv run pytest`
- Run MCP server: `uv run workshop-video-brain-server`
- Run CLI: `uv run wvb version`
- Plugin development: `claude plugin validate .` then `/plugin marketplace add ./`

### Step 10: Write user workflow guide

**Create** `docs/user-workflow.md`:
- Installation: `/plugin marketplace add Caleb68864/ForgeFrame`, `/plugin install workshop-video-brain@forgeframe`
- Planning a video: `/video-idea-to-outline "your idea"` → `/tutorial-script` → `/shot-plan`
- Preparing footage: `wvb workspace create --title "My Video" --media-root /path/to/footage`
- Processing: `wvb media ingest` → `wvb transcript generate` → `wvb markers auto`
- Review: `wvb timeline review` → open .kdenlive in Kdenlive
- Editing notes: `/obsidian-video-note` to sync workspace data to vault
- Rendering: `wvb render preview`
- What's automated vs what's manual

### Step 11: Write AI handoff notes

**Create** `docs/ai-handoff.md`:
- Module boundaries: production_brain (skills, notes) vs edit_mcp (server, adapters, pipelines)
- Dangerous areas: Kdenlive XML parsing (opaque passthrough is critical), Obsidian note merging (section boundaries), snapshot creation (must happen before every write)
- Assumptions: single user, local Linux, Kdenlive 25.12-era, one workspace per project
- Extension ideas: speaker diarization, OTIO, Production Brain as MCP, live Kdenlive bridge
- Known limitations: no GUI automation, no multi-user, no cloud STT, no advanced effects

## Verification Commands

```bash
# Run all tests
uv run pytest -v

# Run only integration tests
uv run pytest tests/integration/ -v

# Test MCP server starts and responds
uv run workshop-video-brain-server &
sleep 2
# (send MCP ping via client)
kill %1

# Test CLI
uv run wvb version
uv run wvb workspace --help
uv run wvb media --help
```

## Acceptance Criteria

- [ ] All MCP tools registered and callable with structured JSON output
- [ ] All MCP resources readable
- [ ] CLI commands mirror MCP capabilities with --help text
- [ ] `wvb prepare-tutorial-project` runs full pipeline
- [ ] End-to-end test passes with all artifacts present
- [ ] Developer setup guide is complete and followable
- [ ] User workflow guide covers install through render
- [ ] AI handoff notes cover boundaries, dangers, assumptions, extensions, limitations
