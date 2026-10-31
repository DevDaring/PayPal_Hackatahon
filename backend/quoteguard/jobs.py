"""Durable PostgreSQL job queue (transactional outbox). No Redis."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from . import timeutil
from .models import Job


def enqueue(db: Session, kind: str, payload: dict, *, dedupe_key: str | None = None, delay_seconds: int = 0, max_attempts: int = 5) -> None:
    """Insert in the caller's transaction so the job commits atomically with its intent."""
    stmt = insert(Job).values(
        kind=kind,
        payload={k: str(v) if v is not None and not isinstance(v, (int, bool, dict, list)) else v for k, v in payload.items()},
        dedupe_key=dedupe_key,
        run_after=timeutil.now() + timedelta(seconds=delay_seconds),
        max_attempts=max_attempts,
        created_at=timeutil.now(),
        updated_at=timeutil.now(),
    )
    if dedupe_key:
        stmt = stmt.on_conflict_do_nothing(index_elements=[Job.dedupe_key])
    db.execute(stmt)


def claim(db: Session, worker_id: str) -> Job | None:
    job = db.execute(
        select(Job)
        .where(Job.status == "queued", Job.run_after <= timeutil.now())
        .order_by(Job.run_after)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if job is None:
        return None
    job.status = "running"
    job.dedupe_key = None  # new work for the same key can queue behind this run
    job.attempts += 1
    job.locked_by = worker_id
    job.locked_at = timeutil.now()
    job.updated_at = timeutil.now()
    return job


def finish(db: Session, job_id, ok: bool, error: str | None = None, retry_in: int = 5) -> None:
    job = db.get(Job, job_id)
    if job is None:
        return
    job.updated_at = timeutil.now()
    job.locked_by = None
    if ok:
        job.status = "succeeded"
        # Free the dedupe key so the same logical work can be scheduled again later.
        job.dedupe_key = None
        return
    job.last_error = (error or "")[:2000]
    if job.attempts >= job.max_attempts:
        job.status = "dead"
        job.dedupe_key = None
    else:
        job.status = "queued"
        job.run_after = timeutil.now() + timedelta(seconds=retry_in * (2 ** (job.attempts - 1)))


def requeue_stale(db: Session, older_than_seconds: int = 300) -> int:
    """Jobs left `running` by a crashed worker go back to the queue."""
    res = db.execute(
        update(Job)
        .where(Job.status == "running", Job.locked_at < timeutil.now() - timedelta(seconds=older_than_seconds))
        .values(status="queued", locked_by=None)
    )
    return res.rowcount or 0
