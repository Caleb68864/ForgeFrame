"""Validation report models."""
from __future__ import annotations

from pydantic import Field

from ._base import SerializableMixin
from .enums import ValidationSeverity


class ValidationItem(SerializableMixin):
    model_config = {"use_enum_values": True}

    severity: ValidationSeverity
    category: str = ""
    message: str = ""
    location: str = ""
    #: The filesystem path this item is about, resolved the way the renderer
    #: would resolve it, when the item is about a file at all (today: the media
    #: check).  ``message`` is prose for a human; this is the same fact as data,
    #: so a caller -- or a test comparing this report against the renderer's own
    #: media check -- does not have to parse English out of it.
    path: str = ""


class ValidationReport(SerializableMixin):
    model_config = {"use_enum_values": True}

    items: list[ValidationItem] = Field(default_factory=list)
    summary: str = ""
