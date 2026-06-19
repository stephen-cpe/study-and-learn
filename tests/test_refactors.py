"""
Tests for Sprint 5 Phase 0.2 refactors.

Covers:
- lesson_orchestrator.build_module_artifacts
- grader._grade_single_question and _get_correct_answer
"""
import pytest
import tempfile
from unittest.mock import patch

from cachelib import FileSystemCache
from src import create_app
from src.services.lesson_orchestrator import build_module_artifacts, make_retriever
from src.services.grader import _grade_single_question, _get_correct_answer


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg2://test:test@localhost:5432/test')
    with tempfile.TemporaryDirectory() as temp_dir:
        app = create_app()
        app.config['TESTING'] = True
        app.config['UPLOAD_FOLDER'] = temp_dir
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SECRET_KEY'] = 'test-secret'
        app.config['SESSION_TYPE'] = 'cachelib'
        app.config['SESSION_CACHELIB'] = FileSystemCache(cache_dir=temp_dir, threshold=500, mode=0o700)
        app.config['SESSION_PERMANENT'] = False
        from flask_session import Session
        Session(app)
        with app.test_client() as client:
            with app.app_context():
                yield client


# ──────────────────────────────────────────────────────────────
# lesson_orchestrator
# ──────────────────────────────────────────────────────────────

def dummy_retriever(query: str):
    return {"context_text": "dummy context", "sources": []}


def test_build_module_artifacts_returns_expected_keys(monkeypatch):
    monkeypatch.setenv('AI_MOCK', 'true')
    module = {"title": "Test Module"}
    result = build_module_artifacts(module, "goal", dummy_retriever)
    assert set(result.keys()) >= {"lesson", "quiz", "checkpoints"}
    assert isinstance(result["checkpoints"], dict)


def test_build_module_artifacts_reuses_existing_slides():
    module = {"title": "Reuse Test"}
    existing_slides = [{"type": "content", "text": "Slide 1"}]
    with patch("src.services.lesson_orchestrator.generate_quiz") as mock_quiz:
        mock_quiz.return_value = {"questions": []}
        with patch("src.services.lesson_orchestrator.generate_inline_checkpoint") as mock_cp:
            mock_cp.return_value = {"type": "mcq", "prompt": "q"}
            result = build_module_artifacts(
                module, "goal", dummy_retriever, existing_slides=existing_slides
            )
    assert result["lesson"]["slides"] == existing_slides


@patch('src.services.lesson_orchestrator.build_rag_context')
def test_make_retriever_returns_context_when_texts_present(mock_build_rag):
    mock_build_rag.return_value = "text one text two"
    retriever = make_retriever("goal", ["text one", "text two"])
    result = retriever("query")
    assert isinstance(result, dict)
    assert "text one" in result["context_text"]
    assert "text two" in result["context_text"]
    assert isinstance(result["sources"], list)


def test_make_retriever_returns_empty_when_no_texts():
    retriever = make_retriever("goal", [])
    result = retriever("q")
    assert isinstance(result, dict)
    assert result["context_text"] == ""
    assert result["sources"] == []


# ──────────────────────────────────────────────────────────────
# grader
# ──────────────────────────────────────────────────────────────

class TestGradeSingleQuestion:
    def test_mcq_correct(self):
        q = {"type": "mcq", "answer_index": 2}
        assert _grade_single_question(q, 2) is True

    def test_mcq_incorrect(self):
        q = {"type": "mcq", "answer_index": 2}
        assert _grade_single_question(q, 1) is False

    def test_true_false_correct(self):
        q = {"type": "true_false", "answer": True}
        assert _grade_single_question(q, "true") is True
        assert _grade_single_question(q, True) is True

    def test_true_false_incorrect(self):
        q = {"type": "true_false", "answer": True}
        assert _grade_single_question(q, "false") is False
        assert _grade_single_question(q, False) is False

    def test_multi_select_correct(self):
        q = {"type": "multi_select", "answer_indices": [0, 2]}
        assert _grade_single_question(q, [0, 2]) is True

    def test_multi_select_incorrect(self):
        q = {"type": "multi_select", "answer_indices": [0, 2]}
        assert _grade_single_question(q, [0, 1]) is False

    def test_fill_blank_correct(self):
        q = {"type": "fill_blank", "answer": "gravity", "acceptable_answers": ["gravity"]}
        assert _grade_single_question(q, "gravity") is True
        assert _grade_single_question(q, " Gravity ") is True

    def test_fill_blank_rejects_multi_word(self):
        q = {"type": "fill_blank", "answer": "gravity", "acceptable_answers": ["gravity"]}
        assert _grade_single_question(q, "force of gravity") is False

    def test_fill_blank_rejects_empty(self):
        q = {"type": "fill_blank", "answer": "gravity", "acceptable_answers": ["gravity"]}
        assert _grade_single_question(q, "") is False
        assert _grade_single_question(q, None) is False

    def test_unknown_type_returns_false(self):
        q = {"type": "short_answer", "answer": "foo"}
        assert _grade_single_question(q, "foo") is False


def test_get_correct_answer_all_types():
    assert _get_correct_answer({"type": "mcq", "answer_index": 3}) == 3
    assert _get_correct_answer({"type": "true_false", "answer": False}) is False
    assert _get_correct_answer({"type": "multi_select", "answer_indices": [1]}) == [1]
    assert _get_correct_answer({"type": "fill_blank", "answer": "moon"}) == "moon"
    assert _get_correct_answer({"type": "unknown"}) is None



