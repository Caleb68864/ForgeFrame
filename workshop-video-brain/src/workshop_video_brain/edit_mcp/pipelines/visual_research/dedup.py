"""Perceptual deduplication of :class:`FrameCandidate` lists.

Two candidates are considered duplicates when their perceptual hashes
(pHash, a DCT-based hash of a 32x32 grayscale thumbnail) differ by no more
than ``threshold`` bits (Hamming distance). Within each duplicate cluster the
candidate ranked highest by ``rank_key`` is kept; the rest are dropped from
the *returned list only* -- their source image files on disk are never
touched.

pHash is computed via the ``imagehash``/Pillow stack when both are
importable; otherwise a dependency-free fallback decodes the frame with
ffmpeg (already a hard dependency of this project) and computes the same
DCT-based hash directly with numpy. Either path yields a 64-bit hash encoded
as a 16-character hex string, stored on ``candidate.metrics.dedup_hash``.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from workshop_video_brain.core.models.visual_research import FrameCandidate

logger = logging.getLogger(__name__)

_HASH_SIZE = 8  # 8x8 low-frequency DCT block -> 64-bit hash
_DCT_SIZE = 32  # thumbnail edge length fed into the DCT
_FFMPEG_TIMEOUT_SECONDS = 60
DEFAULT_DEDUP_THRESHOLD = 8


def _imagehash_available() -> bool:
    try:
        import imagehash  # noqa: F401
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def _phash_via_imagehash(image_path: Path) -> str | None:
    import imagehash
    from PIL import Image

    try:
        with Image.open(image_path) as img:
            hash_value = imagehash.phash(img, hash_size=_HASH_SIZE)
    except Exception as exc:  # noqa: BLE001
        logger.warning("imagehash could not process %s: %s", image_path, exc)
        return None
    return str(hash_value)


def _dct_matrix(n: int):
    import numpy as np

    k = np.arange(n).reshape(-1, 1)
    x = np.arange(n).reshape(1, -1)
    matrix = np.cos(np.pi / n * (x + 0.5) * k)
    matrix[0, :] *= np.sqrt(1.0 / n)
    matrix[1:, :] *= np.sqrt(2.0 / n)
    return matrix


def _decode_grayscale_thumbnail(image_path: Path, size: int):
    import numpy as np

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(image_path),
        "-vf",
        f"scale={size}:{size},format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            check=False,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg thumbnail decode timed out for %s", image_path)
        return None

    expected_bytes = size * size
    if len(result.stdout) < expected_bytes:
        logger.warning(
            "ffmpeg produced %d bytes (expected %d) decoding %s",
            len(result.stdout),
            expected_bytes,
            image_path,
        )
        return None

    return np.frombuffer(result.stdout[:expected_bytes], dtype=np.uint8).reshape(
        size, size
    ).astype(np.float64)


def _phash_via_ffmpeg_numpy(image_path: Path) -> str | None:
    gray = _decode_grayscale_thumbnail(image_path, _DCT_SIZE)
    if gray is None:
        return None

    dct_basis = _dct_matrix(_DCT_SIZE)
    dct = dct_basis @ gray @ dct_basis.T
    low_freq = dct[:_HASH_SIZE, :_HASH_SIZE]

    import numpy as np

    coefficients = low_freq.flatten()[1:]  # drop the DC term
    median = np.median(coefficients)
    bits = (coefficients >= median).astype(int)

    bit_string = "".join(str(b) for b in bits)
    bit_string = bit_string.ljust(_HASH_SIZE * _HASH_SIZE, "0")
    return f"{int(bit_string, 2):016x}"


def compute_perceptual_hash(image_path: Path) -> str | None:
    """Return a 64-bit perceptual hash (hex string) for the image at ``image_path``.

    Returns ``None`` when the image is missing or cannot be decoded.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        logger.debug("Frame image missing at %s; skipping perceptual hash", image_path)
        return None

    if _imagehash_available():
        phash = _phash_via_imagehash(image_path)
        if phash is not None:
            return phash

    return _phash_via_ffmpeg_numpy(image_path)


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Bit-level Hamming distance between two same-length hex hash strings."""
    try:
        int_a = int(hash_a, 16)
        int_b = int(hash_b, 16)
    except (TypeError, ValueError):
        return _HASH_SIZE * _HASH_SIZE
    return bin(int_a ^ int_b).count("1")


def deduplicate(
    candidates: list[FrameCandidate],
    threshold: int = DEFAULT_DEDUP_THRESHOLD,
    rank_key=None,
) -> tuple[list[FrameCandidate], dict]:
    """Filter visually redundant ``candidates``, keeping the best of each cluster.

    Every candidate gets a ``perceptual_hash`` recorded on
    ``candidate.metrics.dedup_hash``. Two candidates cluster together when
    their hashes' Hamming distance is ``<= threshold``. Within a cluster, the
    candidate with the highest ``rank_key(candidate)`` value is kept;
    ``rank_key`` defaults to preserving input order (first occurrence wins).
    Candidate image files on disk are never modified or deleted -- only the
    returned list is filtered.

    Returns ``(kept, duplicate_map)`` where ``duplicate_map`` maps the kept
    candidate's ``candidate_id`` (str) to a list of the duplicate candidate
    ids (str) that were dropped in its favor.
    """
    if rank_key is None:
        def rank_key(_candidate: FrameCandidate) -> float:
            return 0.0

    hashes: dict[str, str | None] = {}
    for candidate in candidates:
        phash = compute_perceptual_hash(candidate.image_path)
        candidate.metrics.dedup_hash = phash
        hashes[str(candidate.candidate_id)] = phash

    order = sorted(
        range(len(candidates)),
        key=lambda i: (-rank_key(candidates[i]), i),
    )

    representatives: list[int] = []  # indices into `candidates`, in cluster-creation order
    duplicate_map: dict[str, list[str]] = {}

    for i in order:
        candidate = candidates[i]
        candidate_hash = hashes[str(candidate.candidate_id)]

        matched_rep = None
        if candidate_hash is not None:
            for rep_index in representatives:
                rep_hash = hashes[str(candidates[rep_index].candidate_id)]
                if rep_hash is None:
                    continue
                if hamming_distance(candidate_hash, rep_hash) <= threshold:
                    matched_rep = rep_index
                    break

        if matched_rep is None:
            representatives.append(i)
            duplicate_map[str(candidate.candidate_id)] = []
            if candidate_hash is not None:
                candidate.metrics.is_duplicate = False
        else:
            rep_candidate = candidates[matched_rep]
            duplicate_map[str(rep_candidate.candidate_id)].append(str(candidate.candidate_id))
            candidate.metrics.is_duplicate = True

    kept_indices = set(representatives)
    kept = [candidates[i] for i in range(len(candidates)) if i in kept_indices]

    return kept, duplicate_map
