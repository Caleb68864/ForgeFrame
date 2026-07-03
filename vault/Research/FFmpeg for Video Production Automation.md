---
title: FFmpeg for Video Production Automation
date: 2026-07-03
type: reference
tags: [ffmpeg, forgeframe, research, automation]
---

# FFmpeg for Video Production Automation

Research for [[ForgeFrame]] on using FFmpeg to automate the mundane parts of a
solo workshop-video pipeline, with emphasis on **clip sorting** and getting
low-value work out of the way. Every filter name below was verified against the
official [FFmpeg filters documentation](https://ffmpeg.org/ffmpeg-filters.html).

## What ForgeFrame already does with FFmpeg

Establishing the baseline so proposals below do not duplicate existing tools.

| Area | Where | Filters / commands in use |
|---|---|---|
| Probe / metadata | `adapters/ffmpeg/probe.py` | `ffprobe -show_format -show_streams`; VFR detection via `r_frame_rate` vs `avg_frame_rate`; MD5 of first 64 KB as a fingerprint |
| Loudness measure | `probe.py::measure_loudness` | `loudnorm=print_format=json` (parses `input_i`, `input_tp`, `input_lra`) |
| Silence detect | `adapters/ffmpeg/silence.py` | `silencedetect=noise=..dB:d=..` |
| Audio cleanup | `adapters/ffmpeg/audio.py` | `loudnorm` (single pass), `acompressor`, `afftdn`, `highpass`, `equalizer` (de-ess), `silenceremove`, `alimiter` |
| Proxies | `adapters/ffmpeg/proxy.py` | `scale=-2:720 -c:v libx264 -preset fast -crf 23` |
| VFR -> CFR | `pipelines/vfr_check.py` | VFR scan + transcode to constant frame rate |
| Post-render QC | `pipelines/qc_check.py` | `blackdetect`, `silencedetect`, `loudnorm`, `astats` (clipping), file-size |
| Color | `pipelines/color_tools.py` | `ffprobe` color metadata only (space / primaries / transfer / HDR); **no pixel-level stats** |

**Gaps** (nothing in the repo touches these yet): scene detection, freezedetect,
cropdetect, `signalstats`/`blurdetect` pixel stats, perceptual/near-duplicate
hashing, keyframe/contact-sheet extraction, `ebur128`, two-pass `loudnorm`,
`vidstab`, `deflicker`, video denoise, `minterpolate`, `deshake`, video
`colorbalance`/`normalize`, silence-based segmenting, stream-copy trims,
gif/preview generation, waveform/vectorscope images, chromaprint fingerprinting,
and hardware acceleration.

---

## 1. Content analysis for auto-sorting

The high-leverage category: turn a folder of raw clips into a labelled,
searchable set that feeds the `broll_library` index and extends the `qc_check`
pattern. All of these run in analysis-only mode (`-f null -`) so they never
write video -- cheap to batch over a shoot.

| Capability | Filter | What it tells you | Proposed MCP tool (contract) |
|---|---|---|---|
| Scene cuts | `scdet` / `select='gt(scene,x)'` | Shot boundaries inside a long recording | `clips_detect_scenes(file) -> cut timestamps + scores` |
| Black frames | `blackdetect` | Lens-cap / dead footage regions | folds into `clips_qc_scan` |
| Frozen frames | `freezedetect` | Dropped-frame / stuck camera | folds into `clips_qc_scan` |
| Crop / letterbox | `cropdetect` | Suggested crop rectangle, pillarbox detection | `media_detect_crop(file) -> crop=w:h:x:y` |
| Silence vs speech | `silencedetect` | Talking vs dead-air ratio (usable-take signal) | folds into `clips_qc_scan` |
| Loudness stats | `ebur128` | Integrated LUFS / LRA / true-peak per clip | `audio_loudness_scan(dir) -> per-clip LUFS` |
| Exposure / histogram | `signalstats` | `YAVG/YMIN/YMAX`, over/under-exposure, clipping | `clips_exposure_scan(file) -> exposure verdict` |
| Blur / sharpness | `blurdetect` | Per-frame blur score (soft/OOF footage) | folds into `clips_qc_scan` |
| Near-duplicate detection | `signature` (MPEG-7) or frame pHash | Duplicate / near-dup clips in library | `clips_find_duplicates(dir) -> dup groups` |
| Keyframe extraction | `thumbnail` / `select` | Representative frames for AI-vision tagging | `media_thumbnail_sheet(file) -> frame paths` |
| Contact sheet | `tile` | One montage image per clip for fast triage | `media_thumbnail_sheet(..., grid=true)` |

### Scene detection

`scdet` writes a per-frame score into metadata; `select` can cut on it. To slice
a long recording into one file per shot:

```bash
# Report scene scores (analysis only)
ffmpeg -i take.mov -vf "scdet=threshold=10" -f null - 2>scenes.log
# scdet emits lavfi.scd.score and lavfi.scd.time in metadata

# Split into per-shot segments at scene changes >= 0.4
ffmpeg -i take.mov -filter_complex \
  "select='gt(scene,0.4)',metadata=print:file=cuts.txt" -vsync vfr shots_%03d.png
```

Surfaces as `clips_detect_scenes`: returns a list of `{time, score}` cut points.
An agent (or `media_segment_at_silence`) then splits the recording, and each shot
lands in the `broll_library` index as its own entry.

### Exposure / histogram via signalstats

`signalstats` is the missing pixel-level companion to the metadata-only
`color_analyze`. Verified metadata keys include `lavfi.signalstats.YAVG`,
`YMIN`, `YMAX`, `YLOW`, `YHIGH`, plus `SATAVG`.

```bash
ffmpeg -i clip.mov -vf "signalstats,metadata=print:file=stats.txt" -f null -
# YAVG < ~40 => underexposed; YMAX pinned at 255 => blown highlights
```

### Blur / sharpness

```bash
ffmpeg -i clip.mov -vf "blurdetect,metadata=print:file=blur.txt" -f null -
# lavfi.blurdetect.blur -- higher = sharper edges; low across a clip = soft/OOF
```

### Near-duplicate detection

MD5-of-64 KB (current `probe.py`) only finds *byte-identical* files. For
*perceptual* near-dups (same shot re-recorded, trimmed copies), FFmpeg's
`signature` filter emits MPEG-7 video signatures and can compare two inputs:

```bash
# Emit binary signatures for a whole folder
ffmpeg -i a.mov -i b.mov -filter_complex \
  "[0:v][1:v]signature=nb_inputs=2:detectmode=full:format=binary:filename=sig.bin" \
  -f null -
```

For a lighter approach that pairs with the existing thumbnail idea: extract 1
frame every N seconds and compute an image perceptual hash (pHash / dHash) in
Python, then cluster by Hamming distance. Surfaces as `clips_find_duplicates`.

### Keyframe extraction + contact sheets

The single most useful primitive for **AI-vision tagging** -- extract a handful
of representative frames, hand them to an agent that looks at the images, and
write the returned tags straight into `broll_library_tag`.

```bash
# N most-representative frames (thumbnail picks the most "typical" frame per batch)
ffmpeg -i clip.mov -vf "thumbnail=100,scale=640:-1" -frames:v 1 thumb.png

# Even sampling -> 3x3 contact sheet, one image summarising the whole clip
ffmpeg -i clip.mov -vf "fps=1/5,scale=320:-1,tile=3x3" -frames:v 1 sheet.png
```

---

## 2. Fixing footage automatically

Batch "make it usable" passes. These write new media, so they follow the repo's
safety rules (never touch `media/raw/`; write to `media/processed/` with a
suffix, mirroring the `_cfr` and `_proxy` conventions).

| Fix | Filter(s) | Notes | Proposed MCP tool |
|---|---|---|---|
| Stabilization | `vidstabdetect` + `vidstabtransform` | Two-pass; needs `libvidstab` build | `media_stabilize(file)` |
| Light stabilization | `deshake` | Single-pass, no extra lib | option inside `media_stabilize` |
| Loudness (proper) | `loudnorm` two-pass | Measure then apply -- more accurate than current single pass | `audio_normalize_two_pass(file)` |
| Flicker | `deflicker` | Rolling-average luminance smoothing (LED/screen flicker) | `media_deflicker(file)` |
| Denoise (video) | `atadenoise`, `hqdn3d` | High-ISO / low-light grain | `media_denoise_video(file)` |
| Slow motion | `minterpolate=mi_mode=mci` | Motion-interpolated smooth slow-mo | `clip_smooth_slowmo(file, factor)` |
| Auto crop | `cropdetect` -> `crop` | Remove black bars / reframe | `media_autocrop(file)` |
| Color balance | `colorbalance`, `normalize` | Auto white-balance / contrast stretch | `media_color_normalize(file)` |

### Two-pass stabilization

```bash
# Pass 1 -- analyse motion
ffmpeg -i shaky.mov -vf vidstabdetect=shakiness=6:result=transforms.trf -f null -
# Pass 2 -- apply
ffmpeg -i shaky.mov -vf \
  vidstabtransform=input=transforms.trf:smoothing=30,unsharp=5:5:0.8 \
  -c:v libx264 -crf 18 stable.mp4
```

### Two-pass loudnorm (upgrade to existing normalize)

Current `normalize_audio` runs `loudnorm` in one pass. The accurate form measures
first, then feeds the measured values back:

```bash
# Pass 1 -- measured values already available via probe.py::measure_loudness
# Pass 2
ffmpeg -i in.wav -af \
  loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=-21.3:measured_TP=-4.1:\
measured_LRA=9.2:measured_thresh=-31.7:linear=true \
  out.wav
```

### Video denoise / deflicker / slow-mo

```bash
ffmpeg -i noisy.mov -vf hqdn3d=4:3:6:4.5 clean.mp4          # spatial+temporal denoise
ffmpeg -i noisy.mov -vf atadenoise clean.mp4               # adaptive temporal denoise
ffmpeg -i flicker.mov -vf deflicker=mode=pm:size=10 out.mp4
ffmpeg -i clip.mov -vf "minterpolate=fps=120:mi_mode=mci:mc_mode=aobmc" -r 24 slowmo.mp4
```

### Auto crop

```bash
ffmpeg -ss 5 -i clip.mov -vf cropdetect -frames:v 200 -f null - 2>&1 | grep crop=
# -> crop=1920:800:0:140 ; feed that into a second pass or Kdenlive crop effect
```

---

## 3. Workflow accelerators

Grab-bag of time savers.

| Accelerator | Mechanism | Proposed MCP tool |
|---|---|---|
| Split long rec at silences | `segment` muxer + silence points | `media_segment_at_silence(file)` |
| Fast lossless trims | `-ss ... -to ... -c copy` | `clip_extract(file, in, out)` (stream copy) |
| Preview clips | animated GIF / tiny mp4 | `clips_preview_gif(file)` |
| QC report visuals | `waveform`, `vectorscope`, `showspectrumpic` | images embedded in `qc_check` report |
| Multicam / take sync | chromaprint audio fingerprint | `media_sync_by_audio(a, b)` |
| Faster encodes | `-hwaccel` / NVENC / QSV / VAAPI | flag on proxy + render tools |

### Segment a long recording at silences

Two moves: get silence points from the existing `silencedetect` adapter, then
cut with the `segment` muxer at those timestamps (stream-copy = near-instant):

```bash
ffmpeg -i lecture.mov -c copy -f segment \
  -segment_times 62.4,145.9,301.2 -reset_timestamps 1 take_%03d.mov
```

### Stream-copy trim (no re-encode)

```bash
ffmpeg -ss 00:01:12 -to 00:01:48 -i clip.mov -c copy sub.mov
```

### QC report visuals

```bash
ffmpeg -i clip.mov -filter_complex "waveform=mode=column" -frames:v 1 wave.png
ffmpeg -i clip.mov -filter_complex "vectorscope=mode=color3" -frames:v 1 vscope.png
ffmpeg -i clip.wav -lavfi showspectrumpic=s=1024x512 spectrum.png
```

These images can be embedded into the QC report note for at-a-glance
exposure/color/audio-spectrum sanity checks.

### Audio fingerprint for multicam sync

FFmpeg's `chromaprint` muxer emits an AcoustID-compatible fingerprint. Fingerprint
each camera/recorder track, cross-correlate the fingerprints, and recover the
offset to align multicam angles or match a lav mic to camera audio.

```bash
ffmpeg -i camA.mov -f chromaprint -fp_format raw -silence_threshold -1 camA.fp
ffmpeg -i camB.mov -f chromaprint -fp_format raw -silence_threshold -1 camB.fp
# cross-correlate the two raw fingerprints in Python -> time offset
```

### Hardware acceleration

Proxy and render passes can offload to the GPU. Detect once, then add the flags:

```bash
ffmpeg -hwaccel cuda -i in.mov -c:v h264_nvenc -preset p5 -cq 23 out.mp4   # NVIDIA
ffmpeg -hwaccel qsv  -i in.mov -c:v h264_qsv  -global_quality 23 out.mp4   # Intel
ffmpeg -hwaccel vaapi -vaapi_device /dev/dri/renderD128 -i in.mov \
  -vf 'format=nv12,hwupload' -c:v h264_vaapi out.mp4                        # AMD/Linux
```

Best value on the existing `proxy_generate` and `render_final` paths where the
current `libx264 -preset fast` is CPU-bound.

---

## TOP 10 by value-to-effort (clip sorting + mundane automation)

Ranked for a solo creator drowning in raw clips. Effort: **S** = a few hours
(one filter + parse, mirrors an existing adapter), **M** = a day (two-pass or new
data model), **L** = multi-day.

| # | Tool | One-liner | Effort | Ties into | Status |
|---|---|---|---|---|---|
| 1 | `media_thumbnail_sheet` | Extract representative keyframes + a contact sheet per clip so an AI-vision agent can auto-tag it | **S** | `broll_library_tag` | ✅ BUILT |
| 2 | `clips_qc_scan` | Batch `blackdetect`+`freezedetect`+`blurdetect`+`signalstats`+silence-ratio to flag unusable clips and auto-rate takes | **S** | extends `qc_check`; writes `rating` to index | ✅ BUILT |
| 3 | `clips_detect_scenes` | Detect shot boundaries in a long recording via `scdet`/`select=scene` and return cut timestamps | **S** | feeds `broll_library_index` | ✅ BUILT |
| 4 | `media_segment_at_silence` | Split a long recording into per-take files at detected silences using the `segment` muxer (stream copy) | **S** | reuses `silence.py`; feeds index | ✅ BUILT |
| 5 | `audio_loudness_scan` | Batch `ebur128`/`loudnorm` measure across clips and store per-clip LUFS for consistency sorting | **S** | reuses `measure_loudness`; index field | ✅ BUILT |
| 6 | `clips_find_duplicates` | Perceptual/`signature`-hash clips to surface near-duplicate and re-recorded takes | **M** | dedupes `broll_library` | |
| 7 | `clips_preview_gif` | Generate a small looping GIF/mp4 preview per clip for fast visual triage | **S** | review UI / index | |
| 8 | `audio_normalize_two_pass` | Upgrade `normalize_audio` to measured two-pass `loudnorm` for accurate broadcast loudness | **S** | replaces single-pass path -- **BUILT 2026-07-03** (pipelines/loudnorm_two_pass.py; verified within +/-1 LU) | |
| 9 | `media_denoise_video` | One-call `hqdn3d`/`atadenoise` cleanup for high-ISO/low-light footage | **S** | `media/processed/` output -- **BUILT 2026-07-03** (pipelines/denoise_video.py; verified noise reduction via YDIF) | |
| 10 | `media_stabilize` | Two-pass `vidstabdetect`+`vidstabtransform` (with `deshake` fallback) stabilization | **M** | `media/processed/` output | ✅ BUILT |

### Why this ordering

- **1-5 are all Small and directly attack clip sorting.** Each reuses an
  existing adapter pattern (`qc_check`, `silence.py`, `measure_loudness`,
  `proxy.py`) and writes results into the `broll_library` index rather than
  producing new media -- fast to build, high daily payoff.
- **1 + 2 + 3 compose into an "ingest brain":** segment a shoot, QC-flag the
  junk, thumbnail the survivors, let a vision agent tag them, and the library
  fills itself.
- **6-10 are fixers.** Valuable but each writes new media and carries more edge
  cases (build flags for vidstab, motion artefacts for minterpolate), so they
  rank below the analysis tools.

### Deferred (lower value-to-effort here)

`minterpolate` slow-mo, `deflicker`, `cropdetect` auto-crop, `colorbalance`/
`normalize`, waveform/vectorscope QC images, chromaprint multicam sync, and
hardware acceleration -- all real wins, but either niche for a solo
workshop-video workflow or better added as flags on existing tools
(`proxy_generate`, `render_final`, `qc_check`) than as standalone tools.

## Sources

- [FFmpeg Filters Documentation](https://ffmpeg.org/ffmpeg-filters.html)
- [FFmpeg chromaprint muxer](https://ffmpeg.org/doxygen/trunk/chromaprint_8c_source.html)
