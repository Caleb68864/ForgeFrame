"""Exercise real detached workers and persisted lifecycle without model downloads."""
import os
import time

import pytest

from workshop_video_brain.workspace import jobs

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Detached jobs require POSIX')


def wait_terminal(root, identifier):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        record = jobs.get_job(root, identifier)
        if record['status'] not in jobs.ACTIVE:
            return record
        time.sleep(0.05)
    jobs.cancel_job(root, identifier)
    pytest.fail('Detached worker did not finish within 15 seconds')


def test_real_detached_worker_persists_success(tmp_path):
    (tmp_path / 'workspace.yaml').write_text('name: detached-test\n')
    (tmp_path / 'media/raw').mkdir(parents=True)
    submitted = jobs.submit_job(tmp_path, 'proxy')
    completed = wait_terminal(tmp_path, submitted['id'])
    assert completed['status'] == 'succeeded', completed['error']
    assert completed['result'] == {'proxied': 0, 'scanned': 0}
    assert completed['progress']['stage'] == 'complete'
    assert jobs.list_jobs(tmp_path, reconcile=False)[0]['result'] == completed['result']
    assert completed['outputs'] == []


def test_real_failed_workflow_can_be_retried(tmp_path):
    (tmp_path / 'workspace.yaml').write_text('name: detached-test\n')
    submitted = jobs.submit_job(tmp_path, 'workflow', {'through': 'footage'})
    failed = wait_terminal(tmp_path, submitted['id'])
    assert failed['status'] == 'failed'
    assert 'Copy recordings' in failed['error']
    # Terminal state is committed before the worker interpreter exits.
    deadline = time.monotonic() + 5
    while jobs._group_alive(failed['pid']) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not jobs._group_alive(failed['pid'])
    retried = jobs.retry_job(tmp_path, failed['id'])
    assert retried['id'] != failed['id']
    again = wait_terminal(tmp_path, retried['id'])
    assert again['status'] == 'failed'
    assert len(jobs.list_jobs(tmp_path, reconcile=False)) == 2
