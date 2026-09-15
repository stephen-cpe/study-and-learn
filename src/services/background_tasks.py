"""
Background-task records — durable cross-tab state for long tasks (bell UX).

The in-page 2s ``progress_tracker`` poller gives live detail but dies on
navigation. These DB rows survive it: created at task submit, flipped to
ready/failed with a ``result_url`` deep link at completion, and read by
any tab via ``GET /tasks`` for the navbar bell badge.

All helpers are best-effort and never raise — task bookkeeping must never
break the learning flows it tracks.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src import db
from src.models import (
    TASK_KIND_GENERATE,
    TASK_KIND_PROCESS,
    TASK_STATUS_FAILED,
    TASK_STATUS_READY,
    TASK_STATUS_RUNNING,
    BackgroundTask,
)

logger = logging.getLogger(__name__)


def create_task(task_id: str, user_id: str, kind: str = TASK_KIND_PROCESS,
                label: str = "") -> Optional[BackgroundTask]:
    """Create (or reset) a running task row. Never raises."""
    try:
        if kind not in BackgroundTask.VALID_KINDS:
            kind = TASK_KIND_PROCESS
        row = BackgroundTask.query.filter_by(task_id=task_id).first()
        if row is None:
            row = BackgroundTask(task_id=task_id, user_id=user_id)
            db.session.add(row)
        row.user_id = user_id
        row.kind = kind
        row.status = TASK_STATUS_RUNNING
        row.label = (label or "")[:200]
        row.error = None
        row.read = False
        db.session.commit()
        return row
    except Exception as e:
        db.session.rollback()
        logger.warning("create_task failed for %s: %s", str(task_id)[:8], str(e))
        return None


def finish_task(task_id: str, result_url: str = "", label: str = "",
                path_id: str = "", pct: int = 100) -> None:
    """Flip a task to ready with a deep link. Never raises."""
    try:
        row = BackgroundTask.query.filter_by(task_id=task_id).first()
        if row is None:
            return
        row.status = TASK_STATUS_READY
        if result_url:
            row.result_url = result_url[:500]
        if label:
            row.label = label[:200]
        if path_id:
            row.path_id = path_id[:36]
        row.pct = pct
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning("finish_task failed for %s: %s", str(task_id)[:8], str(e))


def fail_task(task_id: str, error: str = "", label: str = "") -> None:
    """Flip a task to failed with an error message. Never raises."""
    try:
        row = BackgroundTask.query.filter_by(task_id=task_id).first()
        if row is None:
            return
        row.status = TASK_STATUS_FAILED
        if error:
            row.error = error[:1000]
        if label:
            row.label = label[:200]
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning("fail_task failed for %s: %s", str(task_id)[:8], str(e))


def list_tasks(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Return the user's tasks, newest first. Never raises."""
    try:
        rows = (BackgroundTask.query.filter_by(user_id=user_id)
                .order_by(BackgroundTask.created_at.desc()).limit(limit).all())
        return [{
            'id': r.id, 'task_id': r.task_id, 'kind': r.kind,
            'status': r.status, 'pct': r.pct, 'label': r.label,
            'path_id': r.path_id, 'result_url': r.result_url,
            'error': r.error, 'read': bool(r.read),
            'created_at': r.created_at.isoformat() if r.created_at else None,
        } for r in rows]
    except Exception as e:
        logger.warning("list_tasks failed: %s", str(e))
        return []


def unread_count(user_id: str) -> int:
    """Count unread finished tasks for the bell badge. Never raises."""
    try:
        return BackgroundTask.query.filter_by(
            user_id=user_id, read=False, status=TASK_STATUS_READY,
        ).count() + BackgroundTask.query.filter_by(
            user_id=user_id, read=False, status=TASK_STATUS_FAILED,
        ).count()
    except Exception:
        return 0


def mark_read(task_id: str, user_id: str) -> bool:
    """Mark a task read (owner only). Never raises."""
    try:
        row = BackgroundTask.query.filter_by(task_id=task_id, user_id=user_id).first()
        if row is None:
            return False
        row.read = True
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


def sweep_orphaned_tasks() -> int:
    """Flip stale ``running`` rows to failed. Returns the count flipped.

    Any row still marked running at server boot is orphaned by definition:
    in-flight request handlers die with the old process (Ctrl+C, restart,
    redeploy), so nothing will ever flip them to ready. Without this sweep
    the bell shows "running…" forever and refresh-resume keeps polling a
    dead task. Must be called inside an app context. Never raises.
    """
    try:
        rows = BackgroundTask.query.filter_by(status=TASK_STATUS_RUNNING).all()
        for row in rows:
            row.status = TASK_STATUS_FAILED
            row.error = ('Interrupted — the server stopped while this task '
                         'was running. Please retry.')
        if rows:
            db.session.commit()
            logger.info("sweep_orphaned_tasks: marked %d task(s) failed", len(rows))
        return len(rows)
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.debug("sweep_orphaned_tasks skipped: %s", str(e))
        return 0


__all__ = [
    'TASK_KIND_GENERATE', 'TASK_KIND_PROCESS',
    'TASK_STATUS_FAILED', 'TASK_STATUS_READY', 'TASK_STATUS_RUNNING',
    'clear_finished', 'create_task', 'dismiss_task', 'fail_task',
    'finish_task', 'list_tasks', 'mark_read', 'sweep_orphaned_tasks',
    'unread_count',
]


def dismiss_task(task_id: str, user_id: str) -> bool:
    """Delete one finished task row (owner only). Never raises.

    Running rows are protected — a live task cannot be dismissed, only
    finished ones (ready/failed) disappear from the bell.
    """
    try:
        row = BackgroundTask.query.filter_by(task_id=task_id, user_id=user_id).first()
        if row is None or row.status == TASK_STATUS_RUNNING:
            return False
        db.session.delete(row)
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


def clear_finished(user_id: str) -> int:
    """Delete all finished task rows for a user. Returns count. Never raises."""
    try:
        rows = BackgroundTask.query.filter(
            BackgroundTask.user_id == user_id,
            BackgroundTask.status != TASK_STATUS_RUNNING,
        ).all()
        for row in rows:
            db.session.delete(row)
        db.session.commit()
        return len(rows)
    except Exception:
        db.session.rollback()
        return 0
