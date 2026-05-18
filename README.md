# Study-and-Learn

A Flask web application that converts uploaded study materials into structured summaries, study paths, interactive lessons, and auto-graded quizzes using AI.

## Prerequisites

1. Install Python 3.13 from https://python.org
2. Install Ollama from https://ollama.com/download
3. Install PostgreSQL from https://www.postgresql.org/download/windows

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/stephen-cpe/study-and-learn.git
cd study-and-learn
```

### 2. Create virtual environment

```bash
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up PostgreSQL database

Open PowerShell as Administrator and run:

```bash
# Connect to PostgreSQL as postgres superuser
psql -U postgres -h localhost -d postgres

# Inside psql, run these commands:
CREATE DATABASE study_and_learn;
CREATE USER study_user WITH PASSWORD 'study_pass';
GRANT ALL PRIVILEGES ON DATABASE study_and_learn TO study_user;
GRANT CREATE ON SCHEMA public TO study_user;
GRANT USAGE ON SCHEMA public TO study_user;
\q
```

**Quick start with init_db.sql:**

If you already created the database and user, you can skip alembic migrations and load the complete schema in one command:

```bash
psql -U postgres -d study_and_learn -f init_db.sql
```

This creates all tables (`users`, `study_paths`, `lesson_progress`), indexes, foreign keys, and stamps the alembic version so `flask db upgrade` sees the database as current.

### 5. Pull Ollama models

```bash
ollama pull qwen3:0.6b
ollama pull qwen3-embedding:0.6b
```

Note: qwen3:0.6b is a placeholder model. For better results, use qwen3:8b or gemma3:12b if your system can handle it.

### 6. Create .env file

Create a `.env` file in the project root:

```
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn
OLLAMA_MODEL=qwen3:0.6b
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b
```

### 7. Run database migrations (if not using init_db.sql)

If you used `init_db.sql` above, skip this step. Otherwise, apply Alembic migrations:

```bash
flask db upgrade
```

### 8. Seed demo accounts and enable lesson generation

New accounts have lesson generation **disabled by default** (security gate). To enable access:

```bash
flask shell
```

```python
from src import db
from src.models import User

# Promote your account to admin
me = User.query.filter_by(username='your-username').first()
me.is_admin = True
db.session.commit()

# Seed demo accounts (Bob and Alice) with lesson generation enabled
# (or visit /seed-demo in your browser once logged in as admin)
from src.routes import seed_demo  # call via browser /seed-demo instead
```

### 9. Run the application

```bash
python app.py
```

Open http://localhost:5000 in your browser.

## First-Time Admin & Demo Setup

After launching the app:

1. **Sign up** a new account at `/signup`
2. **Promote yourself to admin** (see Step 8 above or use `flask shell`)
3. Log out and log back in so Flask-Login picks up the role change
4. Visit `/seed-demo` to create Bob and Alice (password: `demo123`)
5. Toggle lesson generation for any user at `/admin/toggle/<user_id>`

## Testing

```bash
pytest -v tests/
```

## Using Ollama Cloud (Optional)

To use Ollama Cloud instead of local models:

1. In `src/services/ai_client.py`, uncomment line 28:
   ```python
   from .ai_client_cloud import call_ollama
   ```

2. Add to your `.env` file:
   ```
   OLLAMA_CLOUD_API_KEY=your-api-key-here
   OLLAMA_MODEL=gemma3:12b-cloud
   ```

## Testing without GPU

Set `AI_MOCK=true` in your `.env` file to use mock responses (no Ollama required).

## Documentation

- SRS.md - Software requirements and user stories
- TODO.md - Sprint plan and task backlog
- DESIGN_AND_TESTING.md - Architecture and testing strategy

## License

MIT - For educational purposes only.
