"""Persistent, detached workspace operations with explicit recovery.

Workers run in separate POSIX sessions: closing the MCP connection does not
stop them. SQLite serializes state updates and allows one active writer per
workspace. Interrupted work is retried explicitly, never silently replayed.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

OPERATIONS = {
    "render": {"profile", "project_file", "mode"},
    "proxy": set(),
    "transcribe": set(),
    "workflow": {"through", "project_file"},
}
ACTIVE = {"queued", "running", "cancelling"}


def _root(root: str | Path) -> Path:
    path = Path(root).resolve()
    if not (path / "workspace.yaml").is_file():
        raise ValueError("Expected a workspace directory containing workspace.yaml")
    return path


@contextmanager
def _db(root: Path):
    directory = root / "jobs"
    from workshop_video_brain.core.utils.paths import assert_not_protected
    assert_not_protected(directory.resolve(), "job storage")
    directory.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(directory / "jobs.sqlite3", timeout=15)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def _save(connection, record: dict) -> None:
    connection.execute("INSERT OR REPLACE INTO jobs VALUES (?, ?)",
                       (record["id"], json.dumps(record, default=str)))


def _read(connection, job_id: str) -> dict:
    UUID(job_id)
    row = connection.execute("SELECT record FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise FileNotFoundError(f"Unknown job: {job_id}")
    return json.loads(row[0])


def _update(root: Path, job_id: str, **changes) -> dict:
    with _db(root) as connection:
        record = _read(connection, job_id)
        record.update(changes, updated_at=time.time())
        _save(connection, record)
    return record


def _worker_alive(record: dict) -> bool:
    pid = record.get("pid")
    if not pid:
        return time.time() - record["created_at"] < 30
    try:
        proc = Path(f"/proc/{pid}")
        if proc.exists():
            command = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            state = (proc / "stat").read_text().rsplit(")", 1)[1].split()[0]
            if state == "Z":
                return False
        else:
            result = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                                    capture_output=True, text=True, timeout=5)
            command = result.stdout
        return "workshop_video_brain.workspace.jobs" in command and record["id"] in command
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return False


def _reconcile(record: dict) -> dict:
    if record["status"] in ACTIVE and not _worker_alive(record):
        record.update(status="cancelled" if record["status"] == "cancelling" else "interrupted",
                      completed_at=time.time(), updated_at=time.time(),
                      error="Worker stopped. Inspect the log and retry explicitly.")
    return record


def list_jobs(root: str | Path, *, reconcile: bool = True) -> list[dict]:
    root = _root(root)
    if not (root / "jobs" / "jobs.sqlite3").exists():
        return []
    if not reconcile:
        connection = sqlite3.connect((root / 'jobs' / 'jobs.sqlite3').as_uri() + '?mode=ro', uri=True)
        try:
            return sorted((json.loads(row[0]) for row in connection.execute("SELECT record FROM jobs")),
                          key=lambda r: r["created_at"], reverse=True)
        finally:
            connection.close()
    with _db(root) as connection:
        records = [_reconcile(json.loads(row[0])) for row in connection.execute("SELECT record FROM jobs")]
        for record in records:
            _save(connection, record)
    return sorted(records, key=lambda r: r["created_at"], reverse=True)


def get_job(root: str | Path, job_id: str) -> dict:
    root = _root(root)
    with _db(root) as connection:
        record = _reconcile(_read(connection, job_id))
        _save(connection, record)
    return record


def submit_job(root: str | Path, operation: str, parameters: dict | None = None) -> dict:
    from workshop_video_brain.workspace.safe_write import locked_path
    root = _root(root)
    with locked_path(root / "jobs" / "submission"):
        return _submit_job(root, operation, parameters)


def _submit_job(root: Path, operation: str, parameters: dict | None) -> dict:
    if os.name != "posix":
        raise RuntimeError("Detached jobs currently require Linux or macOS; synchronous tools remain available.")
    root = _root(root)
    if operation not in OPERATIONS:
        raise ValueError(f"Unknown operation. Choose from: {', '.join(OPERATIONS)}")
    parameters = dict(parameters or {})
    unknown = parameters.keys() - OPERATIONS[operation]
    if unknown:
        raise ValueError(f"Unsupported parameters: {', '.join(sorted(unknown))}")
    if any(not isinstance(value, str) for value in parameters.values()):
        raise ValueError("Job parameters must be strings")
    if operation == "render":
        from workshop_video_brain.edit_mcp.adapters.render.profiles import load_profile
        load_profile(parameters.get("profile", "preview"))
        if parameters.get("mode", "standard") not in {"standard", "proxy", "final"}:
            raise ValueError("Render mode must be standard, proxy, or final")
    if operation == "workflow" and parameters.get("through", "review") not in {
        "footage", "selects", "assembly", "preview", "review"
    }:
        raise ValueError("Unknown workflow stage")
    if operation == "render" or parameters.get("project_file"):
        from workshop_video_brain.edit_mcp.server.tools_helpers._projects import latest_project
        explicit = parameters.get("project_file")
        project = Path(explicit) if explicit else latest_project((root / "projects" / "working_copies").glob("*.kdenlive"))
        if project is None:
            raise FileNotFoundError("No working project available to render")
        if not project.is_absolute():
            project = root / project
        if not project.is_file():
            raise FileNotFoundError(str(project))
        parameters["project_file"] = str(project.resolve())
        parameters["source_sha256"] = hashlib.sha256(project.read_bytes()).hexdigest()
    job_id = str(uuid4())
    log_path = root / "jobs" / f"{job_id}.log"
    record = dict(id=job_id, operation=operation, parameters=parameters,
                  status="queued", created_at=time.time(), updated_at=time.time(),
                  pid=None, progress={"stage": "queued", "completed": 0, "total": 1},
                  log_path=str(log_path), outputs=[], result=None, error="")
    with _db(root) as connection:
        for row in connection.execute("SELECT record FROM jobs").fetchall():
            old = _reconcile(json.loads(row[0]))
            _save(connection, old)
            if old["status"] in ACTIVE:
                raise ValueError(f"Workspace already has an active job: {old['id']}")
            if old["status"] == "interrupted" and _group_alive(old.get("pid")):
                raise ValueError(f"Interrupted job {old['id']} still has live child processes; wait for them before submitting work")
        _save(connection, record)
    env = os.environ.copy()
    source_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (source_root, env.get("PYTHONPATH"))))
    try:
        with log_path.open("ab") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "workshop_video_brain.workspace.jobs", "worker", str(root), job_id],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True, env=env,
            )
        _update(root, job_id, pid=process.pid)
    except Exception as exc:
        _update(root, job_id, status="failed", error=str(exc), completed_at=time.time())
        raise
    return get_job(root, job_id)


def cancel_job(root: str | Path, job_id: str) -> dict:
    root = _root(root)
    with _db(root) as connection:
        record = _reconcile(_read(connection, job_id))
        if record["status"] in ACTIVE:
            record.update(status="cancelling", updated_at=time.time())
        _save(connection, record)
    if record["status"] != "cancelling":
        return record
    pid = record.get("pid")
    if pid and _worker_alive(record):
        # Verify this is a detached worker's session before signalling children.
        try:
            if os.getpgid(pid) != pid:
                raise RuntimeError("Worker process group changed; refusing to signal it")
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    return get_job(root, job_id)


def _group_alive(pid: int | None) -> bool:
    if not pid or os.name != "posix":
        return False
    processes = subprocess.run(["ps", "-eo", "pgid=,stat="], capture_output=True,
                               text=True, check=True, timeout=5)
    return any(len(fields := line.split()) == 2 and fields[0] == str(pid)
               and not fields[1].startswith("Z") for line in processes.stdout.splitlines())


def retry_job(root: str | Path, job_id: str) -> dict:
    from workshop_video_brain.workspace.safe_write import locked_path
    root = _root(root)
    with locked_path(root / "jobs" / "submission"):
        return _retry_job(root, job_id)


def _retry_job(root: Path, job_id: str) -> dict:
    root = _root(root)
    record = get_job(root, job_id)
    if record["status"] in ACTIVE or record["status"] == "succeeded":
        raise ValueError("Only failed, cancelled, or interrupted jobs can be retried")
    if any(job["status"] in ACTIVE for job in list_jobs(root)):
        raise ValueError("Wait for the active workspace job before cleaning and retrying artifacts")
    # A killed Python worker can leave FFmpeg/MLT children running in its
    # detached process group. Do not reuse their outputs while they are live.
    pid = record.get("pid")
    if _group_alive(pid):
        raise RuntimeError("The previous worker process group is still alive; wait for its children to exit before retrying")
    from workshop_video_brain.core.utils.paths import assert_not_protected
    cleanup_paths = []
    for output in record.get("outputs", []):
        path = assert_not_protected(output).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Refusing to clean a pending output outside the workspace")
        relative = path.relative_to(root)
        if not any(relative.is_relative_to(Path(directory)) for directory in (
            "renders", "media/proxies", "media/derived_audio", "transcripts", "markers",
        )):
            raise ValueError(f"Refusing to clean a pending output outside derived artifact directories: {path}")
        cleanup_paths.append(path)
    # Preflight the full set before removing any artifacts.
    for path in cleanup_paths:
        path.unlink(missing_ok=True)
    _update(root, job_id, outputs=[])
    params = {k: v for k, v in record["parameters"].items() if k in OPERATIONS[record["operation"]]}
    return submit_job(root, record["operation"], params)


class _Cancelled(BaseException):
    pass


def _run_worker(root: Path, job_id: str) -> None:
    def terminate(_signum, _frame):
        raise _Cancelled()

    signal.signal(signal.SIGTERM, terminate)
    with _db(root) as connection:
        record = _read(connection, job_id)
        if record["status"] == "cancelling":
            record.update(status="cancelled", completed_at=time.time())
        elif record["status"] == "queued":
            record.update(status="running", pid=os.getpid(), started_at=time.time())
        else:
            return
        record["updated_at"] = time.time()
        _save(connection, record)
    if record["status"] == "cancelled":
        return
    outputs: list[str] = []

    def progress(stage: str, completed: int = 0, total: int = 1, **details):
        if details.get("pending_output"):
            pending_output(Path(details["pending_output"]))
        if details.get("completed_output"):
            completed_output(Path(details["completed_output"]))
        if details.get("render_job_id"):
            _update(root, job_id, render_job_id=details["render_job_id"])
        _update(root, job_id, progress=dict(stage=stage, completed=completed, total=total, **details))
        print(f"{stage}: {completed}/{total} {details}", flush=True)

    def pending_output(path: Path):
        from workshop_video_brain.core.utils.paths import assert_not_protected
        path = assert_not_protected(path)
        if not path.is_relative_to(root):
            raise ValueError("Job output must remain inside its workspace")
        if str(path) not in outputs:
            outputs.append(str(path))
            _update(root, job_id, outputs=outputs)

    def completed_output(path: Path):
        path = path.resolve()
        if str(path) in outputs:
            outputs.remove(str(path))
            _update(root, job_id, outputs=outputs)

    try:
        params = record["parameters"]
        project = params.get("project_file")
        if project and params.get("source_sha256"):
            if hashlib.sha256(Path(project).read_bytes()).hexdigest() != params["source_sha256"]:
                raise ValueError("Pinned project changed after submission. Submit a new job.")
        operation = record["operation"]
        if operation == "render":
            from workshop_video_brain.edit_mcp.pipelines.render_pipeline import run_render
            progress("rendering")
            def on_job(job):
                pending_output(Path(job.output_path))
                _update(root, job_id, render_job_id=str(job.id))
            rendered = run_render(root, project, params.get("profile", "preview"),
                                  mode=params.get("mode", "standard"), on_job=on_job)
            if rendered.status != "succeeded":
                raise RuntimeError(rendered.error_message or f"Render failed; see {rendered.log_path}")
            result = rendered.model_dump(mode="json")
        elif operation == "proxy":
            from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import scan_directory
            from workshop_video_brain.edit_mcp.adapters.ffmpeg.proxy import ProxyPolicy, generate_proxy, needs_proxy, proxy_path_for
            assets = scan_directory(root / "media" / "raw")
            policy = ProxyPolicy()
            directory = root / "media" / "proxies"
            directory.mkdir(parents=True, exist_ok=True)
            count = 0
            for index, asset in enumerate(assets):
                progress("proxy", index, len(assets), source=asset.path)
                output = proxy_path_for(asset, directory)
                source = Path(asset.path)
                fresh = output.is_file() and output.stat().st_size > 0 and output.stat().st_mtime >= source.stat().st_mtime
                if needs_proxy(asset, policy) and not fresh:
                    pending_output(output)
                    if output.is_file() and output.stat().st_size == 0:
                        output.unlink()
                    generate_proxy(asset, directory, policy)
                    completed_output(output)
                    count += 1
            result = {"proxied": count, "scanned": len(assets)}
        elif operation == "transcribe":
            from workshop_video_brain.app.config import load_config
            from workshop_video_brain.edit_mcp.pipelines.ingest import run_ingest
            from workshop_video_brain.workspace.manager import WorkspaceManager
            from dataclasses import asdict
            from workshop_video_brain.edit_mcp.adapters.stt import whisper_engine
            config = load_config()
            if not config.ffmpeg_available or not whisper_engine.is_available():
                raise RuntimeError("Transcription needs FFmpeg and a Whisper backend. Run wvb doctor.")
            result = asdict(run_ingest(WorkspaceManager.open(root), config, progress=progress,
                                      pending_output=pending_output, completed_output=completed_output))
            if result["errors"]:
                raise RuntimeError("; ".join(result["errors"]))
        else:
            from workshop_video_brain.edit_mcp.pipelines.guided_workflow import run_workflow
            result = run_workflow(root, through=params.get("through", "review"),
                                  project_file=params.get("project_file", ""), callback=progress)
        progress("complete", 1, 1)
        _update(root, job_id, status="succeeded", completed_at=time.time(), result=result, outputs=[])
    except BaseException as exc:
        cancelled = isinstance(exc, _Cancelled)
        if not cancelled:
            traceback.print_exc()
        for output in outputs:
            try:
                Path(output).unlink(missing_ok=True)
            except OSError:
                pass
        current = get_job(root, job_id)
        if current.get("render_job_id"):
            try:
                from workshop_video_brain.edit_mcp.pipelines.render_pipeline import list_renders, register_render
                for render in list_renders(root):
                    if str(render.id) == current["render_job_id"] and render.status in {"queued", "running"}:
                        register_render(root, render.model_copy(update={
                            "status": "cancelled" if cancelled else "failed", "error_message": str(exc) or "Cancelled by user",
                        }))
            except Exception:
                traceback.print_exc()
        _update(root, job_id, status="cancelled" if cancelled else "failed",
                completed_at=time.time(), error="Cancelled by user" if cancelled else str(exc), outputs=[])


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "worker":
        raise SystemExit("Internal entry point: worker WORKSPACE JOB_ID")
    _run_worker(_root(sys.argv[2]), sys.argv[3])
