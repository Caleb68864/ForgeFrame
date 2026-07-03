"""``clips_find_duplicates`` bundle tool: perceptual near-duplicate detection.

Supersedes -- perceptually -- the byte-level MD5-of-64KB fingerprint in
``adapters/ffmpeg/probe.py``: extracts a handful of evenly-sampled frames per
clip, computes a dHash per frame and clusters clips by Hamming distance so
re-recorded / trimmed / re-encoded takes surface as duplicate groups.  Analysis
only -- writes a JSON report under ``reports/`` and never touches
``media/raw`` or emits video.  Pure hashing / clustering / command
construction lives in ``edit_mcp/pipelines/clip_dupes.py``.

Auto-imported by ``server/bundles/__init__.py`` so ``@mcp.tool()`` registers on
import.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _err,
    _ok,
    _validate_workspace_path,
)
from workshop_video_brain.edit_mcp.pipelines import clip_dupes as _cd

#: Video extensions considered for duplicate detection.
_VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {".mp4", ".mkv", ".mov", ".avi", ".webm", ".mts", ".m2ts"}
)


def _probe_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, check=False,
        )
        return float(out.stdout.strip()) if out.returncode == 0 else None
    except (ValueError, OSError):
        return None


def _list_clips(source: Path) -> list[Path]:
    return sorted(
        p for p in source.rglob("*")
        if p.is_file() and p.suffix.lower() in _VIDEO_EXTENSIONS
    )


def _hash_clip_phash(
    clip: Path, frames_per_clip: int, tmp_dir: Path
) -> list[int]:
    """Extract + dHash *frames_per_clip* frames; returns the frame hashes."""
    from PIL import Image  # transitive dep; imported lazily so import is cheap

    duration = _probe_duration(clip)
    if not duration or duration <= 0:
        return []
    stamps = _cd.frame_timestamps(duration, frames_per_clip)
    hashes: list[int] = []
    for idx, ts in enumerate(stamps):
        frame_path = tmp_dir / f"{clip.stem}_{idx}.png"
        cmd = _cd.frame_extract_command(clip, ts, frame_path)
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0 or not frame_path.exists():
            continue
        try:
            with Image.open(frame_path) as img:
                hashes.append(_cd.dhash_from_image(img))
        except Exception:  # noqa: BLE001 -- skip an unreadable frame
            continue
        finally:
            frame_path.unlink(missing_ok=True)
    return hashes


def _find_phash(
    clips: list[Path], frames_per_clip: int, threshold: float, source: Path
) -> tuple[list[dict], dict[str, list[int]]]:
    """Return (duplicate_group_dicts, hashes_by_rel) for the phash method."""
    hashes_by_rel: dict[str, list[int]] = {}
    with tempfile.TemporaryDirectory(prefix="wvb_dupframes_") as tmp:
        tmp_dir = Path(tmp)
        for clip in clips:
            rel = str(clip.relative_to(source))
            h = _hash_clip_phash(clip, frames_per_clip, tmp_dir)
            if h:
                hashes_by_rel[rel] = h

    groups = _cd.cluster_by_distance(hashes_by_rel, threshold)
    group_dicts: list[dict] = []
    for members in groups:
        # Similarity is scored against the group's first member (the "keeper").
        keeper = members[0]
        scored = []
        for m in members:
            dist = _cd.clip_distance(hashes_by_rel[keeper], hashes_by_rel[m])
            scored.append({
                "clip": m,
                "distance_to_keeper": round(dist, 3),
                "similarity_pct": _cd.similarity_score(dist),
            })
        group_dicts.append({"keeper": keeper, "members": scored})
    return group_dicts, hashes_by_rel


def _find_signature(
    clips: list[Path], source: Path
) -> list[dict]:
    """Pairwise MPEG-7 signature comparison + union-find clustering."""
    rels = [str(c.relative_to(source)) for c in clips]
    parent = {r: r for r in rels}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    match_frames: dict[tuple[str, str], int | None] = {}
    for i in range(len(clips)):
        for j in range(i + 1, len(clips)):
            cmd = _cd.signature_pair_command(clips[i], clips[j])
            proc = subprocess.run(
                cmd, capture_output=True, text=True, check=False
            )
            verdict = _cd.parse_signature_match(proc.stderr)
            if verdict["matched"]:
                a, b = rels[i], rels[j]
                match_frames[(a, b)] = verdict["frames"]
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[rb] = ra

    groups: dict[str, list[str]] = {}
    for r in rels:
        groups.setdefault(find(r), []).append(r)

    out: list[dict] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        keeper = members[0]
        scored = []
        for m in members:
            key = (keeper, m) if (keeper, m) in match_frames else (m, keeper)
            scored.append({
                "clip": m,
                "frames_matching": match_frames.get(key),
            })
        out.append({"keeper": keeper, "members": scored})
    return out


@mcp.tool()
def clips_find_duplicates(
    workspace_path: str,
    source_dir: str,
    method: str = "phash",
    frames_per_clip: int = 5,
    threshold: int = 10,
) -> dict:
    """Find perceptual near-duplicate video clips in a folder.

    Unlike the byte-level MD5 fingerprint in ``probe.py`` (which only catches
    identical files), this groups re-recorded, trimmed and re-encoded takes.
    Analysis only: extracts small still frames to a temp dir, hashes them, and
    writes a JSON report under ``reports/`` -- no video is written and
    ``media/raw`` is never touched.

    Args:
        workspace_path: Path to the workspace root.
        source_dir: Folder of clips (absolute, or relative to the workspace).
            Scanned recursively for video files.
        method: ``"phash"`` (default -- dHash of sampled frames, no build
            requirements) or ``"signature"`` (FFmpeg MPEG-7 ``signature``
            filter, only available when the local build exposes it).
        frames_per_clip: Frames sampled per clip for the phash method
            (``>= 1``).  Ignored by the signature method.
        threshold: Maximum mean Hamming distance (0-64) for two clips to be
            considered duplicates under the phash method.  Lower = stricter.

    Returns:
        ``{"status":"success","data":{...}}`` with duplicate groups, per-member
        similarity scores and the report path, or ``{"status":"error",...}``.
    """
    try:
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            return _err("ffmpeg/ffprobe are not available on PATH.")

        ws_path = _validate_workspace_path(workspace_path)

        source = Path(source_dir)
        if not source.is_absolute():
            source = ws_path / source_dir
        if not source.exists() or not source.is_dir():
            return _err(f"source_dir not found or not a directory: {source}")

        method = (method or "phash").lower()
        if method not in {"phash", "signature"}:
            return _err(
                f"unknown method {method!r}; expected 'phash' or 'signature'."
            )
        if frames_per_clip < 1:
            return _err("frames_per_clip must be >= 1.")

        clips = _list_clips(source)
        if len(clips) < 2:
            return _err(
                f"need at least 2 video clips to compare; found {len(clips)} "
                f"in {source}."
            )

        if method == "signature":
            if not _cd.has_signature_filter():
                return _err(
                    "method='signature' requires the FFmpeg MPEG-7 'signature' "
                    "filter, which this build does not expose. Rebuild FFmpeg "
                    "with the signature filter, or use method='phash'."
                )
            groups = _find_signature(clips, source)
            hashed = len(clips)
        else:
            groups, hashes_by_rel = _find_phash(
                clips, frames_per_clip, float(threshold), source
            )
            hashed = len(hashes_by_rel)

        reports = ws_path / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_path = reports / f"duplicates_{stamp}.json"
        report = {
            "generated": datetime.now(timezone.utc).isoformat(),
            "source_dir": str(source),
            "method": method,
            "frames_per_clip": frames_per_clip if method == "phash" else None,
            "threshold": threshold if method == "phash" else None,
            "clips_scanned": len(clips),
            "clips_hashed": hashed,
            "duplicate_groups": groups,
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        return _ok({
            "report": str(report_path),
            "source_dir": str(source),
            "method": method,
            "clips_scanned": len(clips),
            "clips_hashed": hashed,
            "duplicate_group_count": len(groups),
            "duplicate_groups": groups,
        })
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))
