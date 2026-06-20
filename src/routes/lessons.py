"""
Lesson routes — generation, slide deck, grading, and retake.
"""
import logging
from flask import (current_app, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from flask_login import current_user, login_required

from src.repositories.lesson_repo import (
    get_active_path,
    get_learning_goal as _db_get_goal,
    get_lessons,
    get_most_recent_active_path,
    get_study_path_data,
    save_lessons,
)
from src.routes import PASS_THRESHOLD, bp
from src.routes._helpers import _build_retriever, _resolve_goal, _resolve_hashes, _resolve_path_id, _resolve_texts, _resolve_filenames
from src.services import progress_tracker
from src.services.grader import _get_correct_answer, _grade_single_question
from src.services.lesson_orchestrator import build_module_artifacts

logger = logging.getLogger(__name__)


@bp.route('/generate-lessons', methods=['POST'])
@login_required
def generate_lessons():
    if not current_user.is_admin and not current_user.can_generate_lessons:
        flash('Lesson generation is disabled for your account. Contact an admin to enable access.', 'error')
        return redirect(url_for('main.dashboard'))

    learning_goal = session.get('learning_goal', '')
    study_path = session.get('study_path', {})

    if (not learning_goal or not study_path.get('modules')) and current_user.is_authenticated:
        learning_goal = _db_get_goal(current_user) or ''
        study_path = get_study_path_data(current_user) or {}

    if not learning_goal or not study_path.get('modules'):
        flash('No study path found. Please upload materials first.', 'error')
        return redirect(url_for('main.index'))

    active_count = current_user.active_lesson_count
    existing_path = get_active_path(current_user)
    if existing_path is None and active_count >= 3:
        flash('You already have 3 active lessons. Complete or abandon one before starting a new one.', 'error')
        return redirect(url_for('main.dashboard'))

    body = request.get_json(silent=True) or {}
    task_id = body.get('task_id', '') or session.sid
    progress_tracker.create_task(task_id=task_id)

    modules = study_path['modules']

    most_recent = get_most_recent_active_path(current_user)
    path_id_val = most_recent.id if most_recent else None
    lessons = get_lessons(current_user, path_id=path_id_val)

    extracted_texts = _resolve_texts()
    file_hashes_data = _resolve_hashes()
    file_names_data = _resolve_filenames()
    retriever = _build_retriever(learning_goal, extracted_texts, file_hashes_data, file_names_data)

    tts_enabled = getattr(current_user, 'tts_enabled', False)
    tts_speaker = getattr(current_user, 'tts_speaker', 'Ava') or 'Ava'
    difficulty = getattr(current_user, 'lesson_difficulty', 'Normal') or 'Normal'
    username = current_user.username

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
                next_module_title=modules[i+1]['title'] if i+1 < len(modules) else None,
                is_last_module=(i == len(modules) - 1),
                path_id=path_id_val,
                module_index=i,
            )
            progress_tracker.update_progress(task_id, 3)

            lessons.append({
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
                # tts_audio_status is the per-module generation state used by
                # the lessons page UI to show "Generating narration..." badges
                # and by the audio route to return 202 when pending. The
                # background worker updates this field as it runs.
                'tts_audio_status': 'pending' if tts_enabled else 'n/a',
                'completed': False,
                'score': None,
                'passed': False
            })

        progress_tracker.update_progress(task_id, 4)
    except Exception as e:
        # Surface the failure to the user via mascot-error.gif so they
        # see the robot in an error state instead of a frozen "busy".
        # The JS sticky-error window keeps the error GIF visible for
        # ~8s even if a later poll arrives. Do NOT swallow the error —
        # re-raise after publishing the cosmetic so Flask's default 500
        # handler still logs the traceback.
        logger.error("Lesson generation failed: %s", str(e), exc_info=True)
        progress_tracker.mark_error(task_id, mascot_msg='AI generation failed — retry')
        raise

    save_lessons(lessons, current_user,
                 title=study_path.get('title', learning_goal[:50]),
                 learning_goal=learning_goal,
                 extracted_texts=extracted_texts,
                 file_hashes_val=file_hashes_data,
                 file_names_val=file_names_data,
                 path_id=path_id_val)

    if path_id_val is None:
        from src.models import StudyPath
        refreshed = StudyPath.query.filter_by(
            user_id=current_user.id, status='active'
        ).order_by(StudyPath.created_at.desc()).first()
        if refreshed:
            path_id_val = refreshed.id

    # Task 5: TTS generation runs in a background thread so the request
    # handler can return immediately. The lessons page polls
    # /lessons/generation-status to display per-module audio status.
    #
    # The redirect signal is ``StudyPath.generation_completed_at``:
    #   - tts_enabled=False  → this handler sets the column now, so
    #     the JS poll-based redirect fires immediately.
    #   - tts_enabled=True   → the TTS background worker sets the
    #     column in its finally block once every module has finished
    #     (success, skipped, or failed). The JS redirect fires when
    #     the user sees the bubble say "All done!".
    # The column is the canonical "navigate now" signal — atomic with
    # the lesson-dict persistence, no shared cache state, no race
    # conditions. The previous cache-based signal (``data.done``) had
    # a race condition where the TTS worker overwrote the request
    # handler's stage 4 (max GENERATE_STAGES) with its own max
    # stage 3 (TTS_STAGES), causing the JS poll-based redirect
    # (``data.stage >= 4``) to never fire.
    from datetime import datetime, timezone
    from src import db
    from src.models import StudyPath

    if tts_enabled and path_id_val:
        try:
            from src.services.tts_worker import spawn_tts_background_task
            spawn_tts_background_task(
                flask_app=current_app._get_current_object(),
                user_id=current_user.id,
                path_id=path_id_val,
                task_id=task_id,
            )
        except Exception as e:
            # Defensive: if the background thread cannot even be
            # started, set the completion column here so the user
            # is not stuck on the results page forever.
            logger.warning("TTS background thread failed to spawn: %s", str(e))
            progress_tracker.mark_error(task_id, mascot_msg='Audio failed — lessons still work')
            _set_generation_completed(path_id_val, current_user.id)
    else:
        # No TTS worker spawned — this handler is the only producer
        # of the completion signal, so it must set the column before
        # returning or the JS poll will hang at "Generating…".
        _set_generation_completed(path_id_val, current_user.id)

    path = StudyPath.query.filter_by(id=path_id_val, user_id=current_user.id).first() if path_id_val else None
    if not path:
        path = StudyPath.query.filter_by(user_id=current_user.id, status='active').order_by(StudyPath.created_at.desc()).first()
    if path:
        path.extracted_texts = None
        db.session.commit()

    flash(f'Generated {len(modules)} lessons successfully!', 'success')
    return jsonify({
        'redirect': url_for('main.lessons', path_id=path_id_val),
        'task_id': task_id,
    })


def _set_generation_completed(path_id: str, user_id: str) -> None:
    """Set ``StudyPath.generation_completed_at`` to NOW().

    This is the canonical "redirect now" signal for the JS client.
    Used by:
      - The ``generate_lessons`` route when TTS is disabled (or path
        is unknown), so the redirect fires immediately on return.
      - The TTS worker's finally block, so the redirect fires when
        every TTS module has reached a terminal state.

    Defensive: if the path cannot be found or the DB write fails,
    the error is logged but not raised — the user must never be
    stuck because the completion flag failed to set. (The JS
    client has a 2-hour hard-timeout safety net that stops
    polling with a "still working" message rather than redirecting
    — this covers the worst case where the column is never set.)
    """
    from src import db
    from src.models import StudyPath
    from datetime import datetime, timezone
    if not path_id:
        return
    try:
        path = StudyPath.query.filter_by(id=path_id, user_id=user_id).first()
        if path is None:
            return
        path.generation_completed_at = datetime.now(timezone.utc)
        db.session.commit()
    except Exception as e:
        logger.warning(
            "Failed to set generation_completed_at for path %s: %s",
            path_id, str(e),
        )
        try:
            db.session.rollback()
        except Exception:
            pass


@bp.route('/lessons')
@login_required
def lessons():
    path_id = _resolve_path_id()
    lessons_data = get_lessons(current_user, path_id=path_id)
    if not lessons_data:
        flash('No lessons generated yet. Generate lessons from your results first.', 'info')
        return redirect(url_for('main.results'))

    for i, lesson in enumerate(lessons_data):
        lesson['unlocked'] = True
        if i > 0:
            prev = lessons_data[i - 1]
            if not prev.get('passed', False):
                lesson['unlocked'] = False

    return render_template('lessons.html',
                           lessons=lessons_data,
                           pass_threshold=PASS_THRESHOLD,
                           path_id=path_id)


@bp.route('/lessons/generation-status')
@login_required
def generation_status():
    """Return per-module TTS audio generation status for the current user.

    Used by the results page (via JS polling) to decide when to
    redirect the user to the lessons page. The endpoint accepts a
    ``path_id`` query string; when missing, falls back to the user's
    most recent active StudyPath.

    The endpoint is the SINGLE SOURCE OF TRUTH for the "navigate
    now" signal. The JS polls this endpoint and redirects when
    ``generation_completed`` is true. The signal is sourced from
    the ``StudyPath.generation_completed_at`` column (set by the
    request handler for TTS-disabled generations, or by the TTS
    background worker's finally block for TTS-enabled generations).
    This replaces the previous cache-based ``progress_tracker.mark_done()``
    signal, which had a race condition.

    Response shape::

        {
            "path_id": "<uuid>",
            "modules": [
                {"module_index": 0, "title": "M1", "tts_enabled": true,
                 "status": "ready" | "pending" | "n/a" | "failed"},
                ...
            ],
            "all_ready": true | false,
            "ready_count": int,
            "total": int,
            "generation_completed": true | false,   # ← redirect when true
            "task_status": {"stage": int, "label": str, "pct": int, "mascot": str}
                         | null  (when no active task for this user)
        }
    """
    path_id = _resolve_path_id()
    if not path_id:
        path = get_most_recent_active_path(current_user)
        path_id = path.id if path else None
    if not path_id:
        return jsonify({
            'path_id': None,
            'modules': [],
            'all_ready': False,
            'ready_count': 0,
            'total': 0,
            'generation_completed': False,
            'task_status': None,
        })
    from src.services.tts_worker import get_path_audio_status
    status = get_path_audio_status(user_id=current_user.id, path_id=path_id)
    status['path_id'] = path_id
    # Read the canonical "redirect now" signal from the StudyPath row.
    # This is atomic, ACID, and unaffected by shared-cache races.
    from src.models import StudyPath
    path = StudyPath.query.filter_by(id=path_id, user_id=current_user.id).first()
    status['generation_completed'] = (
        path is not None and path.generation_completed_at is not None
    )
    # Also include the live progress_tracker status for the user's
    # current task (used by the JS to show the overall mascot progress).
    task_status = None
    task_id = request.args.get('task_id') or session.sid
    if task_id:
        task_status = progress_tracker.get_progress(task_id)
    status['task_status'] = task_status
    return jsonify(status)


@bp.route('/lessons/<int:module_index>')
@login_required
def lesson_deck(module_index):
    path_id = _resolve_path_id()
    lessons_data = get_lessons(current_user, path_id=path_id)
    if not lessons_data:
        flash('No lessons generated yet.', 'error')
        return redirect(url_for('main.results'))

    if module_index < 0 or module_index >= len(lessons_data):
        flash('Invalid module index.', 'error')
        return redirect(url_for('main.lessons'))

    if module_index > 0:
        prev = lessons_data[module_index - 1]
        if not prev.get('passed', False):
            flash('You must pass the previous module before accessing this one.', 'warning')
            return redirect(url_for('main.lessons'))

    lesson = lessons_data[module_index]
    return render_template('lesson_deck.html',
                           lesson=lesson,
                           module_index=module_index,
                           total_modules=len(lessons_data),
                           pass_threshold=PASS_THRESHOLD,
                           path_id=path_id)


@bp.route('/lessons/<int:module_index>/grade', methods=['POST'])
@login_required
def grade_lesson(module_index):
    path_id = _resolve_path_id()
    lessons_data = get_lessons(current_user, path_id=path_id)
    if not lessons_data:
        return jsonify({'error': 'No lessons found'}), 404

    if module_index < 0 or module_index >= len(lessons_data):
        return jsonify({'error': 'Invalid module index'}), 404

    lesson = lessons_data[module_index]
    data = request.get_json(silent=True) or {}
    answers = data.get('answers', [])
    fill_blank_answers = data.get('fill_blank_answers', {})

    quiz_questions = lesson.get('quiz', {}).get('questions', [])
    checkpoints = lesson.get('checkpoints', {})
    checkpoint_answers = data.get('checkpoint_answers', {})

    total_points = len(quiz_questions) + len(checkpoints)
    earned_points = 0
    quiz_results = []

    for i, question in enumerate(quiz_questions):
        if question['type'] == 'fill_blank':
            user_answer = fill_blank_answers.get(question['id'], answers[i] if i < len(answers) else None)
        else:
            user_answer = answers[i] if i < len(answers) else None
        correct = _grade_single_question(question, user_answer)
        if correct:
            earned_points += 1
        quiz_results.append({
            'id': question['id'],
            'type': question['type'],
            'prompt': question['prompt'],
            'user_answer': user_answer,
            'correct_answer': _get_correct_answer(question),
            'correct': correct,
            'explanation': question.get('explanation', '')
        })

    checkpoint_results = []
    for slide_idx, cp in checkpoints.items():
        user_cp = checkpoint_answers.get(slide_idx)
        cp_correct = _grade_single_question(cp, user_cp)
        if cp_correct:
            earned_points += 1
        checkpoint_results.append({
            'slide_index': slide_idx,
            'prompt': cp.get('prompt', ''),
            'user_answer': user_cp,
            'correct_answer': _get_correct_answer(cp),
            'correct': cp_correct,
            'explanation': cp.get('explanation', '')
        })

    if total_points == 0:
        total_points = 1
    score_pct = round((earned_points / total_points) * 100)
    passed = score_pct >= PASS_THRESHOLD

    lessons_data[module_index]['completed'] = True
    lessons_data[module_index]['score'] = score_pct
    lessons_data[module_index]['passed'] = passed
    save_lessons(lessons_data, current_user, path_id=path_id)

    return jsonify({
        'score': score_pct,
        'passed': passed,
        'threshold': PASS_THRESHOLD,
        'earned': earned_points,
        'total': total_points,
        'quiz_results': quiz_results,
        'checkpoint_results': checkpoint_results
    })


@bp.route('/lessons/<int:module_index>/retake', methods=['POST'])
@login_required
def retake_lesson(module_index):
    path_id = _resolve_path_id()
    lessons_data = get_lessons(current_user, path_id=path_id)
    if not lessons_data:
        return jsonify({'error': 'No lessons found'}), 404

    if module_index < 0 or module_index >= len(lessons_data):
        return jsonify({'error': 'Invalid module index'}), 404

    lesson = lessons_data[module_index]
    module_title = lesson.get('module_title', '')
    slides = lesson.get('lesson', {}).get('slides', [])
    goal = _resolve_goal()
    texts = _resolve_texts()
    hashes_data = _resolve_hashes()
    names_data = _resolve_filenames()
    retriever = _build_retriever(goal, texts, hashes_data, names_data)

    difficulty = lesson.get('difficulty', 'Normal')
    tts_enabled = lesson.get('tts_enabled', False)
    tts_speaker = lesson.get('tts_speaker', 'Ava') or 'Ava'
    username = current_user.username

    artifacts = build_module_artifacts(
        {'title': module_title},
        goal,
        retriever,
        existing_slides=slides,
        difficulty=difficulty,
        tts_enabled=tts_enabled,
        username=username,
        tts_speaker=tts_speaker,
    )

    lessons_data[module_index]['quiz'] = artifacts['quiz']
    lessons_data[module_index]['checkpoints'] = artifacts['checkpoints']
    lessons_data[module_index]['lesson'] = artifacts['lesson']
    lessons_data[module_index]['completed'] = False
    lessons_data[module_index]['score'] = None
    lessons_data[module_index]['passed'] = False
    # Reset the user's saved deck position so they restart the lesson from
    # slide 0 instead of being dropped mid-deck with stale UI from the
    # previous (failed) attempt.
    lessons_data[module_index]['deck_position'] = 0
    save_lessons(lessons_data, current_user, path_id=path_id)

    if tts_enabled:
        from src.services.tts_service import delete_module_audio, generate_lesson_audio
        try:
            delete_module_audio(path_id, module_index)
            narration = artifacts['lesson'].get('narration', [])
            if narration:
                try:
                    generate_lesson_audio(
                        path_id=path_id,
                        module_index=module_index,
                        narration_script=narration,
                        speaker=tts_speaker,
                    )
                except Exception as e:
                    logger.warning("TTS retake audio failed for module %d: %s", module_index, str(e))
        except Exception as e:
            # TTS cleanup/regeneration failed (e.g. path_id was None).
            # The lesson content was already regenerated and saved above,
            # so we return success with a warning rather than a 500 —
            # the user can still take the lesson without audio.
            logger.warning("TTS retake cleanup failed for module %d: %s", module_index, str(e))

    # Return a redirect URL so the client navigates the user to the deck for
    # this module with the regenerated content, instead of blind-reloading
    # the results slide they clicked Retake on.
    return jsonify({
        'success': True,
        'redirect': url_for('main.lesson_deck', module_index=module_index, path_id=path_id),
    })


@bp.route('/lessons/<int:module_index>/save-position', methods=['POST'])
@login_required
def save_lesson_position(module_index):
    path_id = _resolve_path_id()
    lessons_data = get_lessons(current_user, path_id=path_id)
    if not lessons_data or module_index >= len(lessons_data):
        return jsonify({'ok': False}), 404
    data = request.get_json(silent=True) or {}
    slide_index = int(data.get('slide_index', 0))
    if not lessons_data[module_index].get('completed', False):
        lessons_data[module_index]['deck_position'] = slide_index
        save_lessons(lessons_data, current_user, path_id=path_id)
    return jsonify({'ok': True})


@bp.route('/lessons/<int:module_index>/audio/<string:slide_index>')
@login_required
def lesson_audio(module_index, slide_index):
    """Serve a TTS audio file for a specific deck slot.

    ``slide_index`` is a string (not int) because the intro audio uses the
    sentinel value ``-1`` which the int URL converter rejects. The value
    is parsed and looked up as a key in the manifest's ``slides`` dict.

    Status codes:
      - 200: audio file is ready and being served.
      - 202: TTS is enabled for this module but the manifest doesn't
        exist on disk yet (the background worker is still generating it).
        The JS player should retry in ~2 seconds.
      - 404: TTS is disabled for this module, OR the manifest exists
        but the requested slide_index has no audio entry.
    """
    path_id = _resolve_path_id()
    if not path_id:
        # The JS may navigate to /lessons/<i>/audio/<j> without a ?path_id=
        # query string (e.g. when the user enters the deck from a deep link
        # or refreshes a page that already filters by active path). Fall
        # back to the user's most recent active StudyPath so the audio
        # route can still resolve the manifest.
        path_id = get_most_recent_active_path_id()
    lessons_data = get_lessons(current_user, path_id=path_id)
    if not lessons_data or module_index >= len(lessons_data):
        return ('', 404)
    if not lessons_data[module_index].get('tts_enabled'):
        return ('', 404)
    from src.services.tts_service import TTS_DIR, get_audio_manifest
    manifest = get_audio_manifest(path_id or '', module_index)
    # Distinguish 'TTS not enabled' (404) from 'TTS pending' (202).
    # We use get_audio_manifest (not is_module_audio_ready from tts_worker)
    # so both checks use the same TTS_DIR that generate_lesson_audio writes to.
    if not manifest:
        return ('', 202)
    rel_path = manifest['slides'].get(str(slide_index))
    if not rel_path:
        return ('', 404)
    full_path = TTS_DIR / rel_path
    if not full_path.exists():
        return ('', 202)
    from flask import send_file
    return send_file(str(full_path), mimetype='audio/mpeg', conditional=True)


@bp.route('/lessons/<int:module_index>/audio/manifest')
@login_required
def lesson_audio_manifest(module_index):
    path_id = _resolve_path_id()
    if not path_id:
        path_id = get_most_recent_active_path_id()
    from src.services.tts_service import get_audio_manifest
    manifest = get_audio_manifest(path_id or '', module_index)
    return jsonify(manifest or {})


def get_most_recent_active_path_id() -> str:
    """Return the user's most recent active StudyPath.id, or empty string.

    Used as a fallback when audio routes are hit without an explicit
    path_id in the URL. Returns empty string when the user has no active
    paths so the audio route can return a clean 404.
    """
    path = get_most_recent_active_path(current_user)
    return path.id if path else ''
