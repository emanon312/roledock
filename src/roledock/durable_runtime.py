"""Single-worker demo runtime: durable HITL and replay-safe request registration.

This is not a distributed transaction coordinator. Side-effecting external tools
need their own idempotency keys and outbox before production use.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from .agent_graph import build_agent_graph
from .models import Principal
from .security import AccessDenied

REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
REVIEWER_ROLES = frozenset({"compliance", "admin"})


def _fingerprint(principal: Principal, question: str, file_id: str | None) -> str:
    payload = json.dumps([principal.role, question, file_id], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TaskLedger:
    """No user prompts, PDF content or model responses in this SQLite table."""

    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(str(path), timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout = 10000")
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS runtime_tasks (
            task_id TEXT PRIMARY KEY,
            actor TEXT NOT NULL,
            role TEXT NOT NULL,
            request_key TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            file_id TEXT,
            status TEXT NOT NULL,
            UNIQUE(actor, request_key)
        );
        CREATE TABLE IF NOT EXISTS runtime_reviews (
            task_id TEXT PRIMARY KEY REFERENCES runtime_tasks(task_id),
            reviewer TEXT NOT NULL,
            reviewer_role TEXT NOT NULL,
            decision TEXT NOT NULL CHECK(decision IN ('approved', 'rejected')),
            recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        self.db.commit()

    def register(self, principal: Principal, request_key: str, question: str, file_id: str | None):
        if not REQUEST_ID.fullmatch(request_key):
            raise ValueError("invalid_idempotency_key")
        fingerprint = _fingerprint(principal, question, file_id)
        task_id = str(uuid4())
        try:
            self.db.execute("""INSERT INTO runtime_tasks
                (task_id, actor, role, request_key, request_hash, file_id, status)
                VALUES (?, ?, ?, ?, ?, ?, 'running')""",
                (task_id, principal.user_id, principal.role, request_key, fingerprint, file_id))
            self.db.commit()
            return self._task(task_id), True
        except sqlite3.IntegrityError:
            self.db.rollback()
            row = self.db.execute(
                "SELECT * FROM runtime_tasks WHERE actor=? AND request_key=?",
                (principal.user_id, request_key),
            ).fetchone()
            if row is None:
                raise
            if row["request_hash"] != fingerprint or row["role"] != principal.role:
                raise ValueError("idempotency_key_reused_with_different_request")
            return dict(row), False

    def _task(self, task_id: str):
        row = self.db.execute("SELECT * FROM runtime_tasks WHERE task_id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def task_for_actor(self, task_id: str, actor: str):
        row = self._task(task_id)
        if row is None or row["actor"] != actor:
            raise AccessDenied("task_not_found")
        return row

    def update(self, task_id: str, status: str):
        if status not in {"pending_approval", "completed", "denied", "failed"}:
            raise ValueError("invalid_task_status")
        self.db.execute("UPDATE runtime_tasks SET status=? WHERE task_id=?", (status, task_id))
        self.db.commit()

    def decision_for(self, task_id: str, actor: str, file_id: str):
        row = self.db.execute("""SELECT r.decision FROM runtime_reviews AS r
              JOIN runtime_tasks AS t ON t.task_id=r.task_id
              WHERE r.task_id=? AND t.actor=? AND t.file_id=?""",
              (task_id, actor, file_id)).fetchone()
        return row["decision"] if row else None

    def record_review(self, task_id: str, reviewer: Principal, approved: bool):
        if reviewer.role not in REVIEWER_ROLES:
            raise AccessDenied("reviewer_role_denied")
        row = self._task(task_id)
        if row is None:
            raise AccessDenied("task_not_found")
        if reviewer.user_id == row["actor"]:
            raise AccessDenied("self_approval_denied")
        decision = "approved" if approved else "rejected"
        existing = self.db.execute("SELECT decision, reviewer FROM runtime_reviews WHERE task_id=?", (task_id,)).fetchone()
        if existing:
            if existing["decision"] != decision or existing["reviewer"] != reviewer.user_id:
                raise ValueError("review_already_decided")
            return row
        if row["status"] != "pending_approval":
            raise ValueError("task_not_pending_approval")
        try:
            self.db.execute("""INSERT INTO runtime_reviews
                (task_id, reviewer, reviewer_role, decision) VALUES (?, ?, ?, ?)""",
                (task_id, reviewer.user_id, reviewer.role, decision))
            self.db.commit()
        except sqlite3.IntegrityError as exc:
            self.db.rollback()
            raise ValueError("review_already_decided") from exc
        return row

    def review_preview(self, task_id: str, reviewer: Principal):
        if reviewer.role not in REVIEWER_ROLES:
            raise AccessDenied("reviewer_role_denied")
        row = self._task(task_id)
        if row is None:
            raise AccessDenied("task_not_found")
        if reviewer.user_id == row["actor"]:
            raise AccessDenied("self_approval_denied")
        if row["status"] != "pending_approval":
            raise ValueError("task_not_pending_approval")
        # Only minimum data for a reviewer; never reveal the raw question,
        # retrieved passages or PDF bytes.
        return {"task_id": task_id, "requester_role": row["role"],
                "tool": "parse_approved_pdf", "file_id": row["file_id"],
                "status": row["status"]}

    def close(self):
        self.db.close()


class DurableAgentRuntime:
    """Per-call manager using persistent SQLite checkpointer and task ledger.

    Open with a context manager. Do not operate concurrently on the same state
    directory from multiple worker processes. Both stores contain sensitive
    metadata/state; deploy with OS-level filesystem controls.
    """

    def __init__(self, service, state_dir: str | Path, model=None):
        self.service = service
        self.state_dir = Path(state_dir)
        self.model = model
        self._context = None

    def __enter__(self):
        from langgraph.checkpoint.sqlite import SqliteSaver
        self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.ledger = TaskLedger(self.state_dir / "tasks.sqlite")
        self._context = SqliteSaver.from_conn_string(str(self.state_dir / "graph.sqlite"))
        self.saver = self._context.__enter__()
        self.graph = build_agent_graph(self.service, model=self.model, checkpointer=self.saver,
                                       require_approval=True, approval_ledger=self.ledger)
        if os.name == "posix":
            for path in (self.state_dir / "tasks.sqlite", self.state_dir / "graph.sqlite"):
                if path.exists():
                    path.chmod(0o600)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self._context.__exit__(exc_type, exc, tb)
        finally:
            self.ledger.close()

    @staticmethod
    def _config(task_id: str):
        return {"configurable": {"thread_id": f"runtime:{task_id}"}}

    def _view(self, row, include_result: bool):
        response = {"task_id": row["task_id"], "status": row["status"],
                    "actor": row["actor"], "role": row["role"]}
        if row["status"] == "pending_approval":
            response["approval"] = {"tool": "parse_approved_pdf", "file_id": row["file_id"]}
        if include_result and row["status"] in {"completed", "denied", "failed"}:
            snap = self.graph.get_state(self._config(row["task_id"]))
            response["result"] = snap.values.get("result") if snap.values else None
        return response

    def _refresh(self, task_id: str):
        row = self.ledger._task(task_id)
        snap = self.graph.get_state(self._config(task_id))
        if snap.values and snap.values.get("result"):
            status = snap.values["result"]["status"]
        elif snap.next and "approval_gate" in snap.next:
            status = "pending_approval"
        else:
            # No checkpoint or incomplete non-approval execution: do NOT auto
            # replay side effects. Operator intervention is required.
            status = "failed"
        if row["status"] != status:
            self.ledger.update(task_id, status)
        return self.ledger._task(task_id)

    def submit(self, principal: Principal, question: str, request_key: str, file_id: str | None = None):
        if not question or len(question) > 4000:
            raise ValueError("invalid_question")
        if file_id is not None and len(file_id) > 100:
            raise ValueError("invalid_file_id")
        if principal.role not in self.service.profiles:
            raise AccessDenied("unknown_role")
        row, created = self.ledger.register(principal, request_key, question, file_id)
        if not created:
            if row["status"] in {"running", "pending_approval"}:
                row = self._refresh(row["task_id"])
            return self._view(row, include_result=True)
        try:
            self.graph.invoke({"task_id": row["task_id"], "actor": principal.user_id,
                               "role": principal.role, "question": question, "file_id": file_id},
                              self._config(row["task_id"]), durability="sync")
        except Exception:
            self.ledger.update(row["task_id"], "failed")
            raise
        return self._view(self._refresh(row["task_id"]), include_result=True)

    def get(self, principal: Principal, task_id: str):
        row = self.ledger.task_for_actor(task_id, principal.user_id)
        if row["status"] in {"running", "pending_approval"}:
            row = self._refresh(task_id)
        return self._view(row, include_result=True)

    def preview(self, reviewer: Principal, task_id: str):
        if reviewer.role not in REVIEWER_ROLES:
            raise AccessDenied("reviewer_role_denied")
        row = self.ledger._task(task_id)
        if row is not None and row["status"] in {"running", "pending_approval"}:
            self._refresh(task_id)
        return self.ledger.review_preview(task_id, reviewer)

    def review(self, reviewer: Principal, task_id: str, approved: bool):
        row = self.ledger._task(task_id)
        if row is not None and row["status"] in {"running", "pending_approval"}:
            self._refresh(task_id)
        row = self.ledger.record_review(task_id, reviewer, approved)
        if row["status"] in {"completed", "denied", "failed"}:
            return self._view(row, include_result=False)
        snap = self.graph.get_state(self._config(task_id))
        if "approval_gate" not in snap.next:
            raise ValueError("checkpoint_not_waiting_for_review")
        from langgraph.types import Command
        # The Command payload is *not* authority; the graph validates the
        # durable server-side review record after interrupt() returns.
        self.graph.invoke(Command(resume={"wake": True}), self._config(task_id), durability="sync")
        return self._view(self._refresh(task_id), include_result=False)
