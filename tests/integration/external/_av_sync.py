"""A/V sync oracle: media whose picture and sound both say which segment is playing.

Four 2 s segments at 25 fps: red/300 Hz, green/600 Hz, blue/900 Hz,
white/1200 Hz. At any rendered frame the colour and the dominant audio
frequency must name the same segment; after an edit that moved the picture
but not the sound (or the reverse) they disagree.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

SEGMENTS = (("red", 300), ("green", 600), ("blue", 900), ("white", 1200))
FPS = 25


def make_media(path: Path) -> Path:
    inputs, colours = [], ("red", "lime", "blue", "white")
    for colour in colours:
        inputs += ["-f", "lavfi", "-i", f"color=c={colour}:s=320x180:r=25:d=2"]
    for _name, freq in SEGMENTS:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={freq}:duration=2:sample_rate=48000"]
    graph = "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v];[4:a][5:a][6:a][7:a]concat=n=4:v=0:a=1[a]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(path)],
                   check=True, capture_output=True, timeout=120)
    return path


def _colour(png: Path) -> str:
    with Image.open(png) as image:
        r, g, b = image.convert("RGB").resize((8, 8)).getpixel((4, 4))
    if min(r, g, b) > 180:
        return "white"
    if max(r, g, b) < 50:
        return "black"
    return max((("red", r), ("green", g), ("blue", b)), key=lambda kv: kv[1])[0]


def av_at(video: Path, frame: int, work: Path) -> tuple[str, int | None]:
    """(colour, dominant frequency rounded to a segment tone, or None for silence) at *frame*."""
    png = work / f"av_{video.stem}_{frame}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"select=eq(n\\,{frame})",
                    "-frames:v", "1", str(png)], check=True, capture_output=True, timeout=120)
    start = frame / FPS + 0.04  # a window inside the frame's interval
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", "0.12", "-i", str(video),
                          "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
                         check=True, capture_output=True, timeout=120).stdout
    samples = np.frombuffer(raw, dtype=np.float32)
    freq = None
    if samples.size and float(np.sqrt(np.mean(samples ** 2))) > 0.01:
        spectrum = np.abs(np.fft.rfft(samples * np.hanning(samples.size)))
        peak = float(np.fft.rfftfreq(samples.size, 1 / 48000)[int(np.argmax(spectrum))])
        freq = min((tone for _n, tone in SEGMENTS), key=lambda tone: abs(tone - peak))
    return _colour(png), freq


def segment(colour: str) -> tuple[str, int]:
    return next(s for s in SEGMENTS if s[0] == colour)
