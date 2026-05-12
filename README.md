# Study-and-Learn

A guided, form-driven AI web application that converts uploaded study materials into structured summaries, relevance assessments, study paths, interactive slide-based lessons, and auto-graded quizzes — all powered by LLMs via Ollama.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.13, Flask, Flask-Session (cachelib) |
| Frontend | Bootstrap 5, custom CSS/JS slide deck, retro pixel fonts |
| AI / RAG | Ollama (qwen3:1.7b + qwen3-embedding:0.6b), LangChain, ChromaDB |
| Testing | pytest, GitHub Actions CI |

## Ollama Setup

1. Install Ollama from https://ollama.com/download
2. Pull required models:
```bash
ollama pull qwen3:1.7b
ollama pull qwen3-embedding:0.6b
```

## Quick Start (Local Development)
```bash
# 1. Clone and enter repo
git clone https://github.com/stephen-cpe/study-and-learn.git
cd study-and-learn

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate
python.exe -m pip install --upgrade pip

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python app.py

# 5. Run tests
pytest -v tests/
```
## Switching Between Local and Cloud

The app uses local Ollama by default. To switch to Ollama Cloud:

**1. Uncomment one import** in `app/services/ai_client.py:41`:

```python
# ── Switch to Ollama Cloud ──────────────────────────────────────────────────
# Uncomment the line below to route all AI calls through Ollama Cloud
# from .ai_client_cloud import call_ollama  # noqa: E402
# ─────────────────────────────────────────────────────────────────────────────
```

Change to:

```python
# ── Switch to Ollama Cloud ──────────────────────────────────────────────────
from .ai_client_cloud import call_ollama  # noqa: E402   # ← uncommented
# ─────────────────────────────────────────────────────────────────────────────
```

**2. Create a `.env` file** (already in `.gitignore`):

```env
OLLAMA_CLOUD_API_KEY=your-api-key-here
OLLAMA_MODEL=gemma3:27b-cloud
```

**3. Done** — no other files need changing. The `from .ai_client_cloud import call_ollama` line replaces the local `call_ollama` at the module level, so every service (summarizer, quiz generator, etc.) automatically uses the cloud.

**To switch back**, comment the import line again:

```python
# from .ai_client_cloud import call_ollama  # noqa: E402
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_MODEL` | `qwen3:1.7b` | Chat generation model |
| `OLLAMA_EMBEDDING_MODEL` | `qwen3-embedding:0.6b` | Vector embeddings model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server address |
| `OLLAMA_TIMEOUT` | `180` | Request timeout in seconds |
| `AI_MOCK` | — | Set to `true` for mock responses (no GPU required) |
| `CI` | — | Set to `true` for in-memory ChromaDB in CI |
| `SECRET_KEY` | `dev-key-for-testing-only` | Flask session signing key |

### Cloud-only variables (ignored in local mode)

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `OLLAMA_CLOUD_API_KEY` | Yes | — | Ollama Cloud API key |
| `OLLAMA_CLOUD_BASE_URL` | No | `https://ollama.com` | Ollama Cloud API base URL |

## Documentation

| Document | Description |
|----------|-------------|
| [SRS.md](SRS.md) | Software requirements, user stories, scope |
| [TODO.md](TODO.md) | Sprint plan, task backlog, scope-creep ladder |
| [DESIGN_AND_TESTING.md](DESIGN_AND_TESTING.md) | Architecture decisions (ADRs), testing strategy, CI/CD |
| [AI_AGENT_PROTOCOL.md](AI_AGENT_PROTOCOL.md) | AI agent operating rules and guardrails |

## Links
- [Public Task Board](https://stephen-cpe.github.io/task-board-v1/)
- [Task Board Repository](https://github.com/stephen-cpe/task-board-v1/)
- [Deployed App](#) *(coming soon — Sprint 7)*

## License
MIT — for educational purposes only.
