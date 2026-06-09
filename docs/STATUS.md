# STATUS.md
Last Updated: 2026-06-09
Sprint: 7 (In Progress)
Last Task Completed: Source citation system, relevance gating (weak/partial), dashboard tabs (Active/Completed/Cancelled + Mark Complete + Delete), per-lesson PDF export via fpdf2, My Lessons navbar link, file_names DB persistence
Commit Message Suggestion: feat: add relevance gating, source citations, dashboard tabs, per-lesson PDF export
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
