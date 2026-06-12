# STATUS.md
Last Updated: 2026-06-11
Sprint: 7 (In Progress)
Last Task Completed: Task #3 — Humor injection in quizzes and lesson example slides. Added HUMOR_INSTRUCTIONS constant (one ridiculous distractor per mcq/multi_select) to quiz_generator.py prompt. Added HUMOR_NOTE constant (light-hearted analogy in example slides) to lesson_generator.py prompt. Added 2 tests verifying constants appear in captured prompts. Full suite 64/64 passed.
Commit Message Suggestion: feat(prompts): inject humor into quiz distractors and lesson example slides
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
