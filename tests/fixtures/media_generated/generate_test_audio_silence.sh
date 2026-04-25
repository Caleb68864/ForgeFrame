#!/usr/bin/env bash
# Generate a 5-second clip with audio shape: 1.5s tone @ 440Hz, 2s silence,
# 1.5s tone @ 880Hz.  Used by ffmpeg smoke tests for silence detection.
set -euo pipefail
FFMPEG="${FFMPEG:-/c/Users/CalebBennett/Music/Get Music/ffmpeg.exe}"
OUT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="${OUT_DIR}/test_audio_with_silence.mp4"

"${FFMPEG}" -y \
  -f lavfi -i "color=c=black:s=320x180:r=30:d=5" \
  -f lavfi -i "sine=f=440:r=48000:d=1.5" \
  -f lavfi -i "anullsrc=r=48000:cl=mono:d=2" \
  -f lavfi -i "sine=f=880:r=48000:d=1.5" \
  -filter_complex "[1:a][2:a][3:a]concat=n=3:v=0:a=1[a]" \
  -map 0:v -map "[a]" \
  -c:v libx264 -preset veryfast -crf 28 -pix_fmt yuv420p \
  -c:a aac -b:a 96k \
  -shortest "${OUT}"

echo "Generated: ${OUT}"
