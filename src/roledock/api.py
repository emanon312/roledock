"""Offline demo API. Static demo keys MUST be replaced before deployment."""
from dataclasses import asdict
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from .runtime import RoleDock
from .security import DEMO_IDENTITIES
from .audit import AuditJournal

app = FastAPI(title="RoleDock (offline demo)", version="0.1.0")
service = RoleDock()
audit_journal = AuditJournal()


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    file_id: str | None = Field(default=None, max_length=100)


@app.get("/health")
def health():
    return {"status": "ok", "stage": "demo", "production_ready": False}


@app.get("/v1/me")
def identity(x_demo_key: str | None = Header(default=None)):
    principal = DEMO_IDENTITIES.get(x_demo_key or "")
    if not principal:
        raise HTTPException(status_code=401, detail="invalid_demo_key")
    return {"user_id": principal.user_id, "role": principal.role}


@app.post("/v1/tasks")
def execute_task(request: QueryRequest, x_demo_key: str | None = Header(default=None)):
    principal = DEMO_IDENTITIES.get(x_demo_key or "")
    if not principal:
        raise HTTPException(status_code=401, detail="invalid_demo_key")
    result = service.execute(principal, request.question, request.file_id)
    audit_journal.record(result)
    return asdict(result)


@app.get("/v1/tasks/{task_id}/audit")
def get_task_audit(task_id: str, x_demo_key: str | None = Header(default=None)):
    principal = DEMO_IDENTITIES.get(x_demo_key or "")
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid_demo_key")
    record = audit_journal.get_for_actor(task_id, principal.user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task_not_found")
    return asdict(record)
