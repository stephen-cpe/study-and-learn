# STATUS.md
Last Updated: 2026-06-09
Sprint: 7 (In Progress)
Last Task Completed: CRT speech bubble tuned (width 288px → 200px ≈30% smaller, font 9px preserved, no CRT filter changes, text gets inner padding, typewriter capped at 4 lines with progress bar pinned to bottom of screen)
Commit Message Suggestion: fix(mascot): shrink CRT bubble ~30% and cap typewriter text at 4 lines with progress bar pinned to bottom
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; use cloud models (gemma3:27b-cloud) for production quality
  - Session storage still FileSystemCache (DB-backed migration planned post-capstone)
  - fpdf2 Latin-1 limitation: all AI-generated text in PDF export must pass through _clean() sanitizer (Unicode NFKD + explicit char mapping). WeasyPrint unavailable on Windows (requires GTK libraries).
Pending Decisions:
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
Next 3 Tasks:
  1. Difficulty/age-level selector (Easy/Moderate/Hard) on upload form with prompt injection
  2. TTS integration (opt-in narration button on slide deck)
  3. Session cleanup (remove extracted_texts after lessons generated)
