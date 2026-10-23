"""Real conditional LangGraph pipeline: role -> policy-gated routing -> expert -> finish.

All authorization happens in deterministic Python code; the LLM is a proposal
and text-generation service, never a tool executor or privileged principal.
"""
from dataclasses import asdict
from typing import Any, TypedDict
from uuid import uuid4

from .models import ExecutionResult, Hit, Principal
from .routing import route_task
from .security import AccessDenied, require_tool


class AgentState(TypedDict, total=False):
    actor: str
    task_id: str
    role: str
    question: str
    file_id: str | None
    tool: str
    expert: str
    events: list[str]
    status: str
    content: str
    hits: list[dict[str, Any]]
    result: dict[str, Any]


EXPERT_BY_TOOL = {
    "search_knowledge": "knowledge_expert",
    "research_plan": "research_expert",
    "parse_approved_pdf": "document_expert",
}


def build_agent_graph(service, model=None, checkpointer=None, *, require_approval=False, approval_ledger=None):
    """Construct policy-gated graph. Approval ledger is trusted server-side state."""
    if require_approval and (checkpointer is None or approval_ledger is None):
        raise ValueError("durable_approval_requires_checkpointer_and_ledger")
    try:
        from langgraph.graph import StateGraph, START, END
        from langgraph.checkpoint.memory import InMemorySaver
    except ImportError as exc:
        raise RuntimeError("LangGraph unavailable. Install pip install -e '.[agent]'") from exc

    def load_role(state: AgentState):
        if state["role"] not in service.profiles:
            raise AccessDenied("unknown_role")
        if not state.get("actor"):
            raise AccessDenied("missing_authenticated_actor")
        return {"events": ["role_profile_loaded"]}

    def route(state: AgentState):
        profile = service.profiles[state["role"]]
        try:
            if model is not None:
                tool = model.classify(state["question"], profile.allowed_tools)
            else:
                _, tool = route_task(state["question"])
            # Independent, server-side check after model or deterministic classifier.
            require_tool(profile, tool)
            expert = EXPERT_BY_TOOL.get(tool)
            if expert is None:
                raise AccessDenied("unknown_tool")
            return {"tool": tool, "expert": expert,
                    "events": [*state["events"], "task_routed", "tool_authorized"]}
        except AccessDenied as exc:
            return {"tool": "denied", "expert": "policy_gate", "status": "denied",
                    "content": str(exc), "hits": [],
                    "events": [*state["events"], "authorization_denied"]}

    def next_expert(state: AgentState) -> str:
        if state.get("status") == "denied":
            return "finish"
        if require_approval and state["tool"] == "parse_approved_pdf":
            return "approval_gate"
        return state["expert"]

    def approval_gate(state: AgentState):
        """Interrupt only after permission checks. Trust the ledger, not resume payload."""
        from langgraph.types import interrupt
        profile = service.profiles[state["role"]]
        file_id = state.get("file_id") or ""
        try:
            # Check *before* requesting approval; do not ask anyone to review
            # unauthorized or nonexistent documents.
            service.pdf_registry.read(profile, file_id)
        except AccessDenied as exc:
            return {"status": "denied", "content": str(exc), "hits": [],
                    "events": [*state["events"], "authorization_denied"]}
        except FileNotFoundError as exc:
            return {"status": "failed", "content": str(exc), "hits": [],
                    "events": [*state["events"], "execution_failed"]}
        # This node re-enters from the top on resume. All code before interrupt
        # must be pure/read-only. We NEVER execute the PDF parser before approval.
        interrupt({"kind": "pdf_read_approval", "task_id": state["task_id"],
                   "tool": "parse_approved_pdf", "file_id": file_id})
        decision = approval_ledger.decision_for(state["task_id"], state["actor"], file_id)
        if decision is None:
            # A forged direct Command(resume=...) cannot approve anything.
            return {"status": "denied", "content": "approval_not_recorded", "hits": [],
                    "events": [*state["events"], "authorization_denied"]}
        if decision != "approved":
            return {"status": "denied", "content": "human_review_rejected", "hits": [],
                    "events": [*state["events"], "human_review_rejected"]}
        return {"events": [*state["events"], "human_review_approved"]}

    def after_approval(state: AgentState) -> str:
        return "finish" if state.get("status") in {"denied", "failed"} else "document_expert"

    def knowledge(state: AgentState):
        profile = service.profiles[state["role"]]
        try:
            require_tool(profile, "search_knowledge")
            hits: list[Hit] = service.kb.search(state["question"], profile)
            # Revalidate *again* before passing any bytes to the model.
            if any(h.partition not in profile.allowed_partitions for h in hits):
                raise AccessDenied("retrieval_result_not_authorized")
            if model is not None:
                content = model.synthesize(state["question"], profile.prompt_profile, hits)
            else:
                content = "\n".join(f"[{h.document_id}] {h.text} (source: {h.source})" for h in hits)
                content = content or "无授权检索结果。"
            return {"hits": [asdict(h) for h in hits], "content": content,
                    "status": "completed", "events": [*state["events"], "retrieved_hits_validated"]}
        except AccessDenied as exc:
            return {"status": "denied", "content": str(exc), "hits": [],
                    "events": [*state["events"], "authorization_denied"]}

    def research(state: AgentState):
        profile = service.profiles[state["role"]]
        try:
            require_tool(profile, "research_plan")
            content = (model.plan(state["question"], profile.prompt_profile) if model is not None
                       else "定义问题 → 验证来源 → 检索授权材料 → 证据表 → 复核与报告。")
            return {"status": "completed", "content": content, "hits": [],
                    "events": [*state["events"], "research_plan_generated"]}
        except AccessDenied as exc:
            return {"status": "denied", "content": str(exc), "hits": [],
                    "events": [*state["events"], "authorization_denied"]}

    def document(state: AgentState):
        from .pdf_tools import parse_approved_pdf
        profile = service.profiles[state["role"]]
        try:
            require_tool(profile, "parse_approved_pdf")
            content = parse_approved_pdf(profile, state.get("file_id") or "", service.pdf_registry)
            return {"status": "completed", "content": content, "hits": [],
                    "events": [*state["events"], "approved_pdf_parsed"]}
        except AccessDenied as exc:
            return {"status": "denied", "content": str(exc), "hits": [],
                    "events": [*state["events"], "authorization_denied"]}
        except (ValueError, FileNotFoundError) as exc:
            return {"status": "failed", "content": str(exc), "hits": [],
                    "events": [*state["events"], "execution_failed"]}

    def finish(state: AgentState):
        return {"result": asdict(ExecutionResult(
            task_id=state.get("task_id") or str(uuid4()), actor=state["actor"], role=state["role"],
            expert=state["expert"], tool=state["tool"],
            status=state.get("status", "failed"), content=state.get("content", ""),
            hits=[Hit(**h) for h in state.get("hits", [])], events=state["events"],
        ))}

    graph = StateGraph(AgentState)
    for name, fn in [("load_role", load_role), ("route", route),
                     ("knowledge_expert", knowledge), ("research_expert", research),
                     ("document_expert", document), ("finish", finish)]:
        graph.add_node(name, fn)
    if require_approval:
        graph.add_node("approval_gate", approval_gate)
        graph.add_conditional_edges("approval_gate", after_approval, {
            "document_expert": "document_expert", "finish": "finish",
        })
    graph.add_edge(START, "load_role")
    graph.add_edge("load_role", "route")
    graph.add_conditional_edges("route", next_expert, {
        "knowledge_expert": "knowledge_expert", "research_expert": "research_expert",
        "document_expert": "document_expert", "finish": "finish",
        **({"approval_gate": "approval_gate"} if require_approval else {}),
    })
    for name in ("knowledge_expert", "research_expert", "document_expert"):
        graph.add_edge(name, "finish")
    graph.add_edge("finish", END)
    return graph.compile(checkpointer=checkpointer if checkpointer is not None else InMemorySaver())


def run_agent(graph, principal: Principal, question: str, file_id: str | None = None,
              request_id: str | None = None) -> ExecutionResult:
    """Per-request checkpoint ID is actor-scoped; never use client-supplied role claims."""
    thread_id = f"{principal.user_id}:{request_id or uuid4()}"
    state = graph.invoke(
        {"actor": principal.user_id, "role": principal.role, "question": question, "file_id": file_id},
        config={"configurable": {"thread_id": thread_id}},
    )
    result = dict(state["result"])
    result["hits"] = [Hit(**h) for h in result["hits"]]
    return ExecutionResult(**result)
