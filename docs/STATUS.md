# STATUS.md
Last Updated: 2026-06-06
Sprint: 7
Last Task Completed: Three bug fixes — (1) .md/.txt files now use extract_text_with_vision() in process route for ContentRegistry + ChromaDB registration, (2) corrupted ChromaDB collections auto-rebuild from ContentRegistry text, (3) /reset only cancels paths with zero LessonProgress rows
Commit Message Suggestion: fix(process): register .md/.txt in ContentRegistry, handle corrupted ChromaDB collections with rebuild, and preserve lessons on reset
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; use cloud models (gemma3:27b-cloud) for production quality
Pending Decisions:
  - Deployment target: Confirm Render vs Railway free tier for final submission (Sprint 8)
Next 3 Tasks:
  1. TTS integration (opt-in narration button on slide deck)
  2. PDF export for completed lessons
  3. Session cleanup (remove extracted_texts after lessons generated)
