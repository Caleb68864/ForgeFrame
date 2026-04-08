# ADR 004: Two-Module Architecture

**Status:** Accepted
**Date:** 2026-04-08

## Context

Workshop Video Brain serves two distinct concerns:

1. **Creative planning** -- turning ideas into outlines, scripts, shot lists,
   and Obsidian notes. This is conversational and Claude-driven.
2. **Mechanical editing** -- executing FFmpeg commands, parsing Kdenlive XML,
   running Whisper transcriptions. This is deterministic and tool-driven.

Mixing these in a single module creates coupling between fast-changing prompt
logic and stable infrastructure code.

## Decision

Split the package into two top-level modules sharing only the `core/` data
models:

- **`production_brain/`** -- Claude Code skills (SKILL.md), note templates,
  and planning workflows. Depends on `core/` models only.
- **`edit_mcp/`** -- FastMCP server, Kdenlive/FFmpeg/Whisper adapters, and
  processing pipelines. Depends on `core/` models only.

The CLI (`app/`) wires them together at the top level.

## Consequences

**Positive:**
- Clean separation of concerns; skills can evolve without touching adapters.
- `edit_mcp/` can be tested independently with headless fixture projects.
- `production_brain/` skills are portable to other MCP servers or CLIs.

**Negative:**
- Slightly more directories to navigate for newcomers.
- Data model changes in `core/` must be coordinated across both modules.
