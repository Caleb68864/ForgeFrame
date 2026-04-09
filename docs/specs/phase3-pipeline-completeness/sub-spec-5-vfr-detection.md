---
type: phase-spec
master_spec: "../2026-04-09-phase3-pipeline-completeness.md"
sub_spec: 5
title: "VFR Detection and CFR Transcode"
dependencies: ["1"]
date: 2026-04-09
---

# Sub-Spec 5: VFR Detection and CFR Transcode

## Scope

Pipeline and MCP tools to scan a workspace for variable frame rate (VFR) media files and transcode them to constant frame rate (CFR). VFR media causes audio drift and editing artifacts in Kdenlive; this feature detects it early and provides a one-tool fix.

## Shared Context

- **Source root:** `workshop-video-brain/src/workshop_video_brain/`
- **Test command:** `uv run pytest tests/ -v`
- **MCP pattern:** `@mcp.tool()`, return `_ok(data)` / `_err(message)`, helpers `_validate_workspace_path()`, `_require_workspace()`
- **Pipeline pattern:** Pure functions returning dataclass reports, per-item try-catch, log warnings, add to `report.errors`
- **Probe adapter:** `edit_mcp/adapters/ffmpeg/probe.py` -- `probe_media(path) -> MediaAsset`
- **MediaAsset fields (from Sub-Spec 1):** `is_vfr: bool`, `fps: float`, plus existing fields

## Interface Contracts

### Requires (from Sub-Spec 1: FFprobe Extended)

- **`MediaAsset.is_vfr: bool`** -- set by extended `probe_media()` when `r_frame_rate` and `avg_frame_rate` diverge by > 5%
- **`probe_media(path) -> MediaAsset`** -- must populate `is_vfr` for every probed file
- **Video file extensions:** `DEFAULT_EXTENSIONS` from `edit_mcp/adapters/ffmpeg/probe.py`

### Provides

- **`check_vfr(workspace_root: Path) -> VFRReport`** -- scans all video files, returns report
- **`transcode_to_cfr(source: Path, target_fps: int | None) -> Path`** -- transcodes VFR to CFR
- **MCP tool `media_check_vfr(workspace_path: str) -> dict`** -- wraps `check_vfr()`
- **MCP tool `media_transcode_cfr(workspace_path: str, file_path: str, target_fps: int) -> dict`** -- wraps `transcode_to_cfr()`

## Implementation Steps

### Step 1: Write VFR report tests

**Create** `tests/unit/test_vfr_check.py`:

```python
"""Tests for VFR detection and CFR transcode pipeline."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.edit_mcp.pipelines.vfr_check import (
    VFRFile,
    VFRReport,
    check_vfr,
    transcode_to_cfr,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_media_asset(path: str, is_vfr: bool, fps: float = 30.0):
    """Create a mock MediaAsset with the fields we need."""
    asset = MagicMock()
    asset.path = path
    asset.is_vfr = is_vfr
    asset.fps = fps
    # Simulate r_frame_rate and avg_frame_rate strings
    if is_vfr:
        asset.r_frame_rate = "30000/1001"
        asset.avg_frame_rate = "25/1"
    else:
        asset.r_frame_rate = "30/1"
        asset.avg_frame_rate = "30/1"
    return asset


@pytest.fixture
def workspace_with_vfr(tmp_path: Path) -> Path:
    """Create a workspace with mixed VFR/CFR files."""
    media = tmp_path / "media" / "raw"
    media.mkdir(parents=True)
    (media / "clip_vfr.mp4").write_text("fake")
    (media / "clip_cfr.mp4").write_text("fake")
    (media / "notes.txt").write_text("not a video")
    return tmp_path


@pytest.fixture
def workspace_all_cfr(tmp_path: Path) -> Path:
    """Create a workspace with only CFR files."""
    media = tmp_path / "media" / "raw"
    media.mkdir(parents=True)
    (media / "a.mp4").write_text("fake")
    (media / "b.mov").write_text("fake")
    return tmp_path


@pytest.fixture
def workspace_empty(tmp_path: Path) -> Path:
    """Workspace with no video files."""
    (tmp_path / "media" / "raw").mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# VFRReport / VFRFile dataclass tests
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_vfr_file_fields(self):
        vf = VFRFile(
            path="/tmp/clip.mp4",
            r_frame_rate="30000/1001",
            avg_frame_rate="25/1",
            divergence_pct=16.7,
        )
        assert vf.divergence_pct == pytest.approx(16.7)
        d = asdict(vf)
        assert "r_frame_rate" in d

    def test_vfr_report_all_cfr(self):
        report = VFRReport(files_checked=3, vfr_files=[], all_cfr=True)
        assert report.all_cfr is True
        assert report.files_checked == 3

    def test_vfr_report_has_vfr(self):
        vf = VFRFile("/x.mp4", "30000/1001", "25/1", 16.7)
        report = VFRReport(files_checked=2, vfr_files=[vf], all_cfr=False)
        assert report.all_cfr is False
        assert len(report.vfr_files) == 1


# ---------------------------------------------------------------------------
# check_vfr pipeline tests
# ---------------------------------------------------------------------------

class TestCheckVFR:
    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.probe_media")
    def test_detects_vfr_files(self, mock_probe, workspace_with_vfr: Path):
        """VFR files should appear in the report."""
        def side_effect(path):
            if "vfr" in path.name:
                return _make_media_asset(str(path), is_vfr=True)
            return _make_media_asset(str(path), is_vfr=False)

        mock_probe.side_effect = side_effect

        report = check_vfr(workspace_with_vfr)
        assert report.files_checked == 2  # 2 video files, not txt
        assert report.all_cfr is False
        assert len(report.vfr_files) == 1
        assert "vfr" in str(report.vfr_files[0].path)

    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.probe_media")
    def test_all_cfr_workspace(self, mock_probe, workspace_all_cfr: Path):
        """All-CFR workspace should report all_cfr=True."""
        mock_probe.return_value = _make_media_asset("/x.mp4", is_vfr=False)

        report = check_vfr(workspace_all_cfr)
        assert report.all_cfr is True
        assert len(report.vfr_files) == 0

    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.probe_media")
    def test_empty_workspace(self, mock_probe, workspace_empty: Path):
        """Empty workspace should return zero files checked."""
        report = check_vfr(workspace_empty)
        assert report.files_checked == 0
        assert report.all_cfr is True
        mock_probe.assert_not_called()

    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.probe_media")
    def test_probe_error_skips_file(self, mock_probe, workspace_all_cfr: Path):
        """If probe_media raises, skip that file and continue."""
        mock_probe.side_effect = Exception("ffprobe failed")
        report = check_vfr(workspace_all_cfr)
        # Should not raise; files checked may be 0 due to errors
        assert report.all_cfr is True


# ---------------------------------------------------------------------------
# transcode_to_cfr tests
# ---------------------------------------------------------------------------

class TestTranscodeToCFR:
    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.subprocess")
    def test_output_path_has_cfr_suffix(self, mock_subprocess, tmp_path: Path):
        """Output should be alongside source with _cfr suffix."""
        source = tmp_path / "clip.mp4"
        source.write_text("fake")
        mock_subprocess.run.return_value = MagicMock(returncode=0)

        result = transcode_to_cfr(source, target_fps=30)

        assert result.name == "clip_cfr.mp4"
        assert result.parent == source.parent

    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.subprocess")
    def test_ffmpeg_command_includes_vsync_cfr(self, mock_subprocess, tmp_path: Path):
        """FFmpeg command should include -vsync cfr -r {fps}."""
        source = tmp_path / "clip.mp4"
        source.write_text("fake")
        mock_subprocess.run.return_value = MagicMock(returncode=0)

        transcode_to_cfr(source, target_fps=30)

        call_args = mock_subprocess.run.call_args[0][0]
        assert "cfr" in call_args
        assert "-r" in call_args
        assert "30" in call_args

    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.subprocess")
    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.probe_media")
    def test_auto_detect_fps_when_none(self, mock_probe, mock_subprocess, tmp_path: Path):
        """When target_fps is None, use avg_frame_rate from probe."""
        source = tmp_path / "clip.mp4"
        source.write_text("fake")
        mock_probe.return_value = _make_media_asset(str(source), is_vfr=True, fps=24.0)
        mock_subprocess.run.return_value = MagicMock(returncode=0)

        transcode_to_cfr(source, target_fps=None)

        call_args = mock_subprocess.run.call_args[0][0]
        assert "24" in call_args

    @patch("workshop_video_brain.edit_mcp.pipelines.vfr_check.subprocess")
    def test_ffmpeg_failure_raises(self, mock_subprocess, tmp_path: Path):
        """Non-zero FFmpeg exit should raise RuntimeError."""
        source = tmp_path / "clip.mp4"
        source.write_text("fake")
        mock_subprocess.run.return_value = MagicMock(
            returncode=1, stderr="Error encoding",
        )

        with pytest.raises(RuntimeError, match="FFmpeg transcode failed"):
            transcode_to_cfr(source, target_fps=30)
```

### Step 2: Implement `vfr_check.py`

**Create** `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/vfr_check.py`:

```python
"""VFR detection and CFR transcode pipeline.

Scans workspace video files for variable frame rate (VFR) media and
provides a transcode function to convert to constant frame rate (CFR).
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import (
    DEFAULT_EXTENSIONS,
    probe_media,
)

logger = logging.getLogger(__name__)

# Only scan video extensions (exclude audio-only)
_VIDEO_EXTENSIONS: set[str] = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".mts", ".m2ts",
}


@dataclass
class VFRFile:
    """A single file identified as VFR."""

    path: str  # str for MCP serialization compatibility
    r_frame_rate: str
    avg_frame_rate: str
    divergence_pct: float


@dataclass
class VFRReport:
    """Result of scanning a workspace for VFR media."""

    files_checked: int
    vfr_files: list[VFRFile] = field(default_factory=list)
    all_cfr: bool = True


def check_vfr(workspace_root: Path) -> VFRReport:
    """Scan all video files in workspace and report VFR files.

    Args:
        workspace_root: Path to workspace root directory.

    Returns:
        VFRReport with counts and list of VFR files.
    """
    video_files = _find_video_files(workspace_root)
    vfr_files: list[VFRFile] = []
    checked = 0

    for vf in video_files:
        try:
            asset = probe_media(vf)
            checked += 1

            if asset.is_vfr:
                # Calculate divergence for the report
                r_rate = getattr(asset, "r_frame_rate", "0/1")
                avg_rate = getattr(asset, "avg_frame_rate", "0/1")
                divergence = _calculate_divergence(r_rate, avg_rate)

                vfr_files.append(VFRFile(
                    path=str(vf),
                    r_frame_rate=r_rate,
                    avg_frame_rate=avg_rate,
                    divergence_pct=divergence,
                ))
        except Exception:
            logger.warning("Failed to probe %s, skipping", vf, exc_info=True)

    return VFRReport(
        files_checked=checked,
        vfr_files=vfr_files,
        all_cfr=len(vfr_files) == 0,
    )


def transcode_to_cfr(
    source: Path,
    target_fps: int | None = None,
) -> Path:
    """Transcode a VFR file to constant frame rate.

    Args:
        source: Path to the VFR source file.
        target_fps: Target FPS. If None, auto-detect from avg_frame_rate via probe.

    Returns:
        Path to the output CFR file (alongside source with _cfr suffix).

    Raises:
        RuntimeError: If FFmpeg transcode fails.
    """
    if target_fps is None:
        asset = probe_media(source)
        target_fps = int(round(asset.fps)) or 30

    # Build output path with _cfr suffix
    output = source.parent / f"{source.stem}_cfr{source.suffix}"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(source),
        "-vsync", "cfr",
        "-r", str(target_fps),
        "-c:a", "copy",
        str(output),
    ]

    logger.info("Transcoding VFR -> CFR: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg transcode failed (exit {result.returncode}): "
            f"{result.stderr[:500]}"
        )

    return output


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_video_files(workspace_root: Path) -> list[Path]:
    """Recursively find video files in workspace."""
    files: list[Path] = []
    for ext in _VIDEO_EXTENSIONS:
        files.extend(workspace_root.rglob(f"*{ext}"))
    return sorted(files)


def _calculate_divergence(r_frame_rate: str, avg_frame_rate: str) -> float:
    """Calculate percentage divergence between two frame rate strings."""
    r_val = _parse_rate(r_frame_rate)
    avg_val = _parse_rate(avg_frame_rate)

    if avg_val == 0:
        return 0.0

    return abs(r_val - avg_val) / avg_val * 100.0


def _parse_rate(rate_str: str) -> float:
    """Parse a frame rate string like '30/1' or '30000/1001' to float."""
    try:
        if "/" in rate_str:
            num, den = rate_str.split("/")
            return float(num) / float(den)
        return float(rate_str)
    except (ValueError, ZeroDivisionError):
        return 0.0
```

### Step 3: Add MCP tools

**Modify** `workshop-video-brain/src/workshop_video_brain/edit_mcp/server/tools.py` -- add two new tools at the end of the file:

```python
# ---------------------------------------------------------------------------
# VFR Detection tools
# ---------------------------------------------------------------------------


@mcp.tool()
def media_check_vfr(workspace_path: str) -> dict:
    """Scan workspace for variable frame rate (VFR) video files.

    VFR media causes audio drift and editing artifacts. This tool identifies
    files that need transcode to constant frame rate before editing.

    Args:
        workspace_path: Absolute path to the workspace root directory.

    Returns:
        Report with files_checked count, list of VFR files with divergence
        details, and all_cfr flag.
    """
    try:
        ws_root = _validate_workspace_path(workspace_path)
        from workshop_video_brain.edit_mcp.pipelines.vfr_check import check_vfr
        from dataclasses import asdict
        report = check_vfr(ws_root)
        data = asdict(report)
        return _ok(data)
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"VFR check failed: {exc}")


@mcp.tool()
def media_transcode_cfr(
    workspace_path: str,
    file_path: str,
    target_fps: int = 0,
) -> dict:
    """Transcode a VFR video file to constant frame rate (CFR).

    Produces a new file alongside the source with a '_cfr' suffix.

    Args:
        workspace_path: Absolute path to the workspace root directory.
        file_path: Path to the VFR file (absolute or relative to workspace).
        target_fps: Target frame rate. Use 0 to auto-detect from source.

    Returns:
        Path to the new CFR file.
    """
    try:
        ws_root = _validate_workspace_path(workspace_path)
        source = Path(file_path)
        if not source.is_absolute():
            source = ws_root / source
        if not source.exists():
            return _err(f"Source file not found: {source}")

        from workshop_video_brain.edit_mcp.pipelines.vfr_check import transcode_to_cfr
        fps = target_fps if target_fps > 0 else None
        output = transcode_to_cfr(source, target_fps=fps)
        return _ok({"output_path": str(output), "target_fps": target_fps or "auto"})
    except (ValueError, FileNotFoundError) as exc:
        return _err(str(exc))
    except RuntimeError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"Transcode failed: {exc}")
```

### Step 4: Run tests and verify

```bash
uv run pytest tests/unit/test_vfr_check.py -v
```

## Verification Commands

```bash
# Run new tests
uv run pytest tests/unit/test_vfr_check.py -v

# Run full suite to confirm no regressions
uv run pytest tests/ -v

# Verify module importable
python3 -c "
from workshop_video_brain.edit_mcp.pipelines.vfr_check import (
    VFRFile, VFRReport, check_vfr, transcode_to_cfr,
)
print('Import: PASS')
"

# Verify dataclass shape
python3 -c "
from dataclasses import fields
from workshop_video_brain.edit_mcp.pipelines.vfr_check import VFRFile, VFRReport
vfr_fields = {f.name for f in fields(VFRFile)}
assert vfr_fields == {'path', 'r_frame_rate', 'avg_frame_rate', 'divergence_pct'}  # path is str
report_fields = {f.name for f in fields(VFRReport)}
assert report_fields == {'files_checked', 'vfr_files', 'all_cfr'}
print('Dataclass shape: PASS')
"
```

## Acceptance Criteria

- [ ] `VFRFile` dataclass has fields: `path: str`, `r_frame_rate: str`, `avg_frame_rate: str`, `divergence_pct: float`
- [ ] `VFRReport` dataclass has fields: `files_checked: int`, `vfr_files: list[VFRFile]`, `all_cfr: bool`
- [ ] `check_vfr(workspace_root)` scans all video files recursively, probes each, returns `VFRReport`
- [ ] VFR files identified via `MediaAsset.is_vfr` flag (from Sub-Spec 1)
- [ ] Probe errors are caught and logged, file skipped (no crash)
- [ ] Empty workspace returns `VFRReport(files_checked=0, vfr_files=[], all_cfr=True)`
- [ ] `transcode_to_cfr(source, target_fps)` runs `ffmpeg -i {src} -vsync cfr -r {fps} {out}`
- [ ] Output file placed alongside source with `_cfr` suffix (e.g., `clip_cfr.mp4`)
- [ ] `target_fps=None` auto-detects from `probe_media()` avg frame rate
- [ ] FFmpeg failure raises `RuntimeError` with stderr excerpt
- [ ] MCP tool `media_check_vfr` validates workspace path and returns serialized report
- [ ] MCP tool `media_transcode_cfr` accepts absolute or relative file paths, handles `target_fps=0` as auto
- [ ] All new tests pass: `uv run pytest tests/unit/test_vfr_check.py -v`
- [ ] All existing tests still pass: `uv run pytest tests/ -v`
