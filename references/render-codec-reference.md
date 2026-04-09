# Render Codec Reference -- H.264, ProRes, DNxHR

## H.264 / libx264 (YouTube/Streaming)

### YouTube Recommended Settings (2026)

| Parameter | 1080p30 | 1080p60 | 4K30 | 4K60 |
|-----------|---------|---------|------|------|
| Video Codec | H.264 High Profile | H.264 High Profile | H.264 High Profile | H.264 High Profile |
| Video Bitrate | 8 Mbps | 12 Mbps | 35 Mbps | 53 Mbps |
| Audio Codec | AAC-LC | AAC-LC | AAC-LC | AAC-LC |
| Audio Bitrate | 384 kbps stereo | 384 kbps stereo | 384 kbps stereo | 384 kbps stereo |
| Sample Rate | 48 kHz | 48 kHz | 48 kHz | 48 kHz |
| Container | MP4 | MP4 | MP4 | MP4 |
| Pixel Format | yuv420p | yuv420p | yuv420p | yuv420p |

### Key Flags

- **`-profile:v high`** -- H.264 High Profile (required for YouTube quality)
- **`-pix_fmt yuv420p`** -- Required for player compatibility
- **`-movflags +faststart`** -- Moves moov atom to start of file for progressive playback (critical for streaming)
- Use **VBR** (variable bitrate), not CBR

### FFmpeg Command (YouTube 1080p)

```bash
ffmpeg -i input.kdenlive \
  -c:v libx264 -profile:v high -pix_fmt yuv420p \
  -b:v 8M \
  -c:a aac -b:a 192k -ar 48000 \
  -movflags +faststart \
  output.mp4
```

### FFmpeg Command (YouTube 4K)

```bash
ffmpeg -i input.kdenlive \
  -vf scale=3840:2160 \
  -c:v libx264 -profile:v high -pix_fmt yuv420p \
  -b:v 35M \
  -c:a aac -b:a 192k -ar 48000 \
  -movflags +faststart \
  output.mp4
```

## Apple ProRes / prores_ks (Master/Vimeo)

### Encoder: `prores_ks`

| Profile | `-profile:v` | Quality | Use Case |
|---------|-------------|---------|----------|
| Proxy | 0 | Lowest | Offline editing |
| LT | 1 | Low | Lightweight editing |
| SQ | 2 | Standard | General use |
| HQ | 3 | High | **Master/delivery** |
| 4444 | 4 | Highest | VFX/compositing |

### Key Settings

- **Pixel format:** `yuv422p10le` (10-bit 4:2:2) for profiles 0-3
- **Container:** `.mov` (required for ProRes)
- **Audio:** `pcm_s24le` (24-bit PCM) for master, `aac` for Vimeo delivery
- **Bitrate:** Rate-controlled (no `-b:v` needed; quality is profile-dependent)

### FFmpeg Command (Master ProRes HQ)

```bash
ffmpeg -i input.kdenlive \
  -c:v prores_ks -profile:v 3 -pix_fmt yuv422p10le \
  -c:a pcm_s24le \
  output.mov
```

### FFmpeg Command (Vimeo HQ)

```bash
ffmpeg -i input.kdenlive \
  -c:v prores_ks -profile:v 3 -pix_fmt yuv422p10le \
  -c:a aac -b:a 320k \
  output.mov
```

## DNxHR / dnxhd (Master)

### Encoder: `dnxhd`

| Profile | `-profile:v` | Bit Depth | Chroma | Use Case |
|---------|-------------|-----------|--------|----------|
| DNxHR LB | dnxhr_lb | 8-bit | 4:2:2 | Low bandwidth |
| DNxHR SQ | dnxhr_sq | 8-bit | 4:2:2 | Standard quality |
| DNxHR HQ | dnxhr_hq | 8-bit | 4:2:2 | High quality |
| DNxHR HQX | dnxhr_hqx | 10-bit | 4:2:2 | **Broadcast delivery** |
| DNxHR 444 | dnxhr_444 | 10-bit | 4:4:4 | Cinema finishing |

### Key Settings

- **Pixel format:** `yuv422p10le` for HQX (10-bit 4:2:2)
- **Container:** `.mov` (standard for DNxHR)
- **Audio:** `pcm_s24le` for master delivery
- **Bitrate:** Rate-controlled (no `-b:v` needed)

### FFmpeg Command (Master DNxHR HQX)

```bash
ffmpeg -i input.kdenlive \
  -c:v dnxhd -profile:v dnxhr_hqx -pix_fmt yuv422p10le \
  -c:a pcm_s24le \
  output.mov
```

## Codec Availability Check

```bash
ffmpeg -codecs 2>/dev/null | grep -w libx264
ffmpeg -codecs 2>/dev/null | grep -w prores_ks
ffmpeg -codecs 2>/dev/null | grep -w dnxhd
```

Each line format: ` DEV.L. codec_name   Description`
Check that the codec name appears as a word token in the output.

---

**Sources:**
- [YouTube recommended upload encoding settings](https://support.google.com/youtube/answer/1722171)
- [ProRes Encoding Guidelines (Academy Software Foundation)](https://academysoftwarefoundation.github.io/EncodingGuidelines/EncodeProres.html)
- [DNxHR encoding tutorial](http://macilatthefront.blogspot.com/2018/12/tutorial-using-ffmpeg-for-dnxhddnxhr.html)
- [YouTube Upload Settings 2026 (Vibbit)](https://vibbit.ai/blog/youtube-upload-best-settings)
- [Best Video Format for YouTube 2026 (Levitate Media)](https://levitatemedia.com/learn/best-video-format-for-youtube)
