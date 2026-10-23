from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class RoleProfile:
    name: str
    display_name: str
    prompt_profile: str
    allowed_partitions: frozenset[str]
    allowed_tools: frozenset[str]
    approved_pdf_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str


@dataclass(frozen=True)
class Document:
    id: str
    partition: str
    source: str
    text: str


@dataclass(frozen=True)
class Hit:
    document_id: str
    partition: str
    source: str
    text: str
    score: float


@dataclass
class ExecutionResult:
    task_id: str
    actor: str
    role: str
    expert: str
    tool: str
    status: Literal["completed", "denied", "failed"]
    content: str
    hits: list[Hit] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
