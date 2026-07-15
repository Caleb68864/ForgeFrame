"""Shot-to-step alignment: map build-step lists to clip transcripts.

The composite move from ``vault/Research/End-to-End Production Gap Analysis.md``
(gap #3): given a numbered list of build steps, find, per step, the clip +
timestamp candidates whose transcript text best matches -- then (optionally)
ensure a thumbnail contact sheet exists per candidate so a *calling vision
agent* can confirm the footage actually shows that step.

Pure stdlib keyword extraction (no new deps). Search is delegated to
``transcript_index.search`` (BM25). Thumbnail generation is delegated to the
existing ``thumbnail_sheet`` pipeline by import (never reimplemented here).

Output: a step->candidates table written as ``reports/shot_map.json`` and a
readable ``reports/shot_map.md``; unmatched steps (coverage gaps for reshoots)
are listed explicitly.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from workshop_video_brain.edit_mcp.pipelines import transcript_index

logger = logging.getLogger(__name__)

# Small stdlib stopword set -- keep step keywords meaningful without a dep.
_STOPWORDS = frozenset(
    """
    a an the this that these those and or but so then now here there of to in on
    at for with from into onto over under up down off out by as is are was were
    be been being do does did done will would shall should can could may might
    must have has had it its it's you your we our they them their he she his her
    i me my mine ours yours them us who whom which what when where why how all any
    each few more most other some such no nor not only own same than too very
    step steps next first second third go going get got let lets make making made
    use using used take taking put putting about after before while your you'll
    """.split()
)

_TOKEN_RE = re.compile(r"[0-9A-Za-z']+")
# Numbered step lines: "1. ...", "2) ...", "3 - ...", "Step 4: ..."
_STEP_RE = re.compile(
    r"^\s*(?:step\s+)?(\d+)\s*[\.\):\-]\s+(.*\S)\s*$",
    re.IGNORECASE,
)


def extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
    """Extract up to *max_keywords* content keywords from *text*.

    Stdlib only: tokenise, lowercase, drop stopwords and <3-char tokens, dedupe
    preserving first-seen order. Order-preserving keeps the most salient early
    words of a step first.
    """
    seen: set[str] = set()
    out: list[str] = []
    for match in _TOKEN_RE.findall(text or ""):
        term = match.lower().strip("'")
        if len(term) < 3 or term in _STOPWORDS or term in seen:
            continue
        seen.add(term)
        out.append(term)
        if len(out) >= max_keywords:
            break
    return out


def parse_steps(steps_file: str | Path) -> list[dict]:
    """Parse a markdown/text file of numbered build steps.

    Recognises ``1. text``, ``2) text``, ``3 - text`` and ``Step 4: text``.
    Falls back to treating every non-empty, non-heading line as a step when no
    numbered lines are found. Returns ``[{index, text}]`` (index is 1-based and
    reflects the parsed step number when present, else sequential).
    """
    path = Path(steps_file)
    if not path.exists():
        raise FileNotFoundError(f"Steps file not found: {steps_file}")

    lines = path.read_text(encoding="utf-8").splitlines()
    steps: list[dict] = []
    for line in lines:
        m = _STEP_RE.match(line)
        if m:
            steps.append({"index": int(m.group(1)), "text": m.group(2).strip()})

    if steps:
        return steps

    # Fallback: non-empty lines that are not markdown headings / list bullets.
    seq = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        stripped = re.sub(r"^[-*+]\s+", "", stripped)
        seq += 1
        steps.append({"index": seq, "text": stripped})
    return steps


def _find_media_for_clip(workspace_path: Path, clip_ref: str) -> Path | None:
    """Best-effort locate the media file whose stem matches *clip_ref*."""
    search_dirs = [
        workspace_path / "media" / "raw",
        workspace_path / "media" / "processed",
        workspace_path / "media" / "derived_audio",
        workspace_path / "media",
    ]
    video_exts = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wav", ".mp3"}
    for d in search_dirs:
        if not d.exists():
            continue
        for candidate in d.glob(f"{clip_ref}.*"):
            if candidate.suffix.lower() in video_exts:
                return candidate
    return None


def _ensure_sheet(workspace_path: Path, clip_ref: str) -> str | None:
    """Ensure a contact sheet exists for *clip_ref*; return its path or None.

    Reuses the existing thumbnail_sheet pipeline. Gracefully returns None when
    no media is found or FFmpeg is unavailable -- the caller records the gap.
    """
    media = _find_media_for_clip(workspace_path, clip_ref)
    if media is None:
        return None
    try:
        from workshop_video_brain.edit_mcp.pipelines.thumbnail_sheet import (
            generate_thumbnail_sheet,
            sheet_output_dir,
        )

        out_dir = sheet_output_dir(workspace_path, media)
        sheet = out_dir / "sheet.png"
        if sheet.exists():
            return str(sheet)
        result = generate_thumbnail_sheet(media, out_dir, grid=True)
        if result.get("success"):
            return result.get("sheet_path")
    except Exception as exc:  # noqa: BLE001
        logger.warning("thumbnail sheet failed for %s: %s", clip_ref, exc)
    return None


def map_shots_to_script(
    workspace_path: str | Path,
    steps_file: str | Path,
    top_k: int = 3,
    include_thumbnails: bool = True,
) -> dict:
    """Align build steps to clip transcript segments.

    For each parsed step, derives keywords, runs :func:`transcript_index.search`
    and keeps the top-*k* clip+timestamp candidates. When *include_thumbnails*,
    ensures a contact sheet exists per candidate clip (for vision confirmation)
    and includes the sheet path. Writes ``reports/shot_map.json`` +
    ``reports/shot_map.md`` and returns
    ``{table, unmatched_steps, json_path, md_path, index}``.
    """
    workspace_path = Path(workspace_path)

    # Ensure the index is current (incremental; cheap when already built).
    index_stats = transcript_index.build_index(workspace_path, rebuild=False)

    steps = parse_steps(steps_file)

    table: list[dict] = []
    unmatched: list[dict] = []
    sheet_cache: dict[str, str | None] = {}

    for step in steps:
        keywords = extract_keywords(step["text"])
        hits = []
        if keywords:
            hits = transcript_index.search(
                workspace_path, " ".join(keywords), limit=top_k
            )

        candidates: list[dict] = []
        for hit in hits:
            clip_ref = hit["clip"]
            cand = {
                "clip": clip_ref,
                "start_seconds": hit["start_seconds"],
                "end_seconds": hit["end_seconds"],
                "text": hit["text"],
                "score": hit["score"],
                "seg_index": hit["seg_index"],
            }
            if include_thumbnails:
                if clip_ref not in sheet_cache:
                    sheet_cache[clip_ref] = _ensure_sheet(
                        workspace_path, clip_ref
                    )
                cand["sheet_path"] = sheet_cache[clip_ref]
            candidates.append(cand)

        row = {
            "step_index": step["index"],
            "step_text": step["text"],
            "keywords": keywords,
            "matched": bool(candidates),
            "candidates": candidates,
        }
        table.append(row)
        if not candidates:
            unmatched.append(
                {"step_index": step["index"], "step_text": step["text"]}
            )

    reports_dir = workspace_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "shot_map.json"
    md_path = reports_dir / "shot_map.md"

    payload = {
        "steps_file": str(Path(steps_file)),
        "top_k": top_k,
        "include_thumbnails": include_thumbnails,
        "index": index_stats,
        "table": table,
        "unmatched_steps": unmatched,
    }
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md_path.write_text(_render_markdown(payload), encoding="utf-8")

    return {
        "table": table,
        "unmatched_steps": unmatched,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "index": index_stats,
    }


def _fmt_ts(seconds: float) -> str:
    seconds = float(seconds)
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m:02d}:{s:05.2f}"


def _render_markdown(payload: dict) -> str:
    lines: list[str] = ["# Shot-to-Step Map", ""]
    lines.append(f"- Steps file: `{payload['steps_file']}`")
    lines.append(f"- top_k: {payload['top_k']}")
    matched = sum(1 for r in payload["table"] if r["matched"])
    total = len(payload["table"])
    lines.append(f"- Coverage: {matched}/{total} steps have candidate footage")
    lines.append("")

    for row in payload["table"]:
        status = "MATCH" if row["matched"] else "NO FOOTAGE"
        lines.append(f"## Step {row['step_index']} — {status}")
        lines.append("")
        lines.append(f"> {row['step_text']}")
        lines.append("")
        if row["keywords"]:
            lines.append(f"Keywords: {', '.join(row['keywords'])}")
            lines.append("")
        if row["candidates"]:
            lines.append("| Clip | Timestamp | Score | Text |")
            lines.append("|---|---|---|---|")
            for c in row["candidates"]:
                text = c["text"].replace("|", "\\|")
                if len(text) > 80:
                    text = text[:77] + "..."
                lines.append(
                    f"| {c['clip']} "
                    f"| {_fmt_ts(c['start_seconds'])}–{_fmt_ts(c['end_seconds'])} "
                    f"| {c['score']} | {text} |"
                )
                sheet = c.get("sheet_path")
                if sheet:
                    lines.append(f"| | contact sheet: `{sheet}` | | |")
            lines.append("")
        else:
            lines.append("_No transcript matches — candidate for reshoot._")
            lines.append("")

    if payload["unmatched_steps"]:
        lines.append("## Coverage Gaps (unmatched steps)")
        lines.append("")
        for u in payload["unmatched_steps"]:
            lines.append(f"- Step {u['step_index']}: {u['step_text']}")
        lines.append("")

    return "\n".join(lines)
