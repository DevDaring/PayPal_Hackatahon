"""Request analysis workflow (LangGraph).

extract_quotes → evaluate_constraints → summarize_recommendation

Node outputs live in PostgreSQL (documents, quote versions, evaluations, explanation), so a
restarted run simply re-enters the graph: completed work is detected and skipped. Approval and
payment are NOT graph nodes the model can reach — they are separate authenticated services.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from .. import audit, timeutil
from ..db import session_scope
from ..models import Document, PurchaseRequest, WorkflowRun
from . import comparison, documents

MAX_PARALLEL_EXTRACTIONS = 3


class AnalysisState(TypedDict, total=False):
    request_id: str
    run_id: str
    pending_documents: list[str]
    extracted: int
    summary: dict | None
    canceled: bool


def _mark(run_id: str, node: str, done: bool = False) -> bool:
    """Persist node progress; returns False when cancellation was requested."""
    with session_scope() as db:
        run = db.get(WorkflowRun, uuid.UUID(run_id), with_for_update=True)
        run.current_node = node
        if done and node not in run.completed_nodes:
            run.completed_nodes = [*run.completed_nodes, node]
        return not run.cancel_requested


def extract_quotes(state: AnalysisState) -> AnalysisState:
    if not _mark(state["run_id"], "extract_quotes"):
        return {**state, "canceled": True}
    with session_scope() as db:
        pending = [str(d.id) for d in db.execute(select(Document).where(Document.request_id == uuid.UUID(state["request_id"]), Document.status.in_(("uploaded", "extracting")))).scalars()]
    if pending:
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_EXTRACTIONS) as pool:
            list(pool.map(lambda d: documents.process(session_scope, d), pending))
    _mark(state["run_id"], "extract_quotes", done=True)
    return {**state, "pending_documents": pending, "extracted": len(pending)}


def evaluate_constraints(state: AnalysisState) -> AnalysisState:
    if state.get("canceled") or not _mark(state["run_id"], "evaluate_constraints"):
        return {**state, "canceled": True}
    with session_scope() as db:
        summary = comparison.evaluate_request(db, state["request_id"])
    _mark(state["run_id"], "evaluate_constraints", done=True)
    return {**state, "summary": summary}


def summarize_recommendation(state: AnalysisState) -> AnalysisState:
    if state.get("canceled") or not state.get("summary") or not _mark(state["run_id"], "summarize_recommendation"):
        return state
    comparison.explain(session_scope, state["request_id"])
    _mark(state["run_id"], "summarize_recommendation", done=True)
    return state


def _build():
    g = StateGraph(AnalysisState)
    g.add_node("extract_quotes", extract_quotes)
    g.add_node("evaluate_constraints", evaluate_constraints)
    g.add_node("summarize_recommendation", summarize_recommendation)
    g.add_edge(START, "extract_quotes")
    g.add_edge("extract_quotes", "evaluate_constraints")
    g.add_edge("evaluate_constraints", "summarize_recommendation")
    g.add_edge("summarize_recommendation", END)
    return g.compile()


GRAPH = _build()


def run_analysis(request_id: str) -> None:
    with session_scope() as db:
        req = db.get(PurchaseRequest, uuid.UUID(str(request_id)))
        if req is None or req.status in ("canceled", "superseded"):
            return
        run = WorkflowRun(workspace_id=req.workspace_id, request_id=req.id, request_version_id=req.current_version_id, kind="analyze_request", status="running", started_at=timeutil.now(), completed_nodes=[])
        db.add(run)
        db.flush()
        run_id = str(run.id)
    try:
        GRAPH.invoke({"request_id": str(request_id), "run_id": run_id}, {"recursion_limit": 8})
        status, err = "succeeded", None
    except Exception as e:
        status, err = "failed", f"{type(e).__name__}: {str(e)[:300]}"
        with session_scope() as db:
            req = db.get(PurchaseRequest, uuid.UUID(str(request_id)))
            audit.event(db, workspace_id=req.workspace_id, request_id=req.id, run_id=uuid.UUID(run_id), stage="workflow", status="failed", title="Analysis step failed; it will be retried", detail=type(e).__name__)
        raise
    finally:
        with session_scope() as db:
            run = db.get(WorkflowRun, uuid.UUID(run_id))
            run.status, run.error, run.finished_at = status, err, timeutil.now()
