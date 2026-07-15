"""Masked / custom-luma wipe pipeline -- pure functions.

Closes SYNTHESIS.md item #7 (`docs/research/2026-07-03-tutorial-effect-analysis/`):
the existing ``compositing.apply_wipe`` hardcodes
``/usr/share/kdenlive/lumas/HD/luma01.pgm`` with no way to pick a different
matte, invert the wipe direction, or soften the edge. Rather than change that
function's signature (which the ``composite_wipe`` tool + its tests depend on),
this module adds new, additive pure functions:

* :func:`resolve_luma` -- turn a luma spec (built-in name *or* user matte path)
  into an MLT ``resource`` string.
* :func:`apply_masked_wipe` -- write a ``<transition mlt_service="luma">`` with a
  custom ``resource``, ``softness`` and ``invert``.
* :func:`apply_luma_key` -- add the FFmpeg ``avfilter.lumakey`` filter (luminance
  -> alpha) to a clip; the luma analogue of chroma-key.

Known limitation (plan §1.1/§1.2,
``docs/plans/2026-07-03-kdenlive-mcp-improvements.md``): the transition lands
outside the ``<tractor>`` and the filter attaches at the MLT root because the
serializer does not read ``position_hint``. Documented, not fixed here.
"""
from __future__ import annotations

import os
from copy import deepcopy

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.core.models.timeline import AddComposition
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.pipelines.effect_apply import apply_effect

#: Standard Kdenlive HD luma directory (matches ``compositing.apply_wipe``).
LUMA_DIR = "/usr/share/kdenlive/lumas/HD"

#: Grayscale-matte extensions MLT's ``luma`` transition accepts as a ``resource``.
LUMA_EXTENSIONS = (".pgm", ".png")

#: FFmpeg ``lumakey`` filter service (luminance -> alpha). Not in the effect
#: catalog; ``apply_effect`` passes any service string through unvalidated.
LUMAKEY_SERVICE = "avfilter.lumakey"


def resolve_luma(luma_file: str) -> str:
    """Resolve a luma spec to an MLT ``resource`` string.

    Accepts BOTH forms named in the tutorials:

    * **User matte path** -- anything containing a path separator, or ending in
      ``.pgm``/``.png`` and existing on disk, is returned verbatim.
    * **Built-in luma name** -- a bare name (e.g. ``"luma03"`` or
      ``"luma03.pgm"``) is resolved under :data:`LUMA_DIR`, appending ``.pgm``
      when no matte extension is present.

    Built-in names are *not* stat-checked (install paths vary across distros);
    only path-like inputs are existence-tested before falling through to
    verbatim use.

    Raises
    ------
    ValueError
        If ``luma_file`` is empty/whitespace.
    """
    if not luma_file or not luma_file.strip():
        raise ValueError("luma_file must be a non-empty string")

    spec = luma_file.strip()
    lower = spec.lower()
    has_sep = os.sep in spec or (os.altsep and os.altsep in spec)
    has_matte_ext = lower.endswith(LUMA_EXTENSIONS)

    # Explicit path (absolute, relative, or ~) -> use as given.
    if has_sep or spec.startswith("~"):
        return os.path.expanduser(spec)

    # Bare filename that is itself a real file in cwd -> verbatim.
    if has_matte_ext and os.path.isfile(spec):
        return spec

    # Otherwise treat as a built-in luma name under the HD luma dir.
    name = spec if has_matte_ext else f"{spec}.pgm"
    return os.path.join(LUMA_DIR, name)


def apply_masked_wipe(
    project: KdenliveProject,
    track_a: int,
    track_b: int,
    start_frame: int,
    end_frame: int,
    luma_file: str,
    invert: bool = False,
    softness: float = 0.0,
) -> KdenliveProject:
    """Add a custom-luma wipe transition between two tracks.

    Writes ``<transition mlt_service="luma">`` with a resolved ``resource``
    (:func:`resolve_luma`), plus ``softness`` (0..1 edge gradient) and ``invert``
    (0/1 direction reversal). This is the parameterised generalisation of
    ``compositing.apply_wipe``'s hardcoded ``luma01.pgm`` branch.

    Raises
    ------
    ValueError
        On same track, non-positive duration, ``softness`` outside 0..1, or an
        empty ``luma_file``.
    """
    if track_a == track_b:
        raise ValueError(
            f"track_a and track_b must be different tracks (got {track_a})"
        )
    if end_frame <= start_frame:
        raise ValueError(
            f"end_frame ({end_frame}) must be greater than start_frame ({start_frame})"
        )
    if not 0.0 <= softness <= 1.0:
        raise ValueError(f"softness must be in [0.0, 1.0] (got {softness})")

    resource = resolve_luma(luma_file)

    params = {
        "resource": resource,
        "softness": f"{softness}",
        "invert": "1" if invert else "0",
    }

    intent = AddComposition(
        composition_type="luma",
        track_a=track_a,
        track_b=track_b,
        start_frame=start_frame,
        end_frame=end_frame,
        params=params,
    )
    return patch_project(deepcopy(project), [intent])


def apply_luma_key(
    project: KdenliveProject,
    track_index: int,
    clip_index: int,
    threshold: float = 0.0,
    tolerance: float = 0.01,
    softness: float = 0.0,
) -> KdenliveProject:
    """Add the ``avfilter.lumakey`` filter (luminance -> alpha) to a clip.

    The luma analogue of :func:`compositing`/``effect_chroma_key``: pixels whose
    luminance is at/below ``threshold`` become transparent, with ``tolerance``
    and ``softness`` feathering the alpha edge. Params are emitted under MLT's
    ``av.`` avfilter convention (``av.threshold`` / ``av.tolerance`` /
    ``av.softness``); the service string is passed through unvalidated, so exact
    option availability depends on the local MLT/FFmpeg build.

    Raises
    ------
    ValueError
        If any of the three scalars is outside 0..1.
    IndexError
        If ``track_index``/``clip_index`` is out of range (from ``apply_effect``).
    """
    for label, value in (
        ("threshold", threshold),
        ("tolerance", tolerance),
        ("softness", softness),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{label} must be in [0.0, 1.0] (got {value})")

    params = {
        "av.threshold": f"{threshold}",
        "av.tolerance": f"{tolerance}",
        "av.softness": f"{softness}",
    }
    return apply_effect(project, track_index, clip_index, LUMAKEY_SERVICE, params)
