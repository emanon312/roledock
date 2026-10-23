"""Offline demo API. Static demo keys MUST be replaced before deployment."""
from dataclasses import asdict
import os
from functools import lru_cache
from threading import RLock
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from .runtime import RoleDock
from .security import DEMO_IDENTITIES
from .audit import AuditJournal

app = FastAPI(title="RoleDock (local-only demo)", version="0.4.0")
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


# v0.4 localhost-only durable runtime, explicitly opt-in. This is NOT a
# multi-worker production task queue or an enterprise identity provider.
_runtime_lock = RLock()


class RuntimeTaskRequest(QueryRequest):
    model_config = {"extra": "forbid"}
    request_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class ReviewRequest(BaseModel):
    model_config = {"extra": "forbid"}
    approved: bool


def runtime_principal(key: str | None):
    principal = DEMO_IDENTITIES.get(key or "")
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid_demo_key")
    if os.getenv("ROLEDOCK_ENABLE_RUNTIME_API") != "1":
        raise HTTPException(status_code=503, detail="runtime_api_not_enabled")
    return principal


@lru_cache(maxsize=1)
def runtime_service():
    from .pdf_tools import synthetic_finance_pdf_registry
    from .runtime import RoleDock
    return RoleDock(pdf_registry=synthetic_finance_pdf_registry())


def runtime_model():
    if os.getenv("ROLEDOCK_RUNTIME_USE_MODEL") != "1":
        return None
    from .model_provider import ModelSettings, OpenAICompatibleChat
    return OpenAICompatibleChat(ModelSettings.from_env())


def runtime_call(callback):
    from .durable_runtime import DurableAgentRuntime
    from .security import AccessDenied
    # Concurrency serialized in this single process only. NEVER run multiple
    # uvicorn workers against the same SQLite files or bind to a public port.
    with _runtime_lock:
        try:
            with DurableAgentRuntime(runtime_service(),
                  os.getenv("ROLEDOCK_STATE_DIR", ".state/runtime"), model=runtime_model()) as runtime:
                return callback(runtime)
        except AccessDenied as exc:
            # Opaque lookup errors to prevent enumerating other actors' tasks.
            status = 404 if str(exc) == "task_not_found" else 403
            raise HTTPException(status_code=status, detail=str(exc)) from exc
        except ValueError as exc:
            error = str(exc)
            status = 409 if error in {"idempotency_key_reused_with_different_request",
                         "review_already_decided", "task_not_pending_approval",
                         "checkpoint_not_waiting_for_review"} else 422
            raise HTTPException(status_code=status, detail=error) from exc
        except (ImportError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail="runtime_dependency_or_model_unavailable") from exc


@app.post("/v1/runtime/tasks")
def submit_runtime_task(request: RuntimeTaskRequest, x_demo_key: str | None = Header(default=None)):
    principal = runtime_principal(x_demo_key)
    return runtime_call(lambda rt: rt.submit(principal, request.question,
                                              request.request_key, request.file_id))


@app.get("/v1/runtime/tasks/{task_id}")
def get_runtime_task(task_id: str, x_demo_key: str | None = Header(default=None)):
    principal = runtime_principal(x_demo_key)
    return runtime_call(lambda rt: rt.get(principal, task_id))


@app.post("/v1/runtime/tasks/{task_id}/review")
def review_runtime_task(task_id: str, request: ReviewRequest,
                        x_demo_key: str | None = Header(default=None)):
    principal = runtime_principal(x_demo_key)
    return runtime_call(lambda rt: rt.review(principal, task_id, request.approved))


@app.get("/v1/runtime/reviews/{task_id}")
def get_runtime_review_preview(task_id: str, x_demo_key: str | None = Header(default=None)):
    reviewer = runtime_principal(x_demo_key)
    return runtime_call(lambda rt: rt.preview(reviewer, task_id))
