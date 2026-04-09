"""Social clip extraction and social media package generation pipeline."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from workshop_video_brain.core.models.social import ClipCandidate, ClipExport, SocialPost

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Patterns that signal strong openings / hooks
_QUESTION_RE = re.compile(
    r"\b(have you ever|did you know|what if|why does|how do you|what is|do you want|"
    r"are you|can you|would you|have you|do you know)\b",
    re.IGNORECASE,
)

_VALUE_STATEMENT_RE = re.compile(
    r"\b(this is the|the most important|the key|the secret|the trick|the best way|"
    r"one thing|here's how|let me show|watch this|check this|i'll show you|"
    r"the reason|the problem is|the issue is|the mistake)\b",
    re.IGNORECASE,
)

_DEMO_RE = re.compile(
    r"\b(watch|look at this|here we go|let me demonstrate|so now i|now i'm going to|"
    r"first thing|start with|begin with|you can see)\b",
    re.IGNORECASE,
)

# Patterns that indicate context dependence (bad for standalone clips)
_CONTEXT_DEPENDENT_RE = re.compile(
    r"\b(as i mentioned|what we just did|like i said|from before|earlier|"
    r"as you can see from|we already|in the last|in the previous|step \d+ was|"
    r"back to|going back|as shown)\b",
    re.IGNORECASE,
)

_DANGLING_PRONOUN_RE = re.compile(
    r"^(this|that|it|these|those|they|he|she)\b",
    re.IGNORECASE,
)

# Words that indicate specificity / engagement
_SPECIFIC_CONTENT_RE = re.compile(
    r"\b(\d+\s*(mm|cm|inch|inches|feet|ft|ml|oz|gram|degree|degrees|percent|%)|"
    r"technique|method|step|tip|trick|hack|shortcut|mistake|problem|fix|solution|"
    r"material|tool|drill|cut|measure|sand|finish|glue|screw|nail|bolt|"
    r"temperature|pressure|speed|time|minute|second|hour)\b",
    re.IGNORECASE,
)

_VAGUE_RE = re.compile(
    r"\b(kind of|sort of|basically|stuff|things|whatever|etc|and so on|"
    r"and stuff like that|blah)\b",
    re.IGNORECASE,
)

# Strong verbs that indicate action / teaching
_STRONG_VERB_RE = re.compile(
    r"^(start|begin|take|use|apply|cut|drill|measure|place|add|remove|"
    r"make sure|check|avoid|never|always|don't|do not)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _full_text_from_segments(
    segments: list[dict],
    start: float,
    end: float,
) -> str:
    """Concatenate segment text between start and end seconds."""
    parts = []
    for seg in segments:
        seg_start = float(seg.get("start_seconds", 0.0))
        seg_end = float(seg.get("end_seconds", 0.0))
        if seg_end <= start:
            continue
        if seg_start >= end:
            break
        parts.append(seg.get("text", "").strip())
    return " ".join(p for p in parts if p)


def _first_sentence(text: str) -> str:
    """Return first sentence of text."""
    match = re.search(r"[.!?]", text)
    if match:
        return text[: match.start() + 1].strip()
    return text[:120].strip()


def _find_end_point(
    segments: list[dict],
    start_idx: int,
    start_seconds: float,
    min_duration: float,
    max_duration: float,
) -> float | None:
    """Find a natural end point for a clip starting at start_seconds.

    Looks for sentence endings, pauses, or topic transitions within
    the duration window.
    """
    target_min = start_seconds + min_duration
    target_max = start_seconds + max_duration

    # Walk segments collecting end candidates
    best_end: float | None = None
    for i in range(start_idx, len(segments)):
        seg = segments[i]
        seg_end = float(seg.get("end_seconds", 0.0))
        seg_start = float(seg.get("start_seconds", 0.0))

        # Past our window
        if seg_start > target_max:
            break

        # Within window, check if this is a sentence ending
        if seg_end >= target_min:
            text = seg.get("text", "").strip()
            if text and text[-1] in ".!?":
                best_end = seg_end
                # Prefer ending closer to middle of window
                mid = (target_min + target_max) / 2.0
                if seg_end >= mid:
                    break
            elif seg_end <= target_max:
                # Not a clean sentence end but within window
                if best_end is None:
                    best_end = seg_end

    # If no clean end found but we have segments in window, use last feasible
    if best_end is None:
        for i in range(start_idx, len(segments)):
            seg = segments[i]
            seg_end = float(seg.get("end_seconds", 0.0))
            if target_min <= seg_end <= target_max:
                best_end = seg_end

    return best_end


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_highlight_segments(
    transcript_text: str,
    segments: list[dict],
    min_duration: float = 15.0,
    max_duration: float = 60.0,
) -> list[ClipCandidate]:
    """Find clip-worthy segments from transcript.

    Scans for strong opening lines: questions, value statements, demonstrations.
    Extends each to a natural end point. Filters by duration and context
    independence. Returns scored ClipCandidate list.
    """
    if not segments:
        return []

    candidates: list[ClipCandidate] = []
    # Track used time ranges to avoid overlap
    used_ranges: list[tuple[float, float]] = []

    for i, seg in enumerate(segments):
        text = seg.get("text", "").strip()
        if not text:
            continue

        start_seconds = float(seg.get("start_seconds", 0.0))
        text_lower = text.lower()

        # Check for strong opening patterns
        is_hook = bool(
            _QUESTION_RE.search(text_lower)
            or _VALUE_STATEMENT_RE.search(text_lower)
            or _DEMO_RE.search(text_lower)
            or _STRONG_VERB_RE.match(text_lower)
        )

        if not is_hook:
            continue

        # Skip if overlaps existing candidate
        overlaps = any(
            s <= start_seconds <= e or start_seconds <= s <= start_seconds + max_duration
            for (s, e) in used_ranges
        )
        if overlaps:
            continue

        # Find natural end point
        end_seconds = _find_end_point(
            segments, i, start_seconds, min_duration, max_duration
        )
        if end_seconds is None:
            continue

        duration = end_seconds - start_seconds
        if duration < min_duration or duration > max_duration:
            continue

        # Build candidate
        full_text = _full_text_from_segments(segments, start_seconds, end_seconds)
        hook_text = _first_sentence(text)
        content_summary = full_text[:200]

        candidate = ClipCandidate(
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            duration_seconds=duration,
            hook_text=hook_text,
            content_summary=content_summary,
        )
        candidates.append(candidate)
        used_ranges.append((start_seconds, end_seconds))

    return score_clip_candidates(candidates)


def score_clip_candidates(candidates: list[ClipCandidate]) -> list[ClipCandidate]:
    """Score each candidate on hook_strength, clarity, engagement, and overall_score.

    Sorts descending by overall_score.
    """
    scored: list[ClipCandidate] = []
    for c in candidates:
        text = c.content_summary or c.hook_text
        hook_text_lower = c.hook_text.lower()
        text_lower = text.lower()

        # --- hook_strength ---
        hook = 0.3  # base
        if _QUESTION_RE.search(hook_text_lower):
            hook = min(1.0, hook + 0.5)
        if _VALUE_STATEMENT_RE.search(hook_text_lower):
            hook = min(1.0, hook + 0.4)
        if _DEMO_RE.search(hook_text_lower):
            hook = min(1.0, hook + 0.3)
        if _STRONG_VERB_RE.match(hook_text_lower):
            hook = min(1.0, hook + 0.2)
        # Penalize context references in hook
        if _CONTEXT_DEPENDENT_RE.search(hook_text_lower):
            hook = max(0.0, hook - 0.4)
        hook_strength = round(min(1.0, hook), 4)

        # --- clarity ---
        clarity = 0.7  # start high, subtract for issues
        # Dangling pronoun at start
        if _DANGLING_PRONOUN_RE.match(hook_text_lower):
            clarity -= 0.3
        # Context-dependent references in full text
        context_hits = len(_CONTEXT_DEPENDENT_RE.findall(text_lower))
        clarity -= min(0.4, context_hits * 0.15)
        # Self-contained explanation bonus
        if len(text.split()) > 30 and not _CONTEXT_DEPENDENT_RE.search(text_lower):
            clarity = min(1.0, clarity + 0.1)
        clarity = round(max(0.0, min(1.0, clarity)), 4)

        # --- engagement ---
        engagement = 0.3  # base
        specific_count = len(_SPECIFIC_CONTENT_RE.findall(text_lower))
        engagement += min(0.5, specific_count * 0.1)
        vague_count = len(_VAGUE_RE.findall(text_lower))
        engagement -= min(0.3, vague_count * 0.1)
        engagement = round(max(0.0, min(1.0, engagement)), 4)

        # --- overall ---
        overall = round(
            hook_strength * 0.4 + clarity * 0.3 + engagement * 0.3, 4
        )

        scored.append(
            ClipCandidate(
                start_seconds=c.start_seconds,
                end_seconds=c.end_seconds,
                duration_seconds=c.duration_seconds,
                hook_text=c.hook_text,
                content_summary=c.content_summary,
                hook_strength=hook_strength,
                clarity=clarity,
                engagement=engagement,
                overall_score=overall,
                source_step=c.source_step,
            )
        )

    scored.sort(key=lambda x: x.overall_score, reverse=True)
    return scored


def generate_clip_titles(
    candidates: list[ClipCandidate], video_title: str
) -> list[str]:
    """Generate short titles (under 50 chars) for YouTube Shorts.

    Pattern: action phrase or question from the clip content.
    """
    titles: list[str] = []
    seen: set[str] = set()

    for i, c in enumerate(candidates):
        text = c.hook_text or c.content_summary or ""

        # Try to extract a question
        q_match = re.search(r"[^.!?]*\?", text)
        if q_match:
            title = q_match.group(0).strip()
        else:
            # Use first clause (up to comma or end of first sentence)
            title = re.split(r"[,.]", text)[0].strip()

        # Truncate to 49 chars
        if len(title) > 49:
            # Try to cut at last word boundary
            title = title[:49].rsplit(" ", 1)[0].strip()

        # Ensure uniqueness
        base = title
        counter = 2
        while title in seen:
            suffix = f" #{counter}"
            title = base[: 49 - len(suffix)] + suffix
            counter += 1

        # Fallback: use video_title fragment + number
        if not title:
            short_vt = video_title[:30].strip() if video_title else "Clip"
            title = f"{short_vt} - Tip {i + 1}"
            if len(title) > 49:
                title = f"Tip {i + 1}"

        seen.add(title)
        titles.append(title)

    return titles


def generate_clip_captions(candidates: list[ClipCandidate]) -> list[dict]:
    """Generate overlay captions for each clip.

    Returns list of dicts with 'caption' and 'overlay_suggestions'.
    """
    results: list[dict] = []

    for c in candidates:
        text = c.content_summary or c.hook_text or ""

        # Caption: 1-2 lines, under 60 chars each
        # Use hook text as caption if it fits
        hook = c.hook_text.strip()
        if len(hook) <= 60:
            caption = hook
        else:
            # Split at word boundary
            words = hook.split()
            line1 = ""
            for w in words:
                if len(line1) + len(w) + 1 <= 60:
                    line1 = (line1 + " " + w).strip()
                else:
                    break
            caption = line1

        # Overlay suggestions: measurements, material names, step numbers
        overlays: list[str] = []

        # Extract measurements
        measurements = re.findall(
            r"\d+\s*(?:mm|cm|inch|inches|feet|ft|ml|oz|gram|g|lb|degree|°|%)",
            text,
            re.IGNORECASE,
        )
        overlays.extend(measurements[:3])

        # Extract step numbers
        step_refs = re.findall(r"step\s*\d+", text, re.IGNORECASE)
        overlays.extend(step_refs[:2])

        # Extract material/tool names (capitalized nouns after common patterns)
        material_match = re.findall(
            r"\b(?:use|apply|add|cut|drill)\s+(?:a\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
            text,
        )
        overlays.extend(material_match[:2])

        # Ensure overlay lines are under 60 chars
        overlays = [o[:59] for o in overlays if o.strip()]

        results.append({
            "caption": caption[:59],
            "overlay_suggestions": overlays,
        })

    return results


def generate_clip_export_manifest(
    candidates: list[ClipCandidate],
    video_title: str,
    source_video: str = "",
    aspect_ratio: str = "9:16",
) -> list[ClipExport]:
    """Create export specifications for each clip."""
    titles = generate_clip_titles(candidates, video_title)
    captions_data = generate_clip_captions(candidates)

    exports: list[ClipExport] = []
    for i, (candidate, title, cap_info) in enumerate(
        zip(candidates, titles, captions_data)
    ):
        clip_id = f"clip_{i + 1:03d}"
        description = candidate.content_summary[:280] if candidate.content_summary else ""

        # Build hashtag list from content
        hashtags = _extract_hashtags_from_text(
            candidate.content_summary or candidate.hook_text
        )

        exports.append(
            ClipExport(
                clip_id=clip_id,
                start_seconds=candidate.start_seconds,
                end_seconds=candidate.end_seconds,
                title=title,
                caption=cap_info["caption"],
                description=description,
                hashtags=hashtags,
                aspect_ratio=aspect_ratio,
                source_video=source_video,
            )
        )

    return exports


def create_social_post_text(
    clip: ClipCandidate,
    platform: str = "youtube",
    video_title: str = "",
    hashtags: list[str] | None = None,
) -> SocialPost:
    """Generate platform-appropriate post text for a clip.

    Platforms: youtube, instagram, tiktok, twitter
    """
    if hashtags is None:
        hashtags = _extract_hashtags_from_text(
            clip.content_summary or clip.hook_text
        )

    hook = clip.hook_text.strip()
    summary = (clip.content_summary or "")[:200].strip()

    if platform == "youtube":
        post_text = f"{hook}\n\n{summary}\n\n[Full video linked above]\n"
        post_text = post_text.strip()

    elif platform == "instagram":
        cta = "Save this for your next project! Follow for more woodworking tips."
        post_text = (
            f"{hook}\n\n{summary}\n\n{cta}\n\n"
            + " ".join(f"#{h}" for h in hashtags)
        )

    elif platform == "tiktok":
        # Ultra-short
        short_hook = hook[:100] if len(hook) > 100 else hook
        post_text = f"{short_hook} #tutorial #howto #diy"
        # Append custom hashtags
        extra = " ".join(f"#{h}" for h in hashtags[:3])
        if extra:
            post_text = f"{post_text} {extra}"
        post_text = post_text[:280]

    elif platform == "twitter":
        # Under 280 chars
        base = f"{hook}"
        tag_str = " ".join(f"#{h}" for h in hashtags[:3])
        full = f"{base} {tag_str}".strip()
        if len(full) > 280:
            # Truncate hook to fit
            available = 280 - len(tag_str) - 2
            base = hook[:available].rsplit(" ", 1)[0]
            full = f"{base}… {tag_str}".strip()
        post_text = full[:280]

    else:
        post_text = f"{hook}\n\n{summary}"

    return SocialPost(
        platform=platform,
        post_text=post_text.strip(),
        hashtags=hashtags,
        clip_title=hook[:50],
    )


def _extract_hashtags_from_text(text: str) -> list[str]:
    """Extract relevant hashtags from clip text."""
    base_tags = ["woodworking", "diy", "tutorial", "howto", "maker"]
    specific: list[str] = []

    text_lower = text.lower()

    tag_map = {
        "wood": "woodworking",
        "drill": "drilling",
        "cut": "cutting",
        "sand": "sanding",
        "finish": "woodfinish",
        "glue": "woodglue",
        "joint": "woodjoinery",
        "measure": "measuring",
        "tool": "tools",
        "router": "router",
        "chisel": "chisel",
        "lathe": "lathe",
        "jig": "woodworkingjig",
    }
    for keyword, tag in tag_map.items():
        if keyword in text_lower and tag not in specific:
            specific.append(tag)

    result = specific[:4] + [t for t in base_tags if t not in specific]
    return result[:8]


def generate_social_package(
    workspace_root: Path,
    max_clips: int = 5,
    aspect_ratio: str = "9:16",
) -> dict:
    """Full pipeline: read transcript -> find highlights -> score -> generate output.

    Saves to reports/social/:
    - clips_manifest.json
    - clip_1_post.txt, clip_2_post.txt, ...
    - social_summary.md

    Returns dict with results summary.
    """
    workspace_root = Path(workspace_root)
    transcripts_dir = workspace_root / "transcripts"

    # Read transcripts
    from workshop_video_brain.core.models.transcript import Transcript

    all_segments: list[dict] = []
    all_text_parts: list[str] = []
    video_title = workspace_root.name

    if transcripts_dir.exists():
        for json_path in sorted(transcripts_dir.glob("*_transcript.json")):
            try:
                transcript = Transcript.from_json(
                    json_path.read_text(encoding="utf-8")
                )
                for seg in transcript.segments:
                    all_segments.append({
                        "start_seconds": seg.start_seconds,
                        "end_seconds": seg.end_seconds,
                        "text": seg.text,
                    })
                    all_text_parts.append(seg.text)
            except Exception:
                pass

    # Try to get project title from manifest
    manifest_path = workspace_root / "workspace.yaml"
    if manifest_path.exists():
        try:
            import yaml
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            video_title = manifest.get("project_title", video_title)
        except Exception:
            pass

    transcript_text = " ".join(all_text_parts)

    # Find and score candidates
    candidates = find_highlight_segments(transcript_text, all_segments)
    candidates = candidates[:max_clips]

    # Generate exports
    source_video = str(workspace_root / "media" / "raw")
    exports = generate_clip_export_manifest(
        candidates, video_title, source_video=source_video, aspect_ratio=aspect_ratio
    )

    # Write outputs
    social_dir = workspace_root / "reports" / "social"
    social_dir.mkdir(parents=True, exist_ok=True)

    # clips_manifest.json
    manifest_data = [json.loads(e.to_json()) for e in exports]
    (social_dir / "clips_manifest.json").write_text(
        json.dumps(manifest_data, indent=2), encoding="utf-8"
    )

    # Per-clip post files
    post_files: list[str] = []
    for i, (candidate, export) in enumerate(zip(candidates, exports), start=1):
        post = create_social_post_text(
            candidate, platform="youtube", video_title=video_title
        )
        fname = f"clip_{i}_post.txt"
        post_path = social_dir / fname
        content = (
            f"Title: {export.title}\n"
            f"Platform: {post.platform}\n"
            f"Hashtags: {' '.join('#' + h for h in post.hashtags)}\n\n"
            f"{post.post_text}\n"
        )
        post_path.write_text(content, encoding="utf-8")
        post_files.append(str(post_path))

    # social_summary.md
    summary_lines = [
        "# Social Media Clips Summary",
        "",
        f"**Project:** {video_title}",
        f"**Clips found:** {len(exports)}",
        f"**Aspect ratio:** {aspect_ratio}",
        "",
        "## Clips",
        "",
    ]
    for i, (candidate, export) in enumerate(zip(candidates, exports), start=1):
        mm_start = int(candidate.start_seconds // 60)
        ss_start = int(candidate.start_seconds % 60)
        mm_end = int(candidate.end_seconds // 60)
        ss_end = int(candidate.end_seconds % 60)
        summary_lines += [
            f"### Clip {i}: {export.title}",
            "",
            f"- **Time:** {mm_start:02d}:{ss_start:02d} – {mm_end:02d}:{ss_end:02d}",
            f"- **Duration:** {candidate.duration_seconds:.1f}s",
            f"- **Score:** {candidate.overall_score:.2f}",
            f"- **Hook:** {candidate.hook_text}",
            f"- **Caption:** {export.caption}",
            "",
        ]

    summary_md = "\n".join(summary_lines)
    summary_path = social_dir / "social_summary.md"
    summary_path.write_text(summary_md, encoding="utf-8")

    return {
        "clips_found": len(exports),
        "manifest_path": str(social_dir / "clips_manifest.json"),
        "summary_path": str(summary_path),
        "post_files": post_files,
        "exports": manifest_data,
    }
