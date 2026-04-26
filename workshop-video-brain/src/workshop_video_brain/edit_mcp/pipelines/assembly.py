"""Script-to-Timeline Assembly pipeline.

Matches clip labels and transcripts to script steps, then builds a Kdenlive
first-cut project.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from workshop_video_brain.core.models.assembly import (
    AssemblyPlan,
    ClipAssignment,
    StepAssembly,
)
from workshop_video_brain.core.models.clips import ClipLabel
from workshop_video_brain.core.models.kdenlive import (
    Guide,
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.transcript import Transcript
from workshop_video_brain.core.utils.naming import slugify
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stop words for key phrase extraction
# ---------------------------------------------------------------------------

_STOP_WORDS: frozenset[str] = frozenset([
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "can", "could", "this", "that", "these",
    "those", "it", "its", "we", "you", "i", "my", "your", "our", "to",
    "of", "in", "for", "on", "at", "by", "with", "from", "and", "or",
    "but", "so", "if", "then", "than", "not", "no", "up", "out", "just",
    "also", "very", "really", "about", "into", "over",
])


def _extract_key_phrases(text: str) -> set[str]:
    """Extract action verbs, material names, tool names, and distinctive nouns.

    Uses simple word extraction: lowercase, remove stop words, keep words > 3 chars.
    """
    if not text:
        return set()
    words = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
    return {w for w in words if w not in _STOP_WORDS}


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two sets of strings."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _score_clip_for_step(
    clip: ClipLabel,
    clip_transcript_words: set[str],
    step_phrases: set[str],
) -> float:
    """Score a clip against a step description.

    Returns a weighted score 0.0-1.0:
    - transcript_match (weight 0.5): Jaccard similarity of transcript words vs step phrases
    - topic_match (weight 0.3): overlap between clip topics and step phrases
    - content_type_match (weight 0.2): content_type alignment
    """
    # transcript_match
    transcript_score = _jaccard_similarity(clip_transcript_words, step_phrases)

    # topic_match: fraction of clip topics that appear in step phrases
    topic_words = {t.lower() for t in clip.topics}
    if topic_words and step_phrases:
        matched_topics = len(topic_words & step_phrases)
        topic_score = matched_topics / max(len(topic_words), len(step_phrases))
    else:
        topic_score = 0.0

    # content_type_match
    if clip.content_type == "tutorial_step":
        content_score = 1.0
    elif clip.content_type in ("talking_head", "materials_overview"):
        content_score = 0.5
    elif clip.content_type == "b_roll":
        content_score = 0.3
    else:
        content_score = 0.1

    combined = (
        0.5 * transcript_score
        + 0.3 * topic_score
        + 0.2 * content_score
    )
    return min(1.0, combined)


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------


def _load_clip_labels(workspace_root: Path) -> list[ClipLabel]:
    """Read ClipLabel JSON files from workspace clips/ directory."""
    clips_dir = workspace_root / "clips"
    labels: list[ClipLabel] = []
    if not clips_dir.exists():
        return labels
    for label_path in sorted(clips_dir.glob("*_label.json")):
        try:
            label = ClipLabel.from_json(label_path.read_text(encoding="utf-8"))
            labels.append(label)
        except Exception as exc:
            logger.warning("Failed to parse clip label %s: %s", label_path, exc)
    return labels


def _load_transcripts(workspace_root: Path) -> dict[str, Transcript]:
    """Read transcript JSON files from workspace transcripts/ directory.

    Returns a dict mapping clip stem → Transcript.
    """
    transcripts_dir = workspace_root / "transcripts"
    result: dict[str, Transcript] = {}
    if not transcripts_dir.exists():
        return result
    for t_path in sorted(transcripts_dir.glob("*_transcript.json")):
        stem = t_path.stem.replace("_transcript", "")
        try:
            t = Transcript.from_json(t_path.read_text(encoding="utf-8"))
            result[stem] = t
        except Exception as exc:
            logger.warning("Failed to parse transcript %s: %s", t_path, exc)
    return result


def _load_script_steps_from_reports(workspace_root: Path) -> list[dict] | None:
    """Try to load script steps from workspace reports/ directory."""
    reports_dir = workspace_root / "reports"
    if not reports_dir.exists():
        return None
    for candidate in ["script.json", "script_draft.json", "script_steps.json"]:
        path = reports_dir / candidate
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "steps" in data:
                    return data["steps"]
            except Exception as exc:
                logger.warning("Failed to parse script data %s: %s", path, exc)
    return None


def _load_chapter_markers_as_steps(workspace_root: Path) -> list[dict]:
    """Fall back to chapter markers from markers/ directory as pseudo-steps."""
    markers_dir = workspace_root / "markers"
    steps: list[dict] = []
    if not markers_dir.exists():
        return steps
    for marker_file in sorted(markers_dir.glob("*_markers.json")):
        try:
            raw = json.loads(marker_file.read_text(encoding="utf-8"))
            for item in raw:
                cat = item.get("category", "")
                if cat in ("chapter_candidate", "step_explanation"):
                    reason = item.get("reason", "") or item.get("suggested_label", "")
                    steps.append({"description": reason, "chapter_title": reason})
        except Exception as exc:
            logger.warning("Failed to parse markers %s: %s", marker_file, exc)
    if not steps:
        steps.append({"description": "Main content", "chapter_title": "Main"})
    return steps


def _normalize_steps(script_data: dict | list | None) -> list[dict]:
    """Normalize various script data shapes into a list of step dicts."""
    if script_data is None:
        return []
    if isinstance(script_data, list):
        result = []
        for i, item in enumerate(script_data):
            if isinstance(item, str):
                result.append({"description": item, "chapter_title": f"Step {i + 1}"})
            elif isinstance(item, dict):
                result.append(item)
        return result
    if isinstance(script_data, dict):
        if "steps" in script_data:
            return _normalize_steps(script_data["steps"])
        if "description" in script_data:
            return [script_data]
    return []


# ---------------------------------------------------------------------------
# Assembly plan builder
# ---------------------------------------------------------------------------


def build_assembly_plan(
    workspace_root: Path,
    script_data: dict | None = None,
) -> AssemblyPlan:
    """Build an assembly plan matching clips to script steps.

    Args:
        workspace_root: Root of the workspace directory.
        script_data: Optional pre-loaded script data (dict or list of steps).
                     If None, tries to load from workspace reports/ or markers/.

    Returns:
        AssemblyPlan with steps mapped to clip assignments.
    """
    workspace_root = Path(workspace_root)

    # --- Load clip labels ---
    clip_labels = _load_clip_labels(workspace_root)

    # --- Load transcripts ---
    transcripts = _load_transcripts(workspace_root)

    # --- Determine project title ---
    project_title = ""
    manifest_path = workspace_root / "workspace_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            project_title = manifest.get("project_title", "") or manifest.get("title", "")
        except Exception:
            pass

    # --- Resolve script steps ---
    steps_raw: list[dict] = []
    if script_data is not None:
        steps_raw = _normalize_steps(script_data)
    if not steps_raw:
        loaded = _load_script_steps_from_reports(workspace_root)
        if loaded:
            steps_raw = _normalize_steps(loaded)
    if not steps_raw:
        steps_raw = _load_chapter_markers_as_steps(workspace_root)

    # --- No clips: return empty plan ---
    if not clip_labels:
        plan = AssemblyPlan(
            project_title=project_title,
            steps=[
                StepAssembly(
                    step_number=i + 1,
                    step_description=s.get("description", f"Step {i + 1}"),
                    chapter_title=s.get("chapter_title", ""),
                )
                for i, s in enumerate(steps_raw)
            ],
            unmatched_clips=[],
            total_estimated_duration=0.0,
            assembly_report="No clips available for assembly.",
        )
        return plan

    # --- Build transcript word sets per clip ---
    clip_transcript_words: dict[str, set[str]] = {}
    for label in clip_labels:
        stem = label.clip_ref
        if stem in transcripts:
            words = _extract_key_phrases(transcripts[stem].raw_text)
        else:
            words = _extract_key_phrases(label.summary)
        clip_transcript_words[stem] = words

    # --- Build steps ---
    step_assemblies: list[StepAssembly] = []
    primary_assigned: set[str] = set()  # clip_refs already used as primary

    PRIMARY_THRESHOLD = 0.15
    INSERT_THRESHOLD = 0.10

    for i, step_raw in enumerate(steps_raw):
        description = step_raw.get("description", f"Step {i + 1}")
        chapter_title = step_raw.get("chapter_title", "")
        step_phrases = _extract_key_phrases(description)

        # Score all clips
        scored: list[tuple[float, ClipLabel]] = []
        for label in clip_labels:
            score = _score_clip_for_step(
                label,
                clip_transcript_words.get(label.clip_ref, set()),
                step_phrases,
            )
            scored.append((score, label))
        scored.sort(key=lambda x: x[0], reverse=True)

        step_clips: list[ClipAssignment] = []

        # Assign primary (best clip not already used as primary)
        for score, label in scored:
            if score < PRIMARY_THRESHOLD:
                break
            if label.clip_ref not in primary_assigned:
                duration = label.duration if label.duration > 0 else 0.0
                step_clips.append(ClipAssignment(
                    clip_ref=label.clip_ref,
                    source_path=label.source_path,
                    role="primary",
                    score=round(score, 4),
                    in_seconds=0.0,
                    out_seconds=duration if duration > 0 else -1.0,
                    reason=f"Best match for step {i + 1}",
                ))
                primary_assigned.add(label.clip_ref)
                break

        # Assign inserts (closeup/overhead/measurement clips, up to 2)
        insert_count = 0
        insert_types = {"closeup", "overhead", "measurement"}
        for score, label in scored:
            if insert_count >= 2:
                break
            if score < INSERT_THRESHOLD:
                break
            if label.shot_type in insert_types or label.content_type == "closeup":
                # Already assigned as primary for THIS step → skip
                already_primary_this_step = any(
                    c.clip_ref == label.clip_ref and c.role == "primary"
                    for c in step_clips
                )
                if already_primary_this_step:
                    continue
                duration = label.duration if label.duration > 0 else 0.0
                step_clips.append(ClipAssignment(
                    clip_ref=label.clip_ref,
                    source_path=label.source_path,
                    role="insert",
                    score=round(score, 4),
                    in_seconds=0.0,
                    out_seconds=duration if duration > 0 else -1.0,
                    reason=f"Insert for step {i + 1}",
                ))
                insert_count += 1

        step_assemblies.append(StepAssembly(
            step_number=i + 1,
            step_description=description,
            clips=step_clips,
            chapter_title=chapter_title,
        ))

    # --- Unmatched clips ---
    unmatched: list[str] = [
        label.clip_ref for label in clip_labels
        if label.clip_ref not in primary_assigned
    ]

    # --- Estimated duration ---
    total_duration = 0.0
    for step in step_assemblies:
        for clip in step.clips:
            if clip.role == "primary":
                if clip.out_seconds >= 0:
                    total_duration += clip.out_seconds - clip.in_seconds
                # If out = -1 (full clip), use the label's duration
                else:
                    for label in clip_labels:
                        if label.clip_ref == clip.clip_ref:
                            total_duration += label.duration
                            break

    # --- Assembly report ---
    report_lines = ["# Assembly Report", ""]
    for step in step_assemblies:
        primaries = [c for c in step.clips if c.role == "primary"]
        inserts = [c for c in step.clips if c.role == "insert"]
        primary_str = (
            f"{primaries[0].clip_ref} (primary, score: {primaries[0].score:.2f})"
            if primaries
            else "(no primary assigned)"
        )
        insert_str = ""
        if inserts:
            insert_str = " + " + " + ".join(
                f"{c.clip_ref} (insert, score: {c.score:.2f})" for c in inserts
            )
        report_lines.append(
            f"Step {step.step_number}: '{step.step_description}' → {primary_str}{insert_str}"
        )
    if unmatched:
        report_lines.append("")
        report_lines.append("## Unmatched clips")
        for clip_ref in unmatched:
            report_lines.append(f"- {clip_ref}")
    assembly_report = "\n".join(report_lines)

    return AssemblyPlan(
        project_title=project_title,
        steps=step_assemblies,
        unmatched_clips=unmatched,
        total_estimated_duration=round(total_duration, 4),
        assembly_report=assembly_report,
    )


# ---------------------------------------------------------------------------
# Timeline builder
# ---------------------------------------------------------------------------

_CROSSFADE_FRAMES = 12  # ~0.5s at 25fps


def assemble_timeline(
    workspace_root: Path,
    plan: AssemblyPlan,
    add_transitions: bool = True,
    add_chapter_markers: bool = True,
) -> Path:
    """Build a Kdenlive first-cut project from an AssemblyPlan.

    Args:
        workspace_root: Root of the workspace directory.
        plan: The assembly plan to use.
        add_transitions: Whether to add crossfade transitions between steps on V2.
        add_chapter_markers: Whether to add guide markers at step boundaries.

    Returns:
        Path to the written .kdenlive file.
    """
    workspace_root = Path(workspace_root)
    fps = 25.0

    project = KdenliveProject(
        version="7",
        title=plan.project_title or "Assembled Timeline",
        profile=ProjectProfile(width=1920, height=1080, fps=fps, colorspace="709"),
    )

    # Tracks: V2 (primary), V1 (inserts/broll), A1 (primary audio), A2 (secondary)
    track_v2 = Track(id="playlist_v2", track_type="video", name="V2 Primary")
    track_v1 = Track(id="playlist_v1", track_type="video", name="V1 Inserts")
    track_a1 = Track(id="playlist_a1", track_type="audio", name="A1 Primary")
    track_a2 = Track(id="playlist_a2", track_type="audio", name="A2 Secondary")
    project.tracks = [track_v2, track_v1, track_a1, track_a2]

    playlist_v2 = Playlist(id="playlist_v2")
    playlist_v1 = Playlist(id="playlist_v1")
    playlist_a1 = Playlist(id="playlist_a1")
    playlist_a2 = Playlist(id="playlist_a2")

    seen_producers: dict[str, Producer] = {}
    current_frame = 0  # current head position on V2/A1

    def _get_or_create_producer(clip_ref: str, source_path: str) -> Producer:
        if clip_ref not in seen_producers:
            from workshop_video_brain.edit_mcp.adapters.kdenlive.producers import (
                make_avformat_producer,
            )
            pid = f"producer_{len(seen_producers)}"
            # We don't know the source duration here; use a generous
            # default (10 minutes at fps) so trims have headroom.  The
            # entry's out_point still bounds the visible portion.
            default_length_frames = int(600 * fps)
            producer = make_avformat_producer(
                pid,
                source_path or clip_ref,
                length_frames=default_length_frames,
            )
            seen_producers[clip_ref] = producer
            project.producers.append(producer)
        return seen_producers[clip_ref]

    def _clip_duration_frames(assignment: ClipAssignment) -> int:
        """Return duration in frames for a clip assignment."""
        if assignment.out_seconds >= 0:
            return max(1, int((assignment.out_seconds - assignment.in_seconds) * fps))
        # Full clip: try to determine from a default duration
        # Fall back to 5s if unknown
        return int(5.0 * fps)

    for step in plan.steps:
        primaries = [c for c in step.clips if c.role == "primary"]
        inserts = [c for c in step.clips if c.role == "insert"]

        if not primaries:
            # Add a blank/gap entry for this step so the timeline is not empty
            gap_frames = int(5.0 * fps)
            blank_entry = PlaylistEntry(producer_id="", in_point=0, out_point=gap_frames - 1)
            playlist_v2.entries.append(blank_entry)
            playlist_a1.entries.append(PlaylistEntry(producer_id="", in_point=0, out_point=gap_frames - 1))
            current_frame += gap_frames
            continue

        primary = primaries[0]
        producer = _get_or_create_producer(primary.clip_ref, primary.source_path)
        in_frames = int(primary.in_seconds * fps)
        if primary.out_seconds >= 0:
            out_frames = int(primary.out_seconds * fps)
        else:
            out_frames = in_frames + int(5.0 * fps) - 1

        # Chapter marker at step start
        if add_chapter_markers:
            label = step.chapter_title or step.step_description or f"Step {step.step_number}"
            project.guides.append(Guide(
                position=current_frame,
                label=label,
                category="chapter",
            ))

        # Add primary to V2
        playlist_v2.entries.append(PlaylistEntry(
            producer_id=producer.id,
            in_point=in_frames,
            out_point=out_frames,
        ))

        # Add primary audio to A1
        playlist_a1.entries.append(PlaylistEntry(
            producer_id=producer.id,
            in_point=in_frames,
            out_point=out_frames,
        ))

        step_duration_frames = out_frames - in_frames + 1
        step_start_frame = current_frame

        # Add insert clips to V1, overlapping the primary's time range
        # V1 might have gaps up to the step start — pad if needed
        v1_entries_count = sum(
            (e.out_point - e.in_point + 1 if e.producer_id else e.out_point + 1)
            for e in playlist_v1.entries
        )
        if v1_entries_count < current_frame:
            gap_needed = current_frame - v1_entries_count
            if gap_needed > 0:
                playlist_v1.entries.append(PlaylistEntry(
                    producer_id="",
                    in_point=0,
                    out_point=gap_needed - 1,
                ))

        if inserts:
            insert_offset = 0
            for ins in inserts:
                ins_producer = _get_or_create_producer(ins.clip_ref, ins.source_path)
                ins_in = int(ins.in_seconds * fps)
                if ins.out_seconds >= 0:
                    ins_out = int(ins.out_seconds * fps)
                else:
                    ins_out = ins_in + int(3.0 * fps) - 1
                ins_duration = ins_out - ins_in + 1
                # Don't exceed the primary clip's range on V1
                if insert_offset + ins_duration > step_duration_frames:
                    ins_duration = max(1, step_duration_frames - insert_offset)
                    ins_out = ins_in + ins_duration - 1
                playlist_v1.entries.append(PlaylistEntry(
                    producer_id=ins_producer.id,
                    in_point=ins_in,
                    out_point=ins_out,
                ))
                insert_offset += ins_duration
                if insert_offset >= step_duration_frames:
                    break
            # Fill remaining V1 range with blank
            remaining = step_duration_frames - insert_offset
            if remaining > 0:
                playlist_v1.entries.append(PlaylistEntry(
                    producer_id="",
                    in_point=0,
                    out_point=remaining - 1,
                ))
        else:
            # No inserts: add a gap on V1 for this step's duration
            playlist_v1.entries.append(PlaylistEntry(
                producer_id="",
                in_point=0,
                out_point=step_duration_frames - 1,
            ))

        current_frame += step_duration_frames

        # Crossfade transition between steps on V2: represented as a guide marker
        if add_transitions:
            project.guides.append(Guide(
                position=current_frame,
                label=f"Transition after step {step.step_number}",
                category="transition",
            ))

    project.playlists = [playlist_v2, playlist_v1, playlist_a1, playlist_a2]
    project.tractor = {"id": "tractor0", "in": "0", "out": str(max(current_frame - 1, 0))}

    # --- Serialize ---
    title_slug = slugify(plan.project_title) if plan.project_title else "assembled"
    if not title_slug:
        title_slug = "assembled"
    kdenlive_path = serialize_versioned(project, workspace_root, f"{title_slug}_assembled")

    # --- Save assembly report ---
    reports_dir = workspace_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "assembly_report.md"
    report_path.write_text(plan.assembly_report, encoding="utf-8")
    logger.info("Assembly report written to %s", report_path)

    # --- Save assembly plan ---
    plan_path = reports_dir / "assembly_plan.json"
    plan_path.write_text(plan.to_json(), encoding="utf-8")
    logger.info("Assembly plan written to %s", plan_path)

    return kdenlive_path
