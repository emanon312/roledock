"""Role -> task router -> authorized executor -> provenance-rich response."""
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4
from .knowledge import InMemoryKnowledge
from .models import ExecutionResult, Principal, RoleProfile
from .pdf_tools import ApprovedPdfRegistry, parse_approved_pdf
from .routing import route_task, authorize_task
from .security import AccessDenied, load_profiles

ROOT = Path(__file__).resolve().parents[2]


class RoleDock:
    def __init__(self, profiles: dict[str, RoleProfile] | None = None,
                 kb: InMemoryKnowledge | None = None, pdf_registry: ApprovedPdfRegistry | None = None):
        self.profiles = profiles or load_profiles(ROOT / "config" / "roles.json")
        self.kb = kb or InMemoryKnowledge.from_json(ROOT / "demo_data" / "documents.json")
        self.pdf_registry = pdf_registry or ApprovedPdfRegistry()

    def execute(self, principal: Principal, question: str, file_id: str | None = None) -> ExecutionResult:
        if principal.role not in self.profiles:
            raise AccessDenied("unknown_role")
        profile = self.profiles[principal.role]
        expert, tool = route_task(question)
        events = ["role_profile_loaded", "task_routed"]
        # Tool choice is never authority: model or user cannot elevate a role.
        try:
            authorize_task(profile, tool)
            events.append("tool_authorized")
            if tool == "search_knowledge":
                hits = self.kb.search(question, profile)
                events += ["acl_prefilter_applied", "retrieved_hits_validated"]
                content = "\n".join(f"[{h.document_id}] {h.text} (source: {h.source})" for h in hits) or "无授权检索结果。"
                return ExecutionResult(str(uuid4()), principal.user_id, profile.name, expert, tool, "completed", content, hits, events)
            if tool == "research_plan":
                content = "研究计划（确定性演示）：定义问题 → 核实来源 → 检索授权材料 → 形成证据表 → 报告与复核。"
                events.append("research_template_generated")
                return ExecutionResult(str(uuid4()), principal.user_id, profile.name, expert, tool, "completed", content, [], events)
            if tool == "parse_approved_pdf":
                # No user-supplied path, only pre-registered approved file IDs.
                content = parse_approved_pdf(profile, file_id or "", self.pdf_registry)
                events.append("approved_pdf_parsed")
                return ExecutionResult(str(uuid4()), principal.user_id, profile.name, expert, tool, "completed", content, [], events)
            raise AccessDenied("unsupported_tool")
        except AccessDenied as exc:
            events.append("authorization_denied")
            return ExecutionResult(str(uuid4()), principal.user_id, profile.name, expert, tool, "denied", str(exc), [], events)
        except (FileNotFoundError, ValueError) as exc:
            events.append("execution_failed")
            return ExecutionResult(str(uuid4()), principal.user_id, profile.name, expert, tool, "failed", str(exc), [], events)


def build_langgraph(service: RoleDock, checkpointer=None):
    """Optional real LangGraph orchestration; install `pip install -e '.[agent]'`."""
    try:
        from langgraph.graph import StateGraph, START, END
        from langgraph.checkpoint.memory import InMemorySaver
    except ImportError as exc:
        raise RuntimeError("LangGraph not installed. Run: pip install -e '.[agent]'") from exc
    from typing import TypedDict, NotRequired

    class TaskState(TypedDict):
        principal: Principal
        question: str
        file_id: NotRequired[str | None]
        role: NotRequired[str]
        expert: NotRequired[str]
        tool: NotRequired[str]
        result: NotRequired[dict]

    def load_role(state: TaskState):
        role = state["principal"].role
        if role not in service.profiles:
            raise AccessDenied("unknown_role")
        return {"role": role}

    def route(state: TaskState):
        expert, tool = route_task(state["question"])
        return {"expert": expert, "tool": tool}

    def execute(state: TaskState):
        result = service.execute(state["principal"], state["question"], state.get("file_id"))
        return {"result": asdict(result)}

    graph = StateGraph(TaskState)
    graph.add_node("load_role", load_role)
    graph.add_node("route_task", route)
    graph.add_node("authorized_execution", execute)
    graph.add_edge(START, "load_role")
    graph.add_edge("load_role", "route_task")
    graph.add_edge("route_task", "authorized_execution")
    graph.add_edge("authorized_execution", END)
    return graph.compile(checkpointer=checkpointer or InMemorySaver())
