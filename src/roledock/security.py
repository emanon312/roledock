"""Server-side authorization is the source of truth, not model output or prompts."""
import json
from pathlib import Path
from .models import Principal, RoleProfile


class AccessDenied(PermissionError):
    pass


DEMO_IDENTITIES = {
    "demo-investor-key": Principal("user-investor", "investor"),
    "demo-ir-key": Principal("user-ir", "ir"),
    "demo-finance-key": Principal("user-finance", "finance"),
    "demo-ops-key": Principal("user-ops", "ops"),
    "demo-admin-key": Principal("user-admin", "admin"),
    "demo-deal-key": Principal("user-deal", "deal"),
    "demo-compliance-key": Principal("user-compliance", "compliance"),
}


def load_profiles(path: str | Path) -> dict[str, RoleProfile]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        name: RoleProfile(
            name=name,
            display_name=raw["display_name"],
            prompt_profile=raw["prompt_profile"],
            allowed_partitions=frozenset(raw["allowed_partitions"]),
            allowed_tools=frozenset(raw["allowed_tools"]),
            approved_pdf_ids=frozenset(raw.get("approved_pdf_ids", [])),
        ) for name, raw in data.items()
    }


def require_tool(profile: RoleProfile, tool: str) -> None:
    if tool not in profile.allowed_tools:
        raise AccessDenied(f"tool_denied:{tool}")


def require_partition(profile: RoleProfile, partition: str) -> None:
    if partition not in profile.allowed_partitions:
        raise AccessDenied("partition_denied")


def require_document(profile: RoleProfile, document_id: str) -> None:
    if document_id not in profile.approved_pdf_ids:
        raise AccessDenied("document_denied")
