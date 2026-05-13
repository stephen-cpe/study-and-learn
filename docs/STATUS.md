# STATUS.md
Last Updated: 2026-05-12
Sprint: 4
Last Task Completed: UI polish, mascot integration (bottom-right), JS refactoring (app.js), CSS fixes (score circle, file list, title overflow, results-detail), cloud model testing, app/ → src/ rename
Commit Message Suggestion: feat: polish UI, integrate mascot, refactor JS, add cloud model toggle, rename app/ to src/
Known Issues:
  - Loading UX: Full-screen overlay still blocks interaction; needs background progress indicator
  - Fill-in-the-blank: Currently accepts multi-word answers; needs one-word-per-blank fix
  - AI output consistency: Lesson/quiz quality varies with qwen3:0.6b; needs prompt refinement
  - Responsive layout: Slide deck needs mobile breakpoint adjustments for smaller screens
  - Mascot animation: Image placed (done), animation frames deferred to later sprint
Pending Decisions:
  - Difficulty toggle scope: Decide if Easy/Moderate/Hard selector is Sprint 4 or deferred
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
  - User account system: PostgreSQL vs SQLite for Sprint 5 authentication
Next 3 Tasks:
  1. Fix fill-in-the-blank quiz: one-word-only validation, inline input per blank, per-blank grading
  2. Improve loading UX: background progress indicator with mascot stage reporting
  3. Tune lesson/quiz prompt templates for better pedagogical consistency with qwen3:0.6b
