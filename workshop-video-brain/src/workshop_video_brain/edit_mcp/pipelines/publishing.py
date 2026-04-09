"""YouTube publishing pipeline.

Generates publish-ready assets from transcript and chapter data:
descriptions, title variants, tags, hashtags, pinned comments, summaries,
and full publish bundles saved to workspace reports.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from workshop_video_brain.core.models.publishing import (
    PublishBundle,
    TitleVariants,
    VideoSummary,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MM_SS_RE = re.compile(r"^\d+:\d{2}$")


def _seconds_to_mmss(seconds: float) -> str:
    """Convert float seconds to MM:SS string."""
    total_secs = int(seconds)
    minutes = total_secs // 60
    secs = total_secs % 60
    return f"{minutes}:{secs:02d}"


def _tokenize(text: str) -> list[str]:
    """Return lowercase word tokens stripped of punctuation."""
    return [w.lower() for w in re.findall(r"\b[a-zA-Z][a-zA-Z0-9'-]{1,}\b", text)]


def _extract_noun_candidates(text: str) -> list[str]:
    """Heuristically extract noun-like terms: capitalized words, tool names, etc."""
    candidates: list[str] = []

    # Capitalized multi-word phrases (likely proper nouns / brand names)
    for match in re.finditer(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)*)\b", text):
        word = match.group(1).lower()
        if len(word) > 2:
            candidates.append(word)

    # Brand-model patterns: word followed by numbers (e.g., "Schmetz 90")
    for match in re.finditer(r"\b([A-Z][a-z]+)\s+\d", text):
        candidates.append(match.group(1).lower())

    return candidates


def _read_transcripts(workspace_root: Path) -> list[dict]:
    """Read all transcript JSON files from workspace. Returns list of transcript dicts."""
    transcripts_dir = workspace_root / "transcripts"
    results = []
    if transcripts_dir.exists():
        for json_path in sorted(transcripts_dir.glob("*_transcript.json")):
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                results.append(data)
            except Exception:
                pass
    return results


def _read_chapters_from_workspace(workspace_root: Path) -> list[dict]:
    """Read chapter markers from workspace markers/ directory.

    Returns list of {time: float, title: str} dicts.
    """
    markers_dir = workspace_root / "markers"
    chapters: list[dict] = []
    if not markers_dir.exists():
        return chapters

    for marker_file in sorted(markers_dir.glob("*_markers.json")):
        try:
            items = json.loads(marker_file.read_text(encoding="utf-8"))
            for item in items:
                cat = item.get("category", "")
                if "chapter_candidate" in cat:
                    time_val = item.get("start_seconds", 0.0)
                    label = (
                        item.get("suggested_label")
                        or item.get("reason")
                        or "Chapter"
                    )
                    # Clean label
                    label = re.sub(r"^chapter_candidate\s*:\s*", "", label, flags=re.IGNORECASE)
                    label = re.sub(r"\[confidence[:\s]*[\d.]+\]", "", label, flags=re.IGNORECASE)
                    label = re.sub(r"\[[^\]]*\]", "", label).strip()
                    if not label:
                        label = "Chapter"
                    chapters.append({"time": float(time_val), "title": label})
        except Exception:
            pass

    chapters.sort(key=lambda c: c["time"])
    return chapters


def _transcript_text_from_workspace(workspace_root: Path) -> str:
    """Concatenate all transcript segment texts from workspace."""
    transcripts = _read_transcripts(workspace_root)
    parts: list[str] = []
    for t in transcripts:
        segs = t.get("segments", [])
        for s in segs:
            text = s.get("text", "").strip()
            if text:
                parts.append(text)
    if not parts:
        raw = transcripts[0].get("raw_text", "") if transcripts else ""
        return raw
    return " ".join(parts)


def _get_workspace_title(workspace_root: Path) -> str:
    """Try to read the title from workspace manifest, fallback to dir name."""
    try:
        manifest_path = workspace_root / "manifest.json"
        if manifest_path.exists():
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            return data.get("project_title") or data.get("title") or workspace_root.name
    except Exception:
        pass
    return workspace_root.name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_youtube_description(
    title: str,
    transcript_text: str,
    chapters: list[dict],
    links: list[str] | None = None,
    cta_text: str = "",
) -> str:
    """Generate a YouTube description.

    Args:
        title: Video title.
        transcript_text: Full transcript text.
        chapters: List of {time: float, title: str} dicts.
        links: Optional list of resource URLs or references.
        cta_text: Call-to-action text for the description footer.

    Returns:
        Formatted YouTube description string.
    """
    lines: list[str] = []

    # --- Hook intro ---
    hook = ""
    if transcript_text.strip():
        # Take the first meaningful sentence from the transcript
        sentences = re.split(r"(?<=[.!?])\s+", transcript_text.strip())
        for s in sentences:
            s = s.strip()
            if len(s) > 20:
                hook = s
                break
    if not hook:
        hook = f"In this video, I show you how to {title.lower()}."
    lines.append(hook)
    lines.append("")

    # --- In this video paragraph ---
    lines.append("In this video:")
    # Extract a brief summary from the transcript
    if transcript_text.strip():
        words = transcript_text.split()
        first_100 = " ".join(words[:80])
        if len(words) > 80:
            first_100 += "..."
        lines.append(first_100)
    else:
        lines.append(f"I walk you through everything you need to know about {title}.")
    lines.append("")

    # --- Chapters ---
    if chapters:
        lines.append("⏱ CHAPTERS")
        # Ensure there's an intro at 0:00 if first chapter is not there
        has_zero = any(c["time"] == 0.0 for c in chapters)
        display_chapters = list(chapters)
        if not has_zero:
            display_chapters = [{"time": 0.0, "title": "Intro"}] + display_chapters
        for ch in display_chapters:
            ts = _seconds_to_mmss(ch["time"])
            lines.append(f"{ts} - {ch['title']}")
        lines.append("")

    # --- Resources/links ---
    if links:
        lines.append("🔗 RESOURCES")
        for link in links:
            lines.append(link)
        lines.append("")

    # --- CTA ---
    if cta_text:
        lines.append(cta_text)
    else:
        lines.append("If this helped, subscribe for more tutorials!")
    lines.append("")
    lines.append("👍 Like and share if you found this useful.")

    return "\n".join(lines)


def generate_title_variants(
    title: str,
    transcript_text: str,
    content_type: str = "tutorial",
) -> TitleVariants:
    """Generate 4 title style variants, all under 70 characters.

    Args:
        title: Base video title.
        transcript_text: Transcript text for extracting key terms.
        content_type: Type of content (e.g., "tutorial", "build", "review").

    Returns:
        TitleVariants with searchable, curiosity, how_to, and short_punchy fields.
    """
    # Extract subject / key noun phrase from title
    # Strip common prefixes like "How to", "DIY", etc.
    clean_title = re.sub(
        r"^(how to|diy|build|make|sew|tutorial[:\s-]+)",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    if not clean_title:
        clean_title = title

    # Determine category label
    ct_lower = content_type.lower()
    if "tutorial" in ct_lower:
        category_label = "Tutorial"
    elif "build" in ct_lower:
        category_label = "DIY Build"
    elif "review" in ct_lower:
        category_label = "Review"
    else:
        category_label = "Tutorial"

    # Try to extract a material/project noun from transcript
    material_hint = ""
    if transcript_text:
        candidates = _extract_noun_candidates(transcript_text)
        # Pick the most frequent capitalized term that's not a sentence starter
        freq = Counter(candidates)
        for term, _ in freq.most_common(5):
            if len(term) > 3 and term not in {"this", "that", "then", "just", "with"}:
                material_hint = term.title()
                break

    # --- searchable ---
    searchable_candidate = f"How to {clean_title} | {category_label}"
    if material_hint and material_hint.lower() not in searchable_candidate.lower():
        alt = f"How to {clean_title} | {material_hint} {category_label}"
        if len(alt) <= 70:
            searchable_candidate = alt
    searchable = searchable_candidate[:70]

    # --- curiosity ---
    curiosity_candidate = f"This Changed My {clean_title} Setup"
    if len(curiosity_candidate) > 70 or len(curiosity_candidate) < 20:
        curiosity_candidate = f"Why I Build My Own {clean_title}"
    curiosity = curiosity_candidate[:70]

    # --- how_to ---
    how_to_raw = f"How to {clean_title}"
    if not how_to_raw.lower().startswith("how to"):
        how_to_raw = f"How to Make a {clean_title}"
    how_to = how_to_raw[:70]

    # --- short_punchy ---
    # Try to get under 40 chars
    words = clean_title.split()
    short_candidate = f"DIY {clean_title}"
    if len(short_candidate) > 40:
        short_candidate = " ".join(words[:3])
        if len(short_candidate) < 5:
            short_candidate = clean_title
    short_punchy = short_candidate[:70]

    return TitleVariants(
        searchable=searchable,
        curiosity=curiosity,
        how_to=how_to,
        short_punchy=short_punchy,
    )


def generate_tags(
    transcript_text: str,
    title: str,
    content_type: str = "tutorial",
) -> list[str]:
    """Extract SEO tags from transcript and title.

    Args:
        transcript_text: Full transcript text.
        title: Video title.
        content_type: Content type for adding relevant category tags.

    Returns:
        List of 15-25 unique lowercase tags.
    """
    tags: list[str] = []

    # Tags from title words
    title_words = _tokenize(title)
    for w in title_words:
        if len(w) > 2 and w not in tags:
            tags.append(w)

    # Content type terms
    ct_lower = content_type.lower()
    type_tags: list[str] = [content_type.lower()]
    if "tutorial" in ct_lower:
        type_tags += ["tutorial", "howto", "diy", "making", "crafts"]
    elif "build" in ct_lower:
        type_tags += ["diy", "build", "making", "howto"]
    elif "review" in ct_lower:
        type_tags += ["review", "unboxing", "comparison"]
    for t in type_tags:
        if t not in tags:
            tags.append(t)

    # MYOG/sewing related terms always useful
    domain_tags = ["myog", "sewing", "handmade", "gear", "workshop"]
    for t in domain_tags:
        if t not in tags:
            tags.append(t)

    # Frequent nouns from transcript
    if transcript_text.strip():
        tokens = _tokenize(transcript_text)
        # Stopwords to skip
        stopwords = {
            "the", "and", "you", "for", "that", "this", "with", "are",
            "was", "have", "not", "just", "like", "want", "going", "gonna",
            "really", "very", "here", "then", "when", "what", "can",
            "will", "its", "your", "our", "but", "also", "about", "from",
            "one", "all", "out", "use", "using", "make", "made", "into",
            "now", "them", "they", "some", "more", "than", "get", "bit",
            "little", "gonna", "wanna", "come", "back", "okay", "right",
            "let", "got", "see", "need", "take", "put", "lot", "good",
        }
        freq = Counter(t for t in tokens if len(t) > 3 and t not in stopwords)
        for term, _ in freq.most_common(20):
            if term not in tags:
                tags.append(term)
                if len(tags) >= 25:
                    break

    # Deduplicate preserving order
    seen: set[str] = set()
    unique_tags: list[str] = []
    for t in tags:
        t_clean = t.lower().strip()
        if t_clean and t_clean not in seen:
            seen.add(t_clean)
            unique_tags.append(t_clean)

    # Trim or pad to 15-25 range
    return unique_tags[:25]


def generate_hashtags(
    tags: list[str],
    content_type: str = "tutorial",
) -> list[str]:
    """Convert top tags to hashtags, adding platform-standard ones.

    Args:
        tags: List of tag strings.
        content_type: Content type for adding standard platform hashtags.

    Returns:
        List of up to 15 hashtags prefixed with #.
    """
    # Platform-standard hashtags based on content type
    standard: list[str] = []
    ct_lower = content_type.lower()
    if "tutorial" in ct_lower:
        standard = ["#MYOG", "#DIY", "#tutorial", "#sewing", "#handmade"]
    elif "build" in ct_lower:
        standard = ["#MYOG", "#DIY", "#build", "#handmade", "#maker"]
    else:
        standard = ["#DIY", "#tutorial", "#handmade"]

    hashtags: list[str] = list(standard)

    # Add from top tags
    for tag in tags[:20]:
        cleaned = re.sub(r"[^a-zA-Z0-9]", "", tag)
        if cleaned:
            candidate = f"#{cleaned}"
            if candidate not in hashtags and candidate.lower() not in [h.lower() for h in hashtags]:
                hashtags.append(candidate)
        if len(hashtags) >= 15:
            break

    return hashtags[:15]


def generate_pinned_comment(
    title: str,
    links: list[str] | None = None,
    cta_text: str = "",
) -> str:
    """Generate a friendly pinned comment for the video.

    Args:
        title: Video title.
        links: Optional list of resource links to include.
        cta_text: Custom call-to-action text.

    Returns:
        Formatted pinned comment string.
    """
    lines: list[str] = []
    lines.append(f"Thanks for watching \"{title}\"! 🙏")
    lines.append("")
    lines.append(
        "If you have any questions about the process, drop them in the comments "
        "below — I read every one."
    )

    if links:
        lines.append("")
        lines.append("📌 Links mentioned in this video:")
        for link in links:
            lines.append(f"  • {link}")

    lines.append("")
    if cta_text:
        lines.append(cta_text)
    else:
        lines.append("If this helped you out, consider subscribing for more tutorials like this!")

    lines.append("")
    lines.append("Happy making! ✂️")

    return "\n".join(lines)


def generate_video_summary(
    transcript_text: str,
    title: str,
) -> VideoSummary:
    """Generate short, medium, and long video summaries.

    Args:
        transcript_text: Full transcript text.
        title: Video title.

    Returns:
        VideoSummary with short (1-2 sentences), medium (3-5 sentences),
        and long (full paragraph) summaries.
    """
    if not transcript_text.strip():
        short = f"This video covers {title}."
        medium = (
            f"This video covers {title}. "
            "The tutorial walks through the complete process step by step. "
            "Viewers will learn all the key techniques needed to complete this project."
        )
        long = (
            f"In this tutorial, we cover {title} from start to finish. "
            "The video provides a comprehensive walkthrough of the process, "
            "covering all essential steps, materials, and techniques. "
            "Whether you're a beginner or experienced maker, this guide has something "
            "to offer. By the end, you'll have everything you need to complete this "
            "project on your own."
        )
        return VideoSummary(
            short_summary=short,
            medium_summary=medium,
            long_summary=long,
        )

    # Split transcript into sentences for summarization
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", transcript_text.strip()) if s.strip()]
    total = len(sentences)

    # short: first 1-2 meaningful sentences
    short_parts = []
    for s in sentences:
        if len(s) > 15:
            short_parts.append(s)
        if len(short_parts) >= 2:
            break
    if not short_parts:
        short_parts = [f"This video covers {title}."]
    short = " ".join(short_parts)

    # medium: first ~4 sentences from different parts of the transcript
    medium_parts = []
    if total >= 4:
        indices = [0, total // 4, total // 2, 3 * total // 4]
        for i in indices:
            s = sentences[i].strip()
            if s and s not in medium_parts:
                medium_parts.append(s)
    else:
        medium_parts = sentences[:4]
    if not medium_parts:
        medium_parts = [short]
    medium = " ".join(medium_parts)

    # long: more comprehensive from beginning, middle, and end
    long_parts = []
    if total >= 8:
        step = max(1, total // 6)
        for i in range(0, min(total, step * 6), step):
            s = sentences[i].strip()
            if s and s not in long_parts:
                long_parts.append(s)
    else:
        long_parts = sentences[:8]
    if not long_parts:
        long_parts = [medium]
    long = " ".join(long_parts)

    # Ensure short < medium < long in char length
    if len(medium) <= len(short):
        medium = short + " " + f"This tutorial covers {title} with step-by-step instructions."
    if len(long) <= len(medium):
        long = medium + f" Throughout the video, you'll learn all the key skills needed to complete this {title} project from start to finish."

    return VideoSummary(
        short_summary=short,
        medium_summary=medium,
        long_summary=long,
    )


def extract_resource_mentions(transcript_text: str) -> list[dict]:
    """Extract tool names, material names, and brand mentions from transcript.

    Args:
        transcript_text: Full transcript text.

    Returns:
        List of {name, context, timestamp_hint} dicts.
    """
    if not transcript_text.strip():
        return []

    resources: list[dict] = []
    seen_names: set[str] = set()

    sentences = re.split(r"(?<=[.!?])\s+", transcript_text.strip())

    # Patterns to detect resource mentions
    patterns = [
        # "I'm using a [tool/material]"
        re.compile(
            r"i'?m?\s+(?:using|use)\s+(?:a\s+|an\s+|the\s+|my\s+)?([A-Za-z][A-Za-z0-9\s\-]+?)(?:\s+to|\s+for|[,.]|$)",
            re.IGNORECASE,
        ),
        # "this is a [item]"
        re.compile(
            r"this\s+is\s+(?:a\s+|an\s+|the\s+)?([A-Za-z][A-Za-z0-9\s\-]+?)(?:\s+that|\s+and|\s+which|[,.]|$)",
            re.IGNORECASE,
        ),
        # Brand + model number (e.g., "Singer 4432", "Schmetz 90")
        re.compile(
            r"\b([A-Z][a-zA-Z]+\s+\d+(?:\s*[A-Z]\d*)?)\b",
        ),
        # Quoted names
        re.compile(
            r'["\u201c]([^"\u201d]{3,40})["\u201d]',
        ),
        # "called [name]" or "known as [name]"
        re.compile(
            r"(?:called|known as)\s+(?:a\s+|an\s+|the\s+)?([A-Za-z][A-Za-z0-9\s\-]+?)(?:\s+[,.]|$)",
            re.IGNORECASE,
        ),
    ]

    for sent_idx, sentence in enumerate(sentences):
        for pattern in patterns:
            for match in pattern.finditer(sentence):
                name = match.group(1).strip()
                # Filter noise
                if len(name) < 3 or len(name) > 50:
                    continue
                name_lower = name.lower()
                if name_lower in {"you", "the", "this", "that", "these", "those", "here", "there"}:
                    continue
                if name_lower in seen_names:
                    continue
                seen_names.add(name_lower)

                # Build context snippet
                context = sentence.strip()
                if len(context) > 100:
                    context = context[:97] + "..."

                resources.append({
                    "name": name,
                    "context": context,
                    "timestamp_hint": f"segment ~{sent_idx + 1}",
                })

    return resources


def _format_chapters_text(chapters: list[dict]) -> str:
    """Format chapters list as MM:SS - Title lines."""
    if not chapters:
        return ""
    lines: list[str] = []
    has_zero = any(c["time"] == 0.0 for c in chapters)
    display = list(chapters)
    if not has_zero:
        display = [{"time": 0.0, "title": "Intro"}] + display
    for ch in display:
        ts = _seconds_to_mmss(ch["time"])
        lines.append(f"{ts} - {ch['title']}")
    return "\n".join(lines)


def package_publish_bundle(
    workspace_root: Path,
    title: str = "",
    links: list[str] | None = None,
    cta_text: str = "If this helped, subscribe for more tutorials!",
) -> PublishBundle:
    """Read workspace data and generate a complete publish bundle.

    Reads transcript and chapters from workspace, calls all generators,
    saves all files to reports/publish/, and returns the PublishBundle.

    Args:
        workspace_root: Path to the workspace root directory.
        title: Video title (auto-detected from workspace if not provided).
        links: Optional list of resource links.
        cta_text: Call-to-action text.

    Returns:
        Populated PublishBundle.
    """
    workspace_root = Path(workspace_root)

    # Resolve title
    if not title:
        title = _get_workspace_title(workspace_root)

    # Read transcript text
    transcript_text = _transcript_text_from_workspace(workspace_root)

    # Read chapters
    chapters = _read_chapters_from_workspace(workspace_root)

    # Generate all components
    title_variants = generate_title_variants(title, transcript_text)
    description = generate_youtube_description(title, transcript_text, chapters, links, cta_text)
    tags = generate_tags(transcript_text, title)
    hashtags = generate_hashtags(tags)
    pinned_comment = generate_pinned_comment(title, links, cta_text)
    chapters_text = _format_chapters_text(chapters)
    summary = generate_video_summary(transcript_text, title)
    resources = extract_resource_mentions(transcript_text)

    bundle = PublishBundle(
        title_variants=title_variants,
        description=description,
        tags=tags,
        hashtags=hashtags,
        pinned_comment=pinned_comment,
        chapters_text=chapters_text,
        summary=summary,
        resources=resources,
    )

    # Save all files to reports/publish/
    publish_dir = workspace_root / "reports" / "publish"
    publish_dir.mkdir(parents=True, exist_ok=True)

    (publish_dir / "title_options.txt").write_text(
        "\n".join([
            f"Searchable: {title_variants.searchable}",
            f"Curiosity:  {title_variants.curiosity}",
            f"How-to:     {title_variants.how_to}",
            f"Short:      {title_variants.short_punchy}",
        ]),
        encoding="utf-8",
    )

    (publish_dir / "description.txt").write_text(description, encoding="utf-8")

    (publish_dir / "tags.txt").write_text(
        "\n".join(tags), encoding="utf-8"
    )

    (publish_dir / "hashtags.txt").write_text(
        "\n".join(hashtags), encoding="utf-8"
    )

    (publish_dir / "pinned_comment.txt").write_text(pinned_comment, encoding="utf-8")

    (publish_dir / "chapters.txt").write_text(chapters_text, encoding="utf-8")

    summary_lines = [
        "# Video Summary",
        "",
        "## Short",
        summary.short_summary,
        "",
        "## Medium",
        summary.medium_summary,
        "",
        "## Long",
        summary.long_summary,
    ]
    (publish_dir / "summary.md").write_text("\n".join(summary_lines), encoding="utf-8")

    resource_lines: list[str] = []
    for r in resources:
        resource_lines.append(f"- {r['name']}: {r['context']}")
    (publish_dir / "resources.txt").write_text(
        "\n".join(resource_lines) if resource_lines else "(no resources detected)",
        encoding="utf-8",
    )

    (publish_dir / "publish_bundle.json").write_text(
        bundle.to_json(), encoding="utf-8"
    )

    return bundle


def generate_publish_note(
    workspace_root: Path,
    vault_path: Path,
    bundle: PublishBundle,
    video_url: str = "",
) -> Path:
    """Create or update an Obsidian publish note with the full bundle.

    Creates a note at {vault_path}/Published/{title}.md.
    If an existing In Progress note is found, updates its status.

    Args:
        workspace_root: Path to the workspace root directory.
        vault_path: Path to the Obsidian vault root.
        bundle: The PublishBundle to write.
        video_url: Optional YouTube URL for the published video.

    Returns:
        Path to the created/updated note.
    """
    from workshop_video_brain.production_brain.notes.frontmatter import write_note, parse_note

    workspace_root = Path(workspace_root)
    vault_path = Path(vault_path)

    title = _get_workspace_title(workspace_root)

    # Sanitize title for filename
    safe_title = re.sub(r'[<>:"/\\|?*]', "", title).strip()
    if not safe_title:
        safe_title = workspace_root.name

    published_dir = vault_path / "Published"
    published_dir.mkdir(parents=True, exist_ok=True)

    note_path = published_dir / f"{safe_title}.md"

    # Build frontmatter
    frontmatter = {
        "title": title,
        "status": "published",
        "publish_date": "2026-04-08",
        "youtube_url": video_url,
        "tags": ["video", "published", "tutorial"],
    }

    # Build resources bullet list
    resources_bullets = "\n".join(
        f"- **{r['name']}**: {r['context']}" for r in bundle.resources
    ) or "(none detected)"

    # Build tags line
    tags_line = ", ".join(bundle.tags) if bundle.tags else ""

    # Build body
    body_lines = [
        f"## Summary",
        "",
        bundle.summary.medium_summary,
        "",
        "## Chapters",
        "",
        bundle.chapters_text or "(no chapters)",
        "",
        "## Description",
        "",
        bundle.description,
        "",
        "## Tags",
        "",
        tags_line,
        "",
        "## Resources",
        "",
        resources_bullets,
        "",
        "## Follow-up Ideas",
        "",
        "<!-- Add follow-up video ideas here -->",
        "",
    ]
    body = "\n".join(body_lines)

    # If note already exists, update its frontmatter; otherwise create fresh
    if note_path.exists():
        from workshop_video_brain.production_brain.notes.frontmatter import merge_frontmatter
        existing_fm, _ = parse_note(note_path)
        merged_fm = merge_frontmatter(existing_fm, frontmatter)
        write_note(note_path, merged_fm, "\n" + body)
    else:
        write_note(note_path, frontmatter, "\n" + body)

    return note_path
