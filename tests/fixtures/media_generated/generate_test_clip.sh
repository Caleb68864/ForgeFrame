#!/usr/bin/env bash
# Generate a deterministic test video for Kdenlive round-trip tests.
# Profile matches atsc_1080p_2997 reference: 1920x1080 @ 30000/1001 fps.
# 5 seconds, H.264 + AAC, color bars + 1kHz tone.

set -euo pipefail

FFMPEG="${FFMPEG:-/c/Users/CalebBennett/Music/Get Music/ffmpeg.exe}"
OUT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="${OUT_DIR}/test_clip_1080p2997_5s.mp4"

"${FFMPEG}" -y \
  -f lavfi -i "smptehdbars=size=1920x1080:rate=30000/1001:duration=5" \
  -f lavfi -i "sine=frequency=1000:sample_rate=48000:duration=5" \
  -c:v libx264 -pix_fmt yuv420p -preset veryfast -crf 23 \
  -c:a aac -b:a 128k -ac 2 \
  -movflags +faststart \
  "${OUT}"

echo "Generated: ${OUT}"
