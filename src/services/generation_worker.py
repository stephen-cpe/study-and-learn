"""
Background lesson-generation worker (#5 — full async /generate-lessons).

Previously the AI generation loop (RAG retrieval + per-module LLM calls
for slides, checkpoints, narration, and quizzes) ran inside the POST
request thread, blocking it for the whole run; only the TTS tail was
truly background. Now the route snapshots everything the run needs,
returns immediately, and this worker does the heavy lifting on a daemon
thread — chained into the existing TTS worker when narration is on.

Threading contract (mirrors ``tts_worker.spawn_tts_background_task``):
  - The route resolves all session state FIRST (Flask ``session`` and
    ``current_user`` are unavailable off-request) and passes a plain
    ``payload`` dict of strings/lists.
  - ``spawn_generation_background_task`` pushes ``flask_app.app_context()``
    so the thread gets an independent scoped DB session. TESTING callers
    invoke :func:`run_generation_for_path` directly inside the request
    (deterministic, no threads in tests).
  - ChromaDB is only ever touched by one thread at a time in practice
    (the request returns immediately without touching it; the TTS worker
    never does), so no extra locking is introduced here.
  - All failures are contained: progress ``mark_error`` + bell ``fail_task``
    + log. The redirect column is intentionally NOT set on failure so the
    client surfaces the error instead of landing on an empty lessons page.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def run_generation_for_path(
    flask_app,
    user_id: str,
    path_id: str,
    payload: Dict[str, Any],
    task_id: str,
) -> Dict[str, Any]:
    """Run the full lesson-generation pipeline for a StudyPath.

    Assumes an app context is active (pushed by the spawner, or the
    request context in TESTING-inline mode). Never raises — every error
    path publishes progress/bell failure state and returns a summary.

    Args:
        flask_app: The Flask app (for chaining the TTS worker).
        user_id: The owning user id (reloaded fresh; never a proxy).
        path_id: Target StudyPath id (shell row guaranteed by the route).
        payload: Snapshot dict with learning_goal, study_title, modules,
            extracted_texts, file_hashes, file_names, content_digest,
            tts_enabled, tts_speaker, difficulty, display_name.
        task_id: Shared progress_tracker + bell task id.

    Returns:
        Dict with keys: ok (bool), path_id, modules (int), fallback
        (list of module titles whose quiz used the placeholder),
        slide_fallback (list of module titles whose slides used the
        placeholder).
    """
    from flask import has_request_context

    from src import db
    from src.models import StudyPath, User
    from src.repositories.lesson_repo import save_lessons
    from src.routes._helpers import _build_retriever
    from src.services import background_tasks as _bt
    from src.services import progress_tracker
    from src.services.lesson_orchestrator import build_module_artifacts
    from src.services.mascot_memory import store_memory as _store_mascot_memory
    from src.services.settings_service import DEFAULT_DIFFICULTY, DEFAULT_TTS_SPEAKER

    user = User.query.filter_by(id=user_id).first()
    if user is None:
        logger.error("Generation worker: user %s not found", str(user_id)[:8])
        progress_tracker.mark_error(task_id, mascot_msg='AI generation failed — retry')
        _bt.fail_task(task_id, error='AI generation failed — please retry')
        return {'ok': False, 'path_id': path_id, 'modules': 0, 'fallback': []}

    learning_goal = payload.get('learning_goal', '')
    study_title = payload.get('study_title', learning_goal[:50])
    modules = payload.get('modules', []) or []
    tts_enabled = bool(payload.get('tts_enabled', False))
    tts_speaker = payload.get('tts_speaker') or DEFAULT_TTS_SPEAKER
    difficulty = payload.get('difficulty') or DEFAULT_DIFFICULTY
    username = payload.get('display_name') or user.display_name

    retriever = _build_retriever(
        learning_goal,
        payload.get('extracted_texts', []) or [],
        payload.get('file_hashes', []) or [],
        payload.get('file_names', []) or [],
        content_digest=payload.get('content_digest', '') or '',
    )

    try:
        from src.services.mascot_memory import get_memories as _get_memories
        learner_memories = [
            m for m in _get_memories(user_id, limit=10)
            if isinstance(m, dict) and (m.get('content') or '').strip()
        ]
    except Exception:
        learner_memories = []

    lessons: List[Dict[str, Any]] = list(payload.get('existing_lessons') or [])
    used_chunk_ids = set()
    # Concept-level dedup: titles + objective bullets of already-generated
    # modules are passed to each subsequent module's prompt so the model
    # does not re-teach the same goal-level content (the audit found all
    # four AZ modules repeated the same triad).
    covered_concepts = []
    # Question-level dedup: normalized prompts already asked in this path
    # are passed to each subsequent quiz prompt and post-filtered, so no
    # two modules ship the same question.
    from src.services.quiz_generator import _normalize_question_prompt
    used_question_prompts = set()
    for _les in lessons:
        for _q in ((_les.get('quiz') or {}).get('questions') or []):
            _norm = _normalize_question_prompt((_q or {}).get('prompt', ''))
            if _norm:
                used_question_prompts.add(_norm)
    progress_tracker.update_progress(task_id, 1)

    try:
        for i, module in enumerate(modules):
            progress_tracker.update_progress(task_id, 2)
            artifacts = build_module_artifacts(
                module,
                learning_goal,
                retriever,
                difficulty=difficulty,
                tts_enabled=tts_enabled,
                username=username,
                tts_speaker=tts_speaker,
                next_module_title=modules[i + 1]['title'] if i + 1 < len(modules) else None,
                is_last_module=(i == len(modules) - 1),
                path_id=path_id,
                module_index=i,
                used_chunk_ids=used_chunk_ids,
                learner_memories=learner_memories,
                covered_concepts=covered_concepts,
                used_question_prompts=used_question_prompts,
            )
            progress_tracker.update_progress(task_id, 3)

            lesson_entry = {
                'index': i,
                'module_title': module['title'],
                'estimated_effort': module.get('estimated_effort', 'N/A'),
                'lesson': artifacts['lesson'],
                'quiz': artifacts['quiz'],
                'checkpoints': artifacts['checkpoints'],
                'sources': artifacts.get('sources', []),
                'difficulty': difficulty,
                'tts_enabled': tts_enabled,
                'tts_speaker': tts_speaker if tts_enabled else None,
                'tts_audio_status': 'pending' if tts_enabled else 'n/a',
                'completed': False,
                'score': None,
                'passed': False
            }
            # Persist the fail-closed content status so the grade route,
            # lessons page, and completion gate can treat a placeholder
            # module as needing regeneration instead of graded content.
            from src.services.lesson_orchestrator import (
                CONTENT_STATUS_DEGRADED,
                CONTENT_STATUS_READY,
            )
            lesson_entry['content_status'] = (
                CONTENT_STATUS_DEGRADED
                if (artifacts['lesson'].get('fallback')
                    or artifacts['quiz'].get('fallback'))
                else CONTENT_STATUS_READY
            )
            lessons.append(lesson_entry)

            # Record this module's concept for the next prompt's
            # do-not-reteach block.
            if lesson_entry['content_status'] == CONTENT_STATUS_READY:
                covered_concepts.append(module.get('title', ''))
                for slide in artifacts['lesson'].get('slides', [])[:2]:
                    heading = slide.get('heading') or slide.get('title')
                    if heading:
                        covered_concepts.append(str(heading))

        progress_tracker.update_progress(task_id, 4)
    except Exception as e:
        logger.error("Lesson generation failed: %s", str(e), exc_info=True)
        progress_tracker.mark_error(task_id, mascot_msg='AI generation failed — retry')
        _bt.fail_task(task_id, error='AI generation failed — please retry')
        return {'ok': False, 'path_id': path_id, 'modules': 0, 'fallback': []}

    # ── Fallback-rate observability ──────────────────────────────────────
    # Emit one structured line per generation so degraded-content rates can
    # be tracked/alerted without re-reading every lesson JSON. ``reason``
    # distinguishes the parse/validation class from backend errors.
    _fallback_reasons = {}
    for _l in lessons:
        if _l.get('lesson', {}).get('fallback'):
            _reason = _l.get('lesson', {}).get('fallback_reason') or 'unknown'
            _fallback_reasons[_reason] = _fallback_reasons.get(_reason, 0) + 1
        if _l.get('quiz', {}).get('fallback'):
            _fallback_reasons['quiz'] = _fallback_reasons.get('quiz', 0) + 1
    _degraded_count = sum(
        1 for _l in lessons if _l.get('content_status') == 'degraded')
    logger.info(
        "generation_summary path_id=%s modules=%d degraded=%d "
        "fallback_rate=%.2f reasons=%s",
        path_id, len(lessons), _degraded_count,
        (_degraded_count / len(lessons)) if lessons else 0.0,
        _fallback_reasons or {},
    )

    fallback_modules = [
        lessons[i].get('module_title', f'Module {i + 1}')
        for i, lesson in enumerate(lessons)
        if lesson.get('quiz', {}).get('fallback')
    ]
    slide_fallback_modules = [
        lessons[i].get('module_title', f'Module {i + 1}')
        for i, lesson in enumerate(lessons)
        if lesson.get('lesson', {}).get('fallback')
    ]
    fallback_note = ''
    if fallback_modules:
        fallback_note = (
            f"AI quiz generation failed for: {', '.join(fallback_modules)}. "
            f"Showing placeholder quizzes — retake those modules for AI-generated questions."
        )
    if slide_fallback_modules:
        slide_note = (
            f"AI lesson generation failed for: {', '.join(slide_fallback_modules)}. "
            f"Showing placeholder slides — retake those modules."
        )
        fallback_note = f"{fallback_note} {slide_note}".strip()
    # Degraded content must be surfaced even when no request context exists
    # (off-thread) — the bell label below carries it, and the flash runs
    # inline under TESTING. This is the fail-closed surface: the learner is
    # told the module failed rather than being graded on untaught material.
    if fallback_note:
        try:
            from flask import flash
            if has_request_context():
                flash(fallback_note, 'warning')
        except Exception:
            pass

    save_lessons(lessons, user,
                 title=study_title,
                 learning_goal=learning_goal,
                 extracted_texts=payload.get('extracted_texts'),
                 file_hashes_val=payload.get('file_hashes'),
                 file_names_val=payload.get('file_names'),
                 path_id=path_id)

    _store_mascot_memory(user_id, 'episodic', f"Started a new study path: {study_title}")

    if tts_enabled and path_id:
        try:
            from src.services.tts_worker import spawn_tts_background_task
            spawn_tts_background_task(
                flask_app=flask_app,
                user_id=user_id,
                path_id=path_id,
                task_id=task_id,
            )
        except Exception as e:
            logger.warning("TTS background thread failed to spawn: %s", str(e))
            progress_tracker.mark_error(task_id, mascot_msg='Audio failed — lessons still work')
            _set_generation_completed(path_id, user_id)
    else:
        _set_generation_completed(path_id, user_id)

    try:
        path = StudyPath.query.filter_by(id=path_id, user_id=user_id).first()
        if path is not None:
            path.extracted_texts = None
            path.content_digest = None
            db.session.commit()
    except Exception as e:
        logger.warning("Generation worker: failed to clear digest for path %s: %s",
                       str(path_id)[:8], str(e))
        try:
            db.session.rollback()
        except Exception:
            pass

    try:
        from flask import flash
        if has_request_context():
            flash(f'Generated {len(modules)} lessons successfully!', 'success')
    except Exception:
        pass
    label = f"Lessons ready: {study_title[:80]}"
    if fallback_modules:
        label = (label + f" (quiz fallback: {', '.join(fallback_modules)[:80]})")[:200]
    elif slide_fallback_modules:
        label = (label + f" (slides fallback: {', '.join(slide_fallback_modules)[:80]})")[:200]
    _bt.finish_task(
        task_id,
        result_url=f"/lessons?path_id={path_id}" if path_id else "/dashboard",
        label=label,
        path_id=path_id or '',
    )
    return {'ok': True, 'path_id': path_id, 'modules': len(modules),
            'fallback': fallback_modules,
            'slide_fallback': slide_fallback_modules}


def _set_generation_completed(path_id: Optional[str], user_id: str) -> None:
    """Set ``StudyPath.generation_completed_at`` to NOW().

    Local copy of the route helper (importing routes from services would
    be circular). Same contract: best-effort, never raises.
    """
    if not path_id:
        return
    try:
        from datetime import datetime, timezone

        from src import db
        from src.models import StudyPath
        path = StudyPath.query.filter_by(id=path_id, user_id=user_id).first()
        if path is None:
            return
        path.generation_completed_at = datetime.now(timezone.utc)
        db.session.commit()
    except Exception as e:
        logger.warning(
            "Failed to set generation_completed_at for path %s: %s",
            str(path_id)[:8], str(e),
        )
        try:
            from src import db as _db
            _db.session.rollback()
        except Exception:
            pass


def spawn_generation_background_task(
    flask_app,
    user_id: str,
    path_id: str,
    payload: Dict[str, Any],
    task_id: str,
) -> threading.Thread:
    """Spawn a daemon thread running :func:`run_generation_for_path`.

    Mirrors the TTS spawner: pushes ``flask_app.app_context()`` for an
    independent DB session, logs uncaught errors, and as a last resort
    fails the bell task so the client stops polling with an error
    instead of hanging until the 2-hour hard timeout.
    """
    def _runner():
        with flask_app.app_context():
            try:
                run_generation_for_path(
                    flask_app=flask_app,
                    user_id=user_id,
                    path_id=path_id,
                    payload=payload,
                    task_id=task_id,
                )
            except Exception as e:
                logger.error(
                    "Generation background task %s died with uncaught error: %s",
                    task_id, str(e), exc_info=True,
                )
                try:
                    from src.services import background_tasks as _bt
                    from src.services import progress_tracker
                    progress_tracker.mark_error(
                        task_id, mascot_msg='AI generation crashed — retry'
                    )
                    _bt.fail_task(task_id, error='AI generation failed — please retry')
                except Exception:
                    pass
    thread = threading.Thread(target=_runner, name=f"gen-{task_id[:8]}", daemon=True)
    thread.start()
    return thread
