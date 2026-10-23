def test_domain_roles_restrict_data(service):
    deal = service.profiles['deal']
    compliance = service.profiles['compliance']
    assert 'deal_execution' in deal.allowed_partitions
    assert 'company_finance' not in deal.allowed_partitions
    assert 'deal_diligence' in compliance.allowed_partitions
    assert 'deal_execution' not in compliance.allowed_partitions


def test_all_roles_reference_real_partitions(service):
    available = {d.partition for d in service.kb.all_documents_for_admin_seed()}
    for role in service.profiles.values():
        assert role.allowed_partitions <= available, role.name
