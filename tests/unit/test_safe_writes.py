"""Safety failures must leave the previous artifact and its history intact."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from workshop_video_brain.workspace.safe_write import atomic_write_text
from workshop_video_brain.workspace.snapshot import create, list_snapshots, restore
from workshop_video_brain.workspace.manifest import read_manifest, write_manifest


def test_validation_failure_cleans_stage_and_preserves_target(tmp_path):
    target = tmp_path / 'draft.txt'
    target.write_text('old')
    with pytest.raises(ValueError, match='Validation failed'):
        atomic_write_text(target, 'new', validator=lambda stage: False)
    assert target.read_text() == 'old'
    assert list(tmp_path.iterdir()) == [target]


def test_snapshot_failure_aborts_replacement(tmp_path, monkeypatch):
    target = tmp_path / 'draft.kdenlive'
    target.write_text('old')
    def fail(*args):
        raise OSError('snapshot disk full')
    monkeypatch.setattr('workshop_video_brain.workspace.snapshot.create', fail)
    with pytest.raises(OSError, match='disk full'):
        atomic_write_text(target, 'new', workspace_root=tmp_path)
    assert target.read_text() == 'old'
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('directory', ['media/raw', 'projects/source'])
def test_symlink_into_protected_tree_is_refused(tmp_path, directory):
    protected = tmp_path / directory
    protected.mkdir(parents=True)
    target = protected / 'original.txt'
    target.write_text('original')
    link = tmp_path / 'alias'
    link.symlink_to(protected, target_is_directory=True)
    with pytest.raises(ValueError, match='protected'):
        atomic_write_text(link / target.name, 'modified')
    assert target.read_text() == 'original'


def test_replace_failure_cleans_stage(tmp_path, monkeypatch):
    target = tmp_path / 'draft.txt'
    target.write_text('old')
    def fail(*args):
        raise OSError('replacement failed')
    monkeypatch.setattr('workshop_video_brain.workspace.safe_write.os.replace', fail)
    with pytest.raises(OSError, match='replacement failed'):
        atomic_write_text(target, 'new')
    assert target.read_text() == 'old'
    assert list(tmp_path.iterdir()) == [target]


def test_concurrent_project_writes_snapshot_every_previous_version(tmp_path):
    target = tmp_path / 'draft.kdenlive'
    target.write_text('initial')
    values = [f'version-{index}' for index in range(8)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda value: atomic_write_text(target, value, workspace_root=tmp_path), values))
    records = list_snapshots(tmp_path)
    history = [(tmp_path / 'projects/snapshots' / record.snapshot_id / target.name).read_text()
               for record in records]
    assert len(records) == len(values)
    assert set(history + [target.read_text()]) == set(values + ['initial'])


def test_restore_snapshots_displaced_revision(tmp_path):
    target = tmp_path / 'draft.kdenlive'
    target.write_text('first')
    saved = create(tmp_path, target)
    target.write_text('second')
    restore(tmp_path, saved.snapshot_id)
    assert target.read_text() == 'first'
    records = list_snapshots(tmp_path)
    assert len(records) == 2
    assert any((tmp_path / 'projects/snapshots' / record.snapshot_id / target.name).read_text() == 'second'
               for record in records)


def test_restore_rejects_traversal(tmp_path):
    with pytest.raises(ValueError, match='snapshot_id'):
        restore(tmp_path, '../escape')


def test_manifest_merge_preserves_extra_nested_settings(tmp_path):
    target = tmp_path / 'workspace.yaml'
    target.write_text(yaml.safe_dump({'project_title': 'Before', 'custom': {'flag': True},
                                     'keyframe_defaults': {'ease_family': 'sine', 'vendor': 42}}))
    manifest = read_manifest(tmp_path)
    manifest.project_title = 'After'
    write_manifest(tmp_path, manifest)
    persisted = yaml.safe_load(target.read_text())
    assert persisted['project_title'] == 'After'
    assert persisted['custom'] == {'flag': True}
    assert persisted['keyframe_defaults'] == {'ease_family': 'sine', 'vendor': 42}
