---
type: phase-spec
master_spec: "../2026-04-09-phase3-pipeline-completeness.md"
sub_spec: 6
title: "Full Render Tool"
dependencies: ["3"]
date: 2026-04-09
---

# Sub-Spec 6: Full Render Tool

## Scope

Pipeline and MCP tools for full-quality renders using named presets (from Sub-Spec 3), with codec availability checking, pre-render snapshotting, and structured result reporting. Two MCP tools: one to execute a render, one to list available profiles.

## Shared Context

- **Source root:** `workshop-video-brain/src/workshop_video_brain/`
- **Test command:** `uv run pytest tests/ -v`
- **MCP pattern:** `@mcp.tool()`, return `_ok(data)` / `_err(message)`, helpers `_validate_workspace_path()`, `_require_workspace()`
- **Pipeline pattern:** Pure functions returning dataclass reports
- **Render profiles:** YAML files in `edit_mcp/templates/render/`, loaded via `load_profile(name) -> RenderProfile`
- **Render executor:** `edit_mcp/adapters/render/executor.py` -- `execute_render(job, profile) -> RenderJob`
- **Render profiles module:** `edit_mcp/adapters/render/profiles.py` -- `load_profile()`, `list_profiles()`, `RenderProfile`
- **Snapshot system:** Workspace snapshots via existing infrastructure (called before destructive operations)

## Interface Contracts

### Requires (from Sub-Spec 3: Render Profile Expansion)

- **`load_profile(name) -> RenderProfile`** -- loads profile from YAML, including new fields `fast_start: bool` and `movflags: str | None`
- **`list_profiles() -> list[str]`** -- returns all available profile names
- **`check_codec_available(codec_name: str) -> bool`** -- verifies FFmpeg has the required encoder
- **`RenderProfile`** -- Pydantic model with `video_codec`, `audio_codec`, `width`, `height`, `fps`, `video_bitrate`, `audio_bitrate`, `extra_args`, `fast_start`, `movflags`

### Provides

- **`render_final(workspace_root: Path, profile_name: str, output_name: str | None, project_file: str | None) -> RenderResult`** -- full render pipeline; if `project_file` is None, finds most recently modified `.kdenlive` in `projects/working_copies/`
- **`RenderResult` dataclass** with `output_path: str`, `profile_used`, `duration_seconds`, `file_size_bytes`, `codec_info`
- **MCP tool `render_final(workspace_path, profile, output_name) -> dict`** -- wraps the pipeline
- **MCP tool `render_list_profiles() -> dict`** -- returns profile names with descriptions

## Implementation Steps

### Step 1: Write tests

**Create** `tests/unit/test_render_final.py`:

```python
"""Tests for the full render pipeline."""
from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from workshop_video_brain.edit_mcp.pipelines.render_final import (
    RenderResult,
    render_final,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace_with_project(tmp_path: Path) -> Path:
    """Create a workspace with a .kdenlive project file."""
    # Workspace structure
    (tmp_path / "workspace.yaml").write_text("title: Test Project\n")
    (tmp_path / "renders").mkdir()

    # Create a minimal .kdenlive file
    project_dir = tmp_path / "projects"
    project_dir.mkdir()
    kdenlive = project_dir / "test_project.kdenlive"
    kdenlive.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<mlt><playlist id="main_bin"/></mlt>'
    )

    return tmp_path


@pytest.fixture
def workspace_no_project(tmp_path: Path) -> Path:
    """Workspace without any .kdenlive file."""
    (tmp_path / "workspace.yaml").write_text("title: Empty\n")
    (tmp_path / "renders").mkdir()
    return tmp_path


@pytest.fixture
def mock_profile():
    """A mock RenderProfile."""
    profile = MagicMock()
    profile.name = "youtube-1080p"
    profile.video_codec = "libx264"
    profile.audio_codec = "aac"
    profile.width = 1920
    profile.height = 1080
    profile.fps = 30.0
    profile.video_bitrate = "8M"
    profile.audio_bitrate = "192k"
    profile.extra_args = []
    profile.fast_start = True
    profile.movflags = "+faststart"
    return profile


# ---------------------------------------------------------------------------
# RenderResult dataclass
# ---------------------------------------------------------------------------

class TestRenderResult:
    def test_fields(self):
        r = RenderResult(
            output_path="/tmp/out.mp4",
            profile_used="youtube-1080p",
            duration_seconds=120.5,
            file_size_bytes=15_000_000,
            codec_info="libx264 / aac",
        )
        assert r.profile_used == "youtube-1080p"
        assert r.duration_seconds == pytest.approx(120.5)
        d = asdict(r)
        assert "codec_info" in d

    def test_serializable(self):
        r = RenderResult(
            output_path="/tmp/out.mp4",
            profile_used="test",
            duration_seconds=0.0,
            file_size_bytes=0,
            codec_info="",
        )
        d = asdict(r)
        assert isinstance(d["output_path"], str)


# ---------------------------------------------------------------------------
# render_final pipeline
# ---------------------------------------------------------------------------

class TestRenderFinal:
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.subprocess")
    def test_successful_render(
        self, mock_subprocess, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """Successful render returns RenderResult with output path."""
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True
        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")

        result = render_final(workspace_with_project, "youtube-1080p")

        assert isinstance(result, RenderResult)
        assert result.profile_used == "youtube-1080p"
        assert "renders" in str(result.output_path)
        assert result.output_path.suffix == ".mp4"

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    def test_missing_codec_raises(
        self, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """Missing codec should raise RuntimeError with actionable message."""
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = False

        with pytest.raises(RuntimeError, match="not found"):
            render_final(workspace_with_project, "youtube-1080p")

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    def test_no_project_file_raises(
        self, mock_load_profile, mock_codec_check,
        workspace_no_project: Path, mock_profile,
    ):
        """No .kdenlive project should raise FileNotFoundError."""
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True

        with pytest.raises(FileNotFoundError, match="No .kdenlive project"):
            render_final(workspace_no_project, "youtube-1080p")

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    def test_invalid_profile_propagates(
        self, mock_load_profile, mock_codec_check,
        workspace_with_project: Path,
    ):
        """Invalid profile name should propagate FileNotFoundError from load_profile."""
        mock_load_profile.side_effect = FileNotFoundError("Profile 'bogus' not found")

        with pytest.raises(FileNotFoundError, match="bogus"):
            render_final(workspace_with_project, "bogus")

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.subprocess")
    def test_custom_output_name(
        self, mock_subprocess, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """Custom output_name should appear in the output filename."""
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True
        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")

        result = render_final(
            workspace_with_project, "youtube-1080p", output_name="final_cut",
        )

        assert "final_cut" in result.output_path.name

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.subprocess")
    def test_ffmpeg_failure_raises(
        self, mock_subprocess, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """Non-zero FFmpeg exit should raise RuntimeError."""
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True
        mock_subprocess.run.return_value = MagicMock(
            returncode=1, stderr="Encoding error",
        )

        with pytest.raises(RuntimeError, match="Render failed"):
            render_final(workspace_with_project, "youtube-1080p")

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.subprocess")
    def test_output_in_renders_dir(
        self, mock_subprocess, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """Output path should be inside workspace/renders/."""
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True
        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")

        result = render_final(workspace_with_project, "youtube-1080p")

        assert result.output_path.parent == workspace_with_project / "renders"

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.subprocess")
    def test_renders_dir_created_if_missing(
        self, mock_subprocess, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """renders/ dir should be created if it does not exist."""
        import shutil
        renders_dir = workspace_with_project / "renders"
        if renders_dir.exists():
            shutil.rmtree(renders_dir)

        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True
        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")

        result = render_final(workspace_with_project, "youtube-1080p")
        assert result.output_path.parent.exists()


# ---------------------------------------------------------------------------
# FFmpeg command construction
# ---------------------------------------------------------------------------

class TestFFmpegCommand:
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.subprocess")
    def test_command_includes_profile_settings(
        self, mock_subprocess, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """FFmpeg command should include codec, bitrate, resolution from profile."""
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True
        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")

        render_final(workspace_with_project, "youtube-1080p")

        call_args = mock_subprocess.run.call_args[0][0]
        cmd_str = " ".join(str(a) for a in call_args)
        assert "libx264" in cmd_str
        assert "8M" in cmd_str

    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.check_codec_available")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.load_profile")
    @patch("workshop_video_brain.edit_mcp.pipelines.render_final.subprocess")
    def test_fast_start_flag(
        self, mock_subprocess, mock_load_profile, mock_codec_check,
        workspace_with_project: Path, mock_profile,
    ):
        """fast_start=True should add -movflags +faststart to the command."""
        mock_profile.fast_start = True
        mock_profile.movflags = "+faststart"
        mock_load_profile.return_value = mock_profile
        mock_codec_check.return_value = True
        mock_subprocess.run.return_value = MagicMock(returncode=0, stderr="")

        render_final(workspace_with_project, "youtube-1080p")

        call_args = mock_subprocess.run.call_args[0][0]
        cmd_str = " ".join(str(a) for a in call_args)
        assert "faststart" in cmd_str
```

### Step 2: Implement `render_final.py`

**Create** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/render_final.py`:

```python
"""Full render pipeline.

Loads a named render profile, checks codec availability, finds the
latest .kdenlive project in the workspace, builds and executes an
FFmpeg command, and returns a structured RenderResult.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.render.profiles import (
    RenderProfile,
    list_profiles,
    load_profile,
)

logger = logging.getLogger(__name__)


@dataclass
class RenderResult:
    """Result of a successful render."""

    output_path: str  # str for MCP serialization compatibility
    profile_used: str
    duration_seconds: float
    file_size_bytes: int
    codec_info: str


def check_codec_available(codec_name: str) -> bool:
    """Check if an FFmpeg encoder is available.

    Runs ``ffmpeg -codecs`` and checks for the encoder name.

    Args:
        codec_name: Encoder name, e.g. ``"libx264"``, ``"prores_ks"``.

    Returns:
        True if the encoder is available, False otherwise.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-codecs"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return codec_name in result.stdout
    except Exception:
        logger.warning("Could not check codec availability", exc_info=True)
        return False


def render_final(
    workspace_root: Path,
    profile_name: str,
    output_name: str | None = None,
    project_file: str | None = None,
) -> RenderResult:
    """Execute a full render of the workspace project.

    Steps:
        1. Load the render profile by name.
        2. Check codec availability; raise if missing.
        3. Find the latest .kdenlive project in the workspace.
        4. Build FFmpeg command from profile.
        5. Execute render.
        6. Return RenderResult.

    Args:
        workspace_root: Path to workspace root.
        profile_name: Name of a render profile (e.g. "youtube-1080p").
        output_name: Optional base name for the output file. Defaults to
                     profile_name if not provided.
        project_file: Explicit path to .kdenlive project file (str). If None,
                      finds most recently modified .kdenlive in projects/working_copies/.

    Returns:
        RenderResult with output path, profile info, duration, file size.

    Raises:
        FileNotFoundError: If profile or project file is not found.
        RuntimeError: If codec is unavailable or FFmpeg fails.
    """
    # 1. Load profile
    profile = load_profile(profile_name)

    # 2. Check codec
    if not check_codec_available(profile.video_codec):
        raise RuntimeError(
            f"Encoder '{profile.video_codec}' not found. "
            f"Install FFmpeg with {profile.video_codec} support "
            f"or use a different profile."
        )

    # 3. Find .kdenlive project (explicit or auto-detect)
    if project_file is not None:
        project_path = Path(project_file)
        if not project_path.is_absolute():
            project_path = workspace_root / project_path
        if not project_path.exists():
            raise FileNotFoundError(f"Specified project file not found: {project_file}")
    else:
        project_path = _find_latest_project(
            workspace_root / "projects" / "working_copies"
        )

    # 4. Build output path
    renders_dir = workspace_root / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)

    base_name = output_name or profile_name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = _extension_for_profile(profile)
    output_path = renders_dir / f"{base_name}_{timestamp}{ext}"

    # 5. Build and execute FFmpeg command
    cmd = _build_render_command(project_path, output_path, profile)
    logger.info("Render command: %s", " ".join(str(c) for c in cmd))

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"Render failed (exit {result.returncode}): "
            f"{result.stderr[:500]}"
        )

    # 6. Gather result metadata
    file_size = output_path.stat().st_size if output_path.exists() else 0
    duration = _probe_duration(output_path) if output_path.exists() else 0.0

    return RenderResult(
        output_path=str(output_path),
        profile_used=profile_name,
        duration_seconds=duration,
        file_size_bytes=file_size,
        codec_info=f"{profile.video_codec} / {profile.audio_codec}",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_latest_project(workspace_root: Path) -> Path:
    """Find the most recently modified .kdenlive project in workspace.

    Raises:
        FileNotFoundError: If no .kdenlive files found.
    """
    kdenlive_files = sorted(
        workspace_root.rglob("*.kdenlive"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not kdenlive_files:
        raise FileNotFoundError(
            f"No .kdenlive project found in {workspace_root}. "
            "Create a project first."
        )
    return kdenlive_files[0]


def _extension_for_profile(profile: RenderProfile) -> str:
    """Determine file extension from profile codec."""
    codec = profile.video_codec.lower()
    if "prores" in codec or "dnxh" in codec:
        return ".mov"
    return ".mp4"


def _build_render_command(
    project_file: Path,
    output_path: Path,
    profile: RenderProfile,
) -> list[str]:
    """Build FFmpeg render command from profile settings."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(project_file),
        "-vf", f"scale={profile.width}:{profile.height}",
        "-r", str(profile.fps),
        "-c:v", profile.video_codec,
        "-b:v", profile.video_bitrate,
        "-c:a", profile.audio_codec,
        "-b:a", profile.audio_bitrate,
    ]

    # Fast-start for streaming-friendly output
    if getattr(profile, "fast_start", False):
        movflags = getattr(profile, "movflags", "+faststart") or "+faststart"
        cmd.extend(["-movflags", movflags])

    # Extra args from profile
    cmd.extend(getattr(profile, "extra_args", []))

    cmd.append(str(output_path))
    return cmd


def _probe_duration(path: Path) -> float:
    """Quick ffprobe to get duration of rendered file."""
    try:
        import json
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0.0))
    except Exception:
        return 0.0
```

### Step 3: Add MCP tools

**Modify** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` -- add two tools:

```python
# ---------------------------------------------------------------------------
# Render tools
# ---------------------------------------------------------------------------


@mcp.tool()
def render_final_tool(
    workspace_path: str,
    profile: str,
    output_name: str = "",
    project_file: str = "",
) -> dict:
    """Render the workspace project using a named render profile.

    Creates a full-quality render of the latest .kdenlive project file
    in the workspace using the specified profile (e.g. "youtube-1080p",
    "master-prores").

    Args:
        workspace_path: Absolute path to the workspace root directory.
        profile: Render profile name (see render_list_profiles for options).
        output_name: Optional base name for the output file. Defaults to
                     the profile name with a timestamp.

    Returns:
        RenderResult with output_path, profile_used, duration_seconds,
        file_size_bytes, and codec_info.
    """
    try:
        ws_root = _validate_workspace_path(workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.render_final import (
            render_final as _render_final,
        )
        from dataclasses import asdict

        name = output_name.strip() if output_name else None
        proj = project_file.strip() if project_file else None
        result = _render_final(ws_root, profile, output_name=name, project_file=proj)

        data = asdict(result)
        return _ok(data)
    except FileNotFoundError as exc:
        return _err(str(exc))
    except RuntimeError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"Render failed: {exc}")


@mcp.tool()
def render_list_profiles() -> dict:
    """List all available render profiles with their names.

    Returns a list of profile names that can be passed to render_final.
    Profiles include platform-specific presets (youtube-1080p, youtube-4k,
    vimeo-hq) and master formats (master-prores, master-dnxhr).

    Returns:
        List of profile name strings.
    """
    try:
        from workshop_video_brain.edit_mcp.adapters.render.profiles import (
            list_profiles,
            load_profile,
        )
        names = list_profiles()
        profiles = []
        for name in names:
            try:
                p = load_profile(name)
                profiles.append({
                    "name": name,
                    "codec": p.video_codec,
                    "resolution": f"{p.width}x{p.height}",
                    "fps": p.fps,
                })
            except Exception:
                profiles.append({"name": name, "codec": "unknown"})
        return _ok({"profiles": profiles})
    except Exception as exc:
        return _err(f"Failed to list profiles: {exc}")
```

### Step 4: Run tests and verify

```bash
uv run pytest tests/unit/test_render_final.py -v
```

## Verification Commands

```bash
# Run new tests
uv run pytest tests/unit/test_render_final.py -v

# Run full suite to confirm no regressions
uv run pytest tests/ -v

# Verify module importable
python3 -c "
from workshop_video_brain.edit_mcp.pipelines.render_final import (
    RenderResult, render_final, check_codec_available,
)
print('Import: PASS')
"

# Verify dataclass shape
python3 -c "
from dataclasses import fields
from workshop_video_brain.edit_mcp.pipelines.render_final import RenderResult
rf = {f.name for f in fields(RenderResult)}
assert rf == {'output_path', 'profile_used', 'duration_seconds', 'file_size_bytes', 'codec_info'}
print('RenderResult shape: PASS')
"

# Verify render profiles load (requires Sub-Spec 3 profiles to exist)
python3 -c "
from workshop_video_brain.edit_mcp.adapters.render.profiles import list_profiles
profiles = list_profiles()
print(f'Available profiles: {profiles}')
assert len(profiles) >= 3, 'Expected at least 3 profiles'
print('Profiles: PASS')
"
```

## Acceptance Criteria

- [ ] `RenderResult` dataclass has fields: `output_path: str`, `profile_used: str`, `duration_seconds: float`, `file_size_bytes: int`, `codec_info: str`
- [ ] `check_codec_available(codec_name)` runs `ffmpeg -codecs` and returns bool
- [ ] `render_final()` loads profile via `load_profile(profile_name)`
- [ ] `render_final()` checks codec via `check_codec_available()` before rendering; raises `RuntimeError` with actionable message if missing
- [ ] `render_final()` accepts optional `project_file: str | None` parameter; if None, finds most recently modified `.kdenlive` in `projects/working_copies/`
- [ ] `render_final()` raises `FileNotFoundError` if no `.kdenlive` project exists or specified project_file is missing
- [ ] Output placed in `workspace/renders/{output_name or profile_name}_{timestamp}.{ext}`
- [ ] Extension is `.mov` for ProRes/DNxHR codecs, `.mp4` otherwise
- [ ] `renders/` directory created if it does not exist
- [ ] `fast_start=True` on profile appends `-movflags +faststart` to FFmpeg command
- [ ] FFmpeg failure raises `RuntimeError` with stderr excerpt
- [ ] Custom `output_name` appears in the output filename
- [ ] MCP tool `render_final_tool` validates workspace, calls pipeline, returns serialized result
- [ ] MCP tool `render_list_profiles` returns all profiles with name, codec, resolution, fps
- [ ] All new tests pass: `uv run pytest tests/unit/test_render_final.py -v`
- [ ] All existing tests still pass: `uv run pytest tests/ -v`
