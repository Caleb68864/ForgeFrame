"""Local frame quality scoring behind a :class:`FrameScorer` interface.

Two tiers of metrics feed :class:`~workshop_video_brain.core.models.visual_research.FrameVisualMetrics`:

1. **FFmpeg-cheap metrics** (always available, no image library required):
   brightness and contrast via the ``signalstats`` filter, with a
   ``blackdetect`` fallback for near-black frames.
2. **Pixel metrics** (numpy + Pillow, gated behind a capability check):
   sharpness (variance of a discrete Laplacian), entropy (Shannon entropy of
   the luma histogram), and a text-density heuristic (edge-pixel fraction,
   stashed on ``candidate.metadata["text_density"]`` since it has no home on
   ``FrameVisualMetrics``). When numpy/Pillow are absent these fields stay
   ``None`` and a debug log is emitted -- ``score`` never raises for a
   missing optional dependency.

Metrics are kept separate on ``FrameVisualMetrics`` -- ``rank`` is the only
place they are combined, via configurable per-mode weight profiles, into a
single derived ordering. The derived number is not persisted back onto the
metrics; it only drives the order of ``rank``'s return value.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from workshop_video_brain.core.models.visual_research import (
    FrameCandidate,
    FrameVisualMetrics,
    ResearchConfig,
)

logger = logging.getLogger(__name__)

_FFMPEG_TIMEOUT_SECONDS = 60

_YAVG_RE = re.compile(r"YAVG:([\d.]+)")
_YMIN_RE = re.compile(r"YMIN:([\d.]+)")
_YMAX_RE = re.compile(r"YMAX:([\d.]+)")

#: Per-mode weight profiles used by :meth:`FrameScorer.rank`. Weights are
#: renormalized over whichever fields are actually populated for a given
#: candidate, so a missing metric (e.g. no numpy/Pillow) doesn't zero out
#: the derived score -- it's simply excluded from that candidate's blend.
MODE_PROFILES: dict[str, dict[str, float]] = {
    "software_ui": {
        "sharpness": 0.45,
        "brightness": 0.15,
        "contrast": 0.15,
        "entropy": 0.15,
        "text_density": 0.10,
    },
    "slide_deck": {
        "sharpness": 0.30,
        "brightness": 0.20,
        "contrast": 0.15,
        "entropy": 0.10,
        "text_density": 0.25,
    },
    "physical_demo": {
        "sharpness": 0.35,
        "brightness": 0.25,
        "contrast": 0.20,
        "entropy": 0.20,
        "text_density": 0.00,
    },
}

DEFAULT_MODE = "software_ui"

# Normalization ceilings mapping raw metric ranges onto roughly [0, 1] before
# weighting. Sharpness (Laplacian variance) and entropy (bits, max 8 for an
# 8-bit luma histogram) are unbounded/differently-scaled from the already
# 0..1 brightness/contrast/text_density fields.
_SHARPNESS_NORMALIZATION_CEILING = 100.0
_ENTROPY_NORMALIZATION_CEILING = 8.0


def _pixel_metrics_available() -> bool:
    """Whether numpy and Pillow are both importable in this environment."""
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def _run_ffmpeg_filter_stderr(image_path: Path, vf: str) -> str:
    cmd = ["ffmpeg", "-y", "-i", str(image_path), "-vf", vf, "-f", "null", "-"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg filter %r timed out for %s", vf, image_path)
        return ""
    return result.stderr


def _run_signalstats(image_path: Path) -> dict[str, float]:
    """Run ffmpeg's ``signalstats`` filter and parse YAVG/YMIN/YMAX."""
    stderr = _run_ffmpeg_filter_stderr(image_path, "signalstats")
    stats: dict[str, float] = {}
    for pattern, key in ((_YAVG_RE, "yavg"), (_YMIN_RE, "ymin"), (_YMAX_RE, "ymax")):
        match = pattern.search(stderr)
        if match:
            stats[key] = float(match.group(1))
    return stats


def _run_blackdetect(image_path: Path, picture_black_ratio_th: float = 0.98) -> bool:
    """Run ffmpeg's ``blackdetect`` filter; True if the frame is flagged black."""
    stderr = _run_ffmpeg_filter_stderr(
        image_path, f"blackdetect=d=0:pic_th={picture_black_ratio_th}"
    )
    return "black_start" in stderr


def _laplacian_variance(gray) -> float:
    """Variance of a discrete 4-neighbor Laplacian, a standard sharpness proxy.

    Implemented with plain numpy slicing (no scipy dependency).
    """
    import numpy as np

    padded = np.pad(gray, 1, mode="edge")
    center = padded[1:-1, 1:-1]
    up = padded[:-2, 1:-1]
    down = padded[2:, 1:-1]
    left = padded[1:-1, :-2]
    right = padded[1:-1, 2:]
    laplacian = up + down + left + right - 4 * center
    return float(np.var(laplacian))


def _shannon_entropy(gray) -> float:
    import numpy as np

    hist, _ = np.histogram(gray, bins=256, range=(0, 255))
    total = hist.sum()
    if total <= 0:
        return 0.0
    probs = hist.astype(np.float64) / total
    probs = probs[probs > 0]
    return float(-(probs * np.log2(probs)).sum())


def _text_density(gray) -> float:
    """Crude text-density heuristic: fraction of high-gradient-magnitude pixels."""
    import numpy as np

    gy, gx = np.gradient(gray)
    magnitude = np.hypot(gx, gy)
    threshold = magnitude.mean() + magnitude.std()
    if threshold <= 0:
        return 0.0
    return float(np.mean(magnitude > threshold))


def _compute_pixel_metrics(image_path: Path) -> dict[str, float] | None:
    """Compute sharpness/entropy/text-density via numpy + Pillow.

    Caller must have already confirmed both libraries import cleanly via
    :func:`_pixel_metrics_available`.
    """
    if not image_path.exists():
        logger.debug("Frame image missing at %s; skipping pixel metrics", image_path)
        return None

    import numpy as np
    from PIL import Image

    try:
        with Image.open(image_path) as img:
            gray = np.asarray(img.convert("L"), dtype=np.float64)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load %s for pixel metrics: %s", image_path, exc)
        return None

    if gray.size == 0:
        return None

    return {
        "sharpness": _laplacian_variance(gray),
        "entropy": _shannon_entropy(gray),
        "text_density": _text_density(gray),
    }


class FrameScorer:
    """Computes independently-inspectable local metrics for one frame.

    FFmpeg-cheap metrics (brightness/contrast, with a blackdetect fallback)
    are always computed. Pixel metrics (sharpness/entropy/text-density) are
    computed only when numpy and Pillow are both importable; otherwise those
    fields are left ``None`` and a debug log is emitted -- ``score`` itself
    never raises on a missing optional dependency.
    """

    def score(self, candidate: FrameCandidate, config: ResearchConfig) -> FrameVisualMetrics:
        """Score a single ``candidate``, returning a new ``FrameVisualMetrics``."""
        metrics = FrameVisualMetrics()
        image_path = Path(candidate.image_path)

        if image_path.exists():
            stats = _run_signalstats(image_path)
            if "yavg" in stats:
                metrics.brightness = max(0.0, min(1.0, stats["yavg"] / 255.0))
            if "ymin" in stats and "ymax" in stats:
                metrics.contrast = max(0.0, min(1.0, (stats["ymax"] - stats["ymin"]) / 255.0))
            if metrics.brightness is None and _run_blackdetect(image_path):
                metrics.brightness = 0.0
            if metrics.brightness is not None:
                candidate.metadata["overexposed"] = metrics.brightness >= 0.98
        else:
            logger.debug(
                "Frame image missing at %s; skipping ffmpeg brightness/contrast metrics",
                image_path,
            )

        if _pixel_metrics_available():
            pixel_metrics = _compute_pixel_metrics(image_path)
            if pixel_metrics is not None:
                metrics.sharpness = pixel_metrics["sharpness"]
                metrics.entropy = pixel_metrics["entropy"]
                candidate.metadata["text_density"] = pixel_metrics["text_density"]
        else:
            logger.debug(
                "numpy/Pillow unavailable; pixel metrics (sharpness/entropy/text-density) "
                "left as None for %s",
                image_path,
            )

        return metrics

    def passes_quality_gate(
        self, metrics: FrameVisualMetrics, config: ResearchConfig
    ) -> bool:
        """Whether ``metrics`` clears ``config.quality``'s brightness/sharpness floors."""
        quality = config.quality
        if metrics.brightness is not None and (
            metrics.brightness < quality.min_brightness
            or metrics.brightness > quality.max_brightness
        ):
            return False
        if metrics.sharpness is not None and metrics.sharpness < quality.min_sharpness:
            return False
        return True

    def rank(
        self,
        candidates: list[FrameCandidate],
        config: ResearchConfig,
        mode: str = DEFAULT_MODE,
        weights: dict[str, float] | None = None,
    ) -> list[FrameCandidate]:
        """Score, quality-gate, and order ``candidates`` by a derived rank.

        ``mode`` selects a base weight profile (``software_ui``,
        ``slide_deck``, ``physical_demo``); ``weights`` overrides individual
        weights on top of that profile. Candidates failing
        :meth:`passes_quality_gate` are dropped. The derived score is used
        only to order the returned list -- it is not written back onto any
        candidate's metrics, keeping the individual metrics inspectable.
        """
        profile = dict(MODE_PROFILES.get(mode, MODE_PROFILES[DEFAULT_MODE]))
        if weights:
            profile.update(weights)

        scored: list[tuple[float, FrameCandidate]] = []
        for candidate in candidates:
            metrics = self.score(candidate, config)
            candidate.metrics = metrics
            if not self.passes_quality_gate(metrics, config):
                continue
            derived = self._derived_score(candidate, metrics, profile)
            scored.append((derived, candidate))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [candidate for _, candidate in scored]

    @staticmethod
    def _derived_score(
        candidate: FrameCandidate,
        metrics: FrameVisualMetrics,
        profile: dict[str, float],
    ) -> float:
        raw_values = {
            "sharpness": metrics.sharpness,
            "brightness": metrics.brightness,
            "contrast": metrics.contrast,
            "entropy": metrics.entropy,
            "text_density": candidate.metadata.get("text_density"),
        }

        weighted_total = 0.0
        weight_used = 0.0
        for key, weight in profile.items():
            value = raw_values.get(key)
            if value is None or weight <= 0:
                continue
            if key == "sharpness":
                normalized = min(1.0, value / _SHARPNESS_NORMALIZATION_CEILING)
            elif key == "entropy":
                normalized = min(1.0, value / _ENTROPY_NORMALIZATION_CEILING)
            else:
                normalized = max(0.0, min(1.0, value))
            weighted_total += weight * normalized
            weight_used += weight

        if weight_used <= 0:
            return 0.0
        return weighted_total / weight_used
