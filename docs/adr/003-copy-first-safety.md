# ADR 003: Copy-First Safety

**Status:** Accepted
**Date:** 2026-04-08

## Context

The MCP server will mutate Kdenlive project files on behalf of the user.
Users' original project files are irreplaceable -- a bad write could destroy
hours of editorial work.

## Decision

All mutations target copies, never originals. The server will:

1. Snapshot the source project to `working_copies/<project>/<timestamp>/`
   before any write operation.
2. Apply all changes to the working copy.
3. Return the working copy path to the user; the user manually promotes it
   when satisfied.

No tool in the MCP server will ever overwrite a file outside of `working_copies/`.

## Consequences

**Positive:**
- Zero risk of data loss from server bugs or incomplete operations.
- The user always has a clean rollback path.
- Snapshots provide a natural audit trail of AI-assisted edits.

**Negative:**
- Slight disk overhead from maintaining working copies.
- Users must consciously move working copies to production paths
  (acceptable for a tutorial workflow where deliberate review is desirable).
