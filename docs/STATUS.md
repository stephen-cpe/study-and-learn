# STATUS.md
Last Updated: 2026-06-05
Sprint: 7
Last Task Completed: Sprint 7 — Mascot animation frames: idle/busy/happy GIF states with state-based glow tints, centralized config (config.py), GIF fallback to static PNG, backend progress tracker returns mascot_state for polling
Commit Message Suggestion: feat(sprint7): add animated mascot states (idle/busy/happy GIFs) with state-based glow tints and progress-driven state switching
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; use cloud models (gemma3:12b-cloud, nemotron-3-nano:30b-cloud) for production quality
Pending Decisions:
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
Next 3 Tasks:
  1. TTS integration (opt-in narration button on slide deck)
  2. PDF export for completed lessons
  3. Session cleanup (remove extracted_texts after lessons generated)
