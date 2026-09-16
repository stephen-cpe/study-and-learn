"""
Lesson routes — generation, slide deck, grading, and retake.
"""
import logging

from flask import (
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required

from src.models import PATH_STATUS_ACTIVE
from src.repositories.lesson_repo import (
    get_active_path,
    get_lessons,
    get_most_recent_active_path,
    get_study_path_data,
    save_lessons,
)
from src.repositories.lesson_repo import (
    get_learning_goal as _db_get_goal,
)
from src.routes import PASS_THRESHOLD, bp
from src.routes._helpers import (
    _build_retriever,
    _resolve_content_digest,
    _resolve_filenames,
    _resolve_goal,
    _resolve_hashes,
    _resolve_path_id,
    _resolve_texts,
)
from src.services import progress_tracker
from src.services.grader import get_correct_answer, grade_single_question
from src.services.lesson_orchestrator import build_module_artifacts
from src.services.mascot_memory import store_memory as _store_mascot_memory
from src.services.settings_service import DEFAULT_DIFFICULTY, DEFAULT_TTS_SPEAKER

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
    progress_tracker.create_task(task_id=task_id,
                                 display_name=current_user.display_name)
    # Durable bell record (Phase 1): other tabs poll /tasks for this.
    from src.services import background_tasks as _bt
    _bt.create_task(task_id, current_user.id, kind='generate',
                    label=f"Lessons: {(study_path.get('title') or learning_goal or '')[:80]}")

    modules = study_path['modules']

    most_recent = get_most_recent_active_path(current_user)
    path_id_val = most_recent.id if most_recent else None
    lessons = get_lessons(current_user, path_id=path_id_val)

    extracted_texts = _resolve_texts()
    file_hashes_data = _resolve_hashes()
    file_names_data = _resolve_filenames()
    content_digest = _resolve_content_digest(path_id=path_id_val)
    retriever = _build_retriever(
        learning_goal, extracted_texts, file_hashes_data, file_names_data,
        content_digest=content_digest,
    )

    tts_enabled = getattr(current_user, 'tts_enabled', False)
    tts_speaker = getattr(current_user, 'tts_speaker', DEFAULT_TTS_SPEAKER) or DEFAULT_TTS_SPEAKER
    difficulty = getattr(current_user, 'lesson_difficulty', DEFAULT_DIFFICULTY) or DEFAULT_DIFFICULTY
    # display_name = nickname or full_name or username — the friendly name the
    # mascot and TTS narration use to address the learner.
    username = current_user.display_name

    # Track chunk IDs used across modules to prevent content repetition.
    # Each module's retrieval excludes chunks already used by earlier modules,
    # forcing the LLM to cover different document content per module.
    used_chunk_ids = set()

    # TTS memory: learner facts for narration callbacks. Never raises —
    # get_memories degrades to [] so generation never blocks on memory.
    # Keep dicts (memory_type+content) so tts_persona can prioritize
    # struggle/mastery signals and drop voice-pref echoes.
    try:
        from src.services.mascot_memory import get_memories as _get_memories
        learner_memories = [
            m for m in _get_memories(current_user.id, limit=10)
            if isinstance(m, dict) and (m.get('content') or '').strip()
        ]
    except Exception:
        learner_memories = []

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
                used_chunk_ids=used_chunk_ids,
                learner_memories=learner_memories,
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
        from src.services import background_tasks as _bt
        _bt.fail_task(task_id, error='AI generation failed — please retry')
        raise

    # Surface a warning if any module's quiz fell back to the
    # topic-aware placeholder (AI generation or JSON parsing failed).
    fallback_modules = [
        lessons[i].get('module_title', f'Module {i + 1}')
        for i, l in enumerate(lessons)
        if l.get('quiz', {}).get('fallback')
    ]
    if fallback_modules:
        flash(
            f"AI quiz generation failed for: {', '.join(fallback_modules)}. "
            f"Showing placeholder quizzes — try retaking for AI-generated questions.",
            'warning'
        )

    save_lessons(lessons, current_user,
                 title=study_path.get('title', learning_goal[:50]),
                 learning_goal=learning_goal,
                 extracted_texts=extracted_texts,
                 file_hashes_val=file_hashes_data,
                 file_names_val=file_names_data,
                 path_id=path_id_val)

    # Memory: record that the learner started a new study path
    _store_mascot_memory(
        current_user.id, 'episodic',
        f"Started a new study path: {study_path.get('title', learning_goal[:50])}"
    )

    if path_id_val is None:
        from src.models import StudyPath
        refreshed = StudyPath.query.filter_by(
            user_id=current_user.id, status=PATH_STATUS_ACTIVE
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
        path = StudyPath.query.filter_by(user_id=current_user.id, status=PATH_STATUS_ACTIVE).order_by(StudyPath.created_at.desc()).first()
    if path:
        path.extracted_texts = None
        path.content_digest = None
        db.session.commit()

    flash(f'Generated {len(modules)} lessons successfully!', 'success')
    # Bell record flips to ready now (lessons are viewable; TTS audio may
    # still generate in the background — the lessons page badges show that).
    from src.services import background_tasks as _bt
    _bt.finish_task(
        task_id,
        result_url=url_for('main.lessons', path_id=path_id_val),
        label=f"Lessons ready: {(study_path.get('title') or learning_goal or '')[:80]}",
        path_id=path_id_val or '',
    )
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
    from datetime import datetime, timezone

    from src import db
    from src.models import StudyPath
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
    # No path_id means the user hit the bare nav URL — the dashboard is
    # the canonical "list of my lessons" page (grouped by Active /
    # Completed / Cancelled with View Lessons buttons per path).
    # Redirect there instead of silently grabbing the most recent active
    # path, which stranded users whose most recent path was completed.
    if not path_id:
        return redirect(url_for('main.dashboard'))
    lessons_data = get_lessons(current_user, path_id=path_id)
    if not lessons_data:
        flash('No lessons found for this study path.', 'info')
        return redirect(url_for('main.dashboard'))

    for i, lesson in enumerate(lessons_data):
        lesson['unlocked'] = True
        if i > 0:
            prev = lessons_data[i - 1]
            if not prev.get('passed', False):
                lesson['unlocked'] = False

    # Resolve the parent StudyPath's status so the template can show the
    # correct path-level action buttons (Mark Complete / Cancel / Back to
    # Completed tab) instead of the legacy "Back to Results" / "Start Over"
    # pair that bounced users through an empty session to /index.
    from src.models import StudyPath
    path_status = PATH_STATUS_ACTIVE
    all_passed = bool(lessons_data) and all(
        l.get('passed', False) for l in lessons_data
    )
    if path_id:
        sp = StudyPath.query.filter_by(
            id=path_id, user_id=current_user.id
        ).first()
        if sp:
            path_status = sp.status

    return render_template('lessons.html',
                           lessons=lessons_data,
                           pass_threshold=PASS_THRESHOLD,
                           path_id=path_id,
                           path_status=path_status,
                           all_passed=all_passed)


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
    This replaces the previous cache-based signal (JS checking ``data.done`` / ``data.stage >= 4``),
    which had a race condition.

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
    checkpoint_answers = data.get('checkpoint_answers', {}) or {}

    # ── Persisted checkpoint answers across sessions ─────────────────────
    # Checkpoint answers are graded formative-style as the user advances
    # through the deck. Because the deck's JS checkpointAnswers map lives
    # only in memory, a user who exits mid-lesson (after answering some
    # checkpoints) and later resumes would otherwise lose those answers —
    # the final-quiz grade would then count every unsubmitted checkpoint
    # as wrong, failing a user who actually answered all checkpoints
    # correctly. To survive a page reload we persist each answered
    # checkpoint into lesson['checkpoint_user_answers'] (a {slide_index:
    # value} map on the JSON content_data — no schema change).
    #
    # On the final-quiz submission we merge the persisted map with the
    # freshly-submitted one (fresh wins) so resumers get credit for the
    # checkpoints they answered in a prior session.
    persisted_cp_answers = lesson.get('checkpoint_user_answers', {}) or {}

    # ── Final-quiz vs checkpoint-only grading ─────────────────────────────
    # The deck calls /grade twice:
    #   (a) Per-checkpoint formative grades — `answers` is empty/absent,
    #       only `checkpoint_answers` carries the single checkpoint being
    #       answered. These MUST NOT flip completed/score/passed, otherwise
    #       a user who exits mid-lesson returns to a "Retry Available /
    #       Retake Lesson" card that regenerates the module and resets
    #       deck_position, discarding their progress.
    #   (b) The final-quiz submission — `answers` carries the per-question
    #       quiz answers (plus any accumulated checkpoint_answers). This is
    #       the only call that marks the lesson complete.
    # Edge case: a lesson with zero quiz questions has no "final quiz" in
    # the deck, so we fall back to the legacy behavior (any grade POST
    # finalizes the lesson) to avoid stranding a lesson that can never be
    # marked complete.
    is_final_submission = bool(answers) or len(quiz_questions) == 0

    # Merge persisted answers for grading. Fresh submissions take
    # precedence so a user who re-answers a checkpoint on resume overrides
    # their earlier choice. checkpoint_answers keys arrive as strings
    # (JSON object keys) — normalize so lookup against the checkpoints
    # dict (whose keys are also strings) is consistent.
    if is_final_submission:
        effective_cp_answers = dict(persisted_cp_answers)
        effective_cp_answers.update(
            {str(k): v for k, v in checkpoint_answers.items()}
        )
    else:
        effective_cp_answers = checkpoint_answers

    total_points = len(quiz_questions) + len(checkpoints)
    earned_points = 0
    quiz_results = []

    for i, question in enumerate(quiz_questions):
        if question['type'] == 'fill_blank':
            user_answer = fill_blank_answers.get(question['id'], answers[i] if i < len(answers) else None)
        else:
            user_answer = answers[i] if i < len(answers) else None
        correct = grade_single_question(question, user_answer)
        if correct:
            earned_points += 1
        quiz_results.append({
            'id': question['id'],
            'type': question['type'],
            'prompt': question['prompt'],
            'user_answer': user_answer,
            'correct_answer': get_correct_answer(question),
            'correct': correct,
            'explanation': question.get('explanation', '')
        })

    checkpoint_results = []
    for slide_idx, cp in checkpoints.items():
        user_cp = effective_cp_answers.get(slide_idx)
        cp_correct = grade_single_question(cp, user_cp)
        if cp_correct:
            earned_points += 1
        checkpoint_results.append({
            'slide_index': slide_idx,
            'prompt': cp.get('prompt', ''),
            'user_answer': user_cp,
            'correct_answer': get_correct_answer(cp),
            'correct': cp_correct,
            'explanation': cp.get('explanation', '')
        })

    if total_points == 0:
        total_points = 1
    score_pct = round((earned_points / total_points) * 100)
    passed = score_pct >= PASS_THRESHOLD

    if is_final_submission:
        lessons_data[module_index]['completed'] = True
        lessons_data[module_index]['score'] = score_pct
        lessons_data[module_index]['passed'] = passed
        save_lessons(lessons_data, current_user, path_id=path_id)

        # Memory: record quiz outcome (fix: lessons store
        # 'module_title', not 'title' — the old lookup always wrote '').
        mod = lessons_data[module_index] if isinstance(lessons_data[module_index], dict) else {}
        module_title = mod.get('module_title') or mod.get('title') or f'Module {module_index + 1}'
        outcome = 'passed' if passed else 'did not pass'
        _store_mascot_memory(
            current_user.id, 'episodic',
            f"{outcome.capitalize()} quiz for '{module_title}' "
            f"with {score_pct}%"
        )
        # Struggle / mastery signals feed the next narration intro via
        # tts_persona filtering (voice-pref echoes are dropped there).
        try:
            if not passed and score_pct < 50:
                _store_mascot_memory(
                    current_user.id, 'semantic',
                    f"Struggling with '{module_title}' — needs simpler review",
                )
            elif passed and score_pct >= 90:
                _store_mascot_memory(
                    current_user.id, 'episodic',
                    f"Mastered '{module_title}' — ready for follow-ups",
                )
        except Exception:
            pass
    else:
        # Persist the answered checkpoint(s) so a resumed session can
        # credit them on the final-quiz grade. Only record checkpoints
        # that actually appear in the lesson's checkpoints dict (defensive
        # guard against stray/legacy keys).
        new_persisted = dict(persisted_cp_answers)
        for k, v in checkpoint_answers.items():
            if str(k) in checkpoints:
                new_persisted[str(k)] = v
        if new_persisted != persisted_cp_answers:
            lessons_data[module_index]['checkpoint_user_answers'] = (
                new_persisted
            )
            save_lessons(lessons_data, current_user, path_id=path_id)

    resp = {
        'score': score_pct,
        'passed': passed,
        'threshold': PASS_THRESHOLD,
        'earned': earned_points,
        'total': total_points,
        'quiz_results': quiz_results,
        'checkpoint_results': checkpoint_results,
    }
    # Spoken results: synthesize the lesson_complete announcement inline
    # so the deck can play it the moment results render (zero gap). This
    # trades ~1-4s of grade latency (edge-tts, cached by text+speaker) for
    # no second round-trip and no interruption of results audio — the
    # results-slot narration is suppressed client-side when audio_url is
    # present. Any failure degrades to available-without-url and the
    # client falls back to POST /tts/announce, then to results audio.
    # Grading itself never fails because of TTS.
    try:
        tts_on = bool(getattr(current_user, 'tts_enabled', False))
    except Exception:
        tts_on = False
    if is_final_submission:
        resp['announcement'] = {
            'available': bool(tts_on),
            'kind': 'lesson_complete',
        }
        if tts_on:
            try:
                from src.services.tts_announcement import (
                    build_announcement_text,
                    check_rate_limit,
                )
                _sugg = None
                _sugg_external = False
                try:
                    from src.models import Suggestion as _Sug
                    _row = _Sug.query.filter_by(
                        study_path_id=path_id, user_id=current_user.id,
                        status='pending',
                    ).order_by(_Sug.created_at.asc()).first()
                    if _row:
                        _sugg = {'title': _row.title, 'reason': _row.reason or ''}
                        _sugg_external = bool(getattr(_row, 'is_external', False))
                except Exception:
                    _sugg = None
                if check_rate_limit(f"grade:{current_user.id}"):
                    _mod = lessons_data[module_index] if isinstance(lessons_data[module_index], dict) else {}
                    _mtitle = _mod.get('module_title') or _mod.get('title') or f'Module {module_index + 1}'
                    _text = build_announcement_text(
                        kind='lesson_complete',
                        display_name=getattr(current_user, 'display_name', 'learner'),
                        module_title=_mtitle,
                        score=score_pct,
                        passed=passed,
                        suggestion=_sugg,
                        is_external=_sugg_external,
                    )
                    from src.services.tts_service import generate_announcement_audio
                    _speaker = getattr(current_user, 'tts_speaker', DEFAULT_TTS_SPEAKER) or DEFAULT_TTS_SPEAKER
                    _result = generate_announcement_audio(current_user.id, _text, _speaker)
                    _audio_url = url_for('main.tts_announcement_audio', ann_id=_result['ann_id'])
                    if path_id:
                        _audio_url += f"?path_id={path_id}"
                    resp['announcement']['text'] = _result['text']
                    resp['announcement']['audio_url'] = _audio_url
            except Exception as e:
                logger.warning("Inline grade announcement failed: %s", str(e))
    return jsonify(resp)


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
    retake_digest = _resolve_content_digest(path_id=path_id)
    retriever = _build_retriever(goal, texts, hashes_data, names_data,
                                 content_digest=retake_digest)

    difficulty = lesson.get('difficulty', DEFAULT_DIFFICULTY)
    tts_enabled = lesson.get('tts_enabled', False)
    tts_speaker = lesson.get('tts_speaker', DEFAULT_TTS_SPEAKER) or DEFAULT_TTS_SPEAKER
    username = current_user.display_name
    prev_score = lesson.get('score')
    try:
        from src.services.mascot_memory import get_memories as _get_memories
        learner_memories = [
            m for m in _get_memories(current_user.id, limit=10)
            if isinstance(m, dict) and (m.get('content') or '').strip()
        ]
    except Exception:
        learner_memories = []

    artifacts = build_module_artifacts(
        {'title': module_title},
        goal,
        retriever,
        existing_slides=slides,
        difficulty=difficulty,
        tts_enabled=tts_enabled,
        username=username,
        tts_speaker=tts_speaker,
        learner_memories=learner_memories,
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
    # Clear any persisted checkpoint answers from the prior attempt so the
    # retake starts with a clean slate (the regenerated checkpoints have
    # new prompts/options and the old answers no longer apply).
    lessons_data[module_index].pop('checkpoint_user_answers', None)
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
    # Memory: retakes signal struggle — the next narration intro can
    # acknowledge the retry instead of sounding like a first run.
    try:
        prev_txt = f" after scoring {prev_score}%" if prev_score is not None else ""
        _store_mascot_memory(
            current_user.id, 'episodic',
            f"Retaking '{module_title}'{prev_txt}",
        )
    except Exception:
        pass
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
    try:
        slide_index = int(data.get('slide_index', 0))
    except (TypeError, ValueError):
        slide_index = 0
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


@bp.route('/tts/announce', methods=['POST'])
@login_required
def tts_announce():
    """Generate a short on-demand TTS announcement (Stage 2).

    Body: { path_id?, module_index?, kind: lesson_complete|suggestion,
            suggestion?: {title, reason} }
    - lesson_complete uses the graded module's title/score when
      module_index is given, else the most recent completed module.
    - suggestion prefers the caller-supplied suggestion (the Keep
      Learning card already fetched it), else the oldest pending
      Suggestion row. No LLM call happens here.
    """
    from src.services.tts_announcement import (
        build_announcement_text,
        check_rate_limit,
    )
    data = request.get_json(silent=True) or {}
    kind = str(data.get('kind', 'lesson_complete') or 'lesson_complete')
    if kind not in ('lesson_complete', 'suggestion'):
        return jsonify({'error': 'Invalid kind'}), 400
    if not getattr(current_user, 'tts_enabled', False):
        return jsonify({'error': 'TTS disabled'}), 404
    if not check_rate_limit(current_user.id):
        return jsonify({'error': 'Rate limited, try in 60s'}), 429

    path_id = data.get('path_id') or _resolve_path_id() or get_most_recent_active_path_id()
    try:
        module_index = data.get('module_index', None)
        module_index = int(module_index) if module_index is not None else None
    except (TypeError, ValueError):
        module_index = None

    module_title = None
    score = None
    passed = None
    try:
        lessons_data = get_lessons(current_user, path_id=path_id) if path_id else []
    except Exception:
        lessons_data = []
    if module_index is not None and lessons_data and 0 <= module_index < len(lessons_data):
        mod = lessons_data[module_index] or {}
        module_title = mod.get('module_title') or mod.get('title')
        score = mod.get('score')
        passed = mod.get('passed')
    elif kind == 'lesson_complete' and lessons_data:
        # Most recent completed module, newest first.
        for mod in reversed(lessons_data):
            if mod.get('completed'):
                module_title = mod.get('module_title') or mod.get('title')
                score = mod.get('score')
                passed = mod.get('passed')
                break

    suggestion = None
    sugg_external = bool((data.get('suggestion') or {}).get('is_external', False)) \
        if isinstance(data.get('suggestion'), dict) else False
    if isinstance(data.get('suggestion'), dict) and str(data['suggestion'].get('title', '')).strip():
        suggestion = {
            'title': str(data['suggestion'].get('title', ''))[:200],
            'reason': str(data['suggestion'].get('reason', ''))[:1000],
        }
    elif kind in ('lesson_complete', 'suggestion') and path_id:
        try:
            from src.models import Suggestion as _Sug
            row = _Sug.query.filter_by(
                study_path_id=path_id, user_id=current_user.id, status='pending',
            ).order_by(_Sug.created_at.asc()).first()
            if row:
                suggestion = {'title': row.title, 'reason': row.reason or ''}
                sugg_external = bool(getattr(row, 'is_external', False))
        except Exception:
            suggestion = None

    text = build_announcement_text(
        kind=kind,
        display_name=getattr(current_user, 'display_name', 'learner'),
        module_title=module_title,
        score=score,
        passed=passed,
        suggestion=suggestion,
        is_external=sugg_external,
    )
    speaker = getattr(current_user, 'tts_speaker', DEFAULT_TTS_SPEAKER) or DEFAULT_TTS_SPEAKER
    try:
        from src.services.tts_service import generate_announcement_audio
        result = generate_announcement_audio(current_user.id, text, speaker)
    except Exception as e:
        logger.warning("TTS announce synthesis failed: %s", str(e))
        return jsonify({'ok': False, 'pending': True, 'text': text}), 202
    audio_url = url_for('main.tts_announcement_audio', ann_id=result['ann_id'])
    if path_id:
        audio_url += f"?path_id={path_id}"
    return jsonify({
        'ok': True,
        'text': result['text'],
        'audio_url': audio_url,
        'from_cache': result['from_cache'],
    })


@bp.route('/tts/announcements/<ann_id>.mp3')
@login_required
def tts_announcement_audio(ann_id):
    """Serve a user's announcement MP3 (per-user isolated)."""
    from src.services.tts_service import get_announcement_path
    full_path = get_announcement_path(current_user.id, ann_id or '')
    if not full_path:
        return ('', 404)
    from flask import send_file
    return send_file(str(full_path), mimetype='audio/mpeg', conditional=True)


@bp.route('/figures/<file_hash>/<filename>')
@login_required
def serve_figure(file_hash, filename):
    """Serve a persisted source-figure thumbnail.

    Figures are content-addressed by upload file hash (shared across
    users/paths like Chroma collections), so authorization checks that
    the hash appears in the ``file_hashes`` of ANY StudyPath owned by the
    current user — never deleted by per-path lifecycle routes.
    """
    import json as _json
    import os as _os
    if (".." in filename or "/" in filename or "\\" in filename
            or not file_hash or not filename):
        return ('', 404)
    try:
        from src.models import StudyPath as _StudyPath
        allowed = False
        paths = _StudyPath.query.filter_by(user_id=current_user.id).all()
        for p in paths:
            try:
                hashes = _json.loads(p.file_hashes) if p.file_hashes else []
            except (TypeError, ValueError):
                continue
            if file_hash in hashes:
                allowed = True
                break
        if not allowed:
            return ('', 404)
        from src.services.figure_store import FIGURES_DIR as _FIGURES_DIR
        full_path = _os.path.join(_FIGURES_DIR, file_hash, filename)
        if not _os.path.isfile(full_path):
            return ('', 404)
        from flask import send_file as _send_file
        return _send_file(full_path, mimetype='image/png', conditional=True)
    except Exception as e:
        logger.warning("serve_figure failed for %s: %s", str(file_hash)[:8], str(e))
        return ('', 404)


def _suggestion_path_or_404(path_id):
    """Return the user's StudyPath or a (json, 404) tuple."""
    from src.models import StudyPath
    path = StudyPath.query.filter_by(id=path_id, user_id=current_user.id).first()
    if not path:
        return None, (jsonify({'error': 'Study path not found'}), 404)
    return path, None


@bp.route('/suggestions', methods=['GET'])
@login_required
def list_suggestions():
    """Return pending suggestions + coverage state for a path.

    Order: cached pending → fresh internal (document-grounded) →
    external web (only when internal empty + all passed + public topic
    + WEB_SEARCH_ENABLED). External rows carry is_external/source_urls.
    """
    import json as _json
    path_id = _resolve_path_id()
    path, err = _suggestion_path_or_404(path_id)
    if err:
        return err
    from src.models import Suggestion

    def _serialize(s):
        try:
            urls = _json.loads(s.source_urls) if s.source_urls else []
        except (TypeError, ValueError):
            urls = []
        return {'id': s.id, 'title': s.title, 'reason': s.reason,
                'source_refs': s.source_refs, 'status': s.status,
                'is_external': bool(getattr(s, 'is_external', False)),
                'source_urls': urls if isinstance(urls, list) else []}

    pending = Suggestion.query.filter_by(
        study_path_id=path.id, user_id=current_user.id,
        status='pending',
    ).order_by(Suggestion.created_at.asc()).all()
    if pending:
        lessons_data = get_lessons(current_user, path_id=path.id)
        all_passed = bool(lessons_data) and all(l.get('passed') for l in lessons_data)
        return jsonify({
            'suggestions': [_serialize(s) for s in pending],
            'all_covered': all_passed,
        })

    lessons_data = get_lessons(current_user, path_id=path.id)
    try:
        modules = _json.loads(path.modules_json) if path.modules_json else []
    except (TypeError, ValueError):
        modules = []
    # Overlay live pass/score state onto the planned modules.
    by_title = {}
    for lesson in lessons_data:
        by_title[(lesson.get('module_title') or '').strip().lower()] = lesson
    for m in modules:
        live = by_title.get((m.get('title') or '').strip().lower(), {})
        m['passed'] = bool(live.get('passed'))
        m['completed'] = bool(live.get('completed'))
        m['score'] = live.get('score')
    try:
        relevance = _json.loads(path.relevance_json) if path.relevance_json else {}
    except (TypeError, ValueError):
        relevance = {}
    missing = relevance.get('missing_material', '') if isinstance(relevance, dict) else ''

    from src.services.suggest_next import compute_suggestions
    computed = compute_suggestions(
        path.learning_goal or '', modules,
        summary=path.summary_text or '', missing_material=missing or '',
    )
    from src import db as _db
    rows = []
    for item in computed.get('suggestions', []):
        row = Suggestion(
            user_id=current_user.id, study_path_id=path.id,
            title=item['title'], reason=item.get('reason', ''),
            source_refs=item.get('source_refs', ''), status='pending',
            is_external=False, source_urls='[]',
        )
        _db.session.add(row)
        rows.append(row)
    if rows:
        _db.session.commit()
    all_passed = bool(lessons_data or modules) and all(
        m.get('passed') for m in modules
    ) if (lessons_data or modules) else False
    if rows:
        return jsonify({
            'suggestions': [_serialize(s) for s in rows],
            'all_covered': False,
            'source': 'internal',
        })

    # Internal exhausted → external web branch (opt-in, fail-closed).
    # Only when every planned module is passed; proprietary topics,
    # disabled flag, missing key, or any web failure return all_covered.
    if not all_passed:
        return jsonify({'suggestions': [], 'all_covered': False, 'source': 'internal'})
    try:
        file_names = _json.loads(path.file_names) if path.file_names else []
    except (TypeError, ValueError):
        file_names = []
    if not isinstance(file_names, list):
        file_names = []
    from src.services.suggest_external import compute_external_suggestions
    external = compute_external_suggestions(
        path.learning_goal or '', modules,
        summary=path.summary_text or '', file_names=file_names,
    )
    ext_rows = []
    for item in (external.get('suggestions', []) or []):
        try:
            urls_json = _json.dumps(item.get('source_urls', []) or [])
        except (TypeError, ValueError):
            urls_json = '[]'
        row = Suggestion(
            user_id=current_user.id, study_path_id=path.id,
            title=item['title'], reason=item.get('reason', ''),
            source_refs=item.get('source_refs', ''), status='pending',
            is_external=True, source_urls=urls_json,
        )
        _db.session.add(row)
        ext_rows.append(row)
    if ext_rows:
        _db.session.commit()
        return jsonify({
            'suggestions': [_serialize(s) for s in ext_rows],
            'all_covered': False,
            'source': 'web',
        })
    return jsonify({
        'suggestions': [],
        'all_covered': True,
        'source': external.get('source', 'none'),
    })


@bp.route('/suggestions/dismiss', methods=['POST'])
@login_required
def dismiss_suggestion():
    """Dismiss a pending suggestion (hides it permanently)."""
    data = request.get_json(silent=True) or {}
    suggestion_id = data.get('suggestion_id', '')
    from src.models import Suggestion
    row = Suggestion.query.filter_by(id=suggestion_id, user_id=current_user.id).first()
    if not row:
        return jsonify({'error': 'Suggestion not found'}), 404
    from src import db as _db
    row.status = 'dismissed'
    _db.session.commit()
    return jsonify({'success': True})


@bp.route('/suggestions/accept', methods=['POST'])
@login_required
def accept_suggestion():
    """Generate a full module for an accepted suggestion.

    Reuses the standard lesson machinery (retriever → artifacts → save →
    TTS worker) scoped to the suggested topic, appended as a new module so
    sequential gating keeps working. Returns a deck redirect.
    """
    import json as _json
    data = request.get_json(silent=True) or {}
    suggestion_id = data.get('suggestion_id', '')
    from src.models import Suggestion
    row = Suggestion.query.filter_by(id=suggestion_id, user_id=current_user.id).first()
    if not row or row.status != 'pending':
        return jsonify({'error': 'Suggestion not found or already handled'}), 404
    path_id = row.study_path_id
    path, err = _suggestion_path_or_404(path_id)
    if err:
        return err

    lessons_data = get_lessons(current_user, path_id=path.id) or []
    new_index = len(lessons_data)
    goal = path.learning_goal or ''
    is_external = bool(getattr(row, 'is_external', False))
    if is_external:
        # Web-grounded retriever (URL-capped): fetch stored verbatim URLs
        # (max 2, 6k chars each). No doc text ever sent to the web here —
        # we only READ the previously stored search results.
        try:
            stored_urls = _json.loads(row.source_urls) if row.source_urls else []
        except (TypeError, ValueError):
            stored_urls = []
        if not isinstance(stored_urls, list):
            stored_urls = []

        def _web_retrieve(query: str, exclude_chunks: set = None):
            from urllib.parse import urlparse as _urlparse

            from src.services.web_search_service import web_fetch as _fetch
            parts, sources = [], []
            for u in (stored_urls or [])[:2]:
                if not isinstance(u, str) or not u.startswith(('http://', 'https://')):
                    continue
                try:
                    body = _fetch(u) or ''
                except Exception:
                    body = ''
                if not body.strip():
                    continue
                parts.append(f"Source: {u}\n{body[:6000]}")
                try:
                    domain = _urlparse(u).netloc or u
                except Exception:
                    domain = u
                sources.append({'filename': domain, 'url': u,
                                'text': body[:2000], 'chunk_id': f"web:{u[:60]}"})
            # Always include the suggestion reason so generation is
            # grounded even when fetches fail (general-education fallback
            # in lesson_generator handles empty context).
            head = f"Suggested topic: {row.title}. {row.reason or ''}".strip()
            context = (head + '\n\n' + '\n\n'.join(parts))[:12000] if parts else head
            return {"context_text": context, "sources": sources}

        retriever = _web_retrieve
    else:
        retriever = _build_retriever(goal, [], _resolve_hashes(), _resolve_filenames(),
                                     content_digest='')
    difficulty = getattr(current_user, 'lesson_difficulty', DEFAULT_DIFFICULTY) or DEFAULT_DIFFICULTY
    tts_enabled = getattr(current_user, 'tts_enabled', False)
    tts_speaker = getattr(current_user, 'tts_speaker', DEFAULT_TTS_SPEAKER) or DEFAULT_TTS_SPEAKER
    try:
        from src.services.mascot_memory import get_memories as _get_memories
        learner_memories = [
            m for m in _get_memories(current_user.id, limit=10)
            if isinstance(m, dict) and (m.get('content') or '').strip()
        ]
    except Exception:
        learner_memories = []

    try:
        artifacts = build_module_artifacts(
            {'title': row.title},
            goal,
            retriever,
            difficulty=difficulty,
            tts_enabled=tts_enabled,
            username=current_user.display_name,
            tts_speaker=tts_speaker,
            next_module_title=None,
            is_last_module=True,
            path_id=path.id,
            module_index=new_index,
            used_chunk_ids=set(),
            learner_memories=learner_memories,
        )
    except Exception as e:
        logger.error("Suggested-module generation failed for '%s': %s", row.title, str(e))
        return jsonify({'error': 'Could not generate materials for this suggestion. Please try again.'}), 500

    lessons_data.append({
        'index': new_index,
        'module_title': row.title,
        'estimated_effort': 'N/A',
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
        'passed': False,
    })
    save_lessons(lessons_data, current_user, path_id=path.id)

    # Keep the durable plan snapshot aware of the added module.
    try:
        modules = _json.loads(path.modules_json) if path.modules_json else []
    except (TypeError, ValueError):
        modules = []
    modules.append({'title': row.title, 'estimated_effort': 'N/A'})
    path.modules_json = _json.dumps(modules)

    from src import db as _db
    row.status = 'accepted'
    _db.session.commit()

    _store_mascot_memory(current_user.id, 'episodic', f"Accepted suggestion '{row.title}'")

    if tts_enabled and path.id:
        try:
            from src.services.tts_worker import spawn_tts_background_task
            spawn_tts_background_task(
                flask_app=current_app._get_current_object(),
                user_id=current_user.id,
                path_id=path.id,
                task_id=session.sid,
            )
        except Exception as e:
            logger.warning("TTS background thread failed to spawn for suggestion: %s", str(e))

    return jsonify({
        'success': True,
        'redirect': url_for('main.lesson_deck', module_index=new_index, path_id=path.id),
    })


def get_most_recent_active_path_id() -> str:
    """Return the user's most recent active StudyPath.id, or empty string.

    Used as a fallback when audio routes are hit without an explicit
    path_id in the URL. Returns empty string when the user has no active
    paths so the audio route can return a clean 404.
    """
    path = get_most_recent_active_path(current_user)
    return path.id if path else ''
