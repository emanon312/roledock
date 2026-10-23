"""Deterministic prototype routing; model-classified routing will be guarded similarly."""
from .models import RoleProfile
from .security import AccessDenied, require_tool


def route_task(question: str) -> tuple[str, str]:
    text = question.casefold()
    if any(term in text for term in ["pdf", "解析文件", "解析报告", "解析pdf"]):
        return "document_expert", "parse_approved_pdf"
    if any(term in text for term in ["研究计划", "调研计划", "research plan", "行业调研"]):
        return "research_expert", "research_plan"
    return "knowledge_expert", "search_knowledge"


def authorize_task(profile: RoleProfile, tool: str) -> None:
    require_tool(profile, tool)
