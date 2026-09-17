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
    'claim_pipeline_task', 'clear_finished', 'create_task',
    'discard_task', 'dismiss_task', 'fail_task',
    'finish_task', 'get_running_task', 'list_tasks', 'mark_read',
    'sweep_orphaned_tasks', 'unread_count',
]


def get_running_task(user_id: str, kind: str, max_age_s: int = 7200):
    """Return the user's freshest running task row of *kind*, or None.

    Rows older than *max_age_s* (by ``created_at``) are treated as stale
    and ignored — a crashed pipeline's row only blocks re-submits until
    the boot sweep flips it to failed. Never raises.
    """
    try:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        rows = (BackgroundTask.query
                .filter_by(user_id=user_id, kind=kind, status=TASK_STATUS_RUNNING)
                .order_by(BackgroundTask.created_at.asc()).all())
        for row in rows:
            created = row.created_at
            if created is None:
                return row
            try:
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                if (now - created).total_seconds() <= max_age_s:
                    return row
            except Exception:
                return row
        return None
    except Exception:
        return None


def claim_pipeline_task(task_id: str, user_id: str, kind: str = TASK_KIND_PROCESS,
                        label: str = "", match_label: str = "") -> tuple:
    """Insert-then-verify singleflight claim for long pipelines.

    Registers our own running row, then looks for an older competing
    running row for the same user+kind. The oldest pipeline wins;
    newer duplicates back off so double-clicks/retries never run two
    expensive pipelines (and never overshoot the 3-active-lesson cap).

    Returns ``(winner: bool, existing_task_id: str | None,
    same_goal: bool)``. ``same_goal`` compares *match_label* against the
    winner's label so callers can follow an identical re-submit but warn
    on a genuinely different concurrent job. Fail-open (``(True, None,
    False)``) on any error to preserve historic behavior. Never raises.
    """
    try:
        create_task(task_id, user_id, kind=kind, label=label)
        rows = (BackgroundTask.query
                .filter_by(user_id=user_id, kind=kind, status=TASK_STATUS_RUNNING)
                .order_by(BackgroundTask.created_at.asc()).all())
        mine = None
        competitors = []
        for row in rows:
            if row.task_id == task_id:
                mine = row
            else:
                competitors.append(row)
        if not competitors:
            return True, None, False
        oldest = competitors[0]
        try:
            from datetime import timezone

            def _aware(dt):
                if dt is not None and dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt

            own_ts = _aware(mine.created_at) if mine is not None else None
            old_ts = _aware(oldest.created_at)
            if own_ts is not None and old_ts is not None:
                if (own_ts, task_id) < (old_ts, oldest.task_id):
                    return True, None, False
            elif mine is not None and oldest.created_at is None:
                return True, None, False
        except Exception:
            pass
        # We lost: mark our row failed so the bell stays honest, then
        # report the winner for resume-or-warn handling upstream.
        fail_task(task_id, error='Superseded — an identical job was already running.')
        same_goal = bool(match_label) and (oldest.label or '') == match_label
        return False, oldest.task_id, same_goal
    except Exception as e:
        logger.warning("claim_pipeline_task failed, failing open: %s", str(e))
        return True, None, False


def discard_task(task_id: str, user_id: str = "") -> bool:
    """Delete a task row outright (owner-scoped when *user_id* given).

    Used for non-AJAX form pipelines that need race-guard bookkeeping
    without leaving bell spam behind. Never raises.
    """
    try:
        query = BackgroundTask.query.filter_by(task_id=task_id)
        if user_id:
            query = query.filter_by(user_id=user_id)
        row = query.first()
        if row is None:
            return False
        db.session.delete(row)
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return False


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
