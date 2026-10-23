"""Minimal SQLite audit journal storing metadata but never raw prompts or snippets.

For a demo only. A production system needs encryption, retention and event signing.
"""
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from .models import ExecutionResult


@dataclass(frozen=True)
class AuditEntry:
    task_id: str
    actor: str
    role: str
    expert: str
    tool: str
    status: str
    created_at: str


class AuditJournal:
    def __init__(self, path: str | Path = ':memory:'):
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.execute('''CREATE TABLE IF NOT EXISTS task_audit (
            task_id TEXT PRIMARY KEY, actor TEXT NOT NULL, role TEXT NOT NULL,
            expert TEXT NOT NULL, tool TEXT NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL)''')
        self.connection.commit()

    def record(self, result: ExecutionResult) -> AuditEntry:
        entry = AuditEntry(result.task_id, result.actor, result.role,
                           result.expert, result.tool, result.status,
                           datetime.now(timezone.utc).isoformat())
        self.connection.execute('''INSERT INTO task_audit VALUES (?, ?, ?, ?, ?, ?, ?)''', tuple(vars(entry).values()))
        self.connection.commit()
        return entry

    def get_for_actor(self, task_id: str, actor: str) -> AuditEntry | None:
        row = self.connection.execute(
            '''SELECT task_id, actor, role, expert, tool, status, created_at
               FROM task_audit WHERE task_id=? AND actor=?''', (task_id, actor)
        ).fetchone()
        return AuditEntry(*row) if row else None

    def close(self) -> None:
        self.connection.close()
