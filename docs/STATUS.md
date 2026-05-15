# STATUS.md
Last Updated: 2026-05-15
Sprint: 5
Last Task Completed: Close Sprint 4 documentation and prepare for Sprint 5 user accounts
Commit Message Suggestion: docs: close sprint 4, remove mobile scope, initialize sprint 5 tracking
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; upgrade to gemma3:12b-cloud for production quality
  - Mascot animation: Image placed (done), animation frames deferred to Sprint 6
Pending Decisions:
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
  - User account system: PostgreSQL for Sprint 5 authentication
  Next 3 Tasks:
    1. Integrate Flask-Login + Flask-SQLAlchemy + PostgreSQL setup
  2. Build sign-up, sign-in, logout routes and templates
  3. Configure session persistence and max 3 active lessons gating