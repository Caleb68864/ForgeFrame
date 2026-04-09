#!/usr/bin/env bash
# Generate synthetic sample assets for the One-Minute Tutorial project
# Requires: ffmpeg
# These assets are CC-free (procedurally generated) and safe for any use.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/../assets-generated"

mkdir -p "$OUTPUT_DIR"

echo "Generating synthetic assets in $OUTPUT_DIR ..."

# 1) 10s 1080p30 test video with timecode
ffmpeg -y -f lavfi -i testsrc2=size=1920x1080:rate=30 \
  -vf "drawtext=text='%{pts\\:hms}':x=40:y=40:fontsize=48:fontcolor=white:box=1:boxcolor=black@0.7:boxborderw=10" \
  -t 10 -pix_fmt yuv420p "$OUTPUT_DIR/synthetic_testsrc_1080p30.mp4"

# 2) 10s stereo A440 tone for audio pipeline tests
ffmpeg -y -f lavfi -i "sine=frequency=440:sample_rate=48000:duration=10" \
  -ac 2 "$OUTPUT_DIR/synthetic_tone_48k.wav"

# 3) 10s silence (for loudness meter testing)
ffmpeg -y -f lavfi -i "anullsrc=r=48000:cl=stereo" \
  -t 10 "$OUTPUT_DIR/silent_48k.wav"

# 4) Title card backgrounds (solid colors, 1920x1080)
for color in "0x1a1a2e" "0x16213e" "0x0f3460" "0x533483"; do
  ffmpeg -y -f lavfi -i "color=c=${color}:size=1920x1080:duration=1:rate=1" \
    -frames:v 1 "$OUTPUT_DIR/title_bg_${color}.png"
done

# 5) Simple gradient overlay (2s, PNG sequence for compositing practice)
ffmpeg -y -f lavfi -i "color=c=black@0.0:size=1280x720:rate=30" \
  -vf "drawbox=x=200:y=150:w=880:h=420:color=white@0.8:t=fill" \
  -t 2 -frames:v 60 "$OUTPUT_DIR/overlay_%03d.png"

echo "Done! Assets generated in $OUTPUT_DIR"
echo "Import these into Kdenlive to start the beginner project."
