"""Bounded, offline environment diagnostics. Never initialize/download models."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess


def _probe(binary: str, arguments: list[str]) -> dict:
    executable = shutil.which(binary)
    if not executable:
        return {'available': False, 'path': None, 'error': 'not found on PATH'}
    try:
        result = subprocess.run([executable, *arguments], capture_output=True, text=True,
                                timeout=10, env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'})
        return {'available': result.returncode == 0, 'path': executable,
                'returncode': result.returncode, 'output': (result.stdout + result.stderr)[-65536:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'available': False, 'path': executable, 'error': str(exc)}


def environment_report() -> dict:
    binaries = {name: _probe(name, ['-version'] if name in ('ffmpeg', 'ffprobe') else ['--version'])
                for name in ('ffmpeg', 'ffprobe', 'melt', 'tesseract')}
    encoders = _probe('ffmpeg', ['-hide_banner', '-encoders'])
    effects = _probe('melt', ['-query', 'filters'])
    optional = {name: importlib.util.find_spec(module) is not None for name, module in
                {'transcription': 'faster_whisper', 'research': 'numpy', 'images': 'PIL',
                 'ocr': 'pytesseract', 'ai_mask': 'rembg', 'onnx': 'onnxruntime',
                 'ai_mask_heavy': 'ultralytics', 'motion_track': 'cv2'}.items()}
    hf_cache = Path(os.environ.get('HF_HUB_CACHE',
                    str(Path(os.environ.get('HF_HOME', str(Path.home() / '.cache/huggingface'))) / 'hub')))
    whisper_models = []
    selected_model = os.environ.get('WVB_WHISPER_MODEL', 'small')
    if hf_cache.is_dir():
        for model in sorted(hf_cache.glob('models--*whisper*')):
            if any(all((snapshot / name).is_file() and (snapshot / name).stat().st_size > 0
                       for name in ('model.bin', 'config.json', 'tokenizer.json'))
                   for snapshot in (model / 'snapshots').glob('*')):
                whisper_models.append(model.name)
    selected_cached = any(name.endswith('--faster-whisper-' + selected_model) for name in whisper_models)
    selected_path = Path(selected_model)
    if selected_path.is_dir():
        selected_cached = all((selected_path / name).is_file()
                              and (selected_path / name).stat().st_size > 0
                              for name in ('model.bin', 'config.json', 'tokenizer.json'))
    mask_cache = Path(os.environ.get('U2NET_HOME', str(Path.home() / '.u2net')))
    mask_models = [p.name for p in sorted(mask_cache.glob('*.onnx')) if p.stat().st_size > 0]
    ffmpeg = binaries['ffmpeg']['available'] and binaries['ffprobe']['available']
    return {'binaries': binaries, 'encoders': encoders, 'mlt_effects': effects,
            'optional_engines': optional,
            'model_cache': {'whisper': whisper_models, 'rembg': mask_models,
                            'selected_whisper_model': selected_model, 'selected_whisper_cached': selected_cached,
                            'note': 'Cached files only; no model is loaded or downloaded.'},
            'features': {'media_processing': ffmpeg,
                         'timeline_render': ffmpeg and binaries['melt']['available'],
                         'transcription_engine': ffmpeg and optional['transcription'],
                         'transcription_offline': ffmpeg and optional['transcription'] and selected_cached,
                         'ai_mask_engine': ffmpeg and optional['ai_mask'] and optional['onnx'],
                         'ai_mask_offline': ffmpeg and optional['ai_mask'] and optional['onnx'] and bool(mask_models),
                         'motion_track_python': ffmpeg and optional['motion_track'],
                         'ocr': optional['ocr'] and binaries['tesseract']['available']},
            'suggestions': {
                'binaries': 'Install missing FFmpeg/ffprobe and MLT melt binaries and expose them on PATH.',
                'optional_engines': 'Use uv sync --extra research / ai-mask / ai-mask-heavy / motion-track as needed.',
                'transcription': 'Install faster-whisper and cache the WVB_WHISPER_MODEL model before offline use.',
            }}
