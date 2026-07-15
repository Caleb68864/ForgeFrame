"""Filter-XML construction surface for the tool layer.

The id-normalizing ``_build_filter_xml`` builder now lives beside its sibling
filter builders in ``pipelines/_common``; it is re-exported here (and from the
``tools_helpers`` package shim) so the historical import surface is unchanged.
Also holds the shared invalid-color message used by the color/composite tools.
"""
from __future__ import annotations

from workshop_video_brain.edit_mcp.pipelines._common import _build_filter_xml

_VALID_COLOR_FORMATS_MSG = (
    "Invalid color. Expected '#RRGGBB' or '#RRGGBBAA' hex format."
)

__all__ = ["_build_filter_xml", "_VALID_COLOR_FORMATS_MSG"]
