# FFmpeg Filters for QC -- loudnorm, blackdetect, silencedetect, astats

## loudnorm (EBU R128 Loudness Normalization)

**Usage:** Measure integrated loudness without modifying:
```bash
ffmpeg -i input.wav -af loudnorm=print_format=json -f null -
```

**JSON output** (appears in stderr):
```json
{
    "input_i" : "-23.5",
    "input_tp" : "-1.2",
    "input_lra" : "8.3",
    "input_thresh" : "-34.2",
    "output_i" : "-16.0",
    "output_tp" : "-1.5",
    "output_lra" : "7.0",
    "output_thresh" : "-26.7",
    "normalization_type" : "dynamic",
    "target_offset" : "0.0"
}
```

**Key fields for ForgeFrame:**
- `input_i` -- Integrated loudness in LUFS
- `input_tp` -- True peak in dBTP
- `input_lra` -- Loudness range in LU

**Parameters:** `I` (target integrated, default -24), `TP` (max true peak, default -2), `LRA` (target loudness range, default 7), `print_format` (json/summary).

**Dual-pass normalization:**
```bash
# Pass 1: measure
ffmpeg -i in.wav -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null -
# Pass 2: normalize using measured values
ffmpeg -i in.wav -af loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=-23.5:measured_TP=-1.2:measured_LRA=8.3:measured_thresh=-34.2:offset=0.0 -ar 48k out.wav
```

## blackdetect

**Usage:**
```bash
ffmpeg -i input.mp4 -vf "blackdetect=d=0.5:pix_th=0.10" -an -f null -
```

**Parameters:** `d` (minimum black duration, default 2.0), `pix_th` (pixel threshold, default 0.10), `pic_th` (picture black ratio threshold, default 0.98).

**Stderr output format:**
```
[blackdetect @ 0x1234] black_start:0.00 black_end:2.50 black_duration:2.50
[blackdetect @ 0x1234] black_start:58.00 black_end:60.00 black_duration:2.00
```

**Parsing regex:** `black_start:(\d+\.?\d*)\s+black_end:(\d+\.?\d*)`

## silencedetect

**Usage:**
```bash
ffmpeg -i input.mp4 -af "silencedetect=n=-50dB:d=1.0" -vn -f null -
```

**Parameters:** `n` (noise floor threshold, default -60dB), `d` (minimum silence duration, default 2.0), `mono` (test each channel separately).

**Stderr output format:**
```
[silencedetect @ 0x5678] silence_start: 10.5
[silencedetect @ 0x5678] silence_end: 15.2 | silence_duration: 4.7
```

**Parsing regex (starts):** `silence_start:\s*(\d+\.?\d*)`
**Parsing regex (ends):** `silence_end:\s*(\d+\.?\d*)`

## astats

**Usage:**
```bash
ffmpeg -i input.mp4 -af "astats=metadata=1:reset=1" -vn -f null -
```

**Parameters:** `metadata` (set to 1 to output per-frame stats), `reset` (number of frames between stat resets, default 0 = no reset).

**Stderr output format:** Reports per-channel statistics including:
- `Flat_factor` -- presence indicates potential digital clipping
- `Number of Nans`, `Number of Infs`, `Number of denormals`
- Peak level, RMS level, Min/Max sample values

**Clipping detection:** Check for `Flat_factor` or `clipping` in stderr output.

---

**Sources:**
- [FFmpeg loudnorm filter](http://k.ylo.ph/2016/04/04/loudnorm.html)
- [FFmpeg Filters Documentation](https://ffmpeg.org/ffmpeg-filters.html)
- [FFmpeg loudnorm docs mirror](https://ayosec.github.io/ffmpeg-filters-docs/7.1/Filters/Audio/loudnorm.html)
- [Blackdetect filter usage](https://blog.gdeltproject.org/using-ffmpegs-blackdetect-filter-to-identify-commercial-blocks/)
