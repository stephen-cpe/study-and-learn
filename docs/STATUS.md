# STATUS.md
Last Updated: 2026-05-14
Sprint: 4
Last Task Completed: Tune lesson/quiz prompt templates for pedagogical consistency and RAG grounding
Commit Message Suggestion: feat: refine lesson/quiz prompts with pedagogical constraints, RAG grounding, anti-hallucination, and plausible distractor instructions
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; upgrade to gemma3:12b-cloud for production quality
  - Responsive layout: Slide deck needs mobile breakpoint adjustments for smaller screens
  - Mascot animation: Image placed (done), animation frames deferred to later sprint
Pending Decisions:
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
  - User account system: PostgreSQL vs SQLite for Sprint 5 authentication
Next 3 Tasks:
  1. Polish responsive layout for slide deck on smaller screens
  2. Update TODO.md to check off completed Sprint 4 items
  3. Begin Sprint 5: user accounts (Flask-Login + PostgreSQL/SQLite)