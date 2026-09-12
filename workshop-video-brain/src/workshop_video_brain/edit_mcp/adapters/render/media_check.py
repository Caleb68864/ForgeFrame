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
later all fall outside the allowlist and are skipped. An *unrecognised*
``mlt_service`` is skipped too, so this check can never refuse a render it does
not understand.

An **absent** ``mlt_service`` is not skipped: see :func:`effective_service`. A
producer that names a file and omits the service still opens that file -- this
repo's serializer writes the service in on the way out, and a hand-written or
third-party document reaches MLT's ``loader``, which picks a demuxer from the
resource. Treating "no service" as "not a file" would have let a media
reference past the guard just by leaving a property out.

Remote resources (``http://``, ``smb://``, ...), ``MLT_DATA``-relative ``%``
names and image **sequences** (``%04d``, ``.all.``, ``glob:``) are skipped:
none can be settled by a cheap ``Path.exists()``, and guessing wrong would
refuse a valid render.

Files that are not producer resources
-------------------------------------
A render opens more than its producers' footage, and melt treats all of it the
same way -- logs, carries on, exits 0. :data:`FILE_BACKED_PROPERTIES` is the
second allowlist, keyed by ``(element tag, mlt_service)``, covering the luma
matte of a wipe, the ``shape`` alpha mask (plain and ``mask_start`` sandwich
forms), the ``avfilter.subtitles`` sidecar and the ``avfilter.lut3d`` LUT.
Same discipline, and the same legitimate absent states: an empty ``resource``
on a ``luma`` transition means "plain dissolve, no matte", and a bare name with
no separator is one of MLT's built-in lumas rather than a file.

The one implementation, and its callers
---------------------------------------
This rule is not allowed to exist twice. Everything that needs it reaches
:func:`resolve_missing_all`, which takes ``(producer_id, mlt_service,
resource)`` triples, ``(element_id, tag, mlt_service, property, value)``
reference quintuples from :func:`element_references`, and the base directory
relative values resolve against. (:func:`resolve_missing` is the
producers-only spelling of the same call, kept for a caller that holds nothing
else.) Both kinds are de-duplicated and ordered together, so a file named by a
producer *and* a filter is one message:

* :func:`missing_media` -- the XML front door, used by ``execute_render``,
  ``pipelines/render_final``, ``bundles/subtitle_track`` and
  ``pipelines/review_loop`` (project thumbnails). It reads the file about to be
  handed to melt, so it sees exactly what melt will open.
* ``adapters/kdenlive/validator.validate_project`` -- the same rule over an
  in-memory :class:`KdenliveProject`, for the advisory report. It used to carry
  a naive copy that flagged the ``color``/``black`` producer, never stripped a
  ``timewarp`` speed, and resolved relative paths against the workspace root;
  ``tests/unit/test_media_check_reconciled.py`` is the table of cases the two
  disagreed about, now answered identically by this module.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
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

#: MLT resolves a leading ``%`` against its own data directory
#: (``MLT_DATA``) -- ``%lumas/HD/luma01.pgm`` is the form Kdenlive writes for a
#: *shipped* luma. Where that directory lives depends on the MLT build, so a
#: ``Path.exists()`` on the literal string is meaningless. Same reasoning as the
#: remote schemes: skipped rather than guessed at.
_MLT_DATA_PREFIX = "%"

#: The ``mlt_service`` a producer that carries only a ``resource`` is written
#: with. See :func:`effective_service`.
DEFAULT_PRODUCER_SERVICE = "avformat"


@dataclass(frozen=True)
class MissingMedia:
    """One file a project references that is not on disk.

    ``producer_id`` is the element/producer that referenced it (empty when the
    caller does not track ids), ``resource`` is the value exactly as written --
    which may carry a ``timewarp`` speed prefix or be relative -- and ``path``
    is that value resolved the way melt resolves it.

    ``element`` is the XML tag that named the file (``producer``, ``chain``,
    ``filter``, ``transition``) and ``prop`` the property it was named in.
    Producer resources -- the original and overwhelmingly common case -- keep
    the defaults, so existing callers and their messages are unchanged.
    """

    producer_id: str
    resource: str
    path: str
    element: str = "producer"
    prop: str = "resource"

    @property
    def location(self) -> str:
        """``<tag>:<id>`` for a reference that has an id, else ``<tag>:<prop>``.

        A ``<transition>`` is usually written without an ``id``; naming the
        property it came from is what lets a reader find it in the document.
        """
        return f"{self.element}:{self.producer_id or self.prop}"


def looks_like_media_resource(resource: str) -> bool:
    """Heuristic: does *resource* point at an on-disk media file?

    Lives here, with the rest of the classification, because three places need
    the same answer and it is not allowed to exist three times:

    * ``adapters/kdenlive/serializer`` -- a media/AV bin producer needs an
      ``mlt_service`` so Kdenlive's bin model classifies it, and our upstream
      producers sometimes carry only ``resource`` + ``length`` (the smoke
      fixtures). The serializer defaults those to ``avformat`` on write.
    * :func:`effective_service` -- so both media-check front doors classify a
      service-less producer the way the document that reaches melt will read.
    * ``adapters/kdenlive/validator`` -- through the two above.

    Builtin producers (``black``, colour hex, ``color:``) are excluded; they
    already carry their own service.
    """
    if not resource:
        return False
    if resource == "black" or resource.startswith(("#", "0x", "color:")):
        return False
    return ("/" in resource) or ("." in resource)


def effective_service(service: str, resource: str) -> str:
    """The ``mlt_service`` a producer will actually be read with.

    A producer that carries a file-shaped ``resource`` and **no**
    ``mlt_service`` still opens that file: this repo's serializer writes the
    missing service in as ``avformat`` (see
    ``serializer.serialize_project``), and a hand-written or third-party
    document goes to MLT's ``loader`` producer, which picks a demuxer from the
    resource for exactly the same result. Either way melt opens the file, so
    either way the file must exist -- and applying the default here is what
    stops the allowlist from being walked straight past by omitting one
    property.
    """
    service = (service or "").strip()
    if service:
        return service
    if looks_like_media_resource((resource or "").strip()):
        return DEFAULT_PRODUCER_SERVICE
    return ""


def _plain_local_path(value: str) -> str | None:
    """Return *value* if it names a plain local file, else None.

    The shared tail of every classifier here: a synthetic/colour literal, a
    remote URL, an ``MLT_DATA``-relative ``%`` name and an image-sequence
    pattern are all things a ``Path.exists()`` cannot settle, so none of them
    may ever be reported missing.
    """
    value = (value or "").strip()
    if not value:
        return None
    lowered = value.lower()
    if lowered in _SYNTHETIC_LITERALS or lowered.startswith(_SYNTHETIC_PREFIXES):
        return None
    if lowered.startswith(_REMOTE_SCHEMES):
        return None
    if lowered.startswith(_MLT_DATA_PREFIX):
        return None
    if any(marker in lowered for marker in _SEQUENCE_MARKERS):
        return None
    if _PRINTF_FRAME.search(value):
        return None
    return value


def resource_to_path(service: str, resource: str) -> str | None:
    """Return the filesystem path a producer's ``resource`` names, else None.

    None means "this resource is not a plain local file" -- a synthetic
    producer, a remote URL, or an image sequence -- and must not be checked.
    This is the whole classification rule for producers; every caller goes
    through it.

    A producer with **no** ``mlt_service`` is classified through
    :func:`effective_service` rather than skipped: the document that reaches
    melt has a service (this repo's serializer writes one; MLT's ``loader``
    supplies one), so skipping it here would have let a media reference past
    the guard just by leaving a property out.
    """
    resource = (resource or "").strip()
    if not resource:
        return None
    service = effective_service(service, resource)
    if service not in FILE_BACKED_SERVICES:
        return None

    if service == "timewarp":
        # "<speed>:<inner>" -- drop the speed to get at what is being retimed.
        resource = _TIMEWARP_PREFIX.sub("", resource, count=1).strip()

    # A retimed colour/blank clip carries a synthetic inner resource, and an
    # imported project can name a colour directly. Neither is a file.
    return _plain_local_path(resource)


# ---------------------------------------------------------------------------
# File references that are not producer resources
# ---------------------------------------------------------------------------
#
# A producer's ``resource`` is not the only file a render opens. A luma wipe
# reads a grayscale matte, Shape Alpha reads a mask image or video, a subtitle
# burn-in reads an ``.ass``/``.srt`` sidecar, a creative grade reads a ``.cube``
# LUT. melt treats all four exactly the way it treats missing footage: it logs,
# carries on with whatever it can, and exits 0 -- so the silent success the
# producer check closes is reachable through any of them.
#
# Same discipline as ``FILE_BACKED_SERVICES``: an ALLOWLIST keyed by the
# element and service, never "any property that looks like a path". The survey
# that produced it (every ``<property name=...>`` in all 46 MLT/kdenlive
# documents in this repo, cross-read against every property name and
# ``mlt_service`` literal the source writes) found four property names that
# hold a path and must NOT be checked:
#
#   * ``<filter mlt_service="affine">``'s ``producer.resource`` -- holds a
#     colour ("0x00aaff96") in every document here, not a file.
#   * ``kdenlive:originalurl`` / ``kdenlive:proxy`` -- Kdenlive's bookkeeping
#     for proxy clips. melt never opens either; ``resource`` is what it reads,
#     and ``proxy_wiring`` swaps that. Refusing on them would block a render
#     whose proxy is in use and whose original is legitimately offline.
#   * ``kdenlive:docproperties.renderurl`` -- an *output* path.
#
#: (element tag, ``mlt_service``) -> property names whose value names a file
#: that must be on disk.
FILE_BACKED_PROPERTIES: dict[tuple[str, str], tuple[str, ...]] = {
    # Luma wipe / masked wipe. ``resource`` is a grayscale matte (.pgm/.png);
    # when MLT cannot read it the transition silently degrades to a plain
    # dissolve. ``pipelines/masked_wipes`` and ``pipelines/compositing`` write
    # it; empty means "no matte, plain dissolve" and is skipped.
    ("transition", "luma"): ("resource",),
    # The older composite-with-luma form Kdenlive wrote before the ``luma``
    # transition; the matte is in a property of its own.
    ("transition", "composite"): ("luma",),
    # Shape Alpha -- an external matte consumed as the clip's alpha channel
    # (``pipelines/shape_alpha``). ``resource`` is always a real file.
    ("filter", "shape"): ("resource",),
    # The masked-effect sandwich form of the same filter: inner properties are
    # ``filter.*`` prefixed (``pipelines/masking``). Only the ``shape`` inner
    # filter has a ``filter.resource`` at all -- ``rotoscoping`` and
    # ``frei0r.alpha0ps_alphaspot`` carry splines and numbers -- so keying on
    # the property name is enough.
    ("filter", "mask_start"): ("filter.resource",),
    # Subtitle sidecar burned in at render time (``pipelines/subtitle_track``).
    ("filter", "avfilter.subtitles"): ("av.filename",),
    ("filter", "avfilter.ass"): ("av.filename",),
    # Creative LUT (``pipelines/color_tools``, ``pipelines/color_grade``).
    ("filter", "avfilter.lut3d"): ("av.file",),
    ("filter", "avfilter.lut1d"): ("av.file",),
}

#: Properties where a value with no path separator names a **built-in** MLT
#: luma rather than a file on disk. MLT ships its own lumas and resolves a bare
#: name against its data directory, so a bare "luma03" is a legitimate absent
#: state and must be skipped -- the same reason ``%``-prefixed values are.
#: There is no equivalent for a subtitle sidecar or a LUT: those are always a
#: file, so a bare "subs.ass" next to the project stays checked.
_BUILTIN_NAME_REFS = frozenset({
    ("transition", "luma", "resource"),
    ("transition", "composite", "luma"),
})


def _is_path_shaped(value: str) -> bool:
    """Does *value* carry a path separator (or a ``~``), rather than a bare name?"""
    return "/" in value or "\\" in value or value.startswith("~")


def property_to_path(tag: str, service: str, name: str, value: str) -> str | None:
    """Return the file a non-producer reference names, else None.

    The classifier for :data:`FILE_BACKED_PROPERTIES`, and the exact analogue
    of :func:`resource_to_path` for producers: None means "not a plain local
    file that must exist" and must never be reported.
    """
    allowed = FILE_BACKED_PROPERTIES.get((tag, (service or "").strip()))
    if not allowed or name not in allowed:
        return None
    value = (value or "").strip()
    if not value:
        return None
    if (tag, service, name) in _BUILTIN_NAME_REFS and not _is_path_shaped(value):
        return None
    return _plain_local_path(value)


def element_references(
    tag: str, element_id: str, properties: dict[str, str]
) -> Iterable[tuple[str, str, str, str, str]]:
    """Yield ``(element_id, tag, mlt_service, property_name, value)`` quintuples.

    The non-producer analogue of the ``(producer_id, mlt_service, resource)``
    triple, and one entry point for both front doors: the XML reader hands it a
    parsed element's properties, the validator hands it a filter/transition
    built from the in-memory model.

    Deliberately a dumb walk over *every* property, not a lookup of the
    allowlisted ones. :func:`property_to_path` is the single place the
    allowlist is enforced, so it must be the thing every candidate passes
    through -- pre-filtering here would make that check a second copy of the
    rule that nothing ever reaches, and a mutation removing it would go
    unnoticed. (It did: that is how this shape was arrived at.)
    """
    service = (properties.get("mlt_service") or "").strip()
    for name, value in properties.items():
        if value:
            yield element_id, tag, service, name, value


def resolve_missing(
    producers: Iterable[tuple[str, str, str]],
    base: Path | str,
) -> list[MissingMedia]:
    """Return the file-backed resources among *producers* that are not on disk.

    This is the shared core. *producers* yields ``(producer_id, mlt_service,
    resource)``; *base* is the directory a relative ``resource`` resolves
    against -- the ``<mlt root>`` attribute where there is one, because that is
    what melt uses.

    Results are de-duplicated by resolved path (one message per file, however
    many producers reference it) and ordered by it, so two callers holding the
    same project always produce the same list in the same order.

    Producer resources only. A project also opens files that are not producer
    resources -- luma mattes, alpha masks, subtitle sidecars, LUTs -- and a
    caller holding a whole project wants :func:`resolve_missing_all`.
    """
    return resolve_missing_all(producers, (), base)


def resolve_missing_all(
    producers: Iterable[tuple[str, str, str]],
    references: Iterable[tuple[str, str, str, str, str]],
    base: Path | str,
) -> list[MissingMedia]:
    """Every file a project names that is not on disk -- producers and the rest.

    *producers* yields ``(producer_id, mlt_service, resource)``; *references*
    yields ``(element_id, tag, mlt_service, property_name, value)`` from
    :func:`element_references`. *base* is the directory a relative value
    resolves against -- the ``<mlt root>`` attribute where there is one,
    because that is what melt uses (MLT qualifies a filter's and a
    transition's paths against ``root`` exactly as it does a producer's).

    De-duplicated by resolved path across **both** kinds, and ordered by it: a
    matte that is also a producer resource is one message, not two, and two
    callers holding the same project produce the same list in the same order.
    """
    base_path = Path(base)
    found: dict[str, MissingMedia] = {}

    def _record(
        element_id: str, written: str, candidate: str, tag: str, prop: str
    ) -> None:
        resolved = Path(candidate)
        if not resolved.is_absolute():
            resolved = base_path / resolved
        key = str(resolved)
        if resolved.exists() or key in found:
            return
        found[key] = MissingMedia(
            producer_id=element_id,
            resource=written,
            path=key,
            element=tag,
            prop=prop,
        )

    for producer_id, service, resource in producers:
        candidate = resource_to_path((service or "").strip(), resource or "")
        if candidate is not None:
            _record(
                producer_id, (resource or "").strip(), candidate,
                "producer", "resource",
            )

    for element_id, tag, service, name, value in references:
        candidate = property_to_path(tag, service, name, value)
        if candidate is not None:
            _record(element_id, (value or "").strip(), candidate, tag, name)

    return [found[key] for key in sorted(found)]


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
    missing = resolve_missing_all(
        _xml_producers(root), _xml_references(root), base
    )
    return [item.path for item in missing]


def xml_properties(element: ET.Element) -> dict[str, str]:
    """The properties MLT will read off *element*.

    MLT's XML parser sets an element's **attributes** as properties before it
    reads the ``<property>`` children, so ``<transition mlt_service="luma">``
    and ``<property name="mlt_service">luma</property>`` are the same document
    to melt -- and ``patcher_intents`` writes compositions in the first form.
    Reading only the children would miss them.
    """
    props: dict[str, str] = {
        name: value for name, value in element.attrib.items()
    }
    props.update(
        {
            p.get("name"): (p.text or "")
            for p in element.findall("property")
            if p.get("name")
        }
    )
    return props


def _xml_producers(root: ET.Element) -> Iterable[tuple[str, str, str]]:
    """Yield ``(id, mlt_service, resource)`` for every producer-ish element.

    ``<chain>`` counts: speed-ramped and link-carrying clips serialize as a
    chain rather than a plain ``<producer>``, and they name footage the same way.
    """
    for element in root.iter():
        if element.tag not in ("producer", "chain"):
            continue
        props = xml_properties(element)
        yield (
            element.get("id", ""),
            props.get("mlt_service", ""),
            props.get("resource", ""),
        )


def _xml_references(root: ET.Element) -> Iterable[tuple[str, str, str, str, str]]:
    """Yield the non-producer file references in the document.

    ``<filter>`` and ``<transition>`` anywhere in the tree -- nested in an
    ``<entry>``, a ``<playlist>``, a ``<tractor>`` or at the top level -- since
    that is everywhere melt honours them.
    """
    for element in root.iter():
        if element.tag not in ("filter", "transition"):
            continue
        yield from element_references(
            element.tag, element.get("id", ""), xml_properties(element)
        )


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
