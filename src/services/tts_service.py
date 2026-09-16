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
import re
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

# On-demand announcement clips (Stage 2) live outside per-module
# manifests: data/tts/announcements/<user_id>/<sha>.mp3
ANNOUNCE_DIR = TTS_DIR / 'announcements'


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
        # Drain lingering async generators (aiohttp SSL sockets) before
        # closing the loop. Without this, file descriptors leak on each
        # module's TTS generation, eventually causing
        # OSError: [Errno 24] Too many open files in production.
        loop.run_until_complete(loop.shutdown_asyncgens())
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


def generate_announcement_audio(user_id: str, text: str, speaker: str) -> dict:
    """Generate (or reuse) a short on-demand announcement MP3.

    Cache key is sha1(text+speaker) per user, so repeat plays skip
    edge-tts. Returns {'ann_id', 'rel_path', 'from_cache', 'text'}.
    Raises on synthesis failure (caller maps to 202/500).
    """
    import asyncio as _asyncio
    import hashlib as _hashlib

    clean = (text or '').strip()
    if not clean:
        raise ValueError("empty announcement text")
    safe_speaker = speaker if speaker in SPEAKER_VOICES else 'Ava'
    voice = _get_voice(safe_speaker)
    digest = _hashlib.sha1(f"{safe_speaker}\n{clean}".encode('utf-8')).hexdigest()[:16]
    user_dir = ANNOUNCE_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    out_path = user_dir / f"{digest}.mp3"
    meta_path = user_dir / f"{digest}.json"
    if out_path.exists():
        return {
            'ann_id': digest,
            'rel_path': str(out_path.relative_to(TTS_DIR)),
            'from_cache': True,
            'text': clean,
        }
    loop = _asyncio.new_event_loop()
    try:
        loop.run_until_complete(_generate_mp3(clean, voice, out_path))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
    try:
        meta_path.write_text(json.dumps({'text': clean, 'speaker': safe_speaker}))
    except Exception:
        pass
    return {
        'ann_id': digest,
        'rel_path': str(out_path.relative_to(TTS_DIR)),
        'from_cache': False,
        'text': clean,
    }


def get_announcement_path(user_id: str, ann_id: str) -> Path | None:
    """Return the MP3 path for a user's announcement, or None."""
    if not ann_id or not user_id:
        return None
    if not re.fullmatch(r'[0-9a-f]{16}', ann_id or ''):
        return None
    candidate = ANNOUNCE_DIR / str(user_id) / f"{ann_id}.mp3"
    try:
        resolved = candidate.resolve()
        base = ANNOUNCE_DIR.resolve()
        if base not in resolved.parents:
            return None
    except Exception:
        return None
    return candidate if candidate.exists() else None


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
