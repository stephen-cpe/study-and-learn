import pytest
from src.services.progress_tracker import (
    STAGES, GENERATE_STAGES, PROCESS_STAGES,
    create_task, update_progress, get_progress,
    complete_task, cleanup_task
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
    assert 'Reading through your uploaded materials' in GENERATE_STAGES[0]['mascot']
    assert 'Splitting content into manageable sections' in GENERATE_STAGES[1]['mascot']
    assert 'Scanning for important concepts' in GENERATE_STAGES[2]['mascot']
    assert 'Crafting your interactive lesson' in GENERATE_STAGES[3]['mascot']
    assert 'Polishing everything up' in GENERATE_STAGES[4]['mascot']


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
    assert 'Receiving your study materials' in PROCESS_STAGES[0]['mascot']
    assert PROCESS_STAGES[8]['pct'] == 100


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
    assert 'Scanning for important concepts' in progress['mascot']


def test_update_progress_process_stages():
    task_id = create_task(stages=PROCESS_STAGES)
    update_progress(task_id, 5)
    progress = get_progress(task_id)
    assert progress['stage'] == 5
    assert progress['pct'] == 70
    assert progress['label'] == 'Generating summary'
    assert 'Summarizing what your materials cover' in progress['mascot']


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


def test_complete_task():
    task_id = create_task()
    complete_task(task_id)
    progress = get_progress(task_id)
    assert progress['stage'] == 4
    assert progress['pct'] == 100


def test_complete_task_process_stages():
    task_id = create_task(stages=PROCESS_STAGES)
    complete_task(task_id)
    progress = get_progress(task_id)
    assert progress['stage'] == 8
    assert progress['pct'] == 100
    assert progress['label'] == 'Complete'


def test_cleanup_task():
    task_id = create_task()
    assert get_progress(task_id) is not None
    cleanup_task(task_id)
    assert get_progress(task_id) is None
