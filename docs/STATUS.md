# STATUS.md
Last Updated: 2026-05-24
Sprint: 6
Last Task Completed: Sprint 6 — OCR/Vision Integration & Global Content Deduplication (GLM-OCR, Qwen3-VL, pdf2image, ContentRegistry, content-keyed ChromaDB, multi-collection retrieval, 172 tests passing)
Commit Message Suggestion: feat(sprint6): OCR/vision integration with GLM-OCR local + Qwen3-VL cloud, global content deduplication, content-keyed ChromaDB, 8 file types, 172 tests
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; use cloud models (gemma3:12b-cloud, nemotron-3-nano:30b-cloud) for production quality
  - Mascot animation: Image placed (done), animation frames deferred to Sprint 7
Pending Decisions:
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
Next 3 Tasks:
  1. Mascot animation frames (idle/waiting/done)
  2. TTS integration (opt-in narration button on slide deck)
  3. PDF export for completed lessons
