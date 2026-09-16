"""Tests for external web suggestions (fail-closed proprietary, verbatim URLs)."""
import json


def test_classifier_blocks_proprietary(monkeypatch):
    from src.services.suggest_external import classify_topic_source
    v = classify_topic_source('Learn HR policies', 'Employee salaries and performance reviews',
                              ['HR_Handbook.pdf'])
    assert v['source'] == 'proprietary'
    v2 = classify_topic_source('Learn quantum mechanics', 'Physics textbook chapters',
                               ['physics101.pdf'])
    assert v2['source'] == 'public'


def test_classifier_fail_closed_on_empty():
    from src.services.suggest_external import classify_topic_source
    assert classify_topic_source('', '', [])['source'] == 'proprietary'


def test_sanitize_query_strips_org():
    from src.services.suggest_external import sanitize_query
    q = sanitize_query('Acme Inc. layoff policy bob@acme.com ABC-1234 next topics')
    assert 'Inc' not in q
    assert 'bob@acme.com' not in q
    assert 'ABC-1234' not in q
    # Bare org name without suffix is removed with its suffix pattern.
    assert 'Acme Inc' not in q


def test_external_disabled_by_default(monkeypatch):
    monkeypatch.setenv('WEB_SEARCH_ENABLED', 'false')
    monkeypatch.setenv('AI_MOCK', 'false')
    from src.services.suggest_external import compute_external_suggestions
    out = compute_external_suggestions('Learn physics', [{'title': 'M1'}], summary='Physics')
    assert out['suggestions'] == []


def test_external_proprietary_never_calls_search(monkeypatch):
    monkeypatch.setenv('WEB_SEARCH_ENABLED', 'true')
    monkeypatch.setenv('AI_MOCK', 'false')
    from src.services.suggest_external import compute_external_suggestions
    called = []

    def fake_search(q, max_results=5):
        called.append(q)
        return [{'title': 'X', 'url': 'https://example.com/x', 'content': 'c'}]

    out = compute_external_suggestions(
        'HR onboarding', [{'title': 'Policies'}], summary='Salaries memo',
        file_names=['HR_Handbook.pdf'], search_fn=fake_search, fetch_fn=lambda u: 'body')
    assert out['suggestions'] == []
    assert called == []


def test_external_verbatim_urls_only(monkeypatch):
    monkeypatch.setenv('WEB_SEARCH_ENABLED', 'true')
    monkeypatch.setenv('AI_MOCK', 'false')
    import src.services.suggest_external as ext
    monkeypatch.setattr(ext, 'call_ollama', lambda prompt, model=None: json.dumps({
        "suggestions": [
            {"title": "Quantum Decoherence", "reason": "Next step.",
             "source_refs": "web", "source_urls": ["https://invented.example/bad"]},
            {"title": "Quantum Entanglement", "reason": "Follows.",
             "source_refs": "web", "source_urls": ["https://real.example/a"]},
        ]}))
    fake_results = [{'title': 'A', 'url': 'https://real.example/a', 'content': 'snip'}]
    out = ext.compute_external_suggestions(
        'Learn quantum physics', [{'title': 'Qubits'}], summary='Physics textbook',
        file_names=['physics.pdf'],
        search_fn=lambda q, max_results=5: fake_results,
        fetch_fn=lambda u: 'fetched body about entanglement')
    titles = [s['title'] for s in out['suggestions']]
    assert 'Quantum Entanglement' in titles
    # Invented URL is stripped to [] per strict JSON rule (never invent),
    # but the suggestion itself is kept — accept still works via fallback.
    by_title = {s['title']: s for s in out['suggestions']}
    assert by_title['Quantum Decoherence']['source_urls'] == []
    assert by_title['Quantum Entanglement']['source_urls'] == ['https://real.example/a']
