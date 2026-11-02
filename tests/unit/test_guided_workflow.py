"""Resumption, version pinning, prerequisite failures and read-only readiness."""
import json
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.pipelines import guided_workflow as workflow


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / 'workspace.yaml').write_text('name: tests\n')
    return tmp_path


def test_status_creates_no_files(workspace):
    before = sorted(workspace.rglob('*'))
    status = workflow.project_status(workspace)
    assert status['next_action'] == 'Copy recordings into media/raw/.'
    assert not any(status['readiness'].values())
    assert sorted(workspace.rglob('*')) == before


def test_wrong_stage_rejected_before_state_write(workspace):
    with pytest.raises(ValueError, match='through must'):
        workflow.run_workflow(workspace, through='publish')
    assert not (workspace / 'reports').exists()


def test_failure_persists_and_resume_skips_completed_stage(workspace, monkeypatch):
    calls = []
    fail = True
    def execute(root, stage, state, callback):
        calls.append(stage)
        if stage == 'selects' and fail:
            raise ValueError('missing transcript')
        return {'count': 1}
    monkeypatch.setattr(workflow, '_execute', execute)
    with pytest.raises(ValueError, match='missing transcript'):
        workflow.run_workflow(workspace, through='selects')
    saved = json.loads((workspace / 'reports/workflow_state.json').read_text())
    assert saved['stages']['footage']['status'] == 'completed'
    assert saved['stages']['selects']['status'] == 'failed'
    fail = False
    workflow.run_workflow(workspace, through='selects')
    assert calls == ['footage', 'selects', 'selects']
    (workspace / 'workspace.yaml').write_text('name: changed\n')
    workflow.run_workflow(workspace, through='selects')
    assert calls[-2:] == ['footage', 'selects']


def test_empty_footage_fails_with_actionable_error(workspace):
    with pytest.raises(ValueError, match='Copy recordings'):
        workflow.run_workflow(workspace, through='footage')
    state = json.loads((workspace / 'reports/workflow_state.json').read_text())
    assert state['stages']['footage']['status'] == 'failed'


def test_explicit_project_must_be_working_copy(workspace):
    external = workspace / 'foreign.kdenlive'
    external.write_text('<mlt/>')
    with pytest.raises(ValueError, match='working_copies'):
        workflow.run_workflow(workspace, project_file=str(external))


def test_changed_explicit_project_requires_reselection(workspace):
    project = workspace / 'projects/working_copies/cut.kdenlive'
    project.parent.mkdir(parents=True)
    project.write_text('<mlt/>')
    state = {'explicit_project': True, 'project_file': str(project), 'project_hash': workflow._hash(project)}
    project.write_text('<mlt changed="yes"/>')
    with pytest.raises(ValueError, match='Pinned project changed'):
        workflow._execute(workspace, 'assembly', state)


def test_preview_and_review_artifact_changes_invalidate_status(workspace, monkeypatch):
    monkeypatch.setattr(workflow, '_fingerprint', lambda root, stage: 'stable')
    project = workspace / 'projects/working_copies/cut.kdenlive'
    project.parent.mkdir(parents=True)
    project.write_text('<mlt/>')
    preview = workspace / 'renders/preview.mp4'
    preview.parent.mkdir()
    preview.write_bytes(b'video')
    review = workspace / 'reports/workflow_review.md'
    review.parent.mkdir()
    review.write_text('review')
    state = {'project_file': str(project), 'project_hash': workflow._hash(project), 'stages': {
        stage: {'status': 'completed', 'fingerprint': 'stable'} for stage in workflow.STAGES}}
    state['stages']['preview'].update(output_path=str(preview), artifact_signature=workflow._artifact_signature(preview))
    state['stages']['review'].update(review_path=str(review), artifact_hash=workflow._hash(review))
    (workspace / 'reports/workflow_state.json').write_text(json.dumps(state))
    assert workflow.project_status(workspace)['readiness']['review']
    review.write_text('edited review')
    assert not workflow.project_status(workspace)['readiness']['review']
    assert workflow.project_status(workspace)['readiness']['preview']
    preview.unlink()
    assert not workflow.project_status(workspace)['readiness']['preview']
    project.write_text('<mlt changed="yes"/>')
    assert not workflow.project_status(workspace)['version_valid']
