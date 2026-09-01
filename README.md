# Study-and-Learn

## Prerequisites

1. Install Python 3.14 from https://python.org
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

This creates all tables (users, study_paths, content_registry, lesson_progress, mascot_memory), indexes, foreign keys, stamps the alembic version, and seeds three pre-configured accounts. The `users` table includes optional `nickname` and `full_name` columns (NULL by default) — set them in **Settings** to make the mascot and narration address the learner by a friendly name instead of the login handle. The `mascot_memory` table stores the mascot's per-learner long-term memory (preferences, quiz outcomes, study path events) so the speech bubble can produce personalized, context-aware lines.

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

The default models are working placeholders — override `OLLAMA_MODEL` with any chat model from the Ollama library that fits your hardware (e.g. a larger model for better quality). The embedding (`qwen3-embedding:0.6b`) and OCR (`glm-ocr`) models are also overridable via `OLLAMA_EMBEDDING_MODEL` and `OLLAMA_OCR_MODEL`.

Note: `config.py` ships `OLLAMA_MODEL=deepseek-v4-flash:cloud` as the package default (used in cloud mode). To run locally, set `AI_BACKEND=local` and `OLLAMA_MODEL=qwen3:0.6b` in your `.env` (see `.env.example`). Any chat model can be substituted via `OLLAMA_MODEL`.

**For cloud deployment (`AI_BACKEND=cloud`):** You only need to pull `qwen3-embedding:0.6b` locally — the embedding model runs on the server for ChromaDB RAG retrieval (Ollama Cloud does not expose the `/api/embed` endpoint). The chat model runs on Ollama Cloud and does NOT need to be pulled locally. The default cloud chat model is `deepseek-v4-flash:cloud`; override `OLLAMA_MODEL` to use any other cloud chat model. See `digitalocean-deployment-guide.md` for full deployment instructions.

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

Tests use SQLite in-memory via a per-fixture config override (`app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'`) for isolation. PostgreSQL-only validation is enforced at the app-factory level (`src/__init__.py`) but bypassed per-test so no external database is required to run the suite.

## Using Ollama Cloud (Optional)

The `AI_BACKEND` env var selects the AI provider. The default is `local` (Ollama on `http://localhost:11434`); setting `AI_BACKEND=cloud` routes all AI calls through the Ollama Cloud OpenAI-compatible endpoint.

1. In your `.env` file, set:
   ```
   AI_BACKEND=cloud
   OLLAMA_CLOUD_API_KEY=your-api-key-here
   OLLAMA_MODEL=deepseek-v4-flash:cloud
   ```
   The default cloud chat model is `deepseek-v4-flash:cloud`; substitute any other cloud chat model you prefer.

2. Restart the application. All AI calls will route through the Ollama Cloud API instead of your local Ollama instance.

## Mock AI Mode (No Ollama Required)

Set `AI_MOCK=true` in your `.env` file to use mock responses. This is useful for testing or running the app without Ollama installed.

## Documentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — system architecture and engineering overview
- [DigitalOcean Deployment Guide](digitalocean-deployment-guide.md) — production deployment reference

## License

MIT License — see [LICENSE](LICENSE) for details.