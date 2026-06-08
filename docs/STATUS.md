# STATUS.md
Last Updated: 2026-06-08
Sprint: 8 (Current Focus)
Last Task Completed: Perfective maintenance — Batch 1 (import ordering, type hints, docstrings on services) + Batch 2 (routes.py split into src/routes/ package with _helpers, auth, admin, processing, lessons, dashboard) + Batch 3 (CSS split: deck-base + deck-components; JS split/rename: mascot, progress, upload, deck-engine, deck-page, results) + new retake route test (191 tests total)
Commit Message Suggestion: refactor: split routes into domain modules, split JS/CSS into components, add retake test
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; use cloud models (gemma3:27b-cloud) for production quality
  - Session storage still FileSystemCache (DB-backed migration planned post-capstone)
Pending Decisions:
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
Next 3 Tasks:
  1. Difficulty/age-level selector (Easy/Moderate/Hard) on upload form with prompt injection
  2. TTS integration (opt-in narration button on slide deck)
  3. PDF export for completed lessons
