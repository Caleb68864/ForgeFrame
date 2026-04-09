---
type: phase-spec
master_spec: "docs/specs/2026-04-09-phase3-pipeline-completeness.md"
sub_spec: 3
title: "Render Profile Expansion"
dependencies: none
date: 2026-04-09
---

# Sub-Spec 3: Render Profile Expansion

## Shared Context
Infrastructure sub-spec. Adds five new render profiles (YouTube 1080p, YouTube 4K, Vimeo HQ, Master ProRes, Master DNxHR) and a codec availability check function. Profiles are loadable via the existing `load_profile(name)` mechanism. Used by sub-specs 6, 10, 11.

## Interface Contract
**Provides:**
- 5 new render profiles: `youtube-1080p`, `youtube-4k`, `vimeo-hq`, `master-prores`, `master-dnxhr`
- `check_codec_available(codec_name: str) -> bool` -- verifies FFmpeg has the encoder
- `fast_start: bool` and `movflags: str | None` fields on `RenderProfile` (informational)

**Requires:** nothing (extends existing profiles.py and executor.py)

## Implementation Steps

### Step 1: Write failing tests for profile loading and codec check

File: `tests/unit/test_render_profiles_expanded.py`

```python
"""Tests for expanded render profiles and codec availability check."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from workshop_video_brain.edit_mcp.adapters.render.profiles import (
    RenderProfile,
    load_profile,
    list_profiles,
)
from workshop_video_brain.edit_mcp.adapters.render.executor import check_codec_available


# ---------------------------------------------------------------------------
# Profile directory fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def profiles_dir(tmp_path):
    """Create a temporary profiles directory with all expected profiles."""
    profiles = {
        "youtube-1080p": {
            "name": "youtube-1080p",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "video_codec": "libx264",
            "video_bitrate": "8M",
            "audio_codec": "aac",
            "audio_bitrate": "192k",
            "extra_args": ["-profile:v", "high", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        },
        "youtube-4k": {
            "name": "youtube-4k",
            "width": 3840,
            "height": 2160,
            "fps": 30,
            "video_codec": "libx264",
            "video_bitrate": "35M",
            "audio_codec": "aac",
            "audio_bitrate": "192k",
            "extra_args": ["-profile:v", "high", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        },
        "vimeo-hq": {
            "name": "vimeo-hq",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "video_codec": "prores_ks",
            "video_bitrate": "0",
            "audio_codec": "aac",
            "audio_bitrate": "320k",
            "extra_args": ["-profile:v", "3", "-pix_fmt", "yuv422p10le"],
        },
        "master-prores": {
            "name": "master-prores",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "video_codec": "prores_ks",
            "video_bitrate": "0",
            "audio_codec": "pcm_s24le",
            "audio_bitrate": "0",
            "extra_args": ["-profile:v", "3", "-pix_fmt", "yuv422p10le"],
        },
        "master-dnxhr": {
            "name": "master-dnxhr",
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "video_codec": "dnxhd",
            "video_bitrate": "0",
            "audio_codec": "pcm_s24le",
            "audio_bitrate": "0",
            "extra_args": ["-profile:v", "dnxhr_hqx", "-pix_fmt", "yuv422p10le"],
        },
    }
    import yaml
    for name, data in profiles.items():
        (tmp_path / f"{name}.yaml").write_text(
            yaml.dump(data, default_flow_style=False), encoding="utf-8"
        )
    return tmp_path


# ---------------------------------------------------------------------------
# Profile loading tests
# ---------------------------------------------------------------------------

class TestYouTube1080pProfile:
    def test_loads_successfully(self, profiles_dir):
        profile = load_profile("youtube-1080p", profiles_dir=profiles_dir)

        assert profile.name == "youtube-1080p"
        assert profile.width == 1920
        assert profile.height == 1080
        assert profile.fps == 30
        assert profile.video_codec == "libx264"
        assert profile.video_bitrate == "8M"
        assert profile.audio_codec == "aac"
        assert profile.audio_bitrate == "192k"
        assert "-movflags" in profile.extra_args
        assert "+faststart" in profile.extra_args

    def test_has_h264_high_profile(self, profiles_dir):
        profile = load_profile("youtube-1080p", profiles_dir=profiles_dir)
        assert "-profile:v" in profile.extra_args
        idx = profile.extra_args.index("-profile:v")
        assert profile.extra_args[idx + 1] == "high"


class TestYouTube4kProfile:
    def test_loads_successfully(self, profiles_dir):
        profile = load_profile("youtube-4k", profiles_dir=profiles_dir)

        assert profile.name == "youtube-4k"
        assert profile.width == 3840
        assert profile.height == 2160
        assert profile.video_bitrate == "35M"

    def test_has_faststart(self, profiles_dir):
        profile = load_profile("youtube-4k", profiles_dir=profiles_dir)
        assert "+faststart" in profile.extra_args


class TestVimeoHQProfile:
    def test_loads_successfully(self, profiles_dir):
        profile = load_profile("vimeo-hq", profiles_dir=profiles_dir)

        assert profile.name == "vimeo-hq"
        assert profile.video_codec == "prores_ks"
        assert profile.audio_bitrate == "320k"

    def test_uses_prores_profile_3(self, profiles_dir):
        profile = load_profile("vimeo-hq", profiles_dir=profiles_dir)
        idx = profile.extra_args.index("-profile:v")
        assert profile.extra_args[idx + 1] == "3"


class TestMasterProResProfile:
    def test_loads_successfully(self, profiles_dir):
        profile = load_profile("master-prores", profiles_dir=profiles_dir)

        assert profile.name == "master-prores"
        assert profile.video_codec == "prores_ks"
        assert profile.audio_codec == "pcm_s24le"
        assert profile.video_bitrate == "0"
        assert profile.audio_bitrate == "0"

    def test_uses_10bit_pixel_format(self, profiles_dir):
        profile = load_profile("master-prores", profiles_dir=profiles_dir)
        assert "yuv422p10le" in profile.extra_args


class TestMasterDNxHRProfile:
    def test_loads_successfully(self, profiles_dir):
        profile = load_profile("master-dnxhr", profiles_dir=profiles_dir)

        assert profile.name == "master-dnxhr"
        assert profile.video_codec == "dnxhd"
        assert profile.audio_codec == "pcm_s24le"

    def test_uses_dnxhr_hqx_profile(self, profiles_dir):
        profile = load_profile("master-dnxhr", profiles_dir=profiles_dir)
        idx = profile.extra_args.index("-profile:v")
        assert profile.extra_args[idx + 1] == "dnxhr_hqx"


class TestListProfiles:
    def test_lists_all_new_profiles(self, profiles_dir):
        names = list_profiles(profiles_dir)

        assert "youtube-1080p" in names
        assert "youtube-4k" in names
        assert "vimeo-hq" in names
        assert "master-prores" in names
        assert "master-dnxhr" in names


# ---------------------------------------------------------------------------
# RenderProfile new fields tests
# ---------------------------------------------------------------------------

class TestRenderProfileNewFields:
    def test_fast_start_default_false(self):
        profile = RenderProfile(name="test")
        assert profile.fast_start is False

    def test_movflags_default_none(self):
        profile = RenderProfile(name="test")
        assert profile.movflags is None

    def test_fast_start_set_true(self):
        profile = RenderProfile(name="test", fast_start=True, movflags="+faststart")
        assert profile.fast_start is True
        assert profile.movflags == "+faststart"


# ---------------------------------------------------------------------------
# Codec availability check tests
# ---------------------------------------------------------------------------

class TestCheckCodecAvailable:
    @patch("subprocess.run")
    def test_available_codec_returns_true(self, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = (
            " DEV.LS h264                 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10\n"
            " DEV.L. libx264              libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10\n"
        )
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        assert check_codec_available("libx264") is True

    @patch("subprocess.run")
    def test_unavailable_codec_returns_false(self, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = (
            " DEV.LS h264                 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10\n"
        )
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        assert check_codec_available("libx265_nonexistent") is False

    @patch("subprocess.run")
    def test_ffmpeg_not_found_returns_false(self, mock_run):
        mock_run.side_effect = FileNotFoundError("ffmpeg not found")

        assert check_codec_available("libx264") is False

    @patch("subprocess.run")
    def test_prores_codec_check(self, mock_run):
        mock_result = MagicMock()
        mock_result.stdout = (
            " DEV.L. prores_ks            Apple ProRes (iCodec Pro)\n"
            " DEV.L. prores_aw            Apple ProRes\n"
        )
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        assert check_codec_available("prores_ks") is True
        assert check_codec_available("prores_aw") is True
        assert check_codec_available("dnxhd") is False
```

Run: `uv run pytest tests/unit/test_render_profiles_expanded.py -v`
Expected: FAIL (check_codec_available not importable; fast_start/movflags fields don't exist on RenderProfile)

### Step 2: Add new fields to RenderProfile

File: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/render/profiles.py`

Add to `RenderProfile` class after `extra_args`:
```python
fast_start: bool = False
movflags: str | None = None
```

### Step 3: Create render profile YAML files

Create the templates directory if it does not exist:
```bash
mkdir -p workshop-video-brain/templates/render
```

File: `workshop-video-brain/templates/render/youtube-1080p.yaml`
```yaml
name: youtube-1080p
width: 1920
height: 1080
fps: 30
video_codec: libx264
video_bitrate: "8M"
audio_codec: aac
audio_bitrate: "192k"
fast_start: true
movflags: "+faststart"
extra_args:
  - "-profile:v"
  - "high"
  - "-pix_fmt"
  - "yuv420p"
  - "-movflags"
  - "+faststart"
```

File: `workshop-video-brain/templates/render/youtube-4k.yaml`
```yaml
name: youtube-4k
width: 3840
height: 2160
fps: 30
video_codec: libx264
video_bitrate: "35M"
audio_codec: aac
audio_bitrate: "192k"
fast_start: true
movflags: "+faststart"
extra_args:
  - "-profile:v"
  - "high"
  - "-pix_fmt"
  - "yuv420p"
  - "-movflags"
  - "+faststart"
```

File: `workshop-video-brain/templates/render/vimeo-hq.yaml`
```yaml
name: vimeo-hq
width: 1920
height: 1080
fps: 30
video_codec: prores_ks
video_bitrate: "0"
audio_codec: aac
audio_bitrate: "320k"
extra_args:
  - "-profile:v"
  - "3"
  - "-pix_fmt"
  - "yuv422p10le"
```

File: `workshop-video-brain/templates/render/master-prores.yaml`
```yaml
name: master-prores
width: 1920
height: 1080
fps: 30
video_codec: prores_ks
video_bitrate: "0"
audio_codec: pcm_s24le
audio_bitrate: "0"
extra_args:
  - "-profile:v"
  - "3"
  - "-pix_fmt"
  - "yuv422p10le"
```

File: `workshop-video-brain/templates/render/master-dnxhr.yaml`
```yaml
name: master-dnxhr
width: 1920
height: 1080
fps: 30
video_codec: dnxhd
video_bitrate: "0"
audio_codec: pcm_s24le
audio_bitrate: "0"
extra_args:
  - "-profile:v"
  - "dnxhr_hqx"
  - "-pix_fmt"
  - "yuv422p10le"
```

### Step 4: Implement check_codec_available()

File: `workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/render/executor.py`

Add function before `execute_render()`:
```python
def check_codec_available(codec_name: str) -> bool:
    """Check if an FFmpeg encoder is available on this system.

    Runs ``ffmpeg -codecs`` and searches for the codec name in the output.

    Args:
        codec_name: Encoder name, e.g. "libx264", "prores_ks", "dnxhd".

    Returns:
        True if the codec is listed in FFmpeg's codec output, False otherwise.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-codecs"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Each codec line looks like: " DEV.L. libx264   description..."
        # Search for the codec name as a whole word
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                # The codec name is typically the second token after the flags
                if codec_name in parts:
                    return True
        return False
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        logger.warning("Could not check codec availability for '%s'", codec_name)
        return False
```

### Step 5: Run new tests

Run: `uv run pytest tests/unit/test_render_profiles_expanded.py -v`
Expected: all PASS

### Step 6: Run full test suite

Run: `uv run pytest tests/ -v`
Expected: all existing tests pass + new tests pass

### Step 7: Commit

```bash
git add tests/unit/test_render_profiles_expanded.py
git add workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/render/profiles.py
git add workshop-video-brain/src/workshop_video_brain/edit_mcp/adapters/render/executor.py
git add workshop-video-brain/templates/render/youtube-1080p.yaml
git add workshop-video-brain/templates/render/youtube-4k.yaml
git add workshop-video-brain/templates/render/vimeo-hq.yaml
git add workshop-video-brain/templates/render/master-prores.yaml
git add workshop-video-brain/templates/render/master-dnxhr.yaml
git commit -m "feat: add 5 render profiles and codec availability check"
```

## Verification

- `uv run pytest tests/unit/test_render_profiles_expanded.py -v` -- all pass
- `uv run pytest tests/ -v` -- all existing tests still pass
- All 5 profiles load correctly via `load_profile(name)`
- `list_profiles()` includes all 5 new profiles
- `check_codec_available()` returns True for present codecs, False for missing/unavailable
- `RenderProfile.fast_start` and `RenderProfile.movflags` fields accessible with safe defaults
- YouTube profiles include `-movflags +faststart` in extra_args
- Master profiles use lossless audio codec (`pcm_s24le`)
- ProRes profiles use 10-bit pixel format (`yuv422p10le`)
