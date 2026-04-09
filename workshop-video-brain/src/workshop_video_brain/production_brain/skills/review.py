"""Rough cut review skill engine.

Analyzes a transcript for pacing issues, repetition, missing visuals,
overlay opportunities, and chapter break candidates.
Produces dual output (markdown string + structured dict).
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher


# Pacing threshold in seconds — segments longer than this without a cut are flagged
PACING_THRESHOLD_SECONDS = 30

# Words that suggest a visual is needed but may be missing
_VISUAL_CUE_PATTERNS = [
    r"\byou can see\b",
    r"\blook at\b",
    r"\bnotice\b",
    r"\blike this\b",
    r"\blike so\b",
    r"\bright here\b",
    r"\bover here\b",
    r"\bthis area\b",
    r"\bhere\b",  # broad — use carefully
    r"\b\d+[\s-]*(inch|inches|in\b|mm|cm|degree|degrees|grit|percent|%)\b",
    r"\bthree[-\s]quarter\b",
    r"\bone[-\s]quarter\b",
    r"\bone[-\s]half\b",
]

# Words that suggest a good overlay opportunity
_OVERLAY_CUE_PATTERNS = {
    "measurement": (
        r"(?:"
        r"\b\d+[\s-]*(inch|inches|in\b|mm|cm|foot|feet|degree|degrees|grit|percent|%)\b"
        r"|"
        r"\b(three[-\s]quarter|one[-\s]quarter|one[-\s]half|three[-\s]eighths"
        r"|one[-\s]eighth|two[-\s]inch|half[-\s]inch)\b"
        r")"
    ),
    "list": r"\b(first|second|third|next|also|finally|and then)\b",
    "tool-name": r"\b(router|lathe|bandsaw|jigsaw|table saw|planer|jointer|spokeshave|chisel|mallet|clamp|vise)\b",
    "safety": r"\b(careful|caution|warning|danger|wear|protect|shield|guard|never|always)\b",
    "chapter-title": r"\b(now (that|we|let)|next (we|step|up)|moving on|the next|let'?s? (move|talk|look))\b",
}

_VISUAL_TRIGGER_WORDS = re.compile(
    "|".join(_VISUAL_CUE_PATTERNS),
    re.IGNORECASE,
)


def generate_review(
    transcript_text: str,
    markers: list[dict],
    edit_notes: str | None = None,
) -> tuple[str, dict]:
    """Analyze a transcript and markers for editorial issues.

    Args:
        transcript_text: Full transcript text. May include timestamps in
                         [HH:MM:SS] or [MM:SS] format.
        markers: List of marker dicts from the workspace. Each may have:
                 category, timestamp_seconds, label, note fields.
        edit_notes: Optional free-text notes from a previous review pass.

    Returns:
        (markdown_string, structured_dict)

    Dict keys: pacing_notes, repetition_flags, insert_suggestions,
               overlay_ideas, chapter_breaks.
    """
    segments = _parse_segments(transcript_text)
    data = {
        "pacing_notes": _analyze_pacing(segments),
        "repetition_flags": _analyze_repetition(segments),
        "insert_suggestions": _analyze_missing_visuals(segments, markers),
        "overlay_ideas": _analyze_overlay_opportunities(segments),
        "chapter_breaks": _suggest_chapter_breaks(segments, markers),
    }
    md = _render_review_markdown(data, transcript_text, markers, edit_notes)
    return md, data


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def _parse_segments(text: str) -> list[dict]:
    """Parse transcript into segments with timestamps if available."""
    # Try to split on timestamp patterns [MM:SS] or [HH:MM:SS]
    ts_pattern = re.compile(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]")
    parts = ts_pattern.split(text)

    if len(parts) <= 1:
        # No timestamps — treat the whole text as one segment, split by sentences
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        chunk_size = max(1, len(sentences) // 8)
        segments = []
        for i in range(0, len(sentences), chunk_size):
            chunk = " ".join(sentences[i: i + chunk_size])
            segments.append({
                "index": i // chunk_size,
                "timestamp": None,
                "text": chunk,
                "word_count": len(chunk.split()),
                "estimated_seconds": len(chunk.split()) // 2,  # ~2 words/sec speaking
            })
        return segments

    # Parts alternate: text, timestamp, text, timestamp, ...
    segments = []
    idx = 0
    if parts[0].strip():
        segments.append({
            "index": idx,
            "timestamp": "0:00",
            "text": parts[0].strip(),
            "word_count": len(parts[0].split()),
            "estimated_seconds": _ts_to_seconds("0:00"),
        })
        idx += 1

    for i in range(1, len(parts) - 1, 2):
        ts = parts[i]
        seg_text = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if seg_text:
            segments.append({
                "index": idx,
                "timestamp": ts,
                "text": seg_text,
                "word_count": len(seg_text.split()),
                "estimated_seconds": _ts_to_seconds(ts),
            })
            idx += 1

    return segments


def _ts_to_seconds(ts: str) -> int:
    """Convert MM:SS or HH:MM:SS to seconds."""
    parts = ts.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except (ValueError, IndexError):
        pass
    return 0


def _analyze_pacing(segments: list[dict]) -> list[dict]:
    """Flag segments longer than PACING_THRESHOLD_SECONDS."""
    issues: list[dict] = []
    issue_id = 1

    for seg in segments:
        # Estimate duration from word count if no next-segment timestamp
        estimated = seg.get("estimated_seconds", 0)
        word_count = seg.get("word_count", 0)
        # ~130 words per minute speaking pace
        duration_estimate = max(estimated, int(word_count / 2.2))

        if duration_estimate > PACING_THRESHOLD_SECONDS:
            ts = seg.get("timestamp") or f"segment {seg['index']}"
            issues.append({
                "id": f"P{issue_id}",
                "segment_start": ts,
                "segment_end": "unknown",
                "problem": (
                    f"Segment runs approximately {duration_estimate}s "
                    f"({word_count} words) without a visual cut."
                ),
                "suggestion": (
                    "Break up with B-roll cutaway, insert shot, or overhead coverage. "
                    "If the content requires this duration, add overlays to maintain engagement."
                ),
            })
            issue_id += 1

    return issues


def _analyze_repetition(segments: list[dict]) -> list[dict]:
    """Find segments with high text similarity."""
    issues: list[dict] = []
    issue_id = 1
    threshold = 0.55  # Similarity ratio above which we flag

    for i, seg_a in enumerate(segments):
        for j, seg_b in enumerate(segments):
            if j <= i:
                continue
            # Only compare segments that are far enough apart (skip adjacent)
            if j - i < 2:
                continue
            text_a = seg_a["text"].lower()
            text_b = seg_b["text"].lower()
            # Only compare segments with enough words to be meaningful
            if len(text_a.split()) < 10 or len(text_b.split()) < 10:
                continue
            ratio = SequenceMatcher(None, text_a, text_b).ratio()
            if ratio >= threshold:
                ts_a = seg_a.get("timestamp") or f"segment {seg_a['index']}"
                ts_b = seg_b.get("timestamp") or f"segment {seg_b['index']}"
                # Extract a representative excerpt
                excerpt_a = text_a[:80].rstrip() + "..."
                issues.append({
                    "id": f"R{issue_id}",
                    "segments": [ts_a, ts_b],
                    "what_repeats": excerpt_a,
                    "suggestion": (
                        f"These segments are {int(ratio * 100)}% similar. "
                        "Consider cutting one or merging them into a single clear take."
                    ),
                })
                issue_id += 1

    return issues


def _analyze_missing_visuals(
    segments: list[dict],
    markers: list[dict],
) -> list[dict]:
    """Find transcript moments that need visual coverage but may not have it."""
    issues: list[dict] = []
    issue_id = 1

    # Build set of covered timestamps from markers
    covered_times = set()
    for m in markers:
        if isinstance(m.get("timestamp_seconds"), (int, float)):
            covered_times.add(int(m["timestamp_seconds"]))

    for seg in segments:
        matches = list(_VISUAL_TRIGGER_WORDS.finditer(seg["text"]))
        for match in matches:
            context_start = max(0, match.start() - 20)
            context_end = min(len(seg["text"]), match.end() + 40)
            excerpt = seg["text"][context_start:context_end]

            ts = seg.get("timestamp") or f"segment {seg['index']}"

            # Determine what kind of shot is needed
            matched_text = match.group(0).lower()
            if re.search(r"\d", matched_text):
                shot_type = "measurement close-up or text overlay"
                priority = "must-have"
            elif any(w in matched_text for w in ["you can see", "look at", "notice"]):
                shot_type = "detail close-up of what is being referenced"
                priority = "must-have"
            else:
                shot_type = "contextual B-roll or close-up"
                priority = "should-have"

            issues.append({
                "id": f"V{issue_id}",
                "transcript_excerpt": excerpt.strip(),
                "timestamp": ts,
                "needed_shot": shot_type,
                "priority": priority,
            })
            issue_id += 1
            # Limit to 3 per segment to avoid noise
            if issue_id > len(segments) * 3 + 1:
                break

    return issues[:20]  # Cap total to keep the review readable


def _analyze_overlay_opportunities(segments: list[dict]) -> list[dict]:
    """Find good overlay candidates in the transcript."""
    opportunities: list[dict] = []

    for seg in segments:
        ts = seg.get("timestamp") or f"segment {seg['index']}"
        for overlay_type, pattern in _OVERLAY_CUE_PATTERNS.items():
            matches = list(re.finditer(pattern, seg["text"], re.IGNORECASE))
            for match in matches:
                content = match.group(0)
                opportunities.append({
                    "timestamp": ts,
                    "type": overlay_type,
                    "content": content,
                })

    # Deduplicate by (timestamp, type, content)
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for o in opportunities:
        key = (o["timestamp"], o["type"], o["content"].lower())
        if key not in seen:
            seen.add(key)
            deduped.append(o)

    return deduped[:30]  # Cap for readability


def _suggest_chapter_breaks(
    segments: list[dict],
    markers: list[dict],
) -> list[dict]:
    """Suggest chapter markers at natural transitions."""
    breaks: list[dict] = []

    # Always start with intro
    first_ts = segments[0].get("timestamp", "0:00") if segments else "0:00"
    breaks.append({"timestamp": first_ts, "title": "Intro", "reason": "Opening"})

    # Look for transition language in segments
    transition_re = re.compile(
        r"\b(now (that|we|let)|next (we|step|up)|moving on|the next step|"
        r"let'?s? (move|talk|look|start|begin)|alright[,\s]|okay[,\s]so)\b",
        re.IGNORECASE,
    )

    for seg in segments[1:]:
        ts = seg.get("timestamp")
        if not ts:
            continue
        match = transition_re.search(seg["text"])
        if match:
            # Derive a chapter title from the text after the transition phrase
            after = seg["text"][match.end():].strip()
            words = after.split()[:6]
            title = " ".join(words).rstrip(".,—:").title() if words else "Next Section"
            breaks.append({
                "timestamp": ts,
                "title": title,
                "reason": f"Transition phrase: '{match.group(0).strip()}'",
            })

    # Add a conclusion chapter near the end
    if segments:
        last_ts = segments[-1].get("timestamp")
        if last_ts and last_ts != first_ts:
            breaks.append({
                "timestamp": last_ts,
                "title": "Result & Wrap-Up",
                "reason": "Final segment",
            })

    # Merge with chapter_candidate markers if available
    for m in markers:
        if m.get("category") == "chapter_candidate":
            ts_s = m.get("timestamp_seconds", 0)
            ts_str = f"{int(ts_s) // 60}:{int(ts_s) % 60:02d}"
            breaks.append({
                "timestamp": ts_str,
                "title": m.get("label", "Chapter"),
                "reason": "Marked as chapter_candidate",
            })

    # Sort by timestamp (crude string sort — sufficient for most cases)
    breaks.sort(key=lambda b: _ts_to_seconds((b["timestamp"] or "0:00").lstrip("~")))

    return breaks


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_review_markdown(
    data: dict,
    transcript_text: str,
    markers: list[dict],
    edit_notes: str | None,
) -> str:
    """Render the review dict as a markdown string."""
    from datetime import datetime, timezone

    lines: list[str] = []
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    word_count = len(transcript_text.split())

    lines.append("# Rough Cut Review")
    lines.append("")
    lines.append(f"Review date: {today}")
    lines.append(f"Transcript length: ~{word_count} words")
    lines.append(f"Markers analyzed: {len(markers)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary
    n_pacing = len(data["pacing_notes"])
    n_rep = len(data["repetition_flags"])
    n_vis = len(data["insert_suggestions"])
    n_overlay = len(data["overlay_ideas"])
    n_ch = len(data["chapter_breaks"])

    lines.append("## Summary")
    lines.append("")
    issues_total = n_pacing + n_rep + n_vis
    if issues_total == 0:
        lines.append(
            "No major issues detected. The cut appears clean. "
            "Review the overlay suggestions and confirm chapter breaks."
        )
    elif issues_total <= 3:
        lines.append(
            f"Cut is in reasonable shape with {issues_total} item(s) to address. "
            "Priority issues are listed below."
        )
    else:
        lines.append(
            f"Cut has {issues_total} items flagged across pacing, repetition, "
            "and missing visuals. Address pacing and missing visuals first."
        )
    lines.append("")

    if edit_notes:
        lines.append(f"*Edit notes from previous pass: {edit_notes}*")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Pacing
    lines.append("## Pacing Notes")
    lines.append("")
    if not data["pacing_notes"]:
        lines.append("No pacing issues detected.")
    else:
        for issue in data["pacing_notes"]:
            lines.append(f"### Issue {issue['id']}")
            lines.append(f"- **Segment:** {issue['segment_start']} - {issue['segment_end']}")
            lines.append(f"- **Problem:** {issue['problem']}")
            lines.append(f"- **Suggestion:** {issue['suggestion']}")
            lines.append("")
    lines.append("---")
    lines.append("")

    # Repetition
    lines.append("## Repetition Flags")
    lines.append("")
    if not data["repetition_flags"]:
        lines.append("No significant repetition detected.")
    else:
        for issue in data["repetition_flags"]:
            lines.append(f"### Issue {issue['id']}")
            lines.append(f"- **Segments:** {' and '.join(issue['segments'])}")
            lines.append(f"- **What repeats:** \"{issue['what_repeats']}\"")
            lines.append(f"- **Suggestion:** {issue['suggestion']}")
            lines.append("")
    lines.append("---")
    lines.append("")

    # Missing visuals
    lines.append("## Missing Visuals")
    lines.append("")
    if not data["insert_suggestions"]:
        lines.append("No missing visual coverage detected.")
    else:
        for issue in data["insert_suggestions"]:
            lines.append(f"### Issue {issue['id']}")
            lines.append(f"- **Transcript:** \"{issue['transcript_excerpt']}\"")
            lines.append(f"- **At:** {issue['timestamp']}")
            lines.append(f"- **Needed shot:** {issue['needed_shot']}")
            lines.append(f"- **Priority:** {issue['priority']}")
            lines.append("")
    lines.append("---")
    lines.append("")

    # Overlay opportunities
    lines.append("## Overlay Opportunities")
    lines.append("")
    if not data["overlay_ideas"]:
        lines.append("No overlay opportunities detected.")
    else:
        lines.append("| # | Timestamp | Type | Content |")
        lines.append("|---|-----------|------|---------|")
        for i, o in enumerate(data["overlay_ideas"], 1):
            content = o["content"].replace("|", "/")
            lines.append(f"| {i} | {o['timestamp']} | {o['type']} | {content} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Chapter breaks
    lines.append("## Suggested Chapter Breaks")
    lines.append("")
    if not data["chapter_breaks"]:
        lines.append("No chapter break suggestions.")
    else:
        lines.append("| # | Timestamp | Chapter Title | Reason |")
        lines.append("|---|-----------|---------------|--------|")
        for i, ch in enumerate(data["chapter_breaks"], 1):
            reason = ch.get("reason", "").replace("|", "/")
            lines.append(f"| {i} | {ch['timestamp']} | {ch['title']} | {reason} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Priority action list
    lines.append("## Priority Action List")
    lines.append("")
    actions: list[str] = []
    for issue in data["pacing_notes"][:2]:
        actions.append(f"Fix pacing ({issue['id']}): {issue['suggestion']}")
    for issue in data["insert_suggestions"]:
        if issue["priority"] == "must-have" and len(actions) < 5:
            actions.append(f"Add missing visual ({issue['id']}): {issue['needed_shot']}")
    for issue in data["repetition_flags"][:1]:
        if len(actions) < 5:
            actions.append(f"Resolve repetition ({issue['id']}): {issue['suggestion']}")

    if not actions:
        lines.append("No priority actions — cut looks good.")
    else:
        for i, action in enumerate(actions[:5], 1):
            lines.append(f"{i}. {action}")
    lines.append("")

    return "\n".join(lines)
