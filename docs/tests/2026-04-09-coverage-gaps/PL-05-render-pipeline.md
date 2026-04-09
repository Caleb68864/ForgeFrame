---
scenario_id: "PL-05"
title: "Render Pipeline"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario PL-05: Render Pipeline

## Description
Tests `run_render`, `register_render`, `list_renders`, and the
`RenderArtifactRegistry` class from `render_pipeline.py`. The registry persists
render job entries as YAML to `renders/render_registry.yaml` inside the
workspace root. Covers: end-to-end `run_render` with mocked executor and
profile loader, registry CRUD (`register_render` / `list_renders`), entry
deduplication by job ID, corrupt registry file handling, and the
`_capture_source_version` workspace manifest snapshot.

## Preconditions
- `workshop-video-brain` installed in editable mode
- `tmp_path` provides isolated workspace directories
- Adapter calls patched: `load_profile`, `create_render_job`, `execute_render`
- `RenderJob` from `workshop_video_brain.core.models.project`
- `JobStatus` from `workshop_video_brain.core.models.enums`

## Test Cases

```
tests/unit/test_render_pipeline.py

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Helpers ──────────────────────────────────────────────────────────────────

def make_render_job(tmp_path, status="queued", job_id=None)
    # Returns a RenderJob with minimal valid fields:
    # id=uuid, workspace_id=uuid, project_path=str(tmp_path/"project.kdenlive"),
    # profile="preview", mode="standard", output_path=str(tmp_path/"out.mp4"),
    # status=status, log_path=None, started_at=None, completed_at=None

# ── RenderArtifactRegistry ───────────────────────────────────────────────────

class TestRenderArtifactRegistryInit:
    def test_registry_path_inside_renders_subdir(tmp_path)
        # registry = RenderArtifactRegistry(tmp_path)
        # registry._registry_path == tmp_path / "renders" / "render_registry.yaml"

class TestRegisterRender:
    def test_creates_yaml_file_on_first_register(tmp_path)
        # job = make_render_job(tmp_path)
        # registry.register_render(job)
        # (tmp_path / "renders" / "render_registry.yaml").exists() is True

    def test_registered_job_retrievable_via_list_renders(tmp_path)
        # register then list; assert len == 1 and job.id matches

    def test_registering_same_job_id_twice_replaces_entry(tmp_path)
        # Register job with status "queued", then same job with status "done"
        # list_renders returns exactly one entry with status "done"

    def test_multiple_distinct_jobs_all_stored(tmp_path)
        # Register two jobs with different IDs
        # len(list_renders()) == 2

    def test_started_at_and_completed_at_serialized_as_iso(tmp_path)
        # job with started_at=datetime.now(tz=timezone.utc)
        # Parse YAML; entry["started_at"] is a string containing "T"

class TestListRenders:
    def test_empty_registry_returns_empty_list(tmp_path)
        # No YAML file present
        # list_renders() == []

    def test_corrupt_yaml_returns_empty_list(tmp_path)
        # Write "!!python/object:builtins.eval" to registry file
        # list_renders() == []  (caught gracefully)

    def test_corrupt_entry_skipped_valid_entry_returned(tmp_path)
        # Write YAML list with one valid entry dict and one entry missing required fields
        # list_renders() returns 1 item (the valid one)

class TestCaptureSourceVersion:
    def test_captures_project_path(tmp_path)
        # Create a dummy project file
        # _capture_source_version returns dict with "project_path" key

    def test_captures_workspace_manifest_fields(tmp_path)
        # Write workspace.yaml with workspace_id, project_title, status, slug
        # _capture_source_version returns dict with those fields

    def test_missing_manifest_does_not_raise(tmp_path)
        # No workspace.yaml present
        # _capture_source_version returns {"project_path": ...} without error

    def test_missing_project_file_omits_mtime(tmp_path)
        # project_path points to nonexistent file
        # "mtime" not in _capture_source_version(...)

# ── Module-level convenience functions ───────────────────────────────────────

class TestRegisterRenderConvenience:
    def test_convenience_register_delegates_to_registry(tmp_path)
        # from render_pipeline import register_render
        # register_render(tmp_path, job)
        # (tmp_path / "renders" / "render_registry.yaml").exists() is True

class TestListRendersConvenience:
    def test_convenience_list_returns_same_as_registry(tmp_path)
        # register via convenience fn, list via convenience fn
        # results match

# ── run_render ────────────────────────────────────────────────────────────────

class TestRunRender:
    def test_run_render_returns_completed_job(tmp_path)
        # Patch load_profile, create_render_job, execute_render
        # execute_render returns job with status JobStatus.done
        # run_render(...) returns that job

    def test_run_render_registers_job_twice(tmp_path)
        # Once as "queued" before execute_render, once with final status after
        # After run_render, list_renders() has one entry with final status

    def test_run_render_calls_load_profile_with_correct_name(tmp_path)
        # Patch load_profile; assert called with "preview"

    def test_run_render_calls_create_render_job_with_correct_args(tmp_path)
        # Patch create_render_job; assert workspace_root and project_path passed

    def test_run_render_calls_execute_render(tmp_path)
        # Patch execute_render; assert called once

    def test_run_render_propagates_executor_exception(tmp_path)
        # execute_render raises RuntimeError
        # run_render raises RuntimeError (not swallowed)
```

## Steps
1. Read source module to understand current API
2. Create test file at `tests/unit/test_render_pipeline.py`
3. Implement test cases with mocked dependencies
4. Run: `uv run pytest tests/unit/test_render_pipeline.py -v`

## Expected Results
- `RenderArtifactRegistry` creates `renders/render_registry.yaml` on first write
- Registering the same job ID twice overwrites — `list_renders` always returns
  at most one entry per job ID
- Corrupt YAML or corrupt individual entries are silently skipped; valid entries
  are still returned
- `run_render` registers the job twice: once as queued and once with the
  executor's final status
- `_capture_source_version` reads `workspace.yaml` when present; omits missing keys

## Pass / Fail Criteria
- Pass: All test cases pass, no import errors
- Fail: Any test fails or source API doesn't match expectations
