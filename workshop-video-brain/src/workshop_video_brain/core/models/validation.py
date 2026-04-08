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


class ValidationReport(SerializableMixin):
    model_config = {"use_enum_values": True}

    items: list[ValidationItem] = Field(default_factory=list)
    summary: str = ""
