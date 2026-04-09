---
scenario_id: "AP-03"
title: "App Logging"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario AP-03: App Logging

## Description
Tests `setup_logging` and `JsonFormatter` in `app/logging.py`.

`setup_logging(workspace_path, job_id)` configures the root logger:
- Always adds a `StreamHandler` to `sys.stderr` at `INFO` level with a
  human-readable formatter.
- When `workspace_path` is provided, creates `<workspace_path>/logs/` and adds
  a `FileHandler` for `wvb.log` at `DEBUG` level using `JsonFormatter`.
- When both `workspace_path` and `job_id` are provided, adds a second
  `FileHandler` for `<job_id>.jsonl` at `DEBUG` level using `JsonFormatter`.

`JsonFormatter` emits single-line JSON objects containing at minimum:
`level`, `logger`, `message`, `time`.  Exception info is included when present.

Edge cases:
- Calling `setup_logging` with no args adds only the console handler.
- `workspace_path` directory does not need to pre-exist (`logs/` is created).
- `JsonFormatter.format` with an exception record includes `exc_info` key.

## Preconditions
- Python 3.12+, `uv run pytest` available.
- Tests isolate root logger handlers using `pytest` fixture teardown so
  handlers added during one test do not bleed into another.
- No real filesystem writes required for `JsonFormatter` tests (only
  `FileHandler` tests use `tmp_path`).

## Test Cases

```python
# tests/unit/test_app_logging.py
import json
import logging
import sys
from pathlib import Path

import pytest

from workshop_video_brain.app.logging import JsonFormatter, setup_logging


# ---------------------------------------------------------------------------
# Fixture: isolated root logger
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_root_logger():
    """Remove any handlers added during the test to avoid bleed-over."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    yield
    # Close and remove any handlers added by the test
    for h in list(root.handlers):
        if h not in original_handlers:
            h.close()
            root.removeHandler(h)


# ---------------------------------------------------------------------------
# JsonFormatter
# ---------------------------------------------------------------------------

class TestJsonFormatter:
    def _make_record(self, message: str = "test message", level=logging.INFO) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test.logger",
            level=level,
            pathname="",
            lineno=0,
            msg=message,
            args=(),
            exc_info=None,
        )
        return record

    def test_format_returns_string(self):
        formatter = JsonFormatter()
        record = self._make_record()
        result = formatter.format(record)
        assert isinstance(result, str)

    def test_format_is_valid_json(self):
        formatter = JsonFormatter()
        record = self._make_record()
        result = formatter.format(record)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_format_contains_level_key(self):
        formatter = JsonFormatter()
        record = self._make_record(level=logging.WARNING)
        parsed = json.loads(formatter.format(record))
        assert parsed["level"] == "WARNING"

    def test_format_contains_logger_key(self):
        formatter = JsonFormatter()
        record = self._make_record()
        parsed = json.loads(formatter.format(record))
        assert parsed["logger"] == "test.logger"

    def test_format_contains_message_key(self):
        formatter = JsonFormatter()
        record = self._make_record("hello world")
        parsed = json.loads(formatter.format(record))
        assert parsed["message"] == "hello world"

    def test_format_contains_time_key(self):
        formatter = JsonFormatter()
        record = self._make_record()
        parsed = json.loads(formatter.format(record))
        assert "time" in parsed

    def test_format_no_exc_info_key_when_no_exception(self):
        formatter = JsonFormatter()
        record = self._make_record()
        parsed = json.loads(formatter.format(record))
        assert "exc_info" not in parsed

    def test_format_includes_exc_info_when_exception_present(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="an error", args=(), exc_info=exc,
        )
        parsed = json.loads(formatter.format(record))
        assert "exc_info" in parsed
        assert "ValueError" in parsed["exc_info"]

    def test_format_produces_single_line(self):
        formatter = JsonFormatter()
        record = self._make_record("single line check")
        result = formatter.format(record)
        assert "\n" not in result


# ---------------------------------------------------------------------------
# setup_logging — console handler
# ---------------------------------------------------------------------------

class TestSetupLoggingConsoleHandler:
    def test_adds_stream_handler(self):
        root = logging.getLogger()
        before = len(root.handlers)
        setup_logging()
        after = len(root.handlers)
        assert after == before + 1

    def test_stream_handler_uses_stderr(self):
        setup_logging()
        root = logging.getLogger()
        stream_handlers = [
            h for h in root.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert any(h.stream is sys.stderr for h in stream_handlers)

    def test_console_handler_level_is_info(self):
        setup_logging()
        root = logging.getLogger()
        stream_handlers = [
            h for h in root.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        levels = [h.level for h in stream_handlers]
        assert logging.INFO in levels

    def test_root_logger_level_set_to_debug(self):
        setup_logging()
        root = logging.getLogger()
        assert root.level == logging.DEBUG


# ---------------------------------------------------------------------------
# setup_logging — file handler
# ---------------------------------------------------------------------------

class TestSetupLoggingFileHandler:
    def test_creates_logs_directory(self, tmp_path: Path):
        setup_logging(workspace_path=tmp_path)
        assert (tmp_path / "logs").is_dir()

    def test_creates_wvb_log_file_handler(self, tmp_path: Path):
        setup_logging(workspace_path=tmp_path)
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        paths = [h.baseFilename for h in file_handlers]
        assert any("wvb.log" in p for p in paths)

    def test_file_handler_uses_json_formatter(self, tmp_path: Path):
        setup_logging(workspace_path=tmp_path)
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        json_handlers = [h for h in file_handlers if isinstance(h.formatter, JsonFormatter)]
        assert len(json_handlers) > 0

    def test_file_handler_level_is_debug(self, tmp_path: Path):
        setup_logging(workspace_path=tmp_path)
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        assert any(h.level == logging.DEBUG for h in file_handlers)

    def test_log_file_written_when_message_logged(self, tmp_path: Path):
        setup_logging(workspace_path=tmp_path)
        logger = logging.getLogger("test_write")
        logger.debug("write this to disk")
        # Flush handlers
        for h in logging.getLogger().handlers:
            h.flush()
        log_file = tmp_path / "logs" / "wvb.log"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "write this to disk" in content


# ---------------------------------------------------------------------------
# setup_logging — per-job file handler
# ---------------------------------------------------------------------------

class TestSetupLoggingJobHandler:
    def test_creates_job_jsonl_file_handler(self, tmp_path: Path):
        setup_logging(workspace_path=tmp_path, job_id="job-abc123")
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        paths = [h.baseFilename for h in file_handlers]
        assert any("job-abc123.jsonl" in p for p in paths)

    def test_no_job_handler_when_job_id_absent(self, tmp_path: Path):
        setup_logging(workspace_path=tmp_path)
        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
        paths = [h.baseFilename for h in file_handlers]
        assert not any(".jsonl" in p for p in paths)

    def test_job_log_is_valid_json_line(self, tmp_path: Path):
        setup_logging(workspace_path=tmp_path, job_id="job-xyz")
        logger = logging.getLogger("job_test")
        logger.info("job message")
        for h in logging.getLogger().handlers:
            h.flush()
        job_file = tmp_path / "logs" / "job-xyz.jsonl"
        assert job_file.exists()
        line = job_file.read_text(encoding="utf-8").strip().splitlines()[0]
        parsed = json.loads(line)
        assert parsed["message"] == "job message"
```

## Steps
1. Read source module at `workshop-video-brain/src/workshop_video_brain/app/logging.py`
2. Create `tests/unit/test_app_logging.py`
3. Implement test cases above
4. Run: `uv run pytest tests/unit/test_app_logging.py -v`

## Expected Results
- `JsonFormatter.format` produces valid single-line JSON with `level`, `logger`, `message`, `time` keys.
- `exc_info` key appears in formatted output only when an exception is attached.
- `setup_logging()` with no args adds exactly one `StreamHandler` (stderr) at `INFO`.
- Root logger level is set to `DEBUG` by `setup_logging`.
- `workspace_path` arg creates `logs/` directory and registers a `FileHandler` using `JsonFormatter`.
- `job_id` arg registers an additional `.jsonl` `FileHandler`.
- A debug message logged after `setup_logging(workspace_path)` appears in `wvb.log`.
- A message logged after `setup_logging(workspace_path, job_id)` appears in the `.jsonl` file as valid JSON.

## Pass / Fail Criteria
- Pass: All tests pass
- Fail: Any test fails
