# Study-and-Learn

A Flask web application that converts uploaded study materials into structured summaries, study paths, interactive lessons, and auto-graded quizzes using AI.

## Links

- [Public Task Board](https://stephen-cpe.github.io/task-board-v1/)
- [Task Board Repository](https://github.com/stephen-cpe/task-board-v1/)
- [Deployed App](https://studyandlearn.duckdns.org/)
- [Design and Testing Document](https://github.com/stephen-cpe/study-and-learn/blob/main/docs/DESIGN_AND_TESTING.md)

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

### 5. Install Poppler (Windows 11)

The OCR pipeline requires Poppler to render PDF pages for AI vision processing.

1. Download the latest Poppler for Windows from: https://github.com/oschwartz10612/poppler-windows/releases
2. Extract the archive (e.g., `poppler-26.02.0`) to `C:\Program Files\poppler-26.02.0\`
3. Add the `bin` directory to your system `PATH`:
   - Open **System Properties > Environment Variables**
   - Under **System variables**, edit `Path` and add: `C:\Program Files\poppler-26.02.0\Library\bin`
   - Alternatively, set `POPPLER_PATH=C:\Program Files\poppler-26.02.0\Library\bin` in your `.env` file
4. Restart any open terminals for the change to take effect

To verify Poppler is installed correctly:
```bash
pdftoppm -v
```

### 6. Pull Ollama models (local backend only)

If you will run with `AI_BACKEND=local` (the default) and no `OLLAMA_MODEL` override:

```bash
ollama pull qwen3:0.6b
ollama pull qwen3-embedding:0.6b
ollama pull glm-ocr
```

The default models are placeholders. For better results, use larger models such as `qwen3:8b` or `gemma3:4b` if your hardware can accommodate them.

Note: `config.py` ships `OLLAMA_MODEL=gemma3:27b-cloud` as the package default — to run locally without a `.env`, set `AI_BACKEND=local` and `OLLAMA_MODEL=qwen3:0.6b` in your `.env` (see `.env.example`).

`glm-ocr` (0.9B) is the local OCR model. Pulling it alone does NOT enable OCR — OCR is additionally gated by `OCR_FULL=true` (default `false`). With `OCR_FULL=false` the app uses traditional text-layer extraction even if `glm-ocr` is installed; set `OCR_FULL=true` to run AI-powered OCR on PDFs and images. Set `OCR_FIGURE_DESCRIPTION=true` to additionally generate cloud figure descriptions. Note: figure descriptions use `OLLAMA_VISION_MODEL` (default `qwen3.5:397b-cloud`) and require `AI_BACKEND=cloud` with valid `OLLAMA_CLOUD_API_KEY` — they do not run on a purely local setup.

### 7. Create .env file

Copy the provided template and edit it:

```bash
copy .env.example .env
```

Open `.env` and update `SECRET_KEY` with a random string and verify `DATABASE_URL` matches your PostgreSQL credentials.

### 8. Run the application

```bash
python app.py
```

Open http://localhost:5000 in your browser.

## Testing

```bash
pytest -v tests/
```

## Using Ollama Cloud (Optional)

The `AI_BACKEND` env var selects the AI provider. The default is `local` (Ollama on `http://localhost:11434`); setting `AI_BACKEND=cloud` routes all AI calls through the Ollama Cloud OpenAI-compatible endpoint.

1. In your `.env` file, set:
   ```
   AI_BACKEND=cloud
   OLLAMA_CLOUD_API_KEY=your-api-key-here
   OLLAMA_MODEL=gemma3:27b-cloud
   ```

2. Restart the application. All AI calls will route through the Ollama Cloud API instead of your local Ollama instance.

## Mock AI Mode (No Ollama Required)

Set `AI_MOCK=true` in your `.env` file to use mock responses. This is useful for testing or running the app without Ollama installed.

## Documentation

- SRS.md - Software requirements and user stories
- TODO.md - Sprint plan and task backlog
- DESIGN_AND_TESTING.md - Architecture and testing strategy
- STATUS.md - Current sprint state and known issues
- AI_AGENT_PROTOCOL.md - AI agent execution protocol and guardrails

## License

MIT - For educational purposes only.
