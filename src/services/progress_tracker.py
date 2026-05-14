import os
import logging
import uuid
from cachelib import FileSystemCache

logger = logging.getLogger(__name__)

_cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'progress_cache')
os.makedirs(_cache_dir, exist_ok=True)

_cache = FileSystemCache(cache_dir=_cache_dir, threshold=500, default_timeout=900)

STAGES = [
    {"stage": 0, "label": "Parsing documents", "pct": 0, "mascot": "Reading through your uploaded materials and extracting text..."},
    {"stage": 1, "label": "Chunking & embedding", "pct": 25, "mascot": "Splitting content into manageable sections and building knowledge maps..."},
    {"stage": 2, "label": "Retrieving context", "pct": 50, "mascot": "Scanning for important concepts and connecting the dots..."},
    {"stage": 3, "label": "Generating lessons", "pct": 75, "mascot": "Crafting your interactive lesson with slides and quizzes..."},
    {"stage": 4, "label": "Finalizing", "pct": 100, "mascot": "Polishing everything up and getting your study path ready..."},
]


def create_task(task_id=None):
    if task_id is None:
        task_id = str(uuid.uuid4())
    _cache.set(task_id, dict(STAGES[0]))
    logger.info(f"[progress] create_task: {task_id} → stage 0")
    return task_id


def update_progress(task_id, stage):
    if not _cache.has(task_id):
        logger.warning(f"[progress] update skipped — task {task_id} not found")
        return
    if 0 <= stage < len(STAGES):
        _cache.set(task_id, dict(STAGES[stage]))
        logger.info(f"[progress] update: {task_id} → stage {stage} ({STAGES[stage]['label']})")


def get_progress(task_id):
    data = _cache.get(task_id)
    if data is None:
        logger.info(f"[progress] get: {task_id} → None")
        return None
    logger.info(f"[progress] get: {task_id} → stage {data.get('stage', '?')}")
    return data


def complete_task(task_id):
    if _cache.has(task_id):
        _cache.set(task_id, dict(STAGES[-1]))
        logger.info(f"[progress] complete: {task_id} → stage 4")


def cleanup_task(task_id):
    _cache.delete(task_id)
    logger.info(f"[progress] cleanup: {task_id} deleted")
