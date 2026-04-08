"""Logging setup for workshop-video-brain.

Provides JSON-formatted structured logging and a human-readable console handler.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, self.datefmt),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(workspace_path: Path | None = None) -> None:
    """Configure root logger with console and optional file handlers.

    Args:
        workspace_path: If provided, a JSON log file is written under
                        <workspace_path>/logs/wvb.log.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Human-readable console handler
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(console)

    # JSON file handler (optional)
    if workspace_path is not None:
        log_dir = Path(workspace_path) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "wvb.log")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JsonFormatter())
        root.addHandler(file_handler)
