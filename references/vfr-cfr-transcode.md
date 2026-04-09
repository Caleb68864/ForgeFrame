# VFR Detection and CFR Transcode Reference

## What is VFR?

**Variable Frame Rate (VFR):** Frames are not evenly spaced in time. Common in screen recordings, phone cameras, and some action cameras. Causes audio drift and editing artifacts in NLEs like Kdenlive.

**Constant Frame Rate (CFR):** Frames are evenly spaced. Required for reliable editing.

## VFR Detection via ffprobe

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=r_frame_rate,avg_frame_rate \
  -of json input.mp4
```

### Output

```json
{
  "streams": [{
    "r_frame_rate": "30/1",
    "avg_frame_rate": "25/1"
  }]
}
```

### Detection Logic

```python
def _parse_rate(rate_str: str) -> float:
    num, den = rate_str.split("/")
    return int(num) / int(den)

r_fps = _parse_rate(r_frame_rate)
avg_fps = _parse_rate(avg_frame_rate)
divergence = abs(r_fps - avg_fps) / max(r_fps, avg_fps)
is_vfr = divergence > 0.05  # 5% threshold
```

**Why 5% threshold?** Some CFR containers report slightly different `r_frame_rate` vs `avg_frame_rate` due to metadata rounding. A 5% threshold avoids false positives while catching genuine VFR content.

### Common VFR Patterns

| Source | r_frame_rate | avg_frame_rate | VFR? |
|--------|-------------|----------------|------|
| Phone camera | `30/1` | `24/1` | Yes (20% divergence) |
| Screen recording | `60/1` | `45/1` | Yes (25% divergence) |
| CFR camera | `30/1` | `30/1` | No (0%) |
| NTSC CFR | `30000/1001` | `30000/1001` | No (0%) |

## VFR to CFR Transcode

### Basic Command

```bash
ffmpeg -i input_vfr.mp4 \
  -vsync cfr \
  -r 30 \
  -c:a copy \
  output_cfr.mp4
```

### Parameters

| Flag | Description |
|------|-------------|
| `-vsync cfr` | Force constant frame rate output |
| `-r 30` | Target frame rate (integer or fraction like `30000/1001`) |
| `-c:a copy` | Copy audio stream without re-encoding |

### Auto-detect Target FPS

When `target_fps` is not specified, use the `avg_frame_rate` from ffprobe as the target:
```python
target_fps = int(round(asset.fps))  # from probe_media()
```

### Output Naming Convention

Place the output alongside the source with a `_cfr` suffix:
```
input.mp4  ->  input_cfr.mp4
clip.mov   ->  clip_cfr.mov
```

### Note on `-vsync` vs `-fps_mode`

In FFmpeg 5.1+, `-vsync` is deprecated in favor of `-fps_mode`. Both accept `cfr` as a value. For maximum compatibility:
```bash
ffmpeg -i input.mp4 -fps_mode cfr -r 30 output.mp4
# or for older FFmpeg:
ffmpeg -i input.mp4 -vsync cfr -r 30 output.mp4
```

---

**Sources:**
- [FFmpeg Changing Frame Rate wiki](https://trac.ffmpeg.org/wiki/ChangingFrameRate)
- [FFprobe documentation](https://ffmpeg.org/ffprobe.html)
