# Logic Chronicler — Vault Schema

This file describes what this vault is, how it's organized, and how automated agents (and you) should treat it. It is NOT a CLAUDE.md — Claude Code's auto-discovery ignores this filename on purpose, so this schema does not leak into the project's own agent context.

## What lives here

This vault is a per-project **second brain** maintained by Logic Chronicler. Its job is to make sure the context produced by every Claude Code session in this project is captured, searchable, and able to compound over time — instead of evaporating when the terminal closes.

## Folder layout

```
sources/
  sessions/     Auto-archived Claude Code session transcripts (cleaned markdown).
                One file per session. Filename: YYYY-MM-DD-<slug>.md.
                Don't edit — these are the authoritative record. Edit the wiki instead.
  raw/          Untouched JSONL mirrors of the source transcripts, kept for provenance.
                Never edited by anyone.
  clips/        Manually added reference material (web clippings, docs, snippets).

inbox/          Fleeting notes and captures waiting to be classified.
                /process-inbox (future) will sweep this into sources/ or wiki/.

wiki/           Human-readable knowledge pages authored and maintained by agents.
                Encyclopedia-style: one concept / entity / topic per page.
                Backlinks tie pages together. Free to edit by hand.

index.md        Catalog of every page in the wiki, grouped by category.
                Regenerated after every ingest / maintenance pass.

log.md          Append-only chronological record of every Chronicler operation.
                Ingests, queries, lint passes. Don't prune it — it's the audit trail.
```

## Agent conventions

When an agent writes or updates a page in `wiki/`:

1. **Start with a one-sentence claim** that captures what the page is about. Everything after elaborates.
2. **Cite sources.** Every substantive claim links back to a file in `sources/` or to an external URL. No unsourced assertions.
3. **Use wikilinks (`[[page-name]]`)** for cross-references. Agents are expected to keep these bidirectional.
4. **Atomize.** One concept per page. Prefer many small focused pages over fewer large ones. Split a page the moment it covers more than one idea.
5. **Don't invent filenames.** Check `index.md` before creating a new page; update existing pages if the topic already has one.
6. **Don't touch pages marked `<!-- user-edited -->`** unless the user explicitly asked for a rewrite. Human authority beats agent initiative.
7. **Every operation ends by appending one line to `log.md`.**

## What Chronicler does automatically

- On every Claude Code `Stop` / `SessionEnd` hook, writes/refreshes the session's archive in `sources/sessions/` and its raw JSONL mirror in `sources/raw/`.
- Detects "open threads" — sessions that ended with the assistant asking a question the user never answered — and surfaces them in Logic Sentinel's UI.
- Maintains a tiny SQLite index at `.chronicler/chronicler.db` for fast keyword search. The markdown files are the source of truth; the DB is a cache you can delete and rebuild.

## What Chronicler does on request (user-invoked only — costs tokens)

- **Digest a session** → a Haiku pass reads a session archive and writes a summary page into `wiki/`.
- **Lint the vault** → a Haiku pass finds contradictions, orphan pages, stale claims, missing cross-references.
- **Ingest a URL or file** → fetch, clean, save under `sources/clips/`, then cross-link into `wiki/`.
- **Answer a question** → search + synthesize from the vault with citations.

All AI-backed operations are explicit. No background token burn.

## Model policy

Default model for Chronicler operations: **claude-haiku-4-5**. Sonnet is opt-in per-command (`--deep` flag).

## Edits by humans

You can edit any file in this vault freely. For `wiki/` pages you plan to keep stable across future agent passes, add `<!-- user-edited -->` near the top — agents will respect it.

---

*This file is seeded by Logic Chronicler on vault bootstrap. Customize freely. The rules above are defaults, not laws.*
