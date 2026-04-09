---
type: phase-spec
master_spec: "docs/specs/2026-04-09-phase3-pipeline-completeness.md"
sub_spec: 12
title: "Project Archive Tool"
dependencies: none
date: 2026-04-09
---

# Sub-Spec 12: Project Archive Tool

## Shared Context
Archives a workspace into a distributable tar.gz or zip file. Streaming write to avoid loading full media into memory. Generates an ArchiveManifest with stats.

## Interface Contract
**Provides:**
- `ArchiveManifest` Pydantic model
- `create_archive(workspace_root, output_dir, include_renders?, include_raw?, format?) -> ArchiveManifest`
- MCP tool `project_archive`

**Requires:**
- `workspace.yaml` in workspace root (for title)

## Implementation Steps

### Step 1: Create archive models

File: `workshop-video-brain/src/workshop_video_brain/core/models/archive.py`

```python
"""Archive models -- manifest for workspace archive operations."""
from __future__ import annotations

from pydantic import BaseModel


class ArchiveManifest(BaseModel):
    workspace_title: str
    archive_path: str
    created_at: str  # ISO 8601
    files_included: int
    total_size_bytes: int
    includes_renders: bool
    includes_raw_media: bool
```

Update `workshop-video-brain/src/workshop_video_brain/core/models/__init__.py` to re-export:
```python
from .archive import ArchiveManifest
```

### Step 2: Write tests

File: `tests/unit/test_archive.py`

```python
"""Tests for project archive pipeline."""
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path
import pytest
import yaml

from workshop_video_brain.core.models.archive import ArchiveManifest
from workshop_video_brain.edit_mcp.pipelines.archive import create_archive


@pytest.fixture
def workspace(tmp_path):
    """Create a minimal workspace directory tree."""
    ws = tmp_path / "my-project"
    ws.mkdir()

    # workspace.yaml
    (ws / "workspace.yaml").write_text(yaml.dump({"title": "Test Project"}))

    # Kdenlive project file
    (ws / "project.kdenlive").write_text("<mlt></mlt>")

    # Reports
    (ws / "reports").mkdir()
    (ws / "reports" / "qc.json").write_text("{}")

    # Transcripts
    (ws / "transcripts").mkdir()
    (ws / "transcripts" / "intro.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")

    # Renders
    (ws / "renders").mkdir()
    (ws / "renders" / "final.mp4").write_bytes(b"\x00" * 1024)

    # Raw media
    (ws / "media").mkdir()
    (ws / "media" / "raw").mkdir()
    (ws / "media" / "raw" / "clip01.mp4").write_bytes(b"\x00" * 4096)

    return ws


class TestCreateArchiveTarGz:
    def test_basic_archive(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output, include_renders=True, include_raw=False)

        assert isinstance(manifest, ArchiveManifest)
        assert manifest.workspace_title == "Test Project"
        assert manifest.includes_renders is True
        assert manifest.includes_raw_media is False
        assert manifest.files_included > 0
        assert Path(manifest.archive_path).exists()
        assert manifest.archive_path.endswith(".tar.gz")

    def test_archive_contains_expected_files(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output, include_renders=True, include_raw=False)

        with tarfile.open(manifest.archive_path, "r:gz") as tar:
            names = tar.getnames()
        # Should contain kdenlive, workspace.yaml, reports, transcripts, renders
        assert any("project.kdenlive" in n for n in names)
        assert any("workspace.yaml" in n for n in names)
        assert any("qc.json" in n for n in names)
        assert any("intro.srt" in n for n in names)
        assert any("final.mp4" in n for n in names)
        # Should NOT contain raw media
        assert not any("clip01.mp4" in n for n in names)

    def test_archive_without_renders(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output, include_renders=False, include_raw=False)

        with tarfile.open(manifest.archive_path, "r:gz") as tar:
            names = tar.getnames()
        assert not any("final.mp4" in n for n in names)
        assert manifest.includes_renders is False

    def test_archive_with_raw(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output, include_renders=False, include_raw=True)

        with tarfile.open(manifest.archive_path, "r:gz") as tar:
            names = tar.getnames()
        assert any("clip01.mp4" in n for n in names)
        assert manifest.includes_raw_media is True


class TestCreateArchiveZip:
    def test_zip_format(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output, format="zip")

        assert manifest.archive_path.endswith(".zip")
        assert Path(manifest.archive_path).exists()

        with zipfile.ZipFile(manifest.archive_path, "r") as zf:
            names = zf.namelist()
        assert any("project.kdenlive" in n for n in names)

    def test_invalid_format_raises(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        with pytest.raises(ValueError, match="format"):
            create_archive(workspace, output, format="rar")


class TestManifestAccuracy:
    def test_file_count(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output, include_renders=True, include_raw=True)
        # workspace.yaml + project.kdenlive + qc.json + intro.srt + final.mp4 + clip01.mp4 = 6
        assert manifest.files_included == 6

    def test_total_size(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output, include_renders=True, include_raw=True)
        assert manifest.total_size_bytes > 0

    def test_created_at_is_iso(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output)
        # Should parse as ISO 8601
        datetime.fromisoformat(manifest.created_at)

    def test_archive_name_includes_title(self, workspace, tmp_path):
        output = tmp_path / "output"
        output.mkdir()
        manifest = create_archive(workspace, output)
        assert "Test_Project" in Path(manifest.archive_path).name or "Test-Project" in Path(manifest.archive_path).name


class TestEmptyWorkspace:
    def test_minimal_workspace(self, tmp_path):
        ws = tmp_path / "empty-ws"
        ws.mkdir()
        (ws / "workspace.yaml").write_text(yaml.dump({"title": "Empty"}))
        output = tmp_path / "output"
        output.mkdir()

        manifest = create_archive(ws, output)
        assert manifest.files_included == 1  # just workspace.yaml
        assert manifest.workspace_title == "Empty"
```

### Step 3: Implement pipeline function

File: `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/archive.py`

```python
"""Project archive pipeline -- bundle workspace into tar.gz or zip."""
from __future__ import annotations

import re
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from workshop_video_brain.core.models.archive import ArchiveManifest

VALID_FORMATS = {"tar.gz", "zip"}

# Directories/patterns always included (relative to workspace root)
ALWAYS_INCLUDE = ["workspace.yaml", "*.kdenlive", "reports", "transcripts"]


def create_archive(
    workspace_root: Path,
    output_dir: Path,
    include_renders: bool = True,
    include_raw: bool = False,
    format: str = "tar.gz",
) -> ArchiveManifest:
    """Archive a workspace into a tar.gz or zip file."""
    if format not in VALID_FORMATS:
        raise ValueError(f"Invalid format '{format}'; must be one of {VALID_FORMATS}")

    # Read workspace title
    ws_yaml = yaml.safe_load((workspace_root / "workspace.yaml").read_text())
    title = ws_yaml.get("title", "untitled")
    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", title)

    # Collect files
    files: list[Path] = []
    for pattern in ALWAYS_INCLUDE:
        if "*" in pattern:
            files.extend(workspace_root.glob(pattern))
        else:
            target = workspace_root / pattern
            if target.is_file():
                files.append(target)
            elif target.is_dir():
                files.extend(f for f in target.rglob("*") if f.is_file())

    if include_renders and (workspace_root / "renders").is_dir():
        files.extend(f for f in (workspace_root / "renders").rglob("*") if f.is_file())

    if include_raw and (workspace_root / "media" / "raw").is_dir():
        files.extend(f for f in (workspace_root / "media" / "raw").rglob("*") if f.is_file())

    # Deduplicate
    files = sorted(set(files))

    # Calculate total size
    total_size = sum(f.stat().st_size for f in files)

    # Build archive name
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ext = ".tar.gz" if format == "tar.gz" else ".zip"
    archive_name = f"{safe_title}_{date_str}{ext}"
    archive_path = output_dir / archive_name

    # Write archive (streaming)
    if format == "tar.gz":
        with tarfile.open(archive_path, "w:gz") as tar:
            for f in files:
                arcname = f.relative_to(workspace_root)
                tar.add(f, arcname=str(arcname))
    else:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                arcname = f.relative_to(workspace_root)
                zf.write(f, arcname=str(arcname))

    return ArchiveManifest(
        workspace_title=title,
        archive_path=str(archive_path),
        created_at=datetime.now(timezone.utc).isoformat(),
        files_included=len(files),
        total_size_bytes=total_size,
        includes_renders=include_renders,
        includes_raw_media=include_raw,
    )
```

### Step 4: Register MCP tool

File: `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` (append)

```python
@mcp.tool()
def project_archive(
    workspace_path: str,
    output_dir: str,
    include_renders: bool = True,
    include_raw: bool = False,
    format: str = "tar.gz",
) -> dict:
    """Archive the workspace into a tar.gz or zip file."""
    from workshop_video_brain.edit_mcp.pipelines.archive import create_archive
    try:
        manifest = create_archive(
            Path(workspace_path),
            Path(output_dir),
            include_renders=include_renders,
            include_raw=include_raw,
            format=format,
        )
        return _ok(manifest.model_dump())
    except Exception as e:
        return _err(str(e))
```

## Verification

```bash
uv run pytest tests/unit/test_archive.py -v
```

**Pass criteria:** All archive formats produce valid archives with correct contents. Manifest file count and size are accurate. Empty workspace archives without error. Invalid format raises ValueError.
