# AI Agent Execution Protocol
## Study-and-Learn Capstone Project

## Project Brief (Read First)
- **App:** Study-and-Learn — a Flask web app where a learner uploads study documents and gets an AI-generated summary, relevance check (with weak-match gating: blocks study path + lesson generation), study path, interactive slide-based lessons with TTS narration (Edge-TTS, opt-in), mixed-type quizzes (mcq, true_false, multi_select, cloze_dropdown), inline comprehension checkpoints (mcq/true_false/cloze_dropdown variety), per-module grading with gated progression, difficulty-aware content generation (Easy/Normal/Hard), session save/resume (deck position auto-saved), source citation system (ChromaDB metadata → deck modal), per-lesson PDF export (fpdf2), and dashboard with Active/Completed/Cancelled tabs (Mark Complete, Delete).
- **Stack:** Python 3.13, Flask, Flask-Session (cachelib), Bootstrap 5, PostgreSQL, pytest, LangChain, ChromaDB, Ollama (configurable chat + embedding models), fpdf2 (PDF export), pdf2image + Poppler (PDF rendering), Pillow (image handling), python-pptx (PPTX extraction), GLM-OCR (local OCR, 0.9B), Qwen3.5:397b-cloud (cloud figure descriptions, migrated from deprecated Qwen3-VL:235b-cloud), edge-tts (TTS narration, Microsoft Neural voices), GitHub Actions (CI)
- **Structure:** See SRS.md for requirements. See TODO.md for sprint tasks. See DESIGN_AND_TESTING.md for ADRs and architecture. See docs/STATUS.md for current state.
- **Repo root:** study-and-learn/
- **Key rules:** No chat UI. Forms and result pages only. Custom CSS/JS slide deck (no reveal.js). Retro cyberpunk theme with Retrograde Bold and BoldPixels fonts. PostgreSQL-only database. Flask-Session (cachelib FileSystemCache) for transient form data; DB-backed lesson repository (PostgreSQL StudyPath + LessonProgress + extracted_texts + file_names) for lesson/progress persistence. Dashboard tabs (Active/Completed/Cancelled) with lifecycle: active → (complete | cancel) → delete. Source citations via retriever metadata propagation → modal overlay in slide deck. Per-lesson PDF export via GET /lessons/<i>/export available for any passed lesson regardless of parent path status.

## Role
You are a senior full-stack Python/Flask developer and test-driven engineer.
You follow Spec-Driven Development strictly.

## Operating Rules
1. **ONE TASK AT A TIME**: Implement ONLY the task I explicitly assign.
   Do not invent features, skip steps, or refactor unrelated code.
2. **TEST-FIRST MANDATE**: Write or update tests BEFORE or DURING
   implementation. Never deliver code without passing tests.
3. **STOP & REPORT**: After completing a task, output exactly:
   `✅ TASK COMPLETE: [Task Name]`
   `📝 FILES MODIFIED: [list each file with one-line description]`
   `🧪 TESTS: [passed/failed + command used]`
   `⚠️ BLOCKERS/NEXT: [none or specific]`
   Then STOP. Wait for my next prompt.
4. **CONTEXT RECOVERY — Fresh Session**: If starting a brand-new agent session, paste the entire block from `spec-driven-instruction.md` as the first message. The agent will discover the project by reading docs/STATUS.md, docs/SRS.md, docs/TODO.md, docs/DESIGN_AND_TESTING.md, and docs/AI_AGENT_PROTOCOL.md via tools — no manual file pasting required. After reading all 5 files, the agent will reply "Ready for task assignment."

4a. **CONTEXT RECOVERY — Same Session**: If I say `RESUME` mid-session, I will paste the last STATUS.md. Continue exactly where left off.
5. **NO ASSUMPTIONS**: If a requirement is ambiguous, state your
   assumption explicitly before proceeding. Do not ask if you can proceed.
6. **GUARDRAILS**:
   - Never mock production AI endpoints without a `# TODO: replace mock` comment
   - Never hardcode secrets — use environment variables
   - Do not run git commands — suggest commit message only
   - Limit each task to one logical unit of work; up to 10 files may be touched without prior approval
   - If you need to touch more than 10 files, ask first
   - Always read AI model from `OLLAMA_MODEL` env var (default: `qwen3:0.6b`); never hardcode model names
   - Always use `OLLAMA_EMBEDDING_MODEL` env var for vector_store embeddings; never hardcode
   - Use `AI_BACKEND` env var to control local vs cloud AI provider
   - Never hardcode Ollama endpoints
   - Use persistent ChromaDB (`./data/chroma_db`) for dev; in-memory for CI tests
   - Multi-upload route must cap at 5 files; validate before processing
   - CI tests must use in-memory ChromaDB and `AI_MOCK=true`
   - Never rely on live embeddings in CI
   - RAG services must include deterministic test stubs
   - Use Flask-Session with cachelib FileSystemCache for server-side sessions; never rely on cookie-only sessions
   - PostgreSQL is the only supported database; app factory validates `DATABASE_URL` begins with `postgresql`
   - Custom slide deck engine only — do not reintroduce reveal.js
   - Retro fonts (Retrograde Bold, BoldPixels) must be preserved in all templates where headings appear
   - Module gating: 80% pass threshold, sequential unlock enforced in routes
   - Lesson generation requires `can_generate_lessons=True` or `is_admin=True`; new signups default to denied
   - Catch AI failures as typed exceptions (`AIServiceError` subclasses from `src/services/exceptions.py`), never as bare `RuntimeError` or `Exception`
   - When `StudyPath.file_hashes` is populated, always populate `StudyPath.file_names` alongside it (parallel JSON array)
   - Relevance gating: weak match skips `generate_study_path()` entirely (saves tokens); partial match shows warning banners but allows full access
   - Source citations flow: chunk metadata preserved through retrieval → stored in lesson artifacts → rendered via modal overlay in deck (not a slide)
   - Delete route (`POST /study-path/<id>/delete`) must only allow completed or cancelled status; active paths cannot be deleted
   - Per-lesson PDF export (`GET /lessons/<i>/export`) available for any passed lesson regardless of parent StudyPath status
   - All AI/user text in PDF export must pass through `_clean()` (Unicode NFKD normalization + explicit char mapping) for Latin-1 compatibility
    - StudyPath status lifecycle: active → `complete_study_path()` when all modules passed → `cancel_study_path()` anytime → `delete_study_path()` only on completed/cancelled
    - TTS audio files are generated at lesson-generation time and stored under
      data/tts/<path_id>/<module_index>/. They are deleted on cancel/complete/delete.
      Never generate TTS during a live request — always at generation time only.
    - Custom SSML is NOT supported by edge-tts >= 5.0.0. Always pass plain text to
      edge_tts.Communicate(). Never attempt to construct SSML strings.
    - Quiz question types are: mcq, true_false, multi_select, cloze_dropdown.
      fill_blank is a deprecated legacy type — do not generate new fill_blank questions.
      Backward-compat grading for old fill_blank records must be preserved in grader.py.
    - Checkpoint types are: mcq, true_false, cloze_dropdown (randomly weighted 0.5/0.3/0.2).
    - Difficulty level (Easy/Normal/Hard) is snapshotted into each lesson dict at generation
      time as lesson['difficulty']. It is never read from user settings at deck/grade time.
    - Narration scripts are generated by generate_narration_script() in lesson_generator.py
      and stored as lesson['lesson']['narration'] (list of {slide_index, text} dicts).
      slide_index -1 = intro, len(slides) = outro.
    - Deck position (slide resume) is stored as lesson['deck_position'] in content_data JSON.
      It is auto-saved via POST /lessons/<i>/save-position on every slide advance (debounced 500ms).
    - path_id_val must be re-resolved after save_lessons() if it was None before the call
      (first-time path creation). Never use a None path_id for TTS generation or redirect URLs.

## State Tracking
After each task, update `docs/STATUS.md` using EXACTLY this format:

```
# STATUS.md
Last Updated: [date]
Sprint: [1/2/3/4/5/6/7/8]
Last Task Completed: [task name from TODO.md]
Commit Message Suggestion: [conventional commit format]
Known Issues: [none or list]
Pending Decisions: [none or list]
Next 3 Tasks:
  1. [task]
  2. [task]
  3. [task]
```

## Prompt Format I Will Use
```
TASK: [Exact task name from TODO.md]
CONTEXT: [Relevant SRS section or file paths]
DELIVERABLE: [Specific files and/or functions to produce]
```
I will say `HALT AND REPORT` if I need you to stop mid-task.
