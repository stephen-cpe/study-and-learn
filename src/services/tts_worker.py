"""
Background TTS worker service (Task 5 — Bug #1 fix).

The TTS audio generation runs as a background ``threading.Thread`` so the
HTTP request handler can return immediately after saving the lessons to
the database. The lessons page polls ``/lessons/generation-status`` to
display per-module audio status.

Key contract:
  - The worker is **idempotent**: if a module's ``manifest.json`` already
    exists on disk, generation is skipped (no overwrite).
  - The worker is **failure-tolerant**: if one module's TTS call raises,
    the worker logs the failure, marks the lesson as ``tts_audio_status =
    'failed'`` and ``tts_enabled = False``, and continues to the next
    module. A single bad module must not block the others.
  - The worker runs inside a Flask app context so it can read/write the
    DB. Errors that escape the per-module try/except are caught by the
    top-level error handler so the thread never dies silently.
  - The worker's progress is visible via the same ``progress_tracker``
    the request handler uses (keyed by task_id), with new TTS-specific
    stages.
"""
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.services import progress_tracker
from src.services.tts_service import (
    TTS_DIR,
    get_audio_manifest,
    generate_lesson_audio,
)

logger = logging.getLogger(__name__)


# ── TTS-specific progress stages ──────────────────────────────────────

TTS_STAGES = [
    {"stage": 0, "label": "Preparing", "pct": 0, "mascot": "Warming up...", "mascot_state": "busy"},
    {"stage": 1, "label": "Generating narration", "pct": 25, "mascot": "Recording narration...", "mascot_state": "busy"},
    {"stage": 2, "label": "Encoding audio", "pct": 75, "mascot": "Encoding audio...", "mascot_state": "busy"},
    {"stage": 3, "label": "Complete", "pct": 100, "mascot": "All done!", "mascot_state": "happy"},
]


# ── Status helpers ────────────────────────────────────────────────────

def is_module_audio_ready(path_id: str, module_index: int) -> bool:
    """Return True if the audio manifest for the given module exists."""
    if not path_id:
        return False
    manifest_path = TTS_DIR / path_id / str(module_index) / 'manifest.json'
    return manifest_path.exists()


def get_module_status(path_id: str, module_index: int) -> str:
    """Return the canonical status string for a module's audio:
    - 'ready'   : manifest exists on disk
    - 'pending' : tts_enabled is True but manifest not yet written
    - 'n/a'     : tts_enabled is False for this module
    - 'missing' : path/module not in the layout
    """
    if is_module_audio_ready(path_id, module_index):
        return 'ready'
    # Caller can layer their own tts_enabled check; default to 'pending'.
    return 'pending'


def get_path_audio_status(user_id: str, path_id: str) -> Dict[str, Any]:
    """Return a status summary for a path's TTS generation.

    Args:
        user_id: The owning user id (used to load the StudyPath from DB).
        path_id: The StudyPath id.

    Returns:
        Dict with keys:
            - 'modules': list of {module_index, status} per lesson
            - 'all_ready': True when every TTS-enabled module is 'ready'
            - 'ready_count': number of modules with status='ready'
            - 'total': total number of modules in the path
    """
    from src.models import StudyPath, LessonProgress
    from src import db
    import json

    path = StudyPath.query.filter_by(id=path_id, user_id=user_id).first()
    if not path or not path.content_data:
        return {
            'modules': [], 'all_ready': False, 'ready_count': 0, 'total': 0,
        }
    try:
        lessons = json.loads(path.content_data)
    except (json.JSONDecodeError, TypeError):
        return {
            'modules': [], 'all_ready': False, 'ready_count': 0, 'total': 0,
        }
    modules = []
    ready_count = 0
    for lesson in lessons:
        i = lesson.get('index', 0)
        tts_on = lesson.get('tts_enabled', False)
        if not tts_on:
            status = 'n/a'
        elif is_module_audio_ready(path_id, i):
            status = 'ready'
            ready_count += 1
        else:
            status = 'pending'
        modules.append({
            'module_index': i,
            'title': lesson.get('module_title', ''),
            'tts_enabled': tts_on,
            'status': status,
        })
    tts_enabled_count = sum(1 for m in modules if m['tts_enabled'])
    return {
        'modules': modules,
        'all_ready': (ready_count == tts_enabled_count) and tts_enabled_count > 0,
        'ready_count': ready_count,
        'total': len(modules),
    }


# ── Background worker ────────────────────────────────────────────────

def run_tts_generation_for_path(
    user_id: str,
    path_id: str,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run TTS generation for all TTS-enabled modules in a StudyPath.

    This function is **synchronous**. The HTTP route spawns it as a
    background thread (see ``spawn_tts_background_task``). The thread
    pushes a Flask app context so it can read/write the DB.

    Idempotency: modules whose ``manifest.json`` already exists on disk
    are skipped (no overwrite). The status field on the lesson dict
    reflects whether the module was newly generated or already ready.

    Failure handling: per-module TTS errors are caught, logged, and
    persisted to the lesson dict (``tts_audio_status='failed'``,
    ``tts_enabled=False``). A failed module does not stop the worker.

    Args:
        user_id: The owning user id.
        path_id: The StudyPath id whose modules to process.
        task_id: Optional progress_tracker task id. When provided, the
            worker reports its progress under this key. When None, the
            worker still runs but does not update the progress tracker.

    Returns:
        Dict with keys:
            - 'modules': list of {module_index, status, error, skipped}
            - 'all_ready': True when every TTS-enabled module is 'ready'
    """
    from src.models import StudyPath
    from src import db
    import json

    if task_id:
        progress_tracker.create_task(task_id=task_id, stages=TTS_STAGES)
        progress_tracker.update_progress(task_id, 0)

    path = StudyPath.query.filter_by(id=path_id, user_id=user_id).first()
    if not path or not path.content_data:
        logger.warning("TTS worker: path %s not found for user %s", path_id, user_id)
        if task_id:
            progress_tracker.update_progress(task_id, 3)
        return {'modules': [], 'all_ready': False}

    try:
        lessons = json.loads(path.content_data)
    except (json.JSONDecodeError, TypeError):
        logger.warning("TTS worker: path %s has invalid content_data", path_id)
        if task_id:
            progress_tracker.update_progress(task_id, 3)
        return {'modules': [], 'all_ready': False}

    results = []
    for lesson in lessons:
        idx = lesson.get('index', 0)
        tts_enabled = lesson.get('tts_enabled', False)
        if not tts_enabled:
            results.append({
                'module_index': idx,
                'status': 'n/a',
                'error': None,
                'skipped': False,
            })
            continue

        if task_id:
            progress_tracker.update_progress(task_id, 1)

        # Idempotency: skip if manifest already exists.
        if is_module_audio_ready(path_id, idx):
            logger.info("TTS worker: module %d already ready, skipping", idx)
            lesson['tts_audio_status'] = 'ready'
            results.append({
                'module_index': idx,
                'status': 'ready',
                'error': None,
                'skipped': True,
            })
            continue

        if task_id:
            progress_tracker.update_progress(task_id, 2)

        narration = lesson.get('lesson', {}).get('narration', [])
        if not narration:
            logger.info("TTS worker: module %d has no narration, marking n/a", idx)
            lesson['tts_audio_status'] = 'n/a'
            lesson['tts_enabled'] = False
            results.append({
                'module_index': idx,
                'status': 'n/a',
                'error': 'no narration',
                'skipped': False,
            })
            continue

        speaker = lesson.get('tts_speaker', 'Ava') or 'Ava'
        try:
            generate_lesson_audio(
                path_id=path_id,
                module_index=idx,
                narration_script=narration,
                speaker=speaker,
            )
            lesson['tts_audio_status'] = 'ready'
            results.append({
                'module_index': idx,
                'status': 'ready',
                'error': None,
                'skipped': False,
            })
        except Exception as e:
            logger.warning(
                "TTS worker: module %d generation failed: %s", idx, str(e)
            )
            lesson['tts_audio_status'] = 'failed'
            lesson['tts_enabled'] = False
            results.append({
                'module_index': idx,
                'status': 'failed',
                'error': str(e),
                'skipped': False,
            })

    if task_id:
        progress_tracker.update_progress(task_id, 3)

    # Persist any lesson dict changes (tts_audio_status, tts_enabled).
    try:
        path.content_data = json.dumps(lessons)
        db.session.commit()
    except Exception as e:
        logger.warning("TTS worker: failed to persist lesson dict updates: %s", str(e))
        db.session.rollback()

    all_ready = all(
        r['status'] in ('ready', 'n/a') for r in results
    )
    return {'modules': results, 'all_ready': all_ready}


def spawn_tts_background_task(
    flask_app,
    user_id: str,
    path_id: str,
    task_id: str,
) -> threading.Thread:
    """Spawn a daemon thread that runs TTS generation in the background.

    The thread pushes ``flask_app.app_context()`` so it can access the
    DB. It catches all uncaught exceptions and logs them, so the thread
    never dies silently. The thread is a daemon so it does not block
    process shutdown.
    """
    def _runner():
        with flask_app.app_context():
            try:
                run_tts_generation_for_path(
                    user_id=user_id, path_id=path_id, task_id=task_id,
                )
            except Exception as e:
                logger.error(
                    "TTS background task %s died with uncaught error: %s",
                    task_id, str(e), exc_info=True,
                )
    thread = threading.Thread(target=_runner, name=f"tts-{task_id[:8]}", daemon=True)
    thread.start()
    return thread
