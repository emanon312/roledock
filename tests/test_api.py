from fastapi.testclient import TestClient
from roledock.api import app

client = TestClient(app)


def test_unauthenticated_rejected():
    response = client.post("/v1/tasks", json={"question": "行业"})
    assert response.status_code == 401


def test_api_does_not_accept_claimed_role():
    response = client.post("/v1/tasks", headers={"X-Demo-Key": "demo-ir-key"},
                           json={"question": "交易财务", "role": "admin"})
    assert response.status_code == 200
    assert response.json()["role"] == "ir"
    assert all(item["partition"] != "company_finance" for item in response.json()["hits"])


def test_health_reports_not_ready():
    response = client.get("/health")
    assert response.json()["production_ready"] is False
