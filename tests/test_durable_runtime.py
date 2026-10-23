"""v0.4 HITL, actor isolation and replay-safe request handling."""
from pathlib import Path

import pytest
from roledock.durable_runtime import DurableAgentRuntime, TaskLedger
from roledock.models import Principal
from roledock.pdf_tools import synthetic_finance_pdf_registry
from roledock.runtime import RoleDock
from roledock.security import AccessDenied


def test_task_ledger_deduplicates_matching_requests(tmp_path, principals):
    ledger = TaskLedger(tmp_path / "tasks.sqlite")
    p = principals["finance"]
    first, created = ledger.register(p, "unique-001", "解析 PDF", "sample-finance-policy")
    assert created
    second, created = ledger.register(p, "unique-001", "解析 PDF", "sample-finance-policy")
    assert not created and first["task_id"] == second["task_id"]
    with pytest.raises(ValueError, match="idempotency_key_reused"):
        ledger.register(p, "unique-001", "不同内容", "sample-finance-policy")
    other, created = ledger.register(principals["investor"], "unique-001", "解析 PDF", None)
    assert created and other["task_id"] != first["task_id"]
    with pytest.raises(AccessDenied, match="task_not_found"):
        ledger.task_for_actor(first["task_id"], principals["investor"].user_id)
    with pytest.raises(ValueError, match="invalid_idempotency_key"):
        ledger.register(p, "../unsafe/path", "PDF", None)
    ledger.close()


def test_ledger_reviewer_role_and_separation_of_duties(tmp_path, principals):
    ledger = TaskLedger(tmp_path / "tasks.sqlite")
    owner = principals["finance"]
    row, _ = ledger.register(owner, "review-1", "解析 PDF", "sample-finance-policy")
    ledger.update(row["task_id"], "pending_approval")
    with pytest.raises(AccessDenied, match="reviewer_role_denied"):
        ledger.record_review(row["task_id"], owner, True)
    with pytest.raises(AccessDenied, match="self_approval_denied"):
        ledger.record_review(row["task_id"], Principal(owner.user_id, "admin"), True)
    preview = ledger.review_preview(row["task_id"], principals["admin"])
    assert preview == {"task_id": row["task_id"], "requester_role": "finance",
                       "tool": "parse_approved_pdf", "file_id": "sample-finance-policy",
                       "status": "pending_approval"}
    with pytest.raises(AccessDenied, match="reviewer_role_denied"):
        ledger.review_preview(row["task_id"], principals["investor"])
    ledger.record_review(row["task_id"], principals["compliance"], True)
    with pytest.raises(ValueError, match="review_already_decided"):
        ledger.record_review(row["task_id"], principals["admin"], True)
    assert ledger.decision_for(row["task_id"], owner.user_id, "sample-finance-policy") == "approved"
    assert ledger.decision_for(row["task_id"], "different-actor", "sample-finance-policy") is None
    assert ledger.decision_for(row["task_id"], owner.user_id, "wrong-document") is None
    with pytest.raises(ValueError, match="review_already_decided"):
        ledger.record_review(row["task_id"], principals["admin"], False)
    ledger.close()


def _runtime(tmp_path, registry=None):
    service = RoleDock(pdf_registry=registry or synthetic_finance_pdf_registry())
    return DurableAgentRuntime(service, tmp_path / "state")


def test_hitl_sqlite_resume_after_restart_and_idempotency(tmp_path, principals):
    pytest.importorskip("langgraph.checkpoint.sqlite")
    finance, compliance = principals["finance"], principals["compliance"]
    with _runtime(tmp_path) as runtime:
        initial = runtime.submit(finance, "请解析pdf", "pdf-1", "sample-finance-policy")
        assert initial["status"] == "pending_approval"
        assert initial["approval"]["file_id"] == "sample-finance-policy"
        task_id = initial["task_id"]
        replay = runtime.submit(finance, "请解析pdf", "pdf-1", "sample-finance-policy")
        assert replay == initial
        with pytest.raises(AccessDenied, match="reviewer_role_denied"):
            runtime.review(finance, task_id, True)
        with pytest.raises(AccessDenied, match="task_not_found"):
            runtime.get(principals["investor"], task_id)
    # Both ledger and checkpoint must survive process/connection restart.
    with _runtime(tmp_path) as runtime:
        assert runtime.get(finance, task_id)["status"] == "pending_approval"
        reviewer_view = runtime.review(compliance, task_id, True)
        assert reviewer_view["status"] == "completed"
        assert "result" not in reviewer_view  # reviewer cannot read finance PDF text
        owner_view = runtime.get(finance, task_id)
        assert owner_view["result"]["status"] == "completed"
        assert owner_view["result"]["task_id"] == task_id
        assert "synthetic finance policy" in owner_view["result"]["content"]
        assert "human_review_approved" in owner_view["result"]["events"]
        assert runtime.review(compliance, task_id, True)["status"] == "completed"
        assert runtime.submit(finance, "请解析pdf", "pdf-1", "sample-finance-policy") == owner_view


def test_rejection_is_final_and_no_document_content_returned(tmp_path, principals):
    pytest.importorskip("langgraph.checkpoint.sqlite")
    with _runtime(tmp_path) as runtime:
        finance = principals["finance"]
        task = runtime.submit(finance, "解析pdf", "pdf-deny", "sample-finance-policy")
        review = runtime.review(principals["admin"], task["task_id"], False)
        assert review["status"] == "denied" and "result" not in review
        owner_view = runtime.get(finance, task["task_id"])
        assert owner_view["result"]["content"] == "human_review_rejected"
        assert "synthetic finance policy" not in str(owner_view)


def test_unauthorized_pdf_never_interrupts(tmp_path, principals):
    pytest.importorskip("langgraph.checkpoint.sqlite")
    with _runtime(tmp_path) as runtime:
        investor = runtime.submit(principals["investor"], "解析pdf", "denied", "sample-finance-policy")
        assert investor["status"] == "denied"
        assert "approval" not in investor
        missing = runtime.submit(principals["finance"], "解析pdf", "missing", "unknown-file")
        assert missing["status"] == "denied"
        assert "approval" not in missing


def test_forged_resume_command_without_review_ledger_cannot_parse(tmp_path, principals):
    pytest.importorskip("langgraph.checkpoint.sqlite")
    from langgraph.types import Command
    with _runtime(tmp_path) as runtime:
        task = runtime.submit(principals["finance"], "解析pdf", "forged", "sample-finance-policy")
        state = runtime.graph.invoke(Command(resume={"approved": True, "role": "admin"}),
                                     runtime._config(task["task_id"]))
        assert state["result"]["status"] == "denied"
        assert state["result"]["content"] == "approval_not_recorded"
        assert "synthetic finance policy" not in str(state)


def test_non_pdf_task_runs_without_approval(tmp_path, principals):
    pytest.importorskip("langgraph.checkpoint.sqlite")
    with _runtime(tmp_path) as runtime:
        task = runtime.submit(principals["investor"], "新能源汽车产业研究", "search-1")
        assert task["status"] == "completed" and "approval" not in task
        assert task["result"]["expert"] == "knowledge_expert"
