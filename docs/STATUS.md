# STATUS.md
Last Updated: 2026-05-18
Sprint: 5
Last Task Completed: Sprint 5 Bug Fix Round 3 — Session leak between users, multi-goal index page, path-aware redirects, JS pathId initialization
Commit Message Suggestion: fix(session): clear session on logout, show all active goals on index, path-aware generate redirect, init pathId from DOM
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; upgrade to gemma3:12b-cloud for production quality
  - Mascot animation: Image placed (done), animation frames deferred to Sprint 6
  - DB migration needed for existing databases: `extracted_texts` column added to study_paths; use `init_db.sql` for fresh install
Pending Decisions:
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
Next 3 Tasks:
  1. Admin dashboard (admin.html) with user management interface
  2. Access-denied page for users without generate privileges
  3. Password reset functionality in user dropdown
