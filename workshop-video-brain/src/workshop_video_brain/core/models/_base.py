"""Base mixin providing YAML and JSON serialization for Pydantic models."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class SerializableMixin(BaseModel):
    """Mixin that adds to_yaml / from_yaml / to_json / from_json to Pydantic models."""

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, data: str | bytes) -> "SerializableMixin":
        return cls.model_validate_json(data)

    def to_yaml(self) -> str:
        # model_dump produces plain Python types (no enum instances)
        return yaml.dump(
            self.model_dump(mode="json"),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    @classmethod
    def from_yaml(cls, data: str | bytes) -> "SerializableMixin":
        obj: Any = yaml.safe_load(data)
        return cls.model_validate(obj)
