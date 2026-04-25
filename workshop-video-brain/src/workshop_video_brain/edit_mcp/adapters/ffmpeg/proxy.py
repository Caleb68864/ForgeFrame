"""Proxy adapter: decide when proxies are needed and generate them."""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from workshop_video_brain.core.models import MediaAsset

logger = logging.getLogger(__name__)


@dataclass
class ProxyPolicy:
    """Thresholds that determine when a proxy should be generated."""

    max_width: int = 1920
    max_height: int = 1080
    heavy_codecs: set[str] = field(
        default_factory=lambda: {"hevc", "h265", "prores"}
    )
    max_bitrate_mbps: float = 50.0


def needs_proxy(asset: MediaAsset, policy: ProxyPolicy | None = None) -> bool:
    """Return True if *asset* should have a proxy generated.

    Conditions (any one triggers a proxy):
    - Resolution exceeds policy max_width / max_height
    - Video codec is in policy.heavy_codecs
    - Bitrate exceeds policy.max_bitrate_mbps
    """
    if policy is None:
        policy = ProxyPolicy()

    # Only video assets need proxies
    if asset.media_type != "video":
        return False

    if asset.width > policy.max_width or asset.height > policy.max_height:
        return True

    codec = (asset.video_codec or "").lower()
    if codec in policy.heavy_codecs:
        return True

    bitrate_mbps = asset.bitrate / 1_000_000
    if bitrate_mbps > policy.max_bitrate_mbps:
        return True

    return False


def proxy_path_for(asset: MediaAsset, proxy_dir: Path) -> Path:
    """Return the deterministic proxy path for *asset* inside *proxy_dir*."""
    source = Path(asset.path)
    return Path(proxy_dir) / f"{source.stem}_proxy.mp4"


PROXY_TIMEOUT_SECONDS = 600  # 10 minutes per clip


def generate_proxy(
    asset: MediaAsset,
    output_dir: Path,
    policy: ProxyPolicy | None = None,
    timeout: int = PROXY_TIMEOUT_SECONDS,
) -> Path:
    """Generate a proxy for *asset* in *output_dir*.

    Skips generation if a proxy already exists and is newer than the source.
    Bounded by *timeout* (seconds) so the MCP server never blocks indefinitely.

    Args:
        asset: The source media asset.
        output_dir: Directory where the proxy file will be written.
        policy: Optional proxy policy (unused during encoding but kept for API
                symmetry; encoding parameters are fixed per spec).
        timeout: Hard wall-clock cap for the ffmpeg subprocess.

    Returns:
        Path to the proxy file.

    Raises:
        subprocess.CalledProcessError: if ffmpeg fails.
        subprocess.TimeoutExpired: if encoding exceeds *timeout*.
    """
    if policy is None:
        policy = ProxyPolicy()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = proxy_path_for(asset, output_dir)
    source_path = Path(asset.path)

    # Skip if proxy already exists and is newer than source
    if output_path.exists():
        if output_path.stat().st_mtime >= source_path.stat().st_mtime:
            logger.info("Proxy already up-to-date: %s", output_path)
            return output_path
        logger.info("Proxy exists but is stale; regenerating: %s", output_path)

    logger.info("Generating proxy %s -> %s (timeout=%ss)", source_path, output_path, timeout)

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i", str(source_path),
                "-vf", "scale=-2:720",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                "-y",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        # Remove any partial file so the next attempt re-encodes from scratch.
        try:
            if output_path.exists():
                output_path.unlink()
        except OSError:
            pass
        logger.warning("Proxy generation timed out after %ss for %s", timeout, source_path)
        raise

    logger.info("Proxy created: %s", output_path)
    return output_path
