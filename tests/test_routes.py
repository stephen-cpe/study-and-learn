import io
import tempfile
import pytest
from unittest.mock import patch
from cachelib import FileSystemCache
from src import create_app, db
from src.models import User

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

@pytest.fixture
def logged_in_client(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg2://test:test@localhost:5432/test')
    with tempfile.TemporaryDirectory() as temp_dir:
        app = create_app()
        app.config.update({
            'TESTING': True,
            'UPLOAD_FOLDER': temp_dir,
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'test-secret',
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(cache_dir=temp_dir, threshold=500, mode=0o700),
            'SESSION_PERMANENT': False,
        })
        from flask_session import Session
        Session(app)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.extensions.pop('sqlalchemy', None)
        db.init_app(app)
        with app.app_context():
            db.create_all()
            user = User(username='difftester', email='diff@example.com',
                         can_generate_lessons=True, lesson_difficulty='Hard')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            with app.test_client() as c:
                c.post('/login', data={'username': 'difftester', 'password': 'pass'})
                yield c
            db.session.remove()
            db.drop_all()

def test_index(client):
    response = client.get('/')
    assert response.status_code == 200

def test_process_empty_goal_rejected(client):
    data = {
        'learning_goal': '',
        'files': [(io.BytesIO(b'Test content'), 'test.txt')]
    }
    response = client.post('/process', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b'Please enter a learning goal' in response.data

def test_process_no_files_rejected(client):
    response = client.post('/process', data={'learning_goal': 'Learn testing'},
                           content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b'No valid files' in response.data

def test_process_valid(monkeypatch, client):
    monkeypatch.setenv('AI_MOCK', 'true')
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    monkeypatch.setenv('CI', 'true')

    data = {
        'learning_goal': 'Learn testing',
        'files': [(io.BytesIO(b'Test content'), 'test.txt')]
    }
    with patch("src.services.vision_parser.is_content_registered", return_value=None), \
         patch("src.services.vision_parser.register_content"):
        response = client.post('/process', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b'Processed' in response.data and b'successfully' in response.data

def test_process_invalid_extension(client):
    data = {
        'learning_goal': 'Learn testing',
        'files': [(io.BytesIO(b'Invalid content'), 'test.exe')]
    }
    response = client.post('/process', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b'Allowed file types' in response.data or b'No valid files' in response.data

def test_process_max_files(client):
    files = [(io.BytesIO(f'Content {i}'.encode()), f'test{i}.txt') for i in range(6)]
    data = {'learning_goal': 'Learn testing', 'files': files}
    response = client.post('/process', data=data, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b'Maximum' in response.data and b'5' in response.data


def test_cloze_dropdown_grader():
    from src.services.grader import _grade_single_question, _get_correct_answer
    q = {
        'id': 'q1', 'type': 'cloze_dropdown',
        'prompt': 'Water is ___.',
        'options': ['H2O', 'CO2', 'NaCl', 'O2'],
        'answer_index': 0, 'explanation': 'Water is H2O.'
    }
    assert _grade_single_question(q, 0) is True
    assert _grade_single_question(q, 1) is False
    assert _grade_single_question(q, None) is False
    assert _get_correct_answer(q) == 0


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_lesson_stores_difficulty_from_user(mock_quiz_ollama, mock_lesson_ollama, logged_in_client):
    mock_lesson_ollama.return_value = '{"module_title": "Intro", "slides": [{"type": "title", "title": "Hello", "subtitle": "World"}]}'
    mock_quiz_ollama.return_value = '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Q?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}]}'

    with logged_in_client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']

    from src.repositories.lesson_repo import get_lessons
    from src.models import User

    response = logged_in_client.post('/generate-lessons')
    assert response.status_code == 200

    user = User.query.filter_by(username='difftester').first()
    lessons = get_lessons(user)
    assert len(lessons) > 0
    assert lessons[0].get('difficulty') == 'Hard'


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_save_position_stores_deck_position(mock_quiz_ollama, mock_lesson_ollama, logged_in_client):
    mock_lesson_ollama.return_value = '{"module_title": "Intro", "slides": [{"type": "title", "title": "Hello", "subtitle": "World"}]}'
    mock_quiz_ollama.return_value = '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Q?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}]}'

    with logged_in_client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']

    logged_in_client.post('/generate-lessons')

    rv = logged_in_client.post('/lessons/0/save-position',
        data='{"slide_index": 3}',
        content_type='application/json')
    assert rv.status_code == 200
    assert rv.get_json()['ok'] is True

    from src.repositories.lesson_repo import get_lessons
    from src.models import User
    user = User.query.filter_by(username='difftester').first()
    lessons = get_lessons(user)
    assert lessons[0].get('deck_position') == 3


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_save_position_does_not_overwrite_completed(mock_quiz_ollama, mock_lesson_ollama, logged_in_client):
    mock_lesson_ollama.return_value = '{"module_title": "Intro", "slides": [{"type": "title", "title": "Hello", "subtitle": "World"}]}'
    mock_quiz_ollama.return_value = '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Q?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}]}'

    with logged_in_client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']

    logged_in_client.post('/generate-lessons')

    from src.repositories.lesson_repo import get_lessons, save_lessons
    from src.models import User
    user = User.query.filter_by(username='difftester').first()
    lessons = get_lessons(user)
    lessons[0]['deck_position'] = 2
    lessons[0]['completed'] = True
    save_lessons(lessons, user)

    rv = logged_in_client.post('/lessons/0/save-position',
        data='{"slide_index": 5}',
        content_type='application/json')
    assert rv.status_code == 200

    lessons = get_lessons(user)
    assert lessons[0].get('deck_position') == 2


@pytest.fixture
def tts_enabled_client(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg2://test:test@localhost:5432/test')
    with tempfile.TemporaryDirectory() as temp_dir:
        app = create_app()
        app.config.update({
            'TESTING': True,
            'UPLOAD_FOLDER': temp_dir,
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'test-secret',
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(cache_dir=temp_dir, threshold=500, mode=0o700),
            'SESSION_PERMANENT': False,
        })
        from flask_session import Session
        Session(app)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.extensions.pop('sqlalchemy', None)
        db.init_app(app)
        with app.app_context():
            db.create_all()
            user = User(username='ttstester', email='tts@example.com',
                         can_generate_lessons=True, tts_enabled=True,
                         tts_speaker='Emma', lesson_difficulty='Normal')
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            with app.test_client() as c:
                c.post('/login', data={'username': 'ttstester', 'password': 'pass'})
                yield c
            db.session.remove()
            db.drop_all()


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
@patch('src.services.tts_service.generate_lesson_audio')
def test_generate_lessons_tts_enabled(mock_tts, mock_quiz_ollama, mock_lesson_ollama, tts_enabled_client):
    mock_lesson_ollama.return_value = '{"module_title": "Intro", "slides": [{"type": "title", "title": "Hello", "subtitle": "World"}]}'
    mock_quiz_ollama.return_value = '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Q?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}]}'
    mock_tts.return_value = {'path_id': 'test', 'module_index': 0, 'speaker': 'Emma', 'voice': 'en-US-EmmaNeural', 'slides': {}}

    with tts_enabled_client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']

    response = tts_enabled_client.post('/generate-lessons')
    assert response.status_code == 200

    from src.repositories.lesson_repo import get_lessons
    from src.models import User
    user = User.query.filter_by(username='ttstester').first()
    lessons = get_lessons(user)
    assert len(lessons) > 0
    assert lessons[0].get('tts_enabled') is True
    assert lessons[0].get('tts_speaker') == 'Emma'


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_generate_lessons_tts_disabled(mock_quiz_ollama, mock_lesson_ollama, logged_in_client):
    mock_lesson_ollama.return_value = '{"module_title": "Intro", "slides": [{"type": "title", "title": "Hello", "subtitle": "World"}]}'
    mock_quiz_ollama.return_value = '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Q?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}]}'

    with logged_in_client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']

    response = logged_in_client.post('/generate-lessons')
    assert response.status_code == 200

    from src.repositories.lesson_repo import get_lessons
    from src.models import User
    user = User.query.filter_by(username='difftester').first()
    lessons = get_lessons(user)
    assert len(lessons) > 0
    assert lessons[0].get('tts_enabled') is False


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
@patch('src.services.tts_service.generate_lesson_audio')
def test_generate_lessons_tts_failure_graceful(mock_tts, mock_quiz_ollama, mock_lesson_ollama, tts_enabled_client):
    """Task 5: TTS runs in a background thread. The route itself must
    return successfully even if TTS would fail. The actual failure
    handling is the background worker's job — it catches the error
    per-module and persists tts_enabled=False + tts_audio_status='failed'
    to the lesson dict. We verify the route does NOT crash and the
    response includes the expected keys."""
    mock_lesson_ollama.return_value = '{"module_title": "Intro", "slides": [{"type": "title", "title": "Hello", "subtitle": "World"}]}'
    mock_quiz_ollama.return_value = '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Q?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}]}'
    mock_tts.side_effect = RuntimeError('Simulated TTS failure')

    with tts_enabled_client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']

    response = tts_enabled_client.post('/generate-lessons')
    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert '/lessons' in data.get('redirect', '')
    # New contract: response includes a task_id for polling.
    assert 'task_id' in data, f"Response missing task_id: {data!r}"

    from src.repositories.lesson_repo import get_lessons
    from src.models import User
    user = User.query.filter_by(username='ttstester').first()
    lessons = get_lessons(user)
    assert len(lessons) > 0
    # The lesson is persisted with tts_audio_status='pending' at request
    # time (the background worker will eventually flip it to 'failed' or
    # 'ready' once it actually runs). The exact tts_enabled value depends
    # on whether the background worker has had a chance to run by the time
    # we re-read the lesson — for this test we only assert the structural
    # invariants the route itself is responsible for.
    assert lessons[0].get('tts_audio_status') in ('pending', 'failed', 'n/a')


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_audio_route_404_when_tts_disabled(mock_quiz_ollama, mock_lesson_ollama, logged_in_client):
    mock_lesson_ollama.return_value = '{"module_title": "Intro", "slides": [{"type": "title", "title": "Hello", "subtitle": "World"}]}'
    mock_quiz_ollama.return_value = '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Q?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}]}'

    with logged_in_client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']

    logged_in_client.post('/generate-lessons')

    rv = logged_in_client.get('/lessons/0/audio/0')
    assert rv.status_code == 404


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_audio_manifest_empty_when_no_tts(mock_quiz_ollama, mock_lesson_ollama, logged_in_client):
    mock_lesson_ollama.return_value = '{"module_title": "Intro", "slides": [{"type": "title", "title": "Hello", "subtitle": "World"}]}'
    mock_quiz_ollama.return_value = '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Q?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}]}'

    with logged_in_client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']

    logged_in_client.post('/generate-lessons')

    rv = logged_in_client.get('/lessons/0/audio/manifest')
    assert rv.status_code == 200
    data = rv.get_json()
    assert data == {}


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_extracted_texts_nullified_after_generation(mock_quiz_ollama, mock_lesson_ollama, logged_in_client):
    mock_lesson_ollama.return_value = '{"module_title": "Intro", "slides": [{"type": "title", "title": "Hello", "subtitle": "World"}]}'
    mock_quiz_ollama.return_value = '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Q?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}]}'

    with logged_in_client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']

    logged_in_client.post('/generate-lessons')

    from src.models import User, StudyPath
    user = User.query.filter_by(username='difftester').first()
    path = StudyPath.query.filter_by(user_id=user.id, status='active').first()
    assert path is not None
    assert path.extracted_texts is None


@patch('src.services.lesson_generator.call_ollama')
@patch('src.services.quiz_generator.call_ollama')
def test_first_generation_redirect_includes_path_id(mock_quiz_ollama, mock_lesson_ollama, logged_in_client):
    mock_lesson_ollama.return_value = '{"module_title": "Intro", "slides": [{"type": "title", "title": "Hello", "subtitle": "World"}]}'
    mock_quiz_ollama.return_value = '{"questions": [{"id": "q1", "type": "mcq", "prompt": "Q?", "options": ["A","B","C","D"], "answer_index": 0, "explanation": "E"}]}'

    with logged_in_client.session_transaction() as sess:
        sess['learning_goal'] = 'Learn stuff'
        sess['study_path'] = {'modules': [{'title': 'M1', 'estimated_effort': '1h'}]}
        sess['extracted_texts'] = ['text']

    response = logged_in_client.post('/generate-lessons')
    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    redirect_url = data.get('redirect', '')
    assert '?path_id=' in redirect_url
    path_id_part = redirect_url.split('path_id=')[1]
    assert len(path_id_part) > 0
