# Study-and-Learn

A guided, form-driven AI web application that converts uploaded study materials into structured summaries, relevance assessments, study paths, interactive slide-based lessons, and auto-graded quizzes — all powered by local LLMs via Ollama.

## Features

- **Unified input** — learning goal + multi-file upload (≤5) in a single form
- **RAG pipeline** — chunking, ChromaDB vector storage, top-k retrieval for grounded AI outputs
- **AI analysis** — summary, relevance check (strong/partial/weak), structured study path with effort estimates
- **Interactive lessons** — slide-based lesson deck with inline comprehension checkpoints
- **Mixed-type quizzes** — MCQ, true/false, multi-select, fill-in-the-blank per module
- **Instant grading** — per-question feedback with explanations
- **Gated progression** — 80% pass threshold; modules unlock sequentially
- **Regenerate on retake** — fresh questions each attempt to prevent memorization
- **Retro theme** — custom pixel fonts (Retrograde Bold, BoldPixels), cyberpunk visual identity

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.13, Flask, Flask-Session (cachelib) |
| Frontend | Bootstrap 5, custom CSS/JS slide deck, retro pixel fonts |
| AI / RAG | Ollama (qwen3:1.7b + qwen3-embedding:0.6b), LangChain, ChromaDB |
| Testing | pytest (45 tests), GitHub Actions CI |

## Ollama Setup

1. Install Ollama from https://ollama.com/download
2. Pull required models:
```bash
ollama pull qwen3:1.7b
ollama pull qwen3-embedding:0.6b
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
python run.py

# 5. Run tests
pytest -v tests/
```

## Documentation

| Document | Description |
|----------|-------------|
| [SRS.md](SRS.md) | Software requirements, user stories, scope |
| [TODO.md](TODO.md) | Sprint plan, task backlog, scope-creep ladder |
| [DESIGN_AND_TESTING.md](DESIGN_AND_TESTING.md) | Architecture decisions (ADRs), testing strategy, CI/CD |
| [AI_AGENT_PROTOCOL.md](AI_AGENT_PROTOCOL.md) | AI agent operating rules and guardrails |
| [POC-MVP-Discussion.md](POC-MVP-Discussion.md) | POC design discussion and decisions |

## Links
- [Public Task Board](https://stephen-cpe.github.io/task-board-v1/)
- [Task Board Repository](https://github.com/stephen-cpe/task-board-v1/)
- [Deployed App](#) *(coming soon — Sprint 5)*

## License
MIT — for educational purposes only.
