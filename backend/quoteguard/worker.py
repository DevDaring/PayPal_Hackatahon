"""Background worker: durable jobs from PostgreSQL. Run as a separate process (`python -m quoteguard.worker`)."""

from __future__ import annotations

import logging
import os
import signal
import socket
import time
from concurrent.futures import ThreadPoolExecutor

from . import jobs
from .config import get_settings
from .db import session_scope
from .services import payments, webhooks
from .services import evaluation as evaluation_svc
from .services.workflow import run_analysis

log = logging.getLogger("quoteguard.worker")
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
_stop = False


def handle(kind: str, payload: dict) -> None:
    if kind in ("analyze_request", "extract_document", "evaluate_request", "explain_request"):
        run_analysis(payload["request_id"])
    elif kind == "reconcile_payment":
        res = payments.reconcile(session_scope, payload["operation_id"], source="worker")
        if res["state"] in ("reconciling", "capture_pending") and res.get("last_error_code") != "PROVIDER_PENDING":
            raise RuntimeError("still reconciling")  # retried with backoff
    elif kind == "process_webhook":
        webhooks.process(session_scope, payload["webhook_event_id"])
    elif kind == "run_evaluation":
        evaluation_svc.execute(payload["run_id"])
    else:
        raise ValueError(f"unknown job kind {kind}")


def run_one(job_id, kind, payload) -> None:
    try:
        handle(kind, payload)
        with session_scope() as db:
            jobs.finish(db, job_id, True)
    except Exception as e:
        log.warning("job %s %s failed: %s", kind, job_id, type(e).__name__)
        with session_scope() as db:
            jobs.finish(db, job_id, False, f"{type(e).__name__}: {e}"[:1000])


def main() -> None:
    logging.basicConfig(level=get_settings().LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    def stop(*_):
        global _stop
        _stop = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info("worker %s started", WORKER_ID)
    last_sweep = 0.0
    pool = ThreadPoolExecutor(max_workers=4)
    inflight: set = set()
    while not _stop:
        if time.time() - last_sweep > 15:
            with session_scope() as db:
                jobs.requeue_stale(db)
                n = payments.recover_stuck(db)
                if n:
                    log.info("recovered %d in-flight payment(s)", n)
            last_sweep = time.time()
        inflight = {f for f in inflight if not f.done()}
        claimed = None
        if len(inflight) < 4:
            with session_scope() as db:
                job = jobs.claim(db, WORKER_ID)
                if job is not None:
                    claimed = (job.id, job.kind, dict(job.payload))
        if claimed is None:
            time.sleep(0.5)
            continue
        inflight.add(pool.submit(run_one, *claimed))
    pool.shutdown(wait=True)
    log.info("worker stopped")


if __name__ == "__main__":
    main()
