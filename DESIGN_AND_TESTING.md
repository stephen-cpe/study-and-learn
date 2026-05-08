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

### ADR-006: Use Single Small Local Model + Mock Fallback
**Decision**: All AI services (summary, relevance, study path) will call a single configurable Ollama model (`qwen3:1.7b` by default). CI/testing will use `AI_MOCK=true` to bypass live inference.

**Reason**: 
- Capstone MVP prioritizes end-to-end reliability over model routing complexity.
- 2B–3B quantized models run efficiently on target hardware and free-tier constraints.
- Mock fallback guarantees deterministic test suites and removes flaky GPU dependencies.
- Single prompt schema across services reduces maintenance and validation overhead.

**Tradeoffs**: 
- ✅ Simpler architecture, faster demo response, easier to test
- ❌ Less specialized per-task optimization (deferred to post-MVP)

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

## 7. Known Risks

| Risk | Impact | Mitigation |
|---|---|---|
| AI model too slow locally | Demo delay | Use small documents and cached/demo responses if needed |
| File parsing issues | Failed workflow | Start with fewer file types and add more gradually |
| Scope creep | Missed MVP | Keep optional features outside official sprint goals |
| Deployment resource limits | App unavailable | Test deployment early |
| AI output inconsistency | Poor demo | Use controlled sample documents and structured prompts |
