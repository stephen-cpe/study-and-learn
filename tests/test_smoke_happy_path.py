"""
Full happy-path smoke test — exercises the entire learner workflow end-to-end.

Routes covered
--------------
/                     → index
POST /process         → upload + AI analysis
/results              → summary / relevance / study path
POST /generate-lessons → lesson + quiz + checkpoint generation
/lessons              → module listing
/lessons/<i>          → slide deck
POST /lessons/<i>/grade → quiz grading
"""
import io
import json
import tempfile
import pytest
from cachelib import FileSystemCache
from src import create_app, db
from src.models import User
from src.repositories.lesson_repo import get_lessons


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(
        'DATABASE_URL',
        'postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn'
    )
    monkeypatch.setenv('AI_MOCK', 'true')
    with tempfile.TemporaryDirectory() as temp_dir:
        app_instance = create_app()
        app_instance.config.update({
            'TESTING': True,
            'UPLOAD_FOLDER': temp_dir,
            'WTF_CSRF_ENABLED': False,
            'SECRET_KEY': 'test-secret',
            'SESSION_TYPE': 'cachelib',
            'SESSION_CACHELIB': FileSystemCache(
                cache_dir=temp_dir, threshold=500, mode=0o700
            ),
            'SESSION_PERMANENT': False,
        })
        from flask_session import Session
        Session(app_instance)
        app_instance.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app_instance.extensions.pop('sqlalchemy', None)
        db.init_app(app_instance)
        with app_instance.app_context():
            db.create_all()
            user = User(username='smoker', email='smoke@example.com',
                         can_generate_lessons=True)
            user.set_password('pass')
            db.session.add(user)
            db.session.commit()
            with app_instance.test_client() as c:
                c.post('/login', data={'username': 'smoker', 'password': 'pass'})
                yield c
            db.session.remove()
            db.drop_all()


def test_full_happy_path_mocked(client):
    """End-to-end smoke test using mocked AI responses."""
    # 1) Landing page
    rv = client.get('/')
    assert rv.status_code == 200
    assert b'Study' in rv.data or b'Learn' in rv.data

    # 2) Upload a document
    data = {
        'learning_goal': 'Learn basic physics',
        'files': (io.BytesIO(b'Force equals mass times acceleration.'), 'physics.txt'),
    }
    rv = client.post('/process', data=data, content_type='multipart/form-data')
    assert rv.status_code in (200, 302)
    if rv.status_code == 200:
        payload = json.loads(rv.data)
        assert 'redirect' in payload
        rv = client.get(payload['redirect'])
    else:
        rv = client.get('/results')
    assert rv.status_code == 200
    assert b'physics' in rv.data.lower() or b'Force' in rv.data

    # 3) Trigger lesson generation
    rv = client.post('/generate-lessons')
    assert rv.status_code == 200
    import json
    redirect_url = rv.get_json().get('redirect', '')
    assert redirect_url, 'Expected redirect URL in generate-lessons response'
    rv = client.get(redirect_url)
    assert rv.status_code == 200
    assert b'pass' in rv.data.lower() or b'module' in rv.data.lower()

    # 4) Open first module deck
    rv = client.get('/lessons/0')
    assert rv.status_code == 200

    # 5) Grade with fake answers (fetch from DB-backed repo)
    from src.models import User as U
    user = U.query.filter_by(username='smoker').first()
    lessons_data = get_lessons(user)
    lesson = lessons_data[0]
    quiz = lesson['quiz']
    checkpoints = lesson.get('checkpoints', {})
    questions = quiz.get('questions', [])

    answers = []
    fill_blank_answers = {}
    for q in questions:
        if q['type'] == 'fill_blank':
            fill_blank_answers[q['id']] = 'answer'
        elif q['type'] in ('mcq', 'true_false'):
            answers.append(0)
        elif q['type'] == 'multi_select':
            answers.append([0])
        else:
            answers.append(None)

    checkpoint_answers = {}
    for k, v in checkpoints.items():
        checkpoint_answers[k] = 0

    payload = {
        'answers': answers,
        'fill_blank_answers': fill_blank_answers,
        'checkpoint_answers': checkpoint_answers,
    }
    rv = client.post(
        '/lessons/0/grade',
        data=json.dumps(payload),
        content_type='application/json'
    )
    assert rv.status_code == 200
    result = json.loads(rv.data)
    assert 'score' in result
    assert 'passed' in result

    # 6) Retake should reset state
    rv = client.post('/lessons/0/retake')
    assert rv.status_code == 200
    assert json.loads(rv.data)['success'] is True
