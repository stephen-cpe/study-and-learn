# STATUS.md
Last Updated: 2026-05-24
Sprint: 6
Last Task Completed: Sprint 6 — Error handling improvements: typed exception hierarchy (AIServiceError, AIModelUnavailableError, AICloudAPIError, AITimeoutError), exponential-backoff retry for transient Ollama failures, user-facing error messages, graceful fallbacks in all AI services, silent exception logging
Commit Message Suggestion: fix(sprint6): typed AI exception hierarchy with retry, user-facing error messages, graceful service fallbacks
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; use cloud models (gemma3:12b-cloud, nemotron-3-nano:30b-cloud) for production quality
  - Mascot animation: Image placed (done), animation frames deferred to Sprint 7
Pending Decisions:
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
Next 3 Tasks:
  1. Mascot animation frames (idle/waiting/done)
  2. TTS integration (opt-in narration button on slide deck)
  3. PDF export for completed lessons
