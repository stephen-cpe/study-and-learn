import os
import logging
import uuid
from cachelib import FileSystemCache

logger = logging.getLogger(__name__)

_cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'progress_cache')
os.makedirs(_cache_dir, exist_ok=True)

_cache = FileSystemCache(cache_dir=_cache_dir, threshold=500, default_timeout=900)

GENERATE_STAGES = [
    {"stage": 0, "label": "Parsing documents", "pct": 0, "mascot": "Parsing docs...", "mascot_state": "busy"},
    {"stage": 1, "label": "Chunking & embedding", "pct": 25, "mascot": "Chunking + indexing...", "mascot_state": "busy"},
    {"stage": 2, "label": "Retrieving context", "pct": 50, "mascot": "Scanning concepts...", "mascot_state": "busy"},
    {"stage": 3, "label": "Generating lessons", "pct": 75, "mascot": "Building lesson...", "mascot_state": "busy"},
    {"stage": 4, "label": "Finalizing", "pct": 100, "mascot": "Polishing...", "mascot_state": "happy"},
]

PROCESS_STAGES = [
    {"stage": 0, "label": "Uploading files",          "pct": 0,   "mascot": "Receiving files...", "mascot_state": "busy"},
    {"stage": 1, "label": "Parsing documents",         "pct": 10,  "mascot": "Parsing docs...", "mascot_state": "busy"},
    {"stage": 2, "label": "OCR scanning pages",        "pct": 25,  "mascot": "OCR scan...", "mascot_state": "busy"},
    {"stage": 3, "label": "Analyzing figures",         "pct": 40,  "mascot": "Analyzing figs...", "mascot_state": "busy"},
    {"stage": 4, "label": "Building knowledge index",  "pct": 55,  "mascot": "Building index...", "mascot_state": "busy"},
    {"stage": 5, "label": "Generating summary",        "pct": 70,  "mascot": "Summarizing...", "mascot_state": "busy"},
    {"stage": 6, "label": "Checking relevance",        "pct": 80,  "mascot": "Relevance check...", "mascot_state": "busy"},
    {"stage": 7, "label": "Creating study path",       "pct": 90,  "mascot": "Building path...", "mascot_state": "busy"},
    {"stage": 8, "label": "Complete",                  "pct": 100, "mascot": "All done!", "mascot_state": "happy"},
]

STAGES = GENERATE_STAGES


def create_task(task_id=None, stages=None):
    if task_id is None:
        task_id = str(uuid.uuid4())
    stage_list = stages or STAGES
    _cache.set(task_id, dict(stage_list[0]))
    _cache.set(task_id + ':stages', stage_list)
    logger.info(f"[progress] create_task: {task_id} → stage 0")
    return task_id


def update_progress(task_id, stage):
    if not _cache.has(task_id):
        logger.warning(f"[progress] update skipped — task {task_id} not found")
        return
    stage_list = _cache.get(task_id + ':stages') or STAGES
    if 0 <= stage < len(stage_list):
        _cache.set(task_id, dict(stage_list[stage]))
        logger.info(f"[progress] update: {task_id} → stage {stage} ({stage_list[stage]['label']})")


def get_progress(task_id):
    data = _cache.get(task_id)
    if data is None:
        logger.info(f"[progress] get: {task_id} → None")
        return None
    logger.info(f"[progress] get: {task_id} → stage {data.get('stage', '?')}")
    return data


def complete_task(task_id):
    stage_list = _cache.get(task_id + ':stages') or STAGES
    if _cache.has(task_id):
        _cache.set(task_id, dict(stage_list[-1]))
        logger.info(f"[progress] complete: {task_id} → stage {len(stage_list) - 1}")


def cleanup_task(task_id):
    _cache.delete(task_id)
    logger.info(f"[progress] cleanup: {task_id} deleted")
