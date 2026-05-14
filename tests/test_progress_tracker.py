import pytest
from src.services.progress_tracker import (
    STAGES, create_task, update_progress, get_progress,
    complete_task, cleanup_task
)


def test_stages_enumeration():
    assert len(STAGES) == 5
    for s in STAGES:
        assert 'stage' in s
        assert 'label' in s
        assert 'pct' in s
        assert 'mascot' in s


def test_stages_have_correct_pct():
    assert STAGES[0]['pct'] == 0
    assert STAGES[1]['pct'] == 25
    assert STAGES[2]['pct'] == 50
    assert STAGES[3]['pct'] == 75
    assert STAGES[4]['pct'] == 100


def test_stages_have_labels():
    assert STAGES[0]['label'] == 'Parsing documents'
    assert STAGES[1]['label'] == 'Chunking & embedding'
    assert STAGES[2]['label'] == 'Retrieving context'
    assert STAGES[3]['label'] == 'Generating lessons'
    assert STAGES[4]['label'] == 'Finalizing'


def test_stages_have_mascot_messages():
    assert 'Reading through your uploaded materials' in STAGES[0]['mascot']
    assert 'Splitting content into manageable sections' in STAGES[1]['mascot']
    assert 'Scanning for important concepts' in STAGES[2]['mascot']
    assert 'Crafting your interactive lesson' in STAGES[3]['mascot']
    assert 'Polishing everything up' in STAGES[4]['mascot']


def test_create_task():
    task_id = create_task()
    assert task_id is not None
    assert isinstance(task_id, str)
    assert len(task_id) > 0
    progress = get_progress(task_id)
    assert progress is not None
    assert progress['stage'] == 0
    assert progress['pct'] == 0


def test_update_progress():
    task_id = create_task()
    update_progress(task_id, 2)
    progress = get_progress(task_id)
    assert progress['stage'] == 2
    assert progress['pct'] == 50
    assert progress['label'] == 'Retrieving context'
    assert 'Scanning for important concepts' in progress['mascot']


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


def test_cleanup_task():
    task_id = create_task()
    assert get_progress(task_id) is not None
    cleanup_task(task_id)
    assert get_progress(task_id) is None
