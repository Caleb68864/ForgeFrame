# ADR 001: Python Stack

**Status:** Accepted
**Date:** 2026-04-08

## Context

Workshop Video Brain needs a local-first MCP server that can orchestrate
FFmpeg for video processing, Whisper for transcription, and Claude Code skills
for planning workflows. The server must run on the developer's machine without
requiring cloud infrastructure.

## Decision

Use Python 3.12+ as the implementation language with the following core
libraries:

- **FastMCP** -- ergonomic MCP server framework with minimal boilerplate
- **Pydantic v2** -- data validation and settings management
- **Click** -- composable CLI with minimal overhead
- **Jinja2** -- templating for script and note generation
- **PyYAML** -- SKILL.md frontmatter and config parsing

## Consequences

**Positive:**
- Rich ecosystem for FFmpeg bindings (ffmpeg-python), STT (faster-whisper),
  and XML manipulation (lxml) needed in later sub-specs.
- Strong cross-platform support (Linux, macOS, Windows).
- uv provides fast, reproducible dependency management.
- Type annotations + Pydantic give confidence without a compiled language.

**Negative:**
- Python startup latency is higher than Go or Rust for the CLI.
- Requires Python 3.12+ on the user's machine (mitigated by uv toolchain).
