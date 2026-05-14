# STATUS.md
Last Updated: 2026-05-14
Sprint: 4
Last Task Completed: Improve loading UX: background progress indicator with mascot stage reporting
Commit Message Suggestion: feat: replace full-screen loading overlay with non-blocking background progress indicator + mascot stage messaging
Known Issues:
  - AI output consistency: Lesson/quiz quality varies with qwen3:0.6b; needs prompt refinement
  - Responsive layout: Slide deck needs mobile breakpoint adjustments for smaller screens
  - Mascot animation: Image placed (done), animation frames deferred to later sprint
Pending Decisions:
  - Difficulty toggle scope: Decide if Easy/Moderate/Hard selector is Sprint 4 or deferred
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
  - User account system: PostgreSQL vs SQLite for Sprint 5 authentication
Next 3 Tasks:
  1. Tune lesson/quiz prompt templates for better pedagogical consistency with qwen3:0.6b
  2. Add difficulty level selector (Easy/Moderate/Hard)
  3. Polish responsive layout for slide deck on smaller screens
