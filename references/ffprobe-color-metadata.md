# ffprobe Color Metadata and VFR Detection Reference

## Color Metadata Fields

ffprobe reports per-stream color metadata via `-show_streams` or `-show_entries`:

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=color_space,color_primaries,color_transfer,color_range,pix_fmt \
  -of json input.mp4
```

### Key Fields

| Field | Description | Common Values |
|-------|-------------|---------------|
| `color_space` | Color matrix coefficients | `bt709`, `bt2020nc`, `bt470bg`, `smpte170m` |
| `color_primaries` | Color primaries | `bt709`, `bt2020`, `bt470bg`, `smpte170m` |
| `color_transfer` | Transfer characteristics | `bt709`, `smpte2084` (PQ/HDR10), `arib-std-b67` (HLG), `smpte170m` |
| `color_range` | Quantization range | `tv` (limited), `pc` (full) |
| `pix_fmt` | Pixel format | `yuv420p`, `yuv422p10le`, `yuv420p10le` |

### HDR Detection

HDR content is identified by transfer characteristics:
- **HDR10/PQ:** `color_transfer = "smpte2084"`
- **HLG:** `color_transfer = "arib-std-b67"`

### Color Space Mapping

| Standard | color_space | color_primaries | color_transfer | Usage |
|----------|-------------|-----------------|----------------|-------|
| BT.709 | `bt709` | `bt709` | `bt709` | HD SDR (standard) |
| BT.601 NTSC | `smpte170m` | `smpte170m` | `smpte170m` | SD NTSC |
| BT.601 PAL | `bt470bg` | `bt470bg` | `bt470bg` | SD PAL |
| BT.2020 SDR | `bt2020nc` | `bt2020` | `bt709` | UHD SDR |
| BT.2020 HDR10 | `bt2020nc` | `bt2020` | `smpte2084` | UHD HDR10 |
| BT.2020 HLG | `bt2020nc` | `bt2020` | `arib-std-b67` | UHD HLG |

### Example JSON Output (HDR source)

```json
{
  "streams": [{
    "color_space": "bt2020nc",
    "color_primaries": "bt2020",
    "color_transfer": "smpte2084",
    "color_range": "tv",
    "pix_fmt": "yuv420p10le"
  }]
}
```

## VFR Detection Fields

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=r_frame_rate,avg_frame_rate \
  -of json input.mp4
```

| Field | Description | Format |
|-------|-------------|--------|
| `r_frame_rate` | Real (container) frame rate | `"30/1"`, `"30000/1001"` |
| `avg_frame_rate` | Average frame rate | `"25/1"`, `"29970/1001"` |

**VFR Detection Logic:** If `abs(r_fps - avg_fps) / max(r_fps, avg_fps) > 0.05`, the file is VFR.

**Note:** Some CFR containers may show slight differences due to metadata rounding. The 5% threshold avoids false positives.

## Full Probe Command (all fields)

```bash
ffprobe -v quiet -print_format json -show_format -show_streams \
  -select_streams v:0 input.mp4
```

---

**Sources:**
- [FFprobe documentation](https://ffmpeg.org/ffprobe.html)
- [Kdenlive Color Hell article](https://kdenlive.org/en/project/color-hell-ffmpeg-transcoding-and-preserving-bt-601/)
- [FFprobe JSON type definitions](https://gist.github.com/termermc/2a62735201cede462763456542d8a266)
- [FastFlix HDR color space discussion](https://github.com/cdgriffith/FastFlix/issues/102)
