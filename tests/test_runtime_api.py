"""v0.4 API authorization and optional real integration with LangGraph."""
from fastapi.testclient import TestClient
from roledock.api import app

client = TestClient(app)


def test_runtime_api_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ROLEDOCK_ENABLE_RUNTIME_API", raising=False)
    url = "/v1/runtime/tasks"
    assert client.post(url, json={"question": "hi", "request_key": "abc"}).status_code == 401
    r = client.post(url, headers={"X-Demo-Key": "demo-finance-key"},
                    json={"question": "hi", "request_key": "abc"})
    assert r.status_code == 503
    assert r.json()["detail"] == "runtime_api_not_enabled"


def test_runtime_api_end_to_end(monkeypatch, tmp_path):
    import pytest
    pytest.importorskip("langgraph.checkpoint.sqlite")
    monkeypatch.setenv("ROLEDOCK_ENABLE_RUNTIME_API", "1")
    monkeypatch.setenv("ROLEDOCK_STATE_DIR", str(tmp_path / "runtime"))
    monkeypatch.delenv("ROLEDOCK_RUNTIME_USE_MODEL", raising=False)
    body = {"question": "解析pdf", "request_key": "http-pdf-001", "file_id": "sample-finance-policy"}
    headers = {"X-Demo-Key": "demo-finance-key"}
    r = client.post("/v1/runtime/tasks", headers=headers, json=body)
    assert r.status_code == 200, r.text
    task = r.json()
    assert task["status"] == "pending_approval"
    assert client.post("/v1/runtime/tasks", headers=headers, json=body).json()["task_id"] == task["task_id"]
    assert client.post("/v1/runtime/tasks", headers=headers,
                       json={**body, "question": "other"}).status_code == 409
    assert client.get(f"/v1/runtime/tasks/{task['task_id']}",
                      headers={"X-Demo-Key": "demo-investor-key"}).status_code == 404
    reviewer_url = f"/v1/runtime/tasks/{task['task_id']}/review"
    preview_url = f"/v1/runtime/reviews/{task['task_id']}"
    assert client.get(preview_url, headers=headers).status_code == 403
    preview = client.get(preview_url, headers={"X-Demo-Key": "demo-compliance-key"})
    assert preview.status_code == 200
    assert preview.json()["file_id"] == "sample-finance-policy"
    assert "question" not in preview.json()
    assert client.post(reviewer_url, headers=headers, json={"approved": True}).status_code == 403
    reviewed = client.post(reviewer_url, headers={"X-Demo-Key": "demo-compliance-key"},
                           json={"approved": True})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "completed" and "result" not in reviewed.json()
    fetched = client.get(f"/v1/runtime/tasks/{task['task_id']}", headers=headers)
    assert fetched.status_code == 200 and fetched.json()["result"]["status"] == "completed"
