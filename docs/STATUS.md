# STATUS.md
Last Updated: 2026-05-14
Sprint: 4
Last Task Completed: Merge progress indicator into mascot speech bubble; update all docs for Sprint 4 progress
Commit Message Suggestion: docs: update SRS, TODO, DESIGN, STATUS to reflect Sprint 4 progress and reprioritize tasks
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; upgrade to gemma3:12b-cloud for production quality
  - Responsive layout: Slide deck needs mobile breakpoint adjustments for smaller screens
  - `/process` route still uses full-screen loading overlay; needs non-blocking replacement
  - Mascot animation: Image placed (done), animation frames deferred to later sprint
Pending Decisions:
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
  - User account system: PostgreSQL vs SQLite for Sprint 5 authentication
Next 3 Tasks:
  1. Replace full-screen loading overlay on `/process` route with non-blocking progress indicator
  2. Tune lesson/quiz prompt templates for better pedagogical consistency (given qwen3 placeholder limits)
  3. Polish responsive layout for slide deck on smaller screens
