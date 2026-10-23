from dataclasses import asdict
from fastapi.testclient import TestClient
from roledock.audit import AuditJournal
from roledock.api import app


def test_metadata_only_journal(service, principals):
    journal = AuditJournal()
    result = service.execute(principals['ir'], '财务敏感词和内部问题')
    journal.record(result)
    rec = journal.get_for_actor(result.task_id, principals['ir'].user_id)
    assert rec and rec.status == 'completed'
    assert '财务敏感词' not in str(asdict(rec))
    assert journal.get_for_actor(result.task_id, 'other-user') is None
    journal.close()


def test_api_audit_is_actor_scoped():
    client = TestClient(app)
    response = client.post('/v1/tasks', headers={'X-Demo-Key': 'demo-ir-key'},
                           json={'question':'公司公开材料'})
    assert response.status_code == 200
    task_id = response.json()['task_id']
    own = client.get(f'/v1/tasks/{task_id}/audit', headers={'X-Demo-Key':'demo-ir-key'})
    other = client.get(f'/v1/tasks/{task_id}/audit', headers={'X-Demo-Key':'demo-finance-key'})
    assert own.status_code == 200
    assert own.json()['actor'] == 'user-ir'
    assert other.status_code == 404
