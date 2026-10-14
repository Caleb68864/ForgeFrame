"""Discovery stays offline even with optional engines absent."""
import json
import subprocess

import click
from click.testing import CliRunner

from workshop_video_brain.app import doctor
from workshop_video_brain.app.capabilities import capability_catalog, catalog_markdown
from workshop_video_brain.app.discovery_cli import register_commands


def test_doctor_absent_binaries_models_and_engines(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor.shutil, 'which', lambda name: None)
    monkeypatch.setattr(doctor.importlib.util, 'find_spec', lambda name: None)
    monkeypatch.setenv('HF_HUB_CACHE', str(tmp_path / 'hf'))
    monkeypatch.setenv('U2NET_HOME', str(tmp_path / 'mask'))
    def forbidden(*args, **kwargs):
        raise AssertionError('must not spawn missing binaries')
    monkeypatch.setattr(doctor.subprocess, 'run', forbidden)
    report = doctor.environment_report()
    assert not any(report['features'].values())
    assert not any(report['optional_engines'].values())
    assert report['model_cache']['whisper'] == []


def test_doctor_probe_timeout_is_reported(monkeypatch):
    monkeypatch.setattr(doctor.shutil, 'which', lambda name: '/bin/tool')
    def timeout(*args, **kwargs):
        assert kwargs['timeout'] == 10
        raise subprocess.TimeoutExpired(args[0], 10)
    monkeypatch.setattr(doctor.subprocess, 'run', timeout)
    assert doctor._probe('tool', ['--version'])['available'] is False


def test_cached_model_requires_complete_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, '_probe', lambda *args: {'available': True})
    monkeypatch.setattr(doctor.importlib.util, 'find_spec', lambda name: object())
    monkeypatch.setenv('HF_HUB_CACHE', str(tmp_path))
    monkeypatch.setenv('U2NET_HOME', str(tmp_path / 'mask'))
    monkeypatch.setenv('WVB_WHISPER_MODEL', 'small')
    snapshot = tmp_path / 'models--Systran--faster-whisper-small/snapshots/version'
    snapshot.mkdir(parents=True)
    (snapshot / 'model.bin').write_bytes(b'data')
    assert doctor.environment_report()['features']['transcription_offline'] is False
    for name in ('config.json', 'tokenizer.json'):
        (snapshot / name).write_text('{}')
    assert doctor.environment_report()['features']['transcription_offline'] is True


def test_cli_json_reports_missing_dependencies(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, 'environment_report', lambda: {'features': {'render': False}})
    group = click.Group()
    register_commands(group)
    result = CliRunner().invoke(group, ['doctor', '--json'])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {'features': {'render': False}}


def test_catalog_counts_names_and_markdown_match():
    catalog = capability_catalog()
    assert catalog['tool_count'] == len(catalog['tools']) > 0
    assert catalog['skill_count'] == len(catalog['skills']) > 0
    names = [item['name'] for item in catalog['tools']]
    assert len(names) == len(set(names))
    assert {'forgeframe_doctor', 'project_status'} <= set(names)
    assert all(item['name'].startswith('ff-') for item in catalog['skills'])
    markdown = catalog_markdown()
    assert f"{catalog['tool_count']} MCP tools; {catalog['skill_count']} skills." in markdown
    assert all(f"| {name} |" in markdown for name in names)


def test_local_model_empty_files_are_not_offline_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, '_probe', lambda *args: {'available': True})
    monkeypatch.setattr(doctor.importlib.util, 'find_spec', lambda name: object())
    monkeypatch.setenv('WVB_WHISPER_MODEL', str(tmp_path))
    monkeypatch.setenv('HF_HUB_CACHE', str(tmp_path / 'hf'))
    monkeypatch.setenv('U2NET_HOME', str(tmp_path / 'mask'))
    for name in ('model.bin', 'config.json', 'tokenizer.json'):
        (tmp_path / name).touch()
    assert doctor.environment_report()['features']['transcription_offline'] is False
