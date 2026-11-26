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

> **Warning:** `init_db.sql` drops and recreates all application tables, including `users`. Run it only for a fresh database. For an existing database, see the upgrade note below (there is no supported in-place upgrade yet).

Initialize database schema:

```bash
psql -U postgres -d study_and_learn -f init_db.sql
```

> **Upgrading an existing database:** not supported yet. The Alembic revisions in `migrations/versions/` do not cover every current table and column (for example `mascot_memory` and the profile/TTS columns on `users`), so do not rely on `flask db upgrade`. Back up the database before re-running `init_db.sql`.

This creates all application tables (`users`, `study_paths`, `content_registry`, `lesson_progress`, `mascot_memory`, `suggestion`, `background_task`), indexes, foreign keys, stamps the Alembic version, and seeds three pre-configured accounts. The seed accounts ship with display names (`Robo`, `Bobby`, `Ali`); other accounts can set `nickname`/`full_name` at signup or later in **Settings** (both default to NULL). The `mascot_memory` table stores the mascot's per-learner long-term memory (preferences, quiz outcomes, study path events) so the speech bubble can produce personalized, context-aware lines.

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
```

The default models are working placeholders — override `OLLAMA_MODEL` with any chat model from the Ollama library that fits your hardware (e.g. a larger model for better quality). The embedding (`qwen3-embedding:0.6b`) model is overridable via `OLLAMA_EMBEDDING_MODEL`.

Note: the local and cloud chat-model defaults live in `config_defaults.py`. `.env.example` sets `OLLAMA_MODEL=qwen3:0.6b` for local development; override `OLLAMA_MODEL` to use a different model on either backend.

**For cloud deployment (`AI_BACKEND=cloud`):** You only need to pull `qwen3-embedding:0.6b` locally — the embedding model runs on the server for ChromaDB RAG retrieval (Ollama Cloud does not expose the `/api/embed` endpoint). The chat model runs on Ollama Cloud and does NOT need to be pulled locally. The cloud chat-model default lives in `config_defaults.py`; override `OLLAMA_MODEL` to use another cloud chat model. See the DigitalOcean or AWS deployment guide in `docs/` for full deployment instructions.

OCR and vision are consolidated onto `OLLAMA_VISION_MODEL` (default in `config_defaults.py`; cloud-served by default). Vision OCR is ON by default (`OCR_FULL=true`) but smart-gated per file: text-layer PDFs skip rendering + LLM calls entirely — vision runs only on scanned/image-heavy PDFs, plus direct image uploads. Setting `OCR_FULL=false` skips the full text+table+figure passes for PDFs, DOCX and PPTX; direct image uploads still make one text-only vision call. With `AI_BACKEND=local`, either point `OLLAMA_VISION_MODEL` at a locally available multimodal model, or set `OCR_FULL=false` so PDFs, DOCX and PPTX skip vision. Image uploads still need a vision model in either case. Figure descriptions use the same vision model and require a backend that can serve it (cloud by default, with a valid `OLLAMA_CLOUD_API_KEY`).

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

Lint (the same command CI runs; install once with `pip install ruff`):

```bash
ruff check src/ tests/ app.py config.py gunicorn.conf.py generate_mascot_anim.py
```

## Using Ollama Cloud (Optional)

The `AI_BACKEND` env var selects the AI provider for chat and vision calls. The default is `local` (Ollama on `http://localhost:11434`); setting `AI_BACKEND=cloud` routes those calls through the Ollama Cloud OpenAI-compatible endpoint. Embeddings always use local Ollama (see below).

1. In your `.env` file, set:
   ```
   AI_BACKEND=cloud
   OLLAMA_CLOUD_API_KEY=your-api-key-here
   OLLAMA_MODEL=gemma4:31b-cloud
   ```
   Substitute any other cloud chat model you prefer.

2. Restart the application. Chat, summarization, lesson/quiz generation, and vision calls route through Ollama Cloud. ChromaDB embeddings still use your local Ollama instance (`OLLAMA_EMBEDDING_MODEL`, default `qwen3-embedding:0.6b`), so keep local Ollama running and the embedding model pulled.

## Mock AI Mode (No Ollama Required)

Set `AI_MOCK=true` in your `.env` file to use mock responses. This is useful for testing or running the app without Ollama installed.

## Documentation

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — system architecture and engineering overview
- [DigitalOcean Deployment Guide](docs/digitalocean-deployment-guide.md) — Linux deployment reference (not actively maintained)
- [AWS EC2 Deployment Guide](docs/aws-deployment-guide.md) — Linux deployment reference (not actively maintained)

## License

MIT License — see [LICENSE](LICENSE) for details.