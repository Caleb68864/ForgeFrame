"""Perceptual near-duplicate detection for video clips (pure functions).

Command-construction, perceptual-hash math and clustering helpers for the
``clips_find_duplicates`` MCP bundle tool
(``edit_mcp/server/bundles/clip_dupes.py``).  Analysis-only: this pipeline
never writes video -- it extracts a handful of small still frames per clip,
hashes them and reports duplicate groups + a JSON report under ``reports/``.

Two methods, chosen by the caller:

* ``"phash"`` (default) -- extract ``frames_per_clip`` evenly-sampled frames
  per clip via FFmpeg, compute a **dHash** (difference hash) per frame on a
  ``(hash_size+1) x hash_size`` grayscale grid, then cluster clips by the mean
  best-match Hamming distance between their frame-hash sets.  This is
  *perceptual*: it groups re-recorded / trimmed / re-encoded takes that the
  existing byte-level MD5-of-64KB fingerprint in ``adapters/ffmpeg/probe.py``
  (line ~115) treats as unrelated files.
* ``"signature"`` -- FFmpeg's MPEG-7 ``signature`` filter compared pairwise
  (``nb_inputs=2:detectmode=full``).  Only usable when the local FFmpeg build
  exposes the filter (:func:`has_signature_filter`); otherwise the bundle
  returns an actionable error for that method.

The hashing math operates on a 2D grayscale pixel matrix (list of rows) so it
is unit-testable without PIL or real images; :func:`dhash_from_image` is the
thin PIL adapter that produces that matrix from a decoded frame.  PIL/Pillow is
a transitive dependency of the project; :func:`dhash_from_gray_bytes` is a
stdlib-only fallback that hashes a raw grayscale byte buffer (e.g. FFmpeg
``-pix_fmt gray`` rawvideo) with no PIL requirement.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

# ---------------------------------------------------------------------------
# Perceptual hash (dHash) math -- pure, PIL-free
# ---------------------------------------------------------------------------


def dhash_from_pixels(rows: list[list[int]]) -> int:
    """Compute a dHash from a grayscale pixel matrix.

    dHash compares each pixel with its right-hand neighbour: a bit is 1 when
    the left pixel is brighter than the one to its right.  For a hash of
    ``hash_size`` bits per row the matrix must have ``hash_size`` rows and
    ``hash_size + 1`` columns, yielding ``hash_size * hash_size`` bits total
    (64 bits for the default ``9x8`` grid).

    Args:
        rows: List of rows; each row a list of grayscale ints (0-255).  Every
            row must have the same length ``>= 2``.

    Returns:
        The hash as a non-negative integer.  Bit ``k`` (MSB-first across rows,
        left-to-right within a row) is set when ``row[c] > row[c + 1]``.

    Raises:
        ValueError: if *rows* is empty or ragged / too narrow.
    """
    if not rows:
        raise ValueError("rows must be non-empty")
    width = len(rows[0])
    if width < 2:
        raise ValueError("each row needs >= 2 columns for a difference hash")
    if any(len(r) != width for r in rows):
        raise ValueError("all rows must have the same width")

    bits = 0
    for row in rows:
        for col in range(width - 1):
            bits = (bits << 1) | (1 if row[col] > row[col + 1] else 0)
    return bits


def dhash_from_gray_bytes(
    data: bytes, width: int, height: int
) -> int:
    """dHash a raw single-channel grayscale buffer (stdlib-only fallback).

    Intended for FFmpeg ``-pix_fmt gray`` rawvideo output already scaled to
    ``width x height`` (use ``width = hash_size + 1``, ``height = hash_size``).

    Args:
        data: ``width * height`` grayscale bytes, row-major.
        width: Grid width (``hash_size + 1``).
        height: Grid height (``hash_size``).

    Returns:
        The dHash integer (``height * (width - 1)`` bits).

    Raises:
        ValueError: if *data* is too short for ``width * height`` pixels.
    """
    if len(data) < width * height:
        raise ValueError(
            f"gray buffer has {len(data)} bytes, need {width * height}"
        )
    rows = [
        list(data[r * width:(r + 1) * width]) for r in range(height)
    ]
    return dhash_from_pixels(rows)


def dhash_from_image(img, hash_size: int = 8) -> int:
    """dHash a decoded frame using PIL.

    Converts to grayscale, resizes to ``(hash_size + 1) x hash_size`` and
    delegates to :func:`dhash_from_pixels`.

    Args:
        img: A ``PIL.Image.Image`` instance.
        hash_size: Bits per row (default 8 -> 64-bit hash on a 9x8 grid).

    Returns:
        The dHash integer.
    """
    small = img.convert("L").resize(
        (hash_size + 1, hash_size)
    )
    # "L" mode -> one grayscale byte per pixel, row-major.
    return dhash_from_gray_bytes(
        small.tobytes(), width=hash_size + 1, height=hash_size
    )


def hamming_distance(a: int, b: int) -> int:
    """Number of differing bits between two hashes."""
    return (a ^ b).bit_count()


# ---------------------------------------------------------------------------
# Frame sampling + extraction commands
# ---------------------------------------------------------------------------


def frame_timestamps(duration: float, n: int) -> list[float]:
    """Return *n* evenly-spaced sample timestamps inside a clip.

    Samples the open interval ``(0, duration)`` at the centres of ``n`` equal
    buckets, i.e. fractions ``(i + 0.5) / n`` of the duration, so the first and
    last frames (often black/fade) are avoided and the spacing is duration-
    relative (robust to trimmed copies).

    Args:
        duration: Clip duration in seconds (``> 0``).
        n: Number of samples (``>= 1``).

    Returns:
        List of ``n`` timestamps in seconds, ascending.

    Raises:
        ValueError: if *duration* or *n* is non-positive.
    """
    if duration <= 0:
        raise ValueError("duration must be positive")
    if n < 1:
        raise ValueError("n must be >= 1")
    return [round(duration * (i + 0.5) / n, 4) for i in range(n)]


def frame_extract_command(
    input_path: Path,
    timestamp: float,
    output_path: Path,
    width: int = 64,
    overwrite: bool = True,
) -> list[str]:
    """FFmpeg command to grab one still frame at *timestamp*.

    ``-ss`` is placed before ``-i`` for a fast keyframe seek; the frame is
    scaled to ``width`` (aspect preserved, even height) -- small because dHash
    only needs a ``hash_size+1``-wide grid afterwards.

    Args:
        input_path: Source clip.
        timestamp: Seek position in seconds.
        output_path: Destination image (``.png``).
        width: Scaled width of the extracted frame.
        overwrite: Add ``-y`` when True.

    Returns:
        The argv list for :func:`subprocess.run`.
    """
    cmd = ["ffmpeg"]
    if overwrite:
        cmd.append("-y")
    cmd += [
        "-ss", f"{max(0.0, timestamp):.4f}",
        "-i", str(input_path),
        "-frames:v", "1",
        "-vf", f"scale={width}:-2",
        str(output_path),
    ]
    return cmd


# ---------------------------------------------------------------------------
# Clip-to-clip distance + clustering
# ---------------------------------------------------------------------------


def clip_distance(hashes_a: list[int], hashes_b: list[int]) -> float:
    """Symmetric perceptual distance between two clips' frame-hash sets.

    For every hash in each clip, the best (minimum) Hamming distance to any
    hash in the other clip is taken; the mean of all those best matches (both
    directions) is the clip distance.  Best-match aggregation tolerates the
    frame misalignment introduced by trimmed / re-encoded copies.

    Args:
        hashes_a: Frame dHashes for clip A (non-empty).
        hashes_b: Frame dHashes for clip B (non-empty).

    Returns:
        Mean best-match Hamming distance (lower = more similar).  Returns
        ``inf`` if either side is empty.
    """
    if not hashes_a or not hashes_b:
        return float("inf")
    d_ab = [min(hamming_distance(x, y) for y in hashes_b) for x in hashes_a]
    d_ba = [min(hamming_distance(y, x) for x in hashes_a) for y in hashes_b]
    both = d_ab + d_ba
    return sum(both) / len(both)


def cluster_by_distance(
    hashes_by_clip: dict[str, list[int]], threshold: float
) -> list[list[str]]:
    """Cluster clips whose pairwise :func:`clip_distance` is ``<= threshold``.

    Union-find over the clip keys: two clips join the same group when their
    distance is within *threshold*; groups are transitively merged.  Only
    groups with more than one member (i.e. actual duplicate sets) are returned.

    Args:
        hashes_by_clip: Mapping of clip id -> its frame dHashes.
        threshold: Maximum mean Hamming distance to consider a duplicate.

    Returns:
        List of duplicate groups (each a list of clip ids, input order
        preserved).  Singletons are omitted.
    """
    keys = list(hashes_by_clip)
    parent = {k: k for k in keys}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            if clip_distance(hashes_by_clip[a], hashes_by_clip[b]) <= threshold:
                union(a, b)

    groups: dict[str, list[str]] = {}
    for k in keys:  # preserve input order within each group
        groups.setdefault(find(k), []).append(k)

    return [members for members in groups.values() if len(members) > 1]


def similarity_score(distance: float, hash_bits: int = 64) -> float:
    """Convert a mean Hamming *distance* to a 0-100 similarity percentage."""
    if distance == float("inf"):
        return 0.0
    return round(max(0.0, (hash_bits - distance) / hash_bits) * 100.0, 2)


# ---------------------------------------------------------------------------
# MPEG-7 signature method (optional, filter-gated)
# ---------------------------------------------------------------------------


def has_signature_filter() -> bool:
    """True when the local FFmpeg build exposes the ``signature`` filter."""
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return False
    return bool(re.search(r"^\s*\S*\s+signature\s", out.stdout, re.MULTILINE))


def signature_pair_command(path_a: Path, path_b: Path) -> list[str]:
    """FFmpeg command comparing two clips with the MPEG-7 ``signature`` filter.

    Runs analysis-only (``-f null -``); the match verdict is logged to stderr
    and parsed by :func:`parse_signature_match`.
    """
    return [
        "ffmpeg", "-hide_banner",
        "-i", str(path_a),
        "-i", str(path_b),
        "-filter_complex",
        "[0:v][1:v]signature=nb_inputs=2:detectmode=full",
        "-f", "null", "-",
    ]


_SIG_MATCH_RE = re.compile(
    r"matching of video (\d+) at ([\d.]+) and (\d+) at ([\d.]+), "
    r"(\d+) frames matching"
)


def parse_signature_match(stderr: str) -> dict:
    """Parse the ``signature`` filter's pairwise verdict from FFmpeg stderr.

    Returns a dict with:
        * ``matched`` (bool) -- True unless FFmpeg logged ``no matching``.
        * ``whole`` (bool) -- ``whole video matching`` was reported.
        * ``frames`` (int | None) -- overlapping frame count, if given.
        * ``at`` (tuple[float, float] | None) -- (video0_time, video1_time).
    """
    if "no matching of video" in stderr:
        return {"matched": False, "whole": False, "frames": None, "at": None}
    m = _SIG_MATCH_RE.search(stderr)
    whole = "whole video matching" in stderr
    if m:
        return {
            "matched": True,
            "whole": whole,
            "frames": int(m.group(5)),
            "at": (float(m.group(2)), float(m.group(4))),
        }
    return {
        "matched": whole,
        "whole": whole,
        "frames": None,
        "at": None,
    }
