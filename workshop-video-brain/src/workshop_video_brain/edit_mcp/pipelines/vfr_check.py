"""VFR detection and CFR transcode pipeline.

Scans workspace video files for variable frame rate (VFR) media and
provides a transcode function to convert to constant frame rate (CFR).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import (
    frame_rate_divergence,
    probe_media,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    DEFAULT_TIMEOUT_SECONDS as _RENDER_TIMEOUT_SECONDS,
    FFmpegCommandError,
    FFmpegResult,
    run_ffmpeg,
)

logger = logging.getLogger(__name__)

# Only scan video extensions (exclude audio-only)
_VIDEO_EXTENSIONS: set[str] = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".mts", ".m2ts",
}


@dataclass
class VFRFile:
    """A single file identified as VFR."""

    path: str  # str for MCP serialization compatibility
    r_frame_rate: str
    avg_frame_rate: str
    divergence_pct: float
    # Next step for the caller: the media_transcode_cfr call that fixes it.
    suggested_action: str = ""


@dataclass
class ResolvedVFRFile:
    """A VFR original that already has a CFR copy beside it.

    ``media_transcode_cfr`` writes ``<stem>_cfr<ext>`` next to the source and
    never deletes the original (``media/raw/`` is protected). The original is
    still VFR, so it is reported -- but as resolved, not as work to do, and it
    does not stop ``all_cfr`` from being true.
    """

    path: str
    cfr_copy: str
    r_frame_rate: str
    avg_frame_rate: str
    divergence_pct: float


@dataclass
class UnprobedFile:
    """A video file whose frame rate could not be determined."""

    path: str
    error: str


@dataclass
class VFRReport:
    """Result of scanning a workspace for VFR media.

    ``all_cfr`` is True only when every video file was probed and every VFR
    file is resolved (has a CFR ``_cfr`` sibling, listed in ``resolved_files``).
    A file that could not be probed is listed in ``unprobed_files`` and makes
    ``all_cfr`` False -- an unknown frame rate is not a confirmed CFR one.
    """

    files_checked: int
    vfr_files: list[VFRFile] = field(default_factory=list)
    all_cfr: bool = True
    unprobed_files: list[UnprobedFile] = field(default_factory=list)
    resolved_files: list[ResolvedVFRFile] = field(default_factory=list)


def check_vfr(workspace_root: Path) -> VFRReport:
    """Scan all video files in workspace and report VFR files.

    Args:
        workspace_root: Path to workspace root directory.

    Returns:
        VFRReport with counts and list of VFR files.
    """
    video_files = _find_video_files(workspace_root)
    vfr_files: list[VFRFile] = []
    resolved: list[ResolvedVFRFile] = []
    unprobed: list[UnprobedFile] = []
    checked = 0
    # path -> is_vfr for every file that probed, so a VFR original can be
    # checked against its _cfr sibling after the scan.
    probed: dict[Path, bool] = {}
    flagged: list[tuple[Path, str, str]] = []

    for vf in video_files:
        try:
            asset = probe_media(vf)
            checked += 1
            probed[vf] = bool(asset.is_vfr)

            if asset.is_vfr:
                flagged.append((
                    vf,
                    getattr(asset, "r_frame_rate", "0/1"),
                    getattr(asset, "avg_frame_rate", "0/1"),
                ))
        except Exception as exc:  # noqa: BLE001 -- one bad file must not abort the scan
            # Previously swallowed: the report then claimed all_cfr=True for a
            # workspace where nothing could be probed (e.g. ffprobe missing).
            logger.warning("Failed to probe %s, skipping", vf, exc_info=True)
            unprobed.append(UnprobedFile(
                path=str(vf), error=f"{type(exc).__name__}: {exc}"[:300],
            ))

    for vf, r_rate, avg_rate in flagged:
        # Resolved only when the copy exists, probed, and is itself CFR.
        entry = _classify_vfr(
            vf, r_rate, avg_rate, sibling_is_cfr=probed.get(cfr_sibling(vf)) is False,
        )
        if isinstance(entry, ResolvedVFRFile):
            resolved.append(entry)
        else:
            vfr_files.append(entry)

    logger.info(
        "VFR scan %s: %d probed, %d VFR, %d resolved, %d unprobed",
        workspace_root, checked, len(vfr_files), len(resolved), len(unprobed),
    )
    return VFRReport(
        files_checked=checked,
        vfr_files=vfr_files,
        all_cfr=not vfr_files and not unprobed,
        unprobed_files=unprobed,
        resolved_files=resolved,
    )


def check_vfr_file(path: Path) -> VFRReport:
    """Check one video file for VFR, with no workspace needed.

    For checking a recording before ingest. The report has the same shape as
    :func:`check_vfr`'s, so the same rules hold: ``all_cfr`` is True only when
    the file probed as video and is CFR -- or is VFR with a CFR ``_cfr`` copy
    beside it (then it is in ``resolved_files``). A file ffprobe cannot read,
    or one with no video stream, lands in ``unprobed_files`` and makes
    ``all_cfr`` False.

    Raises:
        FileNotFoundError: if *path* does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Media file does not exist: {path}")

    def _unprobed(error: str) -> VFRReport:
        return VFRReport(
            files_checked=0, all_cfr=False,
            unprobed_files=[UnprobedFile(path=str(path), error=error[:300])],
        )

    try:
        asset = probe_media(path)
    except Exception as exc:  # noqa: BLE001 -- reported, same as the workspace scan
        logger.warning("Failed to probe %s", path, exc_info=True)
        return _unprobed(f"{type(exc).__name__}: {exc}")
    if getattr(asset, "media_type", "video") != "video":
        return _unprobed(
            "No video stream: frame rate (and so VFR) does not apply to this file."
        )
    if not asset.is_vfr:
        return VFRReport(files_checked=1, all_cfr=True)

    sibling = cfr_sibling(path)
    sibling_is_cfr = False
    if sibling.exists():
        try:
            sibling_is_cfr = not probe_media(sibling).is_vfr
        except Exception:  # noqa: BLE001 -- an unreadable copy resolves nothing
            logger.warning("Failed to probe CFR copy %s", sibling, exc_info=True)

    entry = _classify_vfr(
        path,
        getattr(asset, "r_frame_rate", "0/1"),
        getattr(asset, "avg_frame_rate", "0/1"),
        sibling_is_cfr=sibling_is_cfr,
    )
    if isinstance(entry, ResolvedVFRFile):
        return VFRReport(files_checked=1, all_cfr=True, resolved_files=[entry])
    return VFRReport(files_checked=1, all_cfr=False, vfr_files=[entry])


def _classify_vfr(
    vf: Path, r_rate: str, avg_rate: str, *, sibling_is_cfr: bool,
) -> VFRFile | ResolvedVFRFile:
    """One VFR file: resolved when its ``_cfr`` copy probed CFR, else work to do."""
    divergence = _calculate_divergence(r_rate, avg_rate)
    if sibling_is_cfr:
        return ResolvedVFRFile(
            path=str(vf),
            cfr_copy=str(cfr_sibling(vf)),
            r_frame_rate=r_rate,
            avg_frame_rate=avg_rate,
            divergence_pct=divergence,
        )
    return VFRFile(
        path=str(vf),
        r_frame_rate=r_rate,
        avg_frame_rate=avg_rate,
        divergence_pct=divergence,
        suggested_action=(
            f"media_transcode_cfr(workspace_path, file_path={str(vf)!r})"
        ),
    )


def cfr_sibling(source: Path) -> Path:
    """Where ``transcode_to_cfr`` writes the CFR copy of *source*."""
    source = Path(source)
    return source.parent / f"{source.stem}_cfr{source.suffix}"


class TranscodeSourceUnreadable(RuntimeError):
    """Determined: the source is not something ffprobe can read as media.

    A file the user handed in that is not decodable video is not a defect in
    this tool, and must never be reported with the "unexpected error, please
    report it" voice.
    """


class TranscodeOutputUnwritable(RuntimeError):
    """Determined: the destination cannot be written (missing or read-only
    directory, read-only existing output). Also the user's to fix."""


class TranscodeFailed(RuntimeError):
    """**Undetermined**: ffmpeg exited non-zero and this code could not work out
    why. The source probes as readable and the destination is writable, so the
    only lead is ffmpeg's own last output, which the message carries.

    This is the honest end of the classification, and it is deliberately the
    only place a "this might be a bug" suggestion is allowed.
    """


def transcode_to_cfr(
    source: Path,
    target_fps: int | None = None,
) -> Path:
    """Transcode a VFR file to constant frame rate.

    Args:
        source: Path to the VFR source file.
        target_fps: Target FPS. If None, auto-detect from avg_frame_rate via probe.

    Returns:
        Path to the output CFR file (alongside source with _cfr suffix).

    Raises:
        TranscodeSourceUnreadable: the source is not decodable media.
        TranscodeOutputUnwritable: the destination cannot be written.
        TranscodeFailed: ffmpeg failed for a reason this code could not
            determine; the message carries ffmpeg's own last output.
        FFmpegNotFound / FFmpegTimeout: raised through ``run_ffmpeg`` -- an
            absent binary and a wall-clock kill are already classified by the
            error contract and must not be re-labelled here.
    """
    source = Path(source)
    if target_fps is None:
        try:
            asset = probe_media(source)
        except FFmpegCommandError as exc:
            # ffprobe ran and refused the file. That is a determination, not a
            # guess: the input is the problem and there is nothing to transcode.
            raise TranscodeSourceUnreadable(
                f"{source} could not be read as video. {_one_line(str(exc))}"
            ) from exc
        target_fps = int(round(asset.fps)) or 30

    output = cfr_sibling(source)

    # Through ``run_ffmpeg`` rather than a hand-rolled ``subprocess.run``: it is
    # the one place that turns an absent binary into ``FFmpegNotFound`` and a
    # wall-clock kill into ``FFmpegTimeout`` (both already classified by the
    # error contract), and the one place that refuses to clobber an existing
    # file under media/raw/ or projects/source/.
    #
    # -fps_mode, not -vsync: -vsync was deprecated in ffmpeg 5.1 and removed in
    # 8.0 ("Unrecognized option 'vsync'"). -hide_banner keeps the ~1.5 KB
    # version banner out of stderr so a failure reports ffmpeg's actual error.
    result = run_ffmpeg(
        args=["-fps_mode", "cfr", "-r", str(target_fps), "-c:a", "copy"],
        input_path=source,
        output_path=output,
        overwrite=True,
        pre_input_args=["-hide_banner"],
        timeout=_RENDER_TIMEOUT_SECONDS,
    )
    if result.success:
        return output

    raise _diagnose_transcode_failure(source, output, result)


def _diagnose_transcode_failure(
    source: Path, output: Path, result: FFmpegResult
) -> RuntimeError:
    """Work out what a non-zero ffmpeg exit means -- or admit that it does not.

    This is a **post-mortem**, never a precondition: it runs only after ffmpeg
    has already failed, so it cannot refuse a transcode that would have worked.

    It also never reads ffmpeg's stderr to decide *what kind* of failure this
    was. ``adapters/render/media_check`` already made that argument against
    melt and it holds here: the wording is not part of the tool's API, it
    varies by version and build, and a match on it is a taxonomy invented from
    guesses. Each verdict below is instead something this code establishes for
    itself -- ffprobe either reads the source or it does not; the destination
    either accepts a write or it does not. ffmpeg's own words are carried into
    every message, because they are the best lead even when they cannot be
    classified.
    """
    # Flattened to ONE line on purpose: the error contract renders an
    # exception's first line as ``cause`` (``errors._one_line_cause``), so a
    # multi-line tail would be silently truncated to "ffmpeg said:" and the
    # actual reason -- the only thing that makes these errors actionable --
    # would never reach the caller.
    tail = _one_line(result.stderr_tail) or "(ffmpeg produced no output)"

    if _source_is_readable(source) is False:
        return TranscodeSourceUnreadable(
            f"{source} is not readable as video, so there is nothing to "
            f"transcode. ffmpeg said: {tail}"
        )

    destination = _destination_problem(output)
    if destination is not None:
        return TranscodeOutputUnwritable(f"{destination} ffmpeg said: {tail}")

    return TranscodeFailed(
        f"ffmpeg failed on {source.name} and the cause could not be "
        f"determined. ffmpeg said: {tail}"
    )


def _one_line(text: str) -> str:
    """Collapse a multi-line stderr tail into one ``|``-separated line."""
    return " | ".join(ln.strip() for ln in (text or "").splitlines() if ln.strip())


def _source_is_readable(path: Path) -> bool | None:
    """``True`` / ``False`` / ``None`` when it cannot be established.

    The third state matters: if ffprobe is itself missing or times out, we have
    learned nothing about the file, and saying "your media is unreadable" would
    be a guess dressed as a finding.
    """
    try:
        probe_media(path)
    except FileNotFoundError:
        return False
    except FFmpegCommandError:
        return False
    except Exception:  # FFmpegNotFound, FFmpegTimeout, bad JSON, ...
        return None
    return True


def _destination_problem(output: Path) -> str | None:
    """A one-line reason the output cannot be written, or ``None``."""
    parent = output.parent
    if not parent.is_dir():
        return f"The output directory does not exist: {parent}."
    if not os.access(parent, os.W_OK):
        return f"The output directory is not writable: {parent}."
    if output.exists() and not os.access(output, os.W_OK):
        return f"The output file already exists and is not writable: {output}."
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_video_files(workspace_root: Path) -> list[Path]:
    """Recursively find video files in workspace."""
    files: list[Path] = []
    for ext in _VIDEO_EXTENSIONS:
        files.extend(workspace_root.rglob(f"*{ext}"))
    return sorted(files)


def _calculate_divergence(r_frame_rate: str, avg_frame_rate: str) -> float:
    """Divergence as a percentage -- the same formula ``probe_media`` decides
    ``is_vfr`` with (``probe.frame_rate_divergence``)."""
    return frame_rate_divergence(r_frame_rate, avg_frame_rate) * 100.0
