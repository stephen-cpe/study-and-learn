# STATUS.md
Last Updated: 2026-05-18
Sprint: 5
Last Task Completed: Sprint 5 Bug Fix Patch — Persist extracted_texts to DB, path-aware routing, session-to-DB fallbacks, fix lesson cap, fix AJAX responses
Commit Message Suggestion: fix(session): persist extracted_texts to StudyPath, add path_id routing, DB fallbacks for session data, fix lesson cap logic, AJAX redirect
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; upgrade to gemma3:12b-cloud for production quality
  - Mascot animation: Image placed (done), animation frames deferred to Sprint 6
  - PostgreSQL privilege: study_user cannot CREATE in public schema; use `init_db.sql` which now includes DROP IF EXISTS and full seed accounts
  - session_repo.py still exists on disk as legacy shim; lesson_repo.py is the active implementation
  - DB migration needed: `extracted_texts` column added to study_paths; run `flask db migrate -m \"add extracted_texts to study_paths\" && flask db upgrade` on existing DBs, or re-run `init_db.sql` for fresh install
Pending Decisions:
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
Next 3 Tasks:
  1. Admin dashboard (admin.html) with user management interface
  2. Access-denied page for users without generate privileges
  3. Password reset functionality in user dropdown
