import logging
import os
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
    {"stage": 3, "label": "Generating lessons", "pct": 75, "mascot": "Building your lesson...", "mascot_state": "busy"},
    {"stage": 4, "label": "Finalizing", "pct": 100, "mascot": "All done, {name}!", "mascot_state": "happy"},
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
    {"stage": 8, "label": "Complete",                  "pct": 100, "mascot": "All done, {name}!", "mascot_state": "happy"},
]

STAGES = GENERATE_STAGES


def _resolve_name(text: str, display_name: str) -> str:
    """Replace ``{name}`` placeholders in a mascot message with the
    learner's display name.  Falls back to 'there' if the display name
    is empty (so the message still reads naturally)."""
    if not text:
        return text
    name = display_name or 'there'
    return text.replace('{name}', name)


def create_task(task_id=None, stages=None, display_name=None):
    """Create a progress task.  ``display_name`` is the learner's
    friendly name (nickname/full_name/username) — it's stored on the
    entry so that ``{name}`` placeholders in stage messages can be
    resolved when the task is published."""
    if task_id is None:
        task_id = str(uuid.uuid4())
    stage_list = stages or STAGES
    entry = dict(stage_list[0])
    entry['done'] = False
    entry['display_name'] = display_name or ''
    # Resolve the initial stage's mascot message
    entry['mascot'] = _resolve_name(entry.get('mascot', ''), display_name)
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
        # Preserve the display_name across stage transitions
        old = _cache.get(task_id) or {}
        entry['display_name'] = old.get('display_name', '')
        # Resolve the mascot message for this stage
        entry['mascot'] = _resolve_name(entry.get('mascot', ''),
                                         entry['display_name'])
        _cache.set(task_id, entry)
        logger.info(f"[progress] update: {task_id} → stage {stage} ({stage_list[stage]['label']})")


def update_cosmetic(task_id, **fields):
    """Merge cosmetic fields (label/mascot/pct/mascot_state/error) into
    the existing task entry without changing its stage number or stage
    list.

    Used by background components (e.g. the TTS worker) that need to
    publish UI progress against the same task_id the request handler
    created, but with their own labels and mascot messages. The
    ``done`` flag is preserved; ``stage`` and any other non-cosmetic
    fields are preserved.

    Accepted keyword arguments: label, mascot, pct, mascot_state,
    error. Any other keys are ignored.

    A no-op when the task_id is unknown (e.g. already cleaned up by the
    request handler) or when no cosmetic fields are provided.
    """
    cosmetic_keys = {'label', 'mascot', 'pct', 'mascot_state', 'error'}
    payload = {k: v for k, v in fields.items() if k in cosmetic_keys}
    if not payload:
        return
    if not _cache.has(task_id):
        logger.info(f"[progress] update_cosmetic skipped — task {task_id} not found")
        return
    data = _cache.get(task_id) or {}
    # Resolve {name} placeholders in any mascot string being merged in
    name = data.get('display_name', '')
    if 'mascot' in payload and payload['mascot']:
        payload['mascot'] = _resolve_name(payload['mascot'], name)
    data.update(payload)
    _cache.set(task_id, data)
    logger.info(f"[progress] update_cosmetic: {task_id} → {payload}")


def mark_error(task_id, mascot_msg=None, pct=None, label=None):
    """Publish a sticky error state for a task.

    Sets ``mascot_state='error'`` (which drives the mascot-error sprite
    on the client), the provided mascot bubble message, and an
    ``error=True`` flag that the JS client uses to keep the error
    mascot visible for a short window even if subsequent ``busy``
    cosmetic polls arrive (e.g. from a background TTS worker that is
    still processing other modules).

    ``mascot_msg`` may contain ``{name}`` which is replaced with the
    learner's display name (stored on the task at ``create_task`` time).
    If the task has no display_name (e.g. created before this feature),
    the placeholder falls back to 'there'.

    This is the canonical helper for surfacing failures to the user
    via the mascot without crashing the request. Call it in an
    ``except`` block RIGHT BEFORE returning the error response, so
    no later ``update_progress`` call clobbers the ``error`` flag.

    A no-op when the task_id is unknown (e.g. already cleaned up) —
    never raises. This is critical because error handlers must not
    themselves error.

    Args:
        task_id: The progress_tracker task id.
        mascot_msg: Short message for the CRT speech bubble
            (e.g. "Couldn't reach the AI model, {name}"). If None, a
            default is used.
        pct: Optional progress percentage to freeze the bar at.
        label: Optional internal label (not shown to the user; the
            mascot bubble uses ``mascot_msg``).
    """
    # Resolve {name} from the stored display_name
    data = _cache.get(task_id) or {}
    name = data.get('display_name', '')
    msg = mascot_msg or 'Something went wrong, {name}.'
    msg = _resolve_name(msg, name)
    payload = {
        'mascot_state': 'error',
        'mascot': msg,
        'error': True,
    }
    if pct is not None:
        payload['pct'] = pct
    if label is not None:
        payload['label'] = label
    update_cosmetic(task_id, **payload)
    logger.info(f"[progress] mark_error: {task_id} → {msg!r}")


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
