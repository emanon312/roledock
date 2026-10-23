def test_search_with_no_matching_terms_does_not_return_unrelated_docs(service):
    profile = service.profiles['ir']
    assert service.kb.search('zzzz_unrelated_token_2092', profile) == []
