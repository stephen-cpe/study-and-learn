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
    entry = dict(stage_list[0])
    entry['done'] = False
    _cache.set(task_id, entry)
    _cache.set(task_id + ':stages', stage_list)
    logger.info(f"[progress] create_task: {task_id} → stage 0")
    return task_id


def update_progress(task_id, stage):
    if not _cache.has(task_id):
        logger.warning(f"[progress] update skipped — task {task_id} not found")
        return
    stage_list = _cache.get(task_id + ':stages') or STAGES
    if 0 <= stage < len(stage_list):
        entry = dict(stage_list[stage])
        entry['done'] = False
        _cache.set(task_id, entry)
        logger.info(f"[progress] update: {task_id} → stage {stage} ({stage_list[stage]['label']})")


def update_cosmetic(task_id, **fields):
    """Merge cosmetic fields (label/mascot/pct/mascot_state) into the
    existing task entry without changing its stage number or stage list.

    Used by background components (e.g. the TTS worker) that need to
    publish UI progress against the same task_id the request handler
    created, but with their own labels and mascot messages. The
    ``done`` flag is preserved; ``stage`` and any other non-cosmetic
    fields are preserved.

    Accepted keyword arguments: label, mascot, pct, mascot_state. Any
    other keys are ignored.

    A no-op when the task_id is unknown (e.g. already cleaned up by the
    request handler) or when no cosmetic fields are provided.
    """
    cosmetic_keys = {'label', 'mascot', 'pct', 'mascot_state'}
    payload = {k: v for k, v in fields.items() if k in cosmetic_keys}
    if not payload:
        return
    if not _cache.has(task_id):
        logger.info(f"[progress] update_cosmetic skipped — task {task_id} not found")
        return
    data = _cache.get(task_id) or {}
    data.update(payload)
    _cache.set(task_id, data)
    logger.info(f"[progress] update_cosmetic: {task_id} → {payload}")


def get_progress(task_id):
    data = _cache.get(task_id)
    if data is None:
        logger.info(f"[progress] get: {task_id} → None")
        return None
    logger.info(f"[progress] get: {task_id} → stage {data.get('stage', '?')}")
    return data


def cleanup_task(task_id):
    _cache.delete(task_id)
    logger.info(f"[progress] cleanup: {task_id} deleted")
