# STATUS.md
Last Updated: 2026-05-18
Sprint: 5
Last Task Completed: Sprint 5 Phase 2.4 — Admin Role, Per-User Lesson Generation Toggle, and Demo Account Seeding
Commit Message Suggestion: feat(admin): add admin role, can_generate_lessons toggle, seed-demo endpoint, and default-deny new signups
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; upgrade to gemma3:12b-cloud for production quality
  - Mascot animation: Image placed (done), animation frames deferred to Sprint 6
  - PostgreSQL privilege: study_user cannot CREATE in public schema; use `init_db.sql` or `GRANT CREATE` before `flask db upgrade`
  - session_repo.py still exists on disk as legacy shim; lesson_repo.py is the active implementation
  - New `can_generate_lessons` column requires migration on live DB; included in `c1d0e553b531` migration
Pending Decisions:
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
Next 3 Tasks:
  1. Update task board with Sprint 5 progress
  2. Run DB migration on production PostgreSQL (`flask db upgrade` or re-run `init_db.sql`)
  3. Manual smoke test: sign up new user → denied access → admin toggle → demo seed → generate lessons
