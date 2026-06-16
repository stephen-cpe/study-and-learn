"""
TTS audio generation service using edge-tts.

Converts narration script entries to MP3 files, one per slide.
Files stored under data/tts/<study_path_id>/<module_index>/
Manifest JSON stored at data/tts/<study_path_id>/<module_index>/manifest.json

IMPORTANT: custom SSML is NOT supported by edge-tts >= 5.0.0.
All text passed to Communicate() must be plain text only.
"""
import asyncio
import json
import logging
import shutil
from pathlib import Path

import edge_tts

logger = logging.getLogger(__name__)
TTS_DIR = Path(__file__).resolve().parents[2] / 'data' / 'tts'

SPEAKER_VOICES = {
    'Ava':    'en-US-AvaNeural',
    'Emma':   'en-US-EmmaNeural',
    'Ryan':   'en-GB-RyanNeural',
    'Andrew': 'en-US-AndrewNeural',
}
DEFAULT_VOICE = 'en-US-AvaNeural'


def _get_voice(speaker: str) -> str:
    return SPEAKER_VOICES.get(speaker, DEFAULT_VOICE)


async def _generate_mp3(text: str, voice: str, out_path: Path) -> None:
    """Generate a single MP3. text must be plain text (no SSML)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_path))


def generate_lesson_audio(
    path_id: str,
    module_index: int,
    narration_script: list,
    speaker: str,
) -> dict:
    """
    Generate MP3 files for each entry in narration_script.
    narration_script: list of {slide_index: int, text: str}
    Returns manifest dict. Raises RuntimeError on failure.
    """
    voice = _get_voice(speaker)
    module_dir = TTS_DIR / path_id / str(module_index)
    module_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        'path_id': path_id,
        'module_index': module_index,
        'speaker': speaker,
        'voice': voice,
        'slides': {}
    }
    loop = asyncio.new_event_loop()
    try:
        for entry in narration_script:
            si = entry['slide_index']
            text = entry.get('text', '').strip()
            if not text:
                continue
            fname = f"slide_{si + 1}.mp3"
            out_path = module_dir / fname
            loop.run_until_complete(_generate_mp3(text, voice, out_path))
            manifest['slides'][str(si)] = str(out_path.relative_to(TTS_DIR))
    finally:
        loop.close()
    manifest_path = module_dir / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest


def get_audio_manifest(path_id: str, module_index: int) -> dict | None:
    manifest_path = TTS_DIR / path_id / str(module_index) / 'manifest.json'
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text())
        except Exception:
            return None
    return None


def delete_lesson_audio(path_id: str) -> None:
    """Delete all TTS audio for a study path (call on cancel/complete/delete)."""
    path_dir = TTS_DIR / path_id
    if path_dir.exists():
        shutil.rmtree(path_dir, ignore_errors=True)


def delete_module_audio(path_id: str, module_index: int) -> None:
    """Delete TTS audio for one module (call on retake)."""
    module_dir = TTS_DIR / path_id / str(module_index)
    if module_dir.exists():
        shutil.rmtree(module_dir, ignore_errors=True)
