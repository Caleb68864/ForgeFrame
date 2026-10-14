"""Persistence, recovery, cancellation and artifact boundaries for detached jobs."""
import time
from uuid import uuid4

import pytest

from workshop_video_brain.workspace import jobs


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / 'workspace.yaml').write_text('name: tests\n')
    return tmp_path


def record(workspace, **changes):
    result = dict(id=str(uuid4()), operation='proxy', parameters={}, status='failed',
                  created_at=time.time() - 60, updated_at=time.time(), pid=None,
                  outputs=[], error='', progress={})
    result.update(changes)
    with jobs._db(workspace) as connection:
        jobs._save(connection, result)
    return result


def test_records_survive_independent_connections(workspace):
    saved = record(workspace, result={'proxied': 4})
    assert jobs.get_job(workspace, saved['id'])['result'] == {'proxied': 4}
    assert jobs.list_jobs(workspace)[0]['id'] == saved['id']


@pytest.mark.parametrize('original, expected', [('queued', 'interrupted'), ('running', 'interrupted'), ('cancelling', 'cancelled')])
def test_dead_workers_reconcile_persistently(workspace, monkeypatch, original, expected):
    saved = record(workspace, status=original)
    monkeypatch.setattr(jobs, '_worker_alive', lambda r: False)
    assert jobs.get_job(workspace, saved['id'])['status'] == expected
    assert jobs.list_jobs(workspace, reconcile=False)[0]['status'] == expected


def test_read_only_listing_does_not_reconcile(workspace, monkeypatch):
    record(workspace, status='running')
    monkeypatch.setattr(jobs, '_worker_alive', lambda r: False)
    before = (workspace / 'jobs/jobs.sqlite3').read_bytes()
    assert jobs.list_jobs(workspace, reconcile=False)[0]['status'] == 'running'
    assert (workspace / 'jobs/jobs.sqlite3').read_bytes() == before


def test_cancel_refuses_unexpected_process_group(workspace, monkeypatch):
    saved = record(workspace, status='running', pid=1234)
    monkeypatch.setattr(jobs, '_worker_alive', lambda r: True)
    monkeypatch.setattr(jobs.os, 'getpgid', lambda pid: 4321)
    called = []
    monkeypatch.setattr(jobs.os, 'killpg', lambda *args: called.append(args))
    with pytest.raises(RuntimeError, match='refusing to signal'):
        jobs.cancel_job(workspace, saved['id'])
    assert called == []


@pytest.mark.parametrize('location', ['outside', 'media/raw/clip.mp4', 'projects/source/source.kdenlive', 'reports/report.json'])
def test_retry_never_deletes_unapproved_outputs(workspace, monkeypatch, location):
    output = workspace.parent / 'outside' if location == 'outside' else workspace / location
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('keep')
    saved = record(workspace, outputs=[str(output)])
    monkeypatch.setattr(jobs, '_group_alive', lambda pid: False)
    with pytest.raises((ValueError, PermissionError)):
        jobs.retry_job(workspace, saved['id'])
    assert output.read_text() == 'keep'


def test_retry_blocks_live_orphans_before_cleanup(workspace, monkeypatch):
    output = workspace / 'renders/partial.mp4'
    output.parent.mkdir()
    output.write_text('partial')
    saved = record(workspace, outputs=[str(output)], pid=1234)
    monkeypatch.setattr(jobs, '_group_alive', lambda pid: True)
    with pytest.raises(RuntimeError, match='still alive'):
        jobs.retry_job(workspace, saved['id'])
    assert output.exists()


def test_retry_cleans_partial_derived_output(workspace, monkeypatch):
    output = workspace / 'renders/partial.mp4'
    output.parent.mkdir()
    output.write_text('partial')
    saved = record(workspace, outputs=[str(output)])
    monkeypatch.setattr(jobs, '_group_alive', lambda pid: False)
    monkeypatch.setattr(jobs, 'submit_job', lambda root, operation, parameters: {'status': 'queued'})
    assert jobs.retry_job(workspace, saved['id'])['status'] == 'queued'
    assert not output.exists()
    assert jobs.get_job(workspace, saved['id'])['outputs'] == []


def test_retry_validates_all_outputs_before_deleting_any(workspace, monkeypatch):
    partial = workspace / 'renders/partial.mp4'
    partial.parent.mkdir()
    partial.write_text('partial')
    invalid = workspace / 'reports/keep.json'
    invalid.parent.mkdir()
    invalid.write_text('keep')
    saved = record(workspace, outputs=[str(partial), str(invalid)])
    monkeypatch.setattr(jobs, '_group_alive', lambda pid: False)
    with pytest.raises(ValueError):
        jobs.retry_job(workspace, saved['id'])
    assert partial.exists(), 'Rejected retry must leave earlier outputs untouched'
    assert invalid.exists()


def test_worker_cancellation_cleans_pending_render(workspace, monkeypatch):
    from types import SimpleNamespace
    from workshop_video_brain.edit_mcp.pipelines import render_pipeline
    output = workspace / 'renders/partial.mp4'
    output.parent.mkdir()
    output.write_text('partial')
    saved = record(workspace, status='queued', operation='render')
    monkeypatch.setattr(jobs.signal, 'signal', lambda *args: None)
    def cancelled_render(*args, on_job, **kwargs):
        on_job(SimpleNamespace(output_path=str(output), id=uuid4()))
        raise jobs._Cancelled()
    monkeypatch.setattr(render_pipeline, 'run_render', cancelled_render)
    monkeypatch.setattr(render_pipeline, 'list_renders', lambda root: [])
    jobs._run_worker(workspace, saved['id'])
    finished = jobs.get_job(workspace, saved['id'])
    assert finished['status'] == 'cancelled'
    assert finished['outputs'] == []
    assert not output.exists()


def test_worker_rejects_project_changed_after_submission(workspace, monkeypatch):
    import hashlib
    project = workspace / 'cut.kdenlive'
    project.write_text('original')
    saved = record(workspace, status='queued', operation='render', parameters={
        'project_file': str(project), 'source_sha256': hashlib.sha256(project.read_bytes()).hexdigest()})
    project.write_text('changed')
    monkeypatch.setattr(jobs.signal, 'signal', lambda *args: None)
    jobs._run_worker(workspace, saved['id'])
    finished = jobs.get_job(workspace, saved['id'])
    assert finished['status'] == 'failed'
    assert 'Pinned project changed' in finished['error']
