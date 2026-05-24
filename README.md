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
ollama pull glm-ocr
```

The default models are placeholders. For better results, use larger models such as `qwen3:8b` or `gemma3:4b` if your hardware can accommodate them.

`glm-ocr` (0.9B) enables AI-powered OCR for PDFs and images. If you skip this step, the app falls back to traditional text-only extraction.

### 6. Create .env file

Copy the provided template and edit it:

```bash
copy .env.example .env
```

Open `.env` and update `SECRET_KEY` with a random string and verify `DATABASE_URL` matches your PostgreSQL credentials.

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

1. In your `.env` file, set:
   ```
   AI_BACKEND=cloud
   OLLAMA_CLOUD_API_KEY=your-api-key-here
   OLLAMA_MODEL=gemma3:12b-cloud
   ```

2. Restart the application. All AI calls will route through the Ollama Cloud API instead of your local Ollama instance.

## Mock AI Mode (No Ollama Required)

Set `AI_MOCK=true` in your `.env` file to use mock responses. This is useful for testing or running the app without Ollama installed.

## Documentation

- SRS.md - Software requirements and user stories
- TODO.md - Sprint plan and task backlog
- DESIGN_AND_TESTING.md - Architecture and testing strategy

## Links
- [Public Task Board](https://stephen-cpe.github.io/task-board-v1/)
- [Task Board Repository](https://github.com/stephen-cpe/task-board-v1/)
- [Deployed App](#) *(coming soon — Sprint 7)*

## License

MIT - For educational purposes only.
