"""Pre-render check: does the footage a project references still exist?

melt does **not** fail when a producer's file is gone. It logs a warning, swaps
in a blank/invalid producer for the clip it could not open, renders the rest of
the timeline, and exits **0**. Every caller in this package treats exit 0 as
success, so a render whose footage was moved or deleted after the edit was made
used to come back "succeeded" with an output file that is silently missing those
shots. This module is the precondition that closes that hole.

Why a precondition and not melt's warnings
------------------------------------------
The alternative is to parse melt's stderr for "failed to load" / "invalid" lines
and treat them as failure. That was rejected: the wording is not part of MLT's
API and varies by version and module, it cannot distinguish a fatal missing
source from a benign optional-service warning, and it only ever discovers the
problem *after* paying for a full render. Reading the project's own producer
list is deterministic, version-independent, costs milliseconds, and can name the
exact files -- which is what the user actually needs.

What counts as "must exist"
---------------------------
Only producers whose ``mlt_service`` is a known **file-backed** service (see
``FILE_BACKED_SERVICES``). This is deliberately an allowlist, not a deny-list of
synthetic services: a project legitimately contains producers that have no file
on disk at all, and a render must never be refused because of one.

    <producer id="producer_black">          <!-- every Kdenlive timeline -->
      <property name="mlt_service">color</property>
      <property name="resource">black</property>

    <producer id="title0">
      <property name="mlt_service">kdenlivetitle</property>

colour/`black` backgrounds, titles, `qtext`/`dynamictext`, `noise`, `tone`,
`count`, `frei0r.*` generators and anything else this repo or Kdenlive may add
later all fall outside the allowlist and are skipped. An unrecognised or absent
``mlt_service`` is skipped too. The cost of that choice is a narrower
guarantee -- a file-backed producer that somehow carries no ``mlt_service`` is
not checked -- and the benefit is that this check can never refuse a render that
would have worked. Every producer this repo writes for real footage carries
``mlt_service=avformat`` (the serializer sets it), so the guarantee covers the
footage path that matters.

Remote resources (``http://``, ``smb://``, ...) and image **sequences**
(``%04d``, ``.all.``, ``glob:``) are skipped: neither can be settled by a cheap
``Path.exists()``, and guessing wrong would refuse a valid render.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger(__name__)

#: ``mlt_service`` values whose ``resource`` names a file that must be on disk.
#: Anything not listed here is treated as "not a plain file" and skipped.
FILE_BACKED_SERVICES = frozenset({
    "avformat",           # video/audio via libavformat -- the footage path
    "avformat-novalidate",  # same, with MLT's probe skipped
    "qimage",             # stills (Qt image loader)
    "pixbuf",             # stills (GdkPixbuf loader)
    "timewarp",           # speed-changed clip; resource is "<speed>:<path>"
    "xml",                # a nested MLT/kdenlive project rendered as a clip
})

#: ``resource`` values with one of these URL schemes are not local files.
_REMOTE_SCHEMES = (
    "http://", "https://", "ftp://", "ftps://", "sftp://", "smb://", "cifs://",
    "rtsp://", "rtmp://", "rtmps://", "srt://", "udp://", "tcp://", "rtp://",
    "hls://", "data:", "pipe:",
)

#: An image-sequence resource; melt expands these itself, so a single
#: ``Path.exists()`` on the pattern is meaningless.
_SEQUENCE_MARKERS = ("glob:", ".all.")
_PRINTF_FRAME = re.compile(r"%0?\d*[dqi]")

#: ``timewarp`` stores "<speed>:<inner>", e.g. "2.0:/media/raw/shot.mp4". Only
#: the leading speed is stripped: the rest may be a Windows path whose own
#: drive-letter colon must survive ("4.0:C:/Videos/shot.mp4").
_TIMEWARP_PREFIX = re.compile(r"^-?\d+(?:\.\d+)?:")

#: A ``resource`` that names a colour/synthetic producer rather than a file.
#: ``timewarp`` wraps one of these when the clip it retimes is itself
#: synthetic -- ``patcher_intents`` builds "2:color:black" and "2:color:0xffffffff".
_SYNTHETIC_PREFIXES = ("#", "0x", "color:", "colour:")
_SYNTHETIC_LITERALS = frozenset({"black", "blank", "white", "transparent", ""})


def _resource_to_path(service: str, resource: str) -> str | None:
    """Return the filesystem path a producer's ``resource`` names, else None.

    None means "this resource is not a plain local file" -- a synthetic
    producer, a remote URL, or an image sequence -- and must not be checked.
    """
    resource = (resource or "").strip()
    if not resource:
        return None
    if service not in FILE_BACKED_SERVICES:
        return None

    if service == "timewarp":
        # "<speed>:<inner>" -- drop the speed to get at what is being retimed.
        resource = _TIMEWARP_PREFIX.sub("", resource, count=1).strip()

    lowered = resource.lower()
    # A retimed colour/blank clip carries a synthetic inner resource, and an
    # imported project can name a colour directly. Neither is a file.
    if lowered in _SYNTHETIC_LITERALS or lowered.startswith(_SYNTHETIC_PREFIXES):
        return None
    if lowered.startswith(_REMOTE_SCHEMES):
        return None
    if any(marker in lowered for marker in _SEQUENCE_MARKERS):
        return None
    if _PRINTF_FRAME.search(resource):
        return None
    return resource


def missing_media(project_path: Path | str) -> list[str]:
    """Return the file-backed media a project references that is not on disk.

    Paths are reported resolved: a relative ``resource`` is joined to the
    ``<mlt root="...">`` attribute Kdenlive writes (falling back to the
    project file's own directory), which is how melt itself resolves them.

    Never raises. A project that cannot be read or parsed returns ``[]`` --
    that is a different failure, and melt reports it on its own; this check
    only ever speaks up when it can positively name an absent file.

    Args:
        project_path: Path to the .kdenlive / MLT XML file about to be rendered.

    Returns:
        Sorted, de-duplicated list of resolved paths that do not exist.
    """
    path = Path(project_path)
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        logger.debug("Pre-render media check skipped for %s: %s", path, exc)
        return []

    base = Path(root.get("root") or path.parent)

    missing: set[str] = set()
    for element in root.iter():
        if element.tag not in ("producer", "chain"):
            continue
        props = {
            p.get("name"): (p.text or "")
            for p in element.findall("property")
            if p.get("name")
        }
        candidate = _resource_to_path(
            props.get("mlt_service", "").strip(), props.get("resource", "")
        )
        if candidate is None:
            continue
        resolved = Path(candidate)
        if not resolved.is_absolute():
            resolved = base / resolved
        if not resolved.exists():
            missing.add(str(resolved))

    return sorted(missing)


def missing_media_message(project_path: Path | str, missing: list[str]) -> str:
    """Render a user-facing explanation naming every absent file."""
    listed = "\n".join(f"  - {p}" for p in missing)
    noun = "file" if len(missing) == 1 else "files"
    return (
        f"Cannot render {Path(project_path).name}: {len(missing)} media {noun} "
        f"referenced by the timeline {'is' if len(missing) == 1 else 'are'} "
        f"missing from disk:\n{listed}\n"
        "melt does not fail on missing footage -- it renders those clips blank "
        "and still exits 0 -- so this render was stopped before it produced an "
        "output that silently dropped them. Restore or relink the files above "
        "(or remove those clips from the timeline) and render again."
    )
