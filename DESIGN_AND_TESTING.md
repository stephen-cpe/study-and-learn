# Design and Testing Document
# Study-and-Learn

**Version:** 0.1 starter  
**Status:** Living document

---

## 1. Architecture Overview

Study-and-Learn is planned as a Flask web application with a guided Bootstrap frontend and an AI-assisted backend workflow.

Core workflow:

1. User enters a learning goal.
2. User uploads study documents.
3. Backend validates and stores uploads.
4. Document parser extracts text.
5. AI service generates summary.
6. AI service checks relevance.
7. AI service generates study path.
8. UI presents structured results.

---

## 2. Architecture Decisions

### ADR-001: Use Flask for the MVP

**Decision:** Use Flask for backend development.

**Reason:** Flask is lightweight, Python-based, and suitable for a capstone-scale web application. It allows fast development without imposing a large framework structure.

### ADR-002: Use Bootstrap for the UI

**Decision:** Use Bootstrap 5 for UI styling.

**Reason:** Bootstrap provides responsive layout and common UI components with minimal custom CSS and no complex frontend build process.

### ADR-003: Avoid chat UI in the MVP

**Decision:** Use forms, buttons, and structured result pages.

**Reason:** The project goal is guided learning support, not open-ended chatbot interaction. This also makes the MVP easier to test and demonstrate.

### ADR-004: Use an AI client wrapper

**Decision:** AI calls should go through a service wrapper such as `ai_client.py`.

**Reason:** This makes the application easier to test by allowing mocked AI responses. It also allows Ollama or another model provider to be swapped later.

### ADR-005: Start with simple parsing before advanced retrieval

**Decision:** Implement document parsing and whole-document/section summarization first. Add embeddings/retrieval only after the core workflow works.

**Reason:** The capstone MVP depends on end-to-end functionality. Retrieval adds value but also complexity.

### ADR-006: Implement RAG Pipeline (Chunk → Embed → Retrieve → Generate)
**Decision:** Replace direct document-to-AI prompting with LangChain chunking + ChromaDB retrieval.
**Reason:** Prevents context window overflow, enables source-grounded outputs, scales to multiple documents, and aligns with modern AI engineering standards.
**Tradeoffs:** ✅ Grounded, scalable, traceable • ❌ Adds vector DB dependency, requires embedding strategy

### ADR-007: Use Single Configurable Ollama Model + Mock Fallback
**Decision:** All AI services call one model via `OLLAMA_MODEL` env var (default: `qwen3:1.7b`). CI/testing uses `AI_MOCK=true`.
**Reason:** Capstone MVP prioritizes reliability over model routing complexity. 1B–3B models run efficiently on target hardware. Mock fallback guarantees deterministic tests.

### ADR-008: Dual Ollama Model Strategy (Chat + Embeddings)
**Decision:** Chat uses `OLLAMA_MODEL` (default: qwen3:1.7b), Embeddings use `OLLAMA_EMBEDDING_MODEL` (default: qwen3-embedding:0.6b).
**Reason:** Chat models don't support /api/embed. Separation prevents 501 errors and allows independent tuning of generation vs retrieval models.

---

## 3. Software & Architectural Patterns
- Model-View-Controller (MVC): Flask routes (Controller) delegate to `app/services/` (Model/Business Logic) and render Bootstrap templates (View). Separation keeps routing thin and services testable.
- Service Layer Pattern: All AI, parsing, and RAG logic isolated in `app/services/`. Enables independent unit testing, easy mocking, and future provider swaps.
- Repository/DAO Pattern: ChromaDB vector storage abstracted behind `vector_store.py`. Decouples ingestion from retrieval logic.
- Mock Object Pattern: `AI_MOCK=true` and in-memory ChromaDB replace live LLM/vector calls in CI. Guarantees deterministic, zero-cost, GPU-free test execution.

---

## 3. Testing Strategy

### Unit Tests
    Unit tests will cover isolated logic:
    - allowed file type validation,
    - parser selection,
    - parser error handling,
    - prompt construction,
    - relevance label parsing,
    - curriculum output parsing.
    - LangChain text splitter output validation
    - ChromaDB collection creation & persistence checks
    - ChromaDB uses EphemeralClient when CI=true, PersistentClient otherwise
    - Similarity search context builder accuracy
    - Multi-file upload session & cookie size limits
    - AI calls mocked via AI_MOCK=true

### Integration Tests

Integration tests will cover routes and workflow behavior:
- homepage loads,
- upload route accepts valid files,
- upload route rejects invalid files,
- mocked AI workflow returns expected page content.

### Smoke Tests

Smoke tests will be run before sprint demos and final recording:
- app starts,
- sample document uploads,
- summary appears,
- relevance appears,
- study path appears.

---

## 4. CI/CD

Initial GitHub Actions workflow:

- trigger on push and pull request,
- install Python,
- install dependencies,
- run `pytest -v tests/`.

Future additions:
- linting,
- formatting,
- deployment automation,
- security scanning.

---

## 5. AI Tooling Use

AI tooling may be used to:
- refine specifications,
- draft code,
- generate test ideas,
- debug implementation issues,
- improve documentation.

All AI-generated code must be reviewed before commit. Important project behavior should be covered by tests.

---

## 6. Deployment Notes

Deployment target is undecided. Candidate platforms:
- Render,
- Railway,
- PythonAnywhere,
- DigitalOcean,
- AWS EC2.

The deployed version should be stable enough for capstone demonstration and accessible from the final submission link.

---

## 7. Deployment Strategy & Cost Analysis
- Option A: Local-First Demo (Current)
  - Host: Developer laptop running Ollama + Flask
  - Cost: $0 (uses existing hardware)
  - Tradeoff: Not publicly accessible; suitable for sprint demos & local dev
- Option B: Free-Tier Cloud (Recommended for Submission)
  - Host: Render or Railway (Flask web service)
  - Cost: $0/month (free tier supports 512MB–1GB RAM, sufficient for Flask + static assets)
  - AI Strategy: Swap Ollama for cloud API (OpenRouter/Groq) or keep `AI_MOCK=true` for demo
  - Vector DB: ChromaDB runs in-memory or uses persistent volume (~50MB free tier storage)
  - Tradeoff: Requires API key or mocked AI; free tier sleeps after inactivity but wakes on request
- Option C: VPS (DigitalOcean/AWS)
  - Cost: ~$6–12/month (4GB RAM droplet)
  - Tradeoff: Overkill for capstone; adds operational overhead
Recommendation: Deploy to Render/Railway free tier with `AI_MOCK=true` for grading, document swap path to production API in README.

---

## 8. Known Risks

| Risk | Impact | Mitigation |
|---|---|---|
| AI model too slow locally | Demo delay | Use small documents and cached/demo responses if needed |
| File parsing issues | Failed workflow | Start with fewer file types and add more gradually |
| Scope creep | Missed MVP | Keep optional features outside official sprint goals |
| Deployment resource limits | App unavailable | Test deployment early |
| AI output inconsistency | Poor demo | Use controlled sample documents and structured prompts |
