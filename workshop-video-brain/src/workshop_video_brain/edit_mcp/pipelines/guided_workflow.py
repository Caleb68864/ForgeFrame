"""Resumable first-cut workflow with explicit prerequisites and version pinning."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from workshop_video_brain.workspace.safe_write import atomic_write_text, locked_path

STAGES = ("footage", "selects", "assembly", "preview", "review")


def _root(root: Path | str) -> Path:
    path = Path(root).resolve()
    if not path.is_dir() or not (path / "workspace.yaml").is_file():
        raise ValueError("Choose an initialized workspace containing workspace.yaml.")
    return path


def _state(root: Path) -> dict:
    path = root / "reports" / "workflow_state.json"
    return json.loads(path.read_text()) if path.exists() else {"stages": {}}


def _fingerprint(root: Path, stage: str) -> str:
    patterns = ["workspace.yaml", "media/raw/**/*"]
    if stage != "footage":
        patterns += ["transcripts/*_transcript.json"]
    if STAGES.index(stage) >= 2:
        patterns += ["markers/*_markers.json", "clips/*_label.json", "reports/script*.json"]
    digest = hashlib.sha256()
    for path in sorted({p for pattern in patterns for p in root.glob(pattern) if p.is_file()}):
        digest.update(str(path.relative_to(root)).encode())
        if "media/raw" in path.as_posix():
            stat = path.stat()
            digest.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode())
        else:
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _transcript_gaps(root: Path) -> list[str]:
    from workshop_video_brain.core.utils.paths import safe_filename
    from workshop_video_brain.core.models.transcript import Transcript
    gaps = []
    extensions = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".mxf", ".mts", ".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}
    for source in (root / "media/raw").rglob("*"):
        if not source.is_file() or source.suffix.lower() not in extensions:
            continue
        path = root / "transcripts" / f"{safe_filename(source.stem)}_transcript.json"
        try:
            transcript = Transcript.from_json(path.read_text())
            if not transcript.segments:
                gaps.append(f"{source.name}: transcript has no segments; provide speech transcription or manual clip labels.")
            elif source.stat().st_mtime_ns > path.stat().st_mtime_ns:
                gaps.append(f"{source.name}: recording changed after transcription; regenerate its transcript.")
        except Exception:
            gaps.append(f"{source.name}: missing or invalid transcript.")
    return gaps


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_signature(path: Path) -> dict:
    """Inspect large previews without rereading their entire video payload."""
    metadata = path.stat()
    return {"size": metadata.st_size, "mtime_ns": metadata.st_mtime_ns}


def _call(function: Callable, root: Path) -> dict:
    result = function(str(root))
    if result.get("status") != "success":
        raise ValueError(result.get("message", str(result)))
    data = result["data"]
    if data.get("errors"):
        raise ValueError("; ".join(map(str, data["errors"])))
    return data


def project_status(root: Path | str) -> dict:
    """Read readiness without creating files or starting operations."""
    root = _root(root)
    state = _state(root)
    raw = [p for p in (root / "media/raw").rglob("*") if p.is_file()]
    transcripts = list((root / "transcripts").glob("*_transcript.json"))
    labels = list((root / "clips").glob("*_label.json"))
    scripts = list((root / "reports").glob("script*.json"))
    missing = _transcript_gaps(root)
    if not raw:
        missing.append("Copy recordings into media/raw/.")
    if not transcripts:
        missing.append("Ingest footage to generate transcripts.")
    if not labels:
        missing.append("Generate clip labels before assembly.")
    if not scripts:
        missing.append("Add reports/script.json with a steps list before assembly.")
    selected = state.get("project_file", "")
    pinned = bool(selected and Path(selected).is_file() and _hash(Path(selected)) == state.get("project_hash"))
    ready = {}
    for stage in STAGES:
        record = state.get("stages", {}).get(stage, {})
        ready[stage] = bool(record.get("status") == "completed" and record.get("fingerprint") == _fingerprint(root, stage))
        if stage in ("assembly", "preview", "review"):
            ready[stage] = ready[stage] and pinned
    preview = state.get("stages", {}).get("preview", {}).get("output_path", "")
    if preview and (not Path(preview).is_file() or Path(preview).stat().st_size == 0 or _artifact_signature(Path(preview)) != state.get("stages", {}).get("preview", {}).get("artifact_signature")):
        ready["preview"] = ready["review"] = False
    review = state.get("stages", {}).get("review", {})
    review_path = Path(review.get("review_path", ""))
    if not review_path.is_file() or _hash(review_path) != review.get("artifact_hash"):
        ready["review"] = False
    for index, stage in enumerate(STAGES):
        ready[stage] = ready[stage] and all(ready[prior] for prior in STAGES[:index])
    from workshop_video_brain.workspace.jobs import list_jobs
    jobs = list_jobs(root, reconcile=False)
    active = [j for j in jobs if j.get("status") in ("queued", "running", "cancelling")]
    return {"workspace_path": str(root), "readiness": ready, "missing": missing,
            "next_action": missing[0] if missing else next((f"Run workflow through {s}." for s in STAGES if not ready[s]), "Review the preview and record editorial feedback."),
            "selected_project_version": selected, "version_valid": pinned,
            "active_jobs": active, "latest_preview": preview if ready["preview"] else None,
            "review_status": "awaiting_human_review" if ready["review"] else "not_prepared"}


def run_workflow(root: Path | str, through: str = "review", project_file: str = "", callback: Callable | None = None) -> dict:
    """Execute allowlisted stages, persisting completion only after validation.

    Review prepares a checklist; editorial acceptance remains a human decision.
    """
    root = _root(root)
    if through not in STAGES:
        raise ValueError(f"through must be one of {STAGES}")
    state_path = root / "reports/workflow_state.json"
    with locked_path(state_path):
        state = _state(root)
        if project_file:
            candidate = Path(project_file)
            chosen = (candidate if candidate.is_absolute() else root / candidate).resolve()
            if not chosen.is_relative_to(root / "projects/working_copies") or not chosen.is_file():
                raise ValueError("project_file must be an existing project in projects/working_copies/.")
            if str(chosen) != state.get("project_file") or _hash(chosen) != state.get("project_hash"):
                for s in ("assembly", "preview", "review"):
                    state["stages"].pop(s, None)
                state.update(project_file=str(chosen), project_hash=_hash(chosen), explicit_project=True)
        def save() -> None:
            atomic_write_text(state_path, json.dumps(state, indent=2), workspace_root=root)
        for index, stage in enumerate(STAGES[:STAGES.index(through) + 1]):
            if callback:
                callback(stage, index, STAGES.index(through) + 1)
            fingerprint = _fingerprint(root, stage)
            previous = state["stages"].get(stage, {})
            valid = previous.get("fingerprint") == fingerprint and previous.get("status") == "completed"
            if stage in ("assembly", "preview", "review"):
                chosen = Path(state.get("project_file", ""))
                valid = valid and chosen.is_file() and _hash(chosen) == state.get("project_hash")
            if stage == "preview":
                artifact = Path(previous.get("output_path", ""))
                valid = valid and artifact.is_file() and artifact.stat().st_size > 0 and _artifact_signature(artifact) == previous.get("artifact_signature")
            if stage == "review":
                artifact = Path(previous.get("review_path", ""))
                valid = valid and artifact.is_file() and _hash(artifact) == previous.get("artifact_hash")
            if valid:
                continue
            for downstream in STAGES[index:]:
                state["stages"].pop(downstream, None)
            state["stages"][stage] = {"status": "running"}
            save()
            try:
                result = _execute(root, stage, state, callback)
                state["stages"][stage] = {"status": "completed", "fingerprint": _fingerprint(root, stage), **result}
                save()
            except Exception as exc:
                state["stages"][stage] = {"status": "failed", "error": str(exc)}
                save()
                raise
        if callback:
            callback(through, STAGES.index(through) + 1, STAGES.index(through) + 1)
    return {"project_file": state.get("project_file"), "stages": state["stages"], "review_status": "awaiting_human_review" if through == "review" else "not_prepared"}


def _execute(root: Path, stage: str, state: dict, callback: Callable | None = None) -> dict:
    if stage == "footage":
        if not any(p.is_file() for p in (root / "media/raw").rglob("*")):
            raise ValueError("Copy recordings into media/raw/ before ingest.")
        from dataclasses import asdict
        from workshop_video_brain.workspace.manager import WorkspaceManager
        from workshop_video_brain.app.config import load_config
        from workshop_video_brain.edit_mcp.pipelines.ingest import run_ingest
        def pending(path) -> None:
            if callback:
                callback("footage", 0, 1, pending_output=str(path))
        def completed(path) -> None:
            if callback:
                callback("footage", 0, 1, completed_output=str(path))
        report = run_ingest(WorkspaceManager.open(root), load_config(), progress=callback, pending_output=pending, completed_output=completed)
        result = asdict(report)
        if result.get("errors"):
            raise ValueError("; ".join(result["errors"]))
        if result.get("scanned_count", 0) == 0:
            raise ValueError("No supported media found in media/raw/.")
        return result
    if stage == "selects":
        gaps = _transcript_gaps(root)
        if gaps:
            raise ValueError("; ".join(gaps))
        if not list((root / "transcripts").glob("*_transcript.json")):
            raise ValueError("No transcripts available; complete footage ingest first.")
        from workshop_video_brain.edit_mcp.server.tools.transcript_markers import markers_auto_generate
        from workshop_video_brain.edit_mcp.server.tools.clips_nle import clips_label
        from workshop_video_brain.edit_mcp.server.tools.timeline_project import timeline_build_selects
        markers = _call(markers_auto_generate, root)
        labels = _call(clips_label, root)
        if markers.get("total_markers", 0) == 0 or labels.get("label_count", 0) == 0:
            raise ValueError("No useful markers or clip labels found; add transcripts and review markers.")
        result = _call(timeline_build_selects, root)
        if result.get("selects_count", 0) == 0:
            raise ValueError("No selects meet the confidence threshold; review markers first.")
        return result
    if stage == "assembly":
        if state.get("explicit_project"):
            chosen = Path(state["project_file"])
            if not chosen.is_file() or _hash(chosen) != state["project_hash"]:
                raise ValueError("Pinned project changed; explicitly select the new version to continue.")
            return {"kdenlive_path": str(chosen), "selection_reason": "User selected this working copy."}
        from workshop_video_brain.edit_mcp.pipelines.assembly import build_assembly_plan, assemble_timeline, _load_script_steps_from_reports
        if not _load_script_steps_from_reports(root):
            raise ValueError("Add reports/script.json with a non-empty steps list before assembly.")
        plan = build_assembly_plan(root)
        if not plan.steps or any(not any(c.role == "primary" for c in step.clips) for step in plan.steps):
            raise ValueError("Every script step needs a primary clip match; improve script descriptions or clip labels.")
        for step in plan.steps:
            for clip in step.clips:
                source = Path(clip.source_path)
                # Existing labeler records its transcript JSON as source_path.
                # Resolve only a unique corresponding recording; never put JSON in a timeline.
                if source.suffix.lower() == ".json" or not clip.source_path:
                    from workshop_video_brain.core.utils.paths import safe_filename
                    matches = [p for p in (root / "media/raw").rglob("*") if p.is_file() and safe_filename(p.stem) == clip.clip_ref]
                    if len(matches) != 1:
                        raise ValueError(f"Clip {clip.clip_ref} needs a unique source recording in media/raw/.")
                    source = matches[0]
                if not source.is_absolute():
                    source = root / source
                if not source.is_file() or clip.out_seconds <= clip.in_seconds:
                    raise ValueError(f"Restore source and duration for clip {clip.clip_ref}.")
                clip.source_path = source.as_posix()
        path = assemble_timeline(root, plan)
        state.update(project_file=str(path.resolve()), project_hash=_hash(path))
        return {"kdenlive_path": str(path), "selection_explanations": plan.model_dump(mode="json"), "assembly_report": plan.assembly_report}
    chosen = Path(state.get("project_file", ""))
    if not chosen.is_file() or _hash(chosen) != state.get("project_hash"):
        raise ValueError("Pinned assembly version changed; select a working copy explicitly before continuing.")
    if stage == "preview":
        from workshop_video_brain.edit_mcp.pipelines.render_pipeline import run_render
        def on_job(job) -> None:
            if callback:
                callback("preview", 0, 1, pending_output=job.output_path, render_job_id=str(job.id))
        job = run_render(root, chosen, "preview", on_job=on_job)
        if str(job.status) != "succeeded":
            raise ValueError(job.error_message or f"Preview failed: {job.status}; read {job.log_path}")
        artifact = Path(job.output_path)
        if not artifact.is_file() or not artifact.stat().st_size:
            raise ValueError("Preview render returned no usable artifact.")
        if callback:
            callback("preview", 1, 1, completed_output=str(artifact))
        return {"output_path": str(artifact), "artifact_signature": _artifact_signature(artifact), "job_id": str(job.id)}
    preview = state["stages"].get("preview", {}).get("output_path")
    if not preview or not Path(preview).is_file():
        raise ValueError("Render a preview before preparing review.")
    path = root / "reports/workflow_review.md"
    atomic_write_text(path, f"# First-cut review\n\nProject: {chosen}\n\nPreview: {preview}\n\n- [ ] Watch the full preview.\n- [ ] Check clip choices against reports/assembly_plan.json.\n- [ ] Check audio, cuts, titles, and missing media.\n- [ ] Record changes before final rendering.\n\nEditorial approval is pending.\n", workspace_root=root)
    return {"review_path": str(path), "artifact_hash": _hash(path), "editorial_approval": "pending"}
