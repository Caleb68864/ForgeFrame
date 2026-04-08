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


def setup_logging(
    workspace_path: Path | None = None,
    job_id: str | None = None,
) -> None:
    """Configure root logger with console and optional file handlers.

    Args:
        workspace_path: If provided, a JSON log file is written under
                        <workspace_path>/logs/wvb.log (and per-job file when
                        job_id is also supplied).
        job_id: When provided together with workspace_path, an additional
                per-job JSONL log is written to
                <workspace_path>/logs/<job_id>.jsonl.
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

        main_handler = logging.FileHandler(log_dir / "wvb.log")
        main_handler.setLevel(logging.DEBUG)
        main_handler.setFormatter(JsonFormatter())
        root.addHandler(main_handler)

        # Per-job JSONL log file
        if job_id is not None:
            job_handler = logging.FileHandler(log_dir / f"{job_id}.jsonl")
            job_handler.setLevel(logging.DEBUG)
            job_handler.setFormatter(JsonFormatter())
            root.addHandler(job_handler)
