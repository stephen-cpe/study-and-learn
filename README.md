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

Open PowerShell as Administrator:

```bash
psql -U postgres
```

Inside psql:

```sql
-- Only run these if you want to start from scratch
DROP DATABASE IF EXISTS study_and_learn;
DROP OWNED BY study_user CASCADE;
DROP USER IF EXISTS study_user;

CREATE USER study_user WITH PASSWORD 'study_pass';
CREATE DATABASE study_and_learn;
ALTER DATABASE study_and_learn OWNER TO study_user;
GRANT CREATE ON SCHEMA public TO study_user;
\q
```

Initialize database schema:

```bash
psql -U postgres -d study_and_learn -f init_db.sql
```

This creates all tables, indexes, foreign keys, stamps the alembic version, and seeds three pre-configured accounts:

| Username | Password       | Role  | Can generate lessons |
|----------|---------------|-------|----------------------|
| admin    | ADMINpassword | ADMIN | Yes                  |
| bob      | BOBpassword   | USER  | Yes                  |
| alice    | ALICEpassword | USER  | Yes                  |

### 5. Pull Ollama models

```bash
ollama pull qwen3:0.6b
ollama pull qwen3-embedding:0.6b
```

The default models are placeholders. For better results, use larger models such as `qwen3:8b` or `gemma3:4b` if your hardware can accommodate them.

### 6. Create .env file

Create a `.env` file in the project root:

```
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn
OLLAMA_MODEL=qwen3:0.6b
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b
```

### 7. Run the application

```bash
python app.py
```

Open http://localhost:5000 in your browser.

## Testing

```bash
pytest -v tests/
```

## Using Ollama Cloud (Optional)

1. In `src/services/ai_client.py`, uncomment:
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
