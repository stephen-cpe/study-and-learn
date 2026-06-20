import pytest
from src.services.progress_tracker import (
    STAGES, GENERATE_STAGES, PROCESS_STAGES,
    create_task, update_progress, update_cosmetic, mark_error, get_progress,
    cleanup_task,
)


def test_stages_enumeration():
    assert len(GENERATE_STAGES) == 5
    for s in GENERATE_STAGES:
        assert 'stage' in s
        assert 'label' in s
        assert 'pct' in s
        assert 'mascot' in s


def test_generate_stages_have_correct_pct():
    assert GENERATE_STAGES[0]['pct'] == 0
    assert GENERATE_STAGES[1]['pct'] == 25
    assert GENERATE_STAGES[2]['pct'] == 50
    assert GENERATE_STAGES[3]['pct'] == 75
    assert GENERATE_STAGES[4]['pct'] == 100


def test_generate_stages_have_labels():
    assert GENERATE_STAGES[0]['label'] == 'Parsing documents'
    assert GENERATE_STAGES[1]['label'] == 'Chunking & embedding'
    assert GENERATE_STAGES[2]['label'] == 'Retrieving context'
    assert GENERATE_STAGES[3]['label'] == 'Generating lessons'
    assert GENERATE_STAGES[4]['label'] == 'Finalizing'


def test_generate_stages_have_mascot_messages():
    # New CRT-friendly short messages (must be punchy; see retro.css #speech-bubble).
    assert GENERATE_STAGES[0]['mascot'] == 'Parsing docs...'
    assert GENERATE_STAGES[1]['mascot'] == 'Chunking + indexing...'
    assert GENERATE_STAGES[2]['mascot'] == 'Scanning concepts...'
    assert GENERATE_STAGES[3]['mascot'] == 'Building lesson...'
    assert GENERATE_STAGES[4]['mascot'] == 'Polishing...'


def test_mascot_messages_fit_crt_line():
    """All mascot lines must be short enough to look right inside the
    4:3 CRT speech bubble (one short line, no wrapping)."""
    for s in GENERATE_STAGES + PROCESS_STAGES:
        line = s['mascot']
        assert len(line) <= 28, f'Mascot line too long for CRT bubble: {line!r}'


def test_process_stages_enumeration():
    assert len(PROCESS_STAGES) == 9
    for s in PROCESS_STAGES:
        assert 'stage' in s
        assert 'label' in s
        assert 'pct' in s
        assert 'mascot' in s


def test_process_stages_pct_monotonic():
    pcts = [s['pct'] for s in PROCESS_STAGES]
    assert pcts == sorted(pcts)
    assert pcts[0] == 0
    assert pcts[-1] == 100


def test_process_stages_labels():
    assert PROCESS_STAGES[0]['label'] == 'Uploading files'
    assert PROCESS_STAGES[1]['label'] == 'Parsing documents'
    assert PROCESS_STAGES[2]['label'] == 'OCR scanning pages'
    assert PROCESS_STAGES[3]['label'] == 'Analyzing figures'
    assert PROCESS_STAGES[4]['label'] == 'Building knowledge index'
    assert PROCESS_STAGES[5]['label'] == 'Generating summary'
    assert PROCESS_STAGES[6]['label'] == 'Checking relevance'
    assert PROCESS_STAGES[7]['label'] == 'Creating study path'
    assert PROCESS_STAGES[8]['label'] == 'Complete'


def test_process_stages_mascot_messages():
    assert PROCESS_STAGES[0]['mascot'] == 'Receiving files...'
    assert PROCESS_STAGES[8]['pct'] == 100
    assert PROCESS_STAGES[8]['mascot'] == 'All done!'


def test_stages_alias():
    assert STAGES == GENERATE_STAGES


def test_create_task():
    task_id = create_task()
    assert task_id is not None
    assert isinstance(task_id, str)
    assert len(task_id) > 0
    progress = get_progress(task_id)
    assert progress is not None
    assert progress['stage'] == 0
    assert progress['pct'] == 0


def test_create_task_with_process_stages():
    task_id = create_task(stages=PROCESS_STAGES)
    progress = get_progress(task_id)
    assert progress is not None
    assert progress['stage'] == 0
    assert progress['pct'] == 0
    assert progress['label'] == 'Uploading files'


def test_update_progress():
    task_id = create_task()
    update_progress(task_id, 2)
    progress = get_progress(task_id)
    assert progress['stage'] == 2
    assert progress['pct'] == 50
    assert progress['label'] == 'Retrieving context'
    assert progress['mascot'] == 'Scanning concepts...'


def test_update_progress_process_stages():
    task_id = create_task(stages=PROCESS_STAGES)
    update_progress(task_id, 5)
    progress = get_progress(task_id)
    assert progress['stage'] == 5
    assert progress['pct'] == 70
    assert progress['label'] == 'Generating summary'
    assert progress['mascot'] == 'Summarizing...'


def test_update_progress_bounds():
    task_id = create_task()
    update_progress(task_id, -1)
    progress = get_progress(task_id)
    assert progress['stage'] == 0

    update_progress(task_id, 99)
    progress = get_progress(task_id)
    assert progress['stage'] == 0


def test_update_progress_unknown_task():
    update_progress('bogus', 2)
    assert get_progress('bogus') is None


def test_cleanup_task():
    task_id = create_task()
    assert get_progress(task_id) is not None
    cleanup_task(task_id)
    assert get_progress(task_id) is None


# ── 'done' flag ──────────────────────────────────────────────────────
# The 'done' flag is the canonical "navigate now" signal for the JS
# client. It is set by whichever component finishes last (request
# handler for non-TTS, TTS worker for TTS-enabled) and is independent
# of the stage value. This decouples the redirect from any specific
# stage number, so the request handler and TTS worker can use
# different stage lists without one clobbering the other's progress.

def test_create_task_initializes_done_false():
    """A freshly created task must have done=False, NOT absent.

    The JS client checks ``data.done === true``. If the field were
    absent, the strict-equal check would always fail and the redirect
    would never fire — exactly the bug we are fixing.
    """
    task_id = create_task()
    progress = get_progress(task_id)
    assert progress is not None
    assert 'done' in progress
    assert progress['done'] is False





# ── update_cosmetic ──────────────────────────────────────────────────
# The TTS worker uses update_cosmetic to publish TTS-specific
# bubble/mascot messages against the request handler's task entry
# WITHOUT changing the stage number or the cached stage list. This
# avoids the previous race where the TTS worker's
# create_task(task_id=task_id, stages=TTS_STAGES) overwrote the
# request handler's stage list (max stage 4) with TTS_STAGES
# (max stage 3), causing the JS poll-based redirect to never fire.

def test_update_cosmetic_merges_fields_preserving_stage():
    task_id = create_task()
    update_progress(task_id, 2)  # GENERATE_STAGES[2] = 'Retrieving context'
    update_cosmetic(task_id, label='Recording narration...', mascot='Recording narration...',
                    pct=50, mascot_state='busy')
    progress = get_progress(task_id)
    assert progress['stage'] == 2
    assert progress['label'] == 'Recording narration...'
    assert progress['mascot'] == 'Recording narration...'
    assert progress['pct'] == 50
    assert progress['mascot_state'] == 'busy'
    assert progress['done'] is False


def test_update_cosmetic_ignores_unknown_keys():
    """Non-cosmetic keys (e.g. 'stage', 'foo') must be ignored.

    This prevents accidental stage-number writes that would
    resurrect the original race condition.
    """
    task_id = create_task()
    update_progress(task_id, 3)
    update_cosmetic(task_id, stage=99, foo='bar', label='Updated')
    progress = get_progress(task_id)
    assert progress['stage'] == 3
    assert progress['label'] == 'Updated'
    assert 'foo' not in progress


def test_update_cosmetic_on_unknown_task_is_noop():
    """update_cosmetic on a non-existent task must not raise."""
    update_cosmetic('does-not-exist', label='x', pct=50)


def test_update_cosmetic_with_no_known_keys_is_noop():
    """If no recognized cosmetic keys are provided, do nothing.

    This avoids needless cache writes and keeps the helper safe to
    call with arbitrary user-supplied dicts.
    """
    task_id = create_task()
    original = dict(get_progress(task_id))
    update_cosmetic(task_id, stage=99, foo='bar')
    current = get_progress(task_id)
    assert current['stage'] == original['stage']
    assert current['label'] == original['label']
    assert current['mascot'] == original['mascot']


# ── mark_error ──────────────────────────────────────────────────────
# mark_error is the canonical helper for surfacing failures to the
# user via the mascot (mascot-error.gif) without crashing the request.
# It sets mascot_state='error', a bubble message, and a sticky
# ``error=True`` flag the JS client uses to keep the error GIF visible
# for a short window even if subsequent busy polls arrive.

def test_mark_error_sets_mascot_state_error():
    task_id = create_task()
    mark_error(task_id, mascot_msg='AI unreachable')
    progress = get_progress(task_id)
    assert progress['mascot_state'] == 'error'
    assert progress['mascot'] == 'AI unreachable'
    assert progress['error'] is True


def test_mark_error_preserves_stage_and_done():
    """mark_error must not change the stage number or done flag —
    it only merges cosmetic fields."""
    task_id = create_task()
    update_progress(task_id, 3)
    mark_error(task_id, mascot_msg='fail')
    progress = get_progress(task_id)
    assert progress['stage'] == 3
    assert progress['done'] is False


def test_mark_error_uses_default_message_when_none():
    task_id = create_task()
    mark_error(task_id)
    progress = get_progress(task_id)
    assert progress['mascot_state'] == 'error'
    assert isinstance(progress['mascot'], str)
    assert len(progress['mascot']) > 0


def test_mark_error_sets_optional_pct_and_label():
    task_id = create_task()
    mark_error(task_id, mascot_msg='DB locked', pct=42, label='Error')
    progress = get_progress(task_id)
    assert progress['pct'] == 42
    assert progress['label'] == 'Error'


def test_mark_error_on_unknown_task_is_noop():
    """mark_error must never raise — error handlers cannot themselves
    error. A missing task_id (e.g. already cleaned up) is a no-op."""
    mark_error('does-not-exist', mascot_msg='fail')


def test_mark_error_error_flag_survives_subsequent_busy_cosmetic():
    """The ``error=True`` flag must persist across a subsequent
    update_cosmetic(busy) call — the JS client reads it to keep the
    error GIF sticky. update_cosmetic only overwrites fields it is
    given; if it does not pass ``error``, the flag must remain True."""
    task_id = create_task()
    mark_error(task_id, mascot_msg='AI down')
    # Simulate a background worker publishing a busy cosmetic on the
    # same task_id (e.g. TTS still processing the next module).
    update_cosmetic(task_id, mascot='Encoding audio...', mascot_state='busy', pct=75)
    progress = get_progress(task_id)
    assert progress['error'] is True, (
        "error=True flag was clobbered by a subsequent busy cosmetic — "
        "the JS sticky-error window would break."
    )


def test_update_cosmetic_accepts_error_key():
    """update_cosmetic must accept 'error' as a recognized cosmetic key
    so mark_error can set it via the same merge path."""
    task_id = create_task()
    update_cosmetic(task_id, error=True, mascot_state='error', mascot='fail')
    progress = get_progress(task_id)
    assert progress['error'] is True
    assert progress['mascot_state'] == 'error'
