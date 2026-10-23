"""Offline demo API. Static demo keys MUST be replaced before deployment."""
from dataclasses import asdict
import os
from functools import lru_cache
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from .runtime import RoleDock
from .security import DEMO_IDENTITIES
from .audit import AuditJournal

app = FastAPI(title="RoleDock (local-only demo)", version="0.3.0")
def make_service():
    if os.getenv("ROLEDOCK_RETRIEVAL_MODE", "offline") != "qdrant":
        return RoleDock()
    from .rag_cli import build_vector_knowledge
    return RoleDock(kb=build_vector_knowledge())


service = make_service()
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


@lru_cache(maxsize=1)
def configured_agent_graph():
    if os.getenv("ROLEDOCK_ENABLE_AGENT_API") != "1":
        raise HTTPException(status_code=503, detail="agent_api_not_enabled")
    from .agent_graph import build_agent_graph
    from .model_provider import ModelSettings, OpenAICompatibleChat
    try:
        model = OpenAICompatibleChat(ModelSettings.from_env())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="model_not_configured") from exc
    return build_agent_graph(service, model=model)


@app.post("/v1/agent/tasks")
def execute_agent_task(request: QueryRequest, x_demo_key: str | None = Header(default=None)):
    principal = DEMO_IDENTITIES.get(x_demo_key or "")
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid_demo_key")
    graph = configured_agent_graph()
    from .agent_graph import run_agent
    result = run_agent(graph, principal, request.question, request.file_id)
    audit_journal.record(result)
    return asdict(result)
