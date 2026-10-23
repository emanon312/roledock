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


def build_agent_graph(service, model=None, checkpointer=None):
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
        return state["expert"]

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
            task_id=str(uuid4()), actor=state["actor"], role=state["role"],
            expert=state["expert"], tool=state["tool"],
            status=state.get("status", "failed"), content=state.get("content", ""),
            hits=[Hit(**h) for h in state.get("hits", [])], events=state["events"],
        ))}

    graph = StateGraph(AgentState)
    for name, fn in [("load_role", load_role), ("route", route),
                     ("knowledge_expert", knowledge), ("research_expert", research),
                     ("document_expert", document), ("finish", finish)]:
        graph.add_node(name, fn)
    graph.add_edge(START, "load_role")
    graph.add_edge("load_role", "route")
    graph.add_conditional_edges("route", next_expert, {
        "knowledge_expert": "knowledge_expert", "research_expert": "research_expert",
        "document_expert": "document_expert", "finish": "finish",
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
