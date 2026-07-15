"""Segment-level transcript search index (SQLite FTS5).

This is the *derived, rebuildable* index described in
``vault/Research/Local Transcription and Clip Search Index.md``. The JSON
transcripts in ``<workspace>/transcripts/*_transcript.json`` remain the
human-readable source of truth; this module walks them into a SQLite
database at ``<workspace>/reports/transcript_index.db`` whose ``segments_fts``
FTS5 table gives BM25-ranked, timestamped, segment-level search.

Zero external dependencies -- ``sqlite3`` (with FTS5 compiled into CPython)
and stdlib ``json``/``re`` only. Complementary to ``clips_search`` (which is
coarse, clip-level, over derived labels); this is fine-grained retrieval over
actual transcript text with a jump-to timestamp.

Public surface (imported by ``server/bundles/transcript_index.py``):

- :func:`build_index` -- walk transcripts -> DB, incremental by mtime.
- :func:`search` -- BM25-ranked segment hits.
- :func:`edit_segment` -- correct a segment in the JSON source + reindex.
- :func:`index_db_path` -- canonical DB location under a workspace.
- :func:`clip_ref_from_path` / :func:`extract_query_terms` -- helpers reused
  by the shot-alignment pipeline.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Locations / naming
# ---------------------------------------------------------------------------

_TRANSCRIPT_SUFFIX = "_transcript.json"


def index_db_path(workspace_path: str | Path) -> Path:
    """Return the canonical index DB path under *workspace_path*.

    Lives in ``reports/`` because the DB is a derived artifact (like other
    reports), can be ``.gitignore``d, and is always safe to delete + rebuild
    from ``transcripts/*.json``.
    """
    return Path(workspace_path) / "reports" / "transcript_index.db"


def transcripts_dir(workspace_path: str | Path) -> Path:
    return Path(workspace_path) / "transcripts"


def clips_dir(workspace_path: str | Path) -> Path:
    return Path(workspace_path) / "clips"


def clip_ref_from_path(path: str | Path) -> str:
    """Derive the clip reference (``{stem}``) from a transcript JSON path.

    ``clip_step1_transcript.json`` -> ``clip_step1``.
    """
    name = Path(path).name
    if name.endswith(_TRANSCRIPT_SUFFIX):
        return name[: -len(_TRANSCRIPT_SUFFIX)]
    # Fall back to the plain stem (handles already-stripped refs).
    return Path(path).stem.replace("_transcript", "")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
    clip_ref     TEXT PRIMARY KEY,
    asset_id     TEXT,
    source_path  TEXT,
    engine       TEXT,
    model        TEXT,
    language     TEXT,
    duration     REAL,
    content_type TEXT,
    mtime        REAL,
    updated_at   TEXT
);

CREATE TABLE IF NOT EXISTS segments (
    segment_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_ref      TEXT REFERENCES clips(clip_ref) ON DELETE CASCADE,
    seg_index     INTEGER,
    start_seconds REAL,
    end_seconds   REAL,
    text          TEXT,
    confidence    REAL,
    edited        INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_segments_clip ON segments(clip_ref);

CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
    text,
    content='segments',
    content_rowid='segment_id',
    tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS tags (
    clip_ref TEXT REFERENCES clips(clip_ref) ON DELETE CASCADE,
    tag      TEXT
);

CREATE INDEX IF NOT EXISTS idx_tags_clip ON tags(clip_ref);

-- Keep the external-content FTS index in sync automatically.
CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
    INSERT INTO segments_fts(rowid, text) VALUES (new.segment_id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
    INSERT INTO segments_fts(segments_fts, rowid, text)
        VALUES ('delete', old.segment_id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS segments_au AFTER UPDATE ON segments BEGIN
    INSERT INTO segments_fts(segments_fts, rowid, text)
        VALUES ('delete', old.segment_id, old.text);
    INSERT INTO segments_fts(rowid, text) VALUES (new.segment_id, new.text);
END;
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _fts5_available(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)"
        )
        conn.execute("DROP TABLE IF EXISTS _fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False


def _ensure_schema(conn: sqlite3.Connection) -> None:
    if not _fts5_available(conn):
        raise RuntimeError(
            "SQLite FTS5 is not available in this Python build; "
            "the transcript index requires FTS5 (standard in CPython)."
        )
    conn.executescript(_SCHEMA)


# ---------------------------------------------------------------------------
# Query sanitisation
# ---------------------------------------------------------------------------

_TERM_RE = re.compile(r"[0-9A-Za-z']+")


def extract_query_terms(query: str) -> list[str]:
    """Tokenise *query* into safe, lowercased FTS terms (dedup, order-kept)."""
    seen: set[str] = set()
    terms: list[str] = []
    for match in _TERM_RE.findall(query or ""):
        term = match.lower().strip("'")
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _build_match_expr(terms: list[str]) -> str:
    """Build an OR-joined FTS5 MATCH expression from *terms*.

    OR semantics let BM25 rank a segment matching more (and rarer) terms
    higher, so exact/full matches float to the top without excluding partial
    matches. Each term is double-quoted so reserved words / stray chars are
    treated as literals.
    """
    return " OR ".join(f'"{t}"' for t in terms)


# ---------------------------------------------------------------------------
# Build / incremental index
# ---------------------------------------------------------------------------


def _load_content_types(workspace_path: str | Path) -> dict[str, dict]:
    """Return ``{clip_ref: {content_type, tags}}`` from ``clips/*_label.json``.

    Best-effort: missing/malformed label files are skipped silently so the
    index never depends on labels existing.
    """
    out: dict[str, dict] = {}
    cdir = clips_dir(workspace_path)
    if not cdir.exists():
        return out
    for label_path in cdir.glob("*_label.json"):
        try:
            raw = json.loads(label_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping malformed label %s: %s", label_path, exc)
            continue
        ref = raw.get("clip_ref") or label_path.name.replace("_label.json", "")
        out[ref] = {
            "content_type": raw.get("content_type", ""),
            "tags": list(raw.get("tags", []) or []),
        }
    return out


def _index_one(
    conn: sqlite3.Connection,
    json_path: Path,
    content_types: dict[str, dict],
) -> int:
    """(Re)index a single transcript JSON. Returns segment count indexed."""
    from datetime import datetime, timezone

    clip_ref = clip_ref_from_path(json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    segments = data.get("segments", []) or []

    label = content_types.get(clip_ref, {})
    duration = 0.0
    if segments:
        try:
            duration = max(float(s.get("end_seconds", 0.0)) for s in segments)
        except (TypeError, ValueError):
            duration = 0.0

    mtime = json_path.stat().st_mtime

    # Replace any prior rows for this clip (cascade clears segments + tags).
    conn.execute("DELETE FROM clips WHERE clip_ref = ?", (clip_ref,))
    conn.execute(
        """INSERT INTO clips
           (clip_ref, asset_id, source_path, engine, model, language,
            duration, content_type, mtime, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            clip_ref,
            str(data.get("asset_id", "")),
            str(json_path),
            data.get("engine", ""),
            data.get("model", ""),
            data.get("language", ""),
            duration,
            label.get("content_type", ""),
            mtime,
            datetime.now(tz=timezone.utc).isoformat(),
        ),
    )

    for tag in label.get("tags", []):
        conn.execute(
            "INSERT INTO tags (clip_ref, tag) VALUES (?, ?)",
            (clip_ref, str(tag).lower()),
        )

    count = 0
    for idx, seg in enumerate(segments):
        text = (seg.get("text") or "").strip()
        conn.execute(
            """INSERT INTO segments
               (clip_ref, seg_index, start_seconds, end_seconds, text,
                confidence, edited)
               VALUES (?, ?, ?, ?, ?, ?, 0)""",
            (
                clip_ref,
                idx,
                float(seg.get("start_seconds", 0.0)),
                float(seg.get("end_seconds", 0.0)),
                text,
                float(seg.get("confidence", 1.0)),
            ),
        )
        count += 1
    return count


def build_index(workspace_path: str | Path, rebuild: bool = False) -> dict:
    """Walk ``transcripts/*_transcript.json`` into the SQLite FTS index.

    Idempotent and incremental: a transcript whose file ``mtime`` matches the
    stored value is skipped unless *rebuild* is set, in which case the DB is
    dropped and fully rebuilt.

    Returns ``{clips_indexed, segments_indexed, clips_skipped, db_path}``.
    """
    workspace_path = Path(workspace_path)
    tdir = transcripts_dir(workspace_path)
    db_path = index_db_path(workspace_path)

    if rebuild and db_path.exists():
        db_path.unlink()

    conn = _connect(db_path)
    try:
        _ensure_schema(conn)

        if not tdir.exists():
            conn.commit()
            return {
                "clips_indexed": 0,
                "segments_indexed": 0,
                "clips_skipped": 0,
                "db_path": str(db_path),
            }

        stored_mtimes = {
            row["clip_ref"]: row["mtime"]
            for row in conn.execute("SELECT clip_ref, mtime FROM clips")
        }
        content_types = _load_content_types(workspace_path)

        present_refs: set[str] = set()
        clips_indexed = 0
        clips_skipped = 0
        segments_indexed = 0

        for json_path in sorted(tdir.glob(f"*{_TRANSCRIPT_SUFFIX}")):
            clip_ref = clip_ref_from_path(json_path)
            present_refs.add(clip_ref)
            mtime = json_path.stat().st_mtime

            prior = stored_mtimes.get(clip_ref)
            if not rebuild and prior is not None and abs(prior - mtime) < 1e-6:
                clips_skipped += 1
                continue

            try:
                segments_indexed += _index_one(conn, json_path, content_types)
                clips_indexed += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to index %s: %s", json_path, exc)

        # Drop clips whose transcript files have disappeared.
        for stale in set(stored_mtimes) - present_refs:
            conn.execute("DELETE FROM clips WHERE clip_ref = ?", (stale,))

        conn.commit()
        return {
            "clips_indexed": clips_indexed,
            "segments_indexed": segments_indexed,
            "clips_skipped": clips_skipped,
            "db_path": str(db_path),
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def search(
    workspace_path: str | Path,
    query: str,
    limit: int = 10,
    clip: str | None = None,
) -> list[dict]:
    """Return BM25-ranked segment hits for *query*.

    Each hit: ``{clip, start_seconds, end_seconds, text, score, seg_index}``.
    ``score`` is ``-bm25`` so higher is better (exact/full matches first).
    Optionally restrict to a single *clip* (clip_ref). Returns ``[]`` when the
    index is missing or the query has no searchable terms.
    """
    workspace_path = Path(workspace_path)
    db_path = index_db_path(workspace_path)
    if not db_path.exists():
        return []

    terms = extract_query_terms(query)
    if not terms:
        return []
    match_expr = _build_match_expr(terms)

    sql = (
        "SELECT s.clip_ref AS clip, s.seg_index, s.start_seconds, "
        "s.end_seconds, s.text, bm25(segments_fts) AS rank "
        "FROM segments_fts "
        "JOIN segments s ON s.segment_id = segments_fts.rowid "
        "WHERE segments_fts MATCH ? "
    )
    params: list = [match_expr]
    if clip:
        sql += "AND s.clip_ref = ? "
        params.append(clip)
    sql += "ORDER BY rank LIMIT ?"
    params.append(int(limit))

    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        logger.warning("transcript search failed for %r: %s", query, exc)
        return []
    finally:
        conn.close()

    return [
        {
            "clip": row["clip"],
            "seg_index": row["seg_index"],
            "start_seconds": round(float(row["start_seconds"]), 3),
            "end_seconds": round(float(row["end_seconds"]), 3),
            "text": row["text"],
            "score": round(-float(row["rank"]), 4),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Edit + single-row reindex
# ---------------------------------------------------------------------------


def edit_segment(
    workspace_path: str | Path,
    clip: str,
    segment_index: int,
    new_text: str,
) -> dict:
    """Correct one segment's text in the JSON source and reindex that row.

    Writes back to ``transcripts/{clip}_transcript.json`` (the source of
    truth), marks the row ``edited=1``, and updates the single FTS row via the
    update trigger. Returns ``{clip, segment_index, old_text, new_text}``.

    Raises ``FileNotFoundError`` / ``IndexError`` / ``ValueError`` on bad input.
    """
    workspace_path = Path(workspace_path)
    json_path = transcripts_dir(workspace_path) / f"{clip}{_TRANSCRIPT_SUFFIX}"
    if not json_path.exists():
        raise FileNotFoundError(f"Transcript not found for clip: {clip}")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    segments = data.get("segments", []) or []
    if segment_index < 0 or segment_index >= len(segments):
        raise IndexError(
            f"segment_index {segment_index} out of range "
            f"(clip {clip} has {len(segments)} segments)"
        )

    cleaned = (new_text or "").strip()
    old_text = (segments[segment_index].get("text") or "").strip()
    segments[segment_index]["text"] = cleaned

    # Rewrite raw_text from segment texts so it stays consistent.
    data["raw_text"] = " ".join(
        (s.get("text") or "").strip() for s in segments
    ).strip()
    json_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    db_path = index_db_path(workspace_path)
    if db_path.exists():
        conn = _connect(db_path)
        try:
            _ensure_schema(conn)
            cur = conn.execute(
                "SELECT segment_id FROM segments "
                "WHERE clip_ref = ? AND seg_index = ?",
                (clip, segment_index),
            )
            row = cur.fetchone()
            if row is not None:
                conn.execute(
                    "UPDATE segments SET text = ?, edited = 1 "
                    "WHERE segment_id = ?",
                    (cleaned, row["segment_id"]),
                )
            else:
                # Row not present yet (index stale) -- (re)index the clip.
                content_types = _load_content_types(workspace_path)
                _index_one(conn, json_path, content_types)
            conn.commit()
        finally:
            conn.close()

    return {
        "clip": clip,
        "segment_index": segment_index,
        "old_text": old_text,
        "new_text": cleaned,
    }
