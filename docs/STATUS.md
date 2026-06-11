# STATUS.md
Last Updated: 2026-06-11
Sprint: 7 (In Progress)
Last Task Completed: CSS badge truncation — widened .goal-badge max-width from 400px to 100% (matching .results-card-summary width) and added ellipsis truncation to .filename-badge for long filenames. Parent .results-meta got width:100% to provide proper reference. No template or JS changes needed. Full suite 283/283 passed.
Commit Message Suggestion: fix(css): expand goal-badge and filename-badge truncation width to match card width
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; use cloud models (gemma3:27b-cloud) for production quality
  - Session storage still FileSystemCache (DB-backed migration planned post-capstone)
  - fpdf2 Latin-1 limitation: all AI-generated text in PDF export must pass through _clean() sanitizer (Unicode NFKD + explicit char mapping). WeasyPrint unavailable on Windows (requires GTK libraries).
  - Settings page is placeholder-only: TTS does not actually narrate slides yet, and lesson_difficulty is not yet injected into prompts.
Pending Decisions:
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
  - TTS provider confirmed as Edge-TTS (voice IDs will be mapped in a future task)
Next 3 Tasks:
  1. TTS integration (opt-in narration button on slide deck) — speakers and toggle now persisted on User
  2. Difficulty/age-level selector — slider value now persisted; needs prompt injection on upload + lesson generation
  3. Session cleanup (remove extracted_texts after lessons generated)
