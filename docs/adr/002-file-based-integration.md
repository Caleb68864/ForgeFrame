# ADR 002: File-Based Kdenlive Integration

**Status:** Accepted
**Date:** 2026-04-08

## Context

Kdenlive project files (.kdenlive) are XML documents. Automating Kdenlive
edits could be achieved via GUI automation (xdotool, AT-SPI) or by
parsing/generating the XML directly.

## Decision

Parse and generate Kdenlive project XML directly rather than driving the GUI.
The MCP server reads existing projects, applies mutations (cut points, clip
insertions, title cards), and writes to a working copy that the user then
opens in Kdenlive.

## Consequences

**Positive:**
- Reliable -- no dependency on window manager, display server, or Kdenlive
  version-specific UI layouts.
- Testable -- XML round-trip tests can run headlessly in CI.
- Composable -- the same adapter can target any MLT-based project format.

**Negative:**
- Requires reverse-engineering the .kdenlive XML schema (documented in
  docs/reference/kdenlive/).
- Changes are not applied live to an open Kdenlive session; the user must
  reload the project.
