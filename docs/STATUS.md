# STATUS.md
Last Updated: 2026-05-15
Sprint: 5
Last Task Completed: Sprint 5 Phase 1.4 — Build sign-up, login, logout routes and templates
Commit Message Suggestion: feat(auth): add signup, login, logout routes and templates with tests
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; upgrade to gemma3:12b-cloud for production quality
  - Mascot animation: Image placed (done), animation frames deferred to Sprint 6
  - PostgreSQL privilege: study_user cannot CREATE in public schema, blocking `flask db migrate` / `flask db upgrade` on live DB; workaround via SQLite-isolated test fixtures
Pending Decisions:
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
Next 3 Tasks:
  1. Add StudyPath / Module SQLAlchemy models and wire 3-active-lessons cap
  2. Replace session-backed lesson repository with DB-backed LessonRepository
  3. Implement progress persistence and per-user lesson limits