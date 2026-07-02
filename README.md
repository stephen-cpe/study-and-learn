# Study-and-Learn

## Links

- [Public Task Board](https://stephen-cpe.github.io/task-board-v1/)
- [Deployed App](https://studyandlearn.duckdns.org/)
- [Design and Testing Document](https://github.com/stephen-cpe/study-and-learn/blob/main/docs/DESIGN_AND_TESTING.md)
- [1st Set of Demo Documents](https://github.com/stpnpl/azthreus-systems/tree/main/demo-documents/1st-set)
- [2nd Set of Demo Documents](https://github.com/stpnpl/azthreus-systems/tree/main/demo-documents/2nd-set)

## Demo Access

The deployed app is at [https://studyandlearn.duckdns.org/](https://studyandlearn.duckdns.org/). For security, production credentials differ from the local seed defaults and are provided in the recorded demo/presentation. To run locally with the seeded accounts below, follow the "Setup" section.

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

Note: `config.py` ships `OLLAMA_MODEL=gemma4:31b-cloud` as the package default — to run locally without a `.env`, set `AI_BACKEND=local` and `OLLAMA_MODEL=qwen3:0.6b` in your `.env` (see `.env.example`).

**For cloud deployment (`AI_BACKEND=cloud`):** You only need to pull `qwen3-embedding:0.6b` locally — the embedding model runs on the server for ChromaDB RAG retrieval. The chat model (`gemma4:31b-cloud`) runs on Ollama Cloud and does NOT need to be pulled locally. See `digitalocean-deployment-guide.md` for full deployment instructions.

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
   OLLAMA_MODEL=gemma4:31b-cloud
   ```

2. Restart the application. All AI calls will route through the Ollama Cloud API instead of your local Ollama instance.

## Mock AI Mode (No Ollama Required)

Set `AI_MOCK=true` in your `.env` file to use mock responses. This is useful for testing or running the app without Ollama installed.

## Documentation

- SRS.md - Software requirements and user stories
- TODO.md - Sprint plan and task backlog
- DESIGN_AND_TESTING.md - Design and testing document
- STATUS.md - Current sprint state and known issues
- AI_AGENT_PROTOCOL.md - AI agent execution protocol and guardrails

## License

MIT - For educational purposes only.
