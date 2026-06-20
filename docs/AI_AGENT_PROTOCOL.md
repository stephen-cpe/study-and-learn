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
   - Always read AI model from `OLLAMA_MODEL` env var. Note `config.py` ships `gemma3:27b-cloud` as the package default (used only by `Config.summary()` diagnostics); `ai_client.py` falls back to `qwen3:0.6b` when `AI_BACKEND=local` and `OLLAMA_MODEL` is unset at call time. Never hardcode model names
    - Always use `OLLAMA_EMBEDDING_MODEL` env var for vector_store embeddings; never hardcode
    - Use `AI_BACKEND` env var to control local vs cloud AI provider. `AI_BACKEND` is read at call time in `ai_client.py::call_ollama` (line 99), NOT from `config.py` — there is no `Config.AI_BACKEND` attribute; do not read it from `current_app.config`
    - Never hardcode Ollama endpoints
    - `call_ollama(prompt, model, force_local=False)` has a `force_local` parameter (`ai_client.py:84`). OCR/vision calls always pass `force_local=True` because GLM-OCR has no cloud variant and must run on local Ollama regardless of `AI_BACKEND`. Never route OCR calls through `AI_BACKEND=cloud` — the cloud endpoint has no GLM-OCR model and will fail silently
    - OCR behavior is dual-gated. Pulling `glm-ocr` is necessary but NOT sufficient: OCR is also gated by `OCR_FULL=true` (default `false`, `config.py:77`, `vision_parser.py:316`) which switches from text-only extraction to text+table+figure OCR per page. `OCR_FIGURE_DESCRIPTION=true` (default `false`, `config.py:79`, `vision_parser.py:332`) additionally enables cloud Qwen3.5 figure descriptions. With `OCR_FULL=false` the app does traditional text-layer extraction even if `glm-ocr` is installed
    - Use persistent ChromaDB (`./data/chroma_db`) for dev; in-memory for CI tests; optional Chroma Cloud via `CHROMA_DB=cloud` (see ADR-027)
    - Multi-upload route must cap at 5 files; validate before processing
    - CI tests must use in-memory ChromaDB and `AI_MOCK=true`. In-memory ChromaDB is activated by the `CI=true` env var (`vector_store.py::get_chroma_client`) — there is no conftest-level default that sets it automatically; set it explicitly in the CI workflow or per-test via `monkeypatch.setenv('CI', 'true')`. `CI=true` ALWAYS wins over `CHROMA_DB=cloud` to keep tests isolated and offline. Likewise `AI_MOCK` is re-read at call time in `ai_client.py:92` and `ai_client_cloud.py:33` (not just `config.py:92`) so tests can `monkeypatch.setenv` before invoking `call_ollama`
    - `CHROMA_DB` env var controls the ChromaDB backend: `local` (default, PersistentClient) or `cloud` (CloudClient). It is read at call time in `vector_store.py::get_chroma_client`, NOT from `current_app.config` — mirrors the `AI_BACKEND` pattern. When `CHROMA_DB=cloud` is requested, `get_chroma_client()` requires three credentials: `CHROMA_CLOUD_API_KEY`, `CHROMA_CLOUD_CONNECTION_STRING` (the Chroma tenant ID), and `CHROMA_COLLECTION_NAME` (becomes the Chroma Cloud database name — the app's per-file `doc_<hash>` collections live inside it). If any credential is empty/missing, the `CloudClient` constructor raises, OR the `heartbeat()` connectivity probe fails, the function logs a clear actionable error and reverts to the local PersistentClient. Never hardcode these credentials — always use env vars. The cloud fallback path must never strand the app: a single `_try_cloud_client()` failure logs and returns None, and the caller transparently uses the local client
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
    - TTS generation runs in a background `threading.Thread` daemon
      (`spawn_tts_background_task()` in `src/services/tts_worker.py`) so the
      request handler can return immediately. The worker is idempotent (skips
      modules whose manifest.json already exists) and failure-tolerant (a
      single failed module sets `tts_audio_status='failed'` and
      `tts_enabled=False` on that lesson dict and continues to the next module).
      The worker runs inside a Flask app context so it can read/write the DB.
      There is NO retry — a failed module is terminal for that module; the user
      must retake the lesson to regenerate audio for it. Do not add retry loops
      that would delay `generation_completed_at` or strand the user on the
      results page.
    - The canonical "navigate now" redirect signal is the
      `StudyPath.generation_completed_at` DB column (atomic, ACID), NOT the
      cache-based `progress_tracker.mark_done()`. It is set by the request
      handler's else branch (TTS disabled), the TTS worker's finally block
      (TTS enabled), and the spawn wrapper's defensive catch. The JS results
      page runs two parallel polls on one 2-second ticker: (A)
      `/progress?task_id=<id>` for cosmetic-only mascot/progress-bar updates
      (MUST NEVER trigger a redirect — ignore legacy `data.done` /
      `data.stage >= 4`); (B) `/lessons/generation-status?path_id=<id>&task_id=<id>`
      for the sole redirect decision (redirect iff
      `generation_completed === true`, read from the DB column). Hard timeout
      is 2 hours and MUST stop polling without redirecting. Do not reintroduce a
      single-poll design that uses cache `done`/`stage>=4` to redirect — that
      was the race-condition root cause (see ADR-026).
    - Custom SSML is NOT supported by edge-tts >= 5.0.0. Always pass plain text to
      edge_tts.Communicate(). Never attempt to construct SSML strings.
    - Quiz question types are: mcq, true_false, multi_select, cloze_dropdown.
      fill_blank is a deprecated legacy type — the generator prompt requests
      only the 4 active types, but `_validate_questions` in quiz_generator.py
      still *tolerates* an AI-emitted fill_blank (normalizing it to cloze_dropdown
      when it carries options+answer_index, or passing it through as fill_blank
      when it carries a free-text `answer`). This tolerance is intentional
      backward-compat for legacy lesson JSON — do not remove it. The grader
      (`grader.py::_grade_single_question`) must keep its `fill_blank` branch
      to grade legacy records. Do not author new fill_blank prompts.
    - Checkpoint types are: mcq, true_false, cloze_dropdown (randomly weighted 0.5/0.3/0.2).
    - Difficulty level (Easy/Normal/Hard) is snapshotted into each lesson dict at generation
      time as lesson['difficulty']. It is never read from user settings at deck/grade time.
    - Narration scripts are generated by generate_narration_script() in lesson_generator.py
      and stored as lesson['lesson']['narration'] (list of {slide_index, text} dicts).
      The active contract is keyed by deck_index from lesson['lesson']['deck_layout']
      (built by build_deck_layout() in lesson_orchestrator.py): one entry per deck slot
      (content, checkpoint, quiz, results), plus intro at slide_index=-1; the Results
      slot (last deck_index) doubles as the outro. The legacy
      "slide_index -1 = intro, len(slides) = outro" form is a fallback only
      (deck_layout=None) and is not used in production. Always preserve/rebuild
      deck_layout when modifying lesson JSON or regenerating narration, or TTS audio
      will desync from the visible slides.
    - lesson['lesson']['deck_layout'] is the canonical flat deck sequence (content slides
      interleaved with their checkpoints, then Final Quiz, then Results). Each entry has
      a unique deck_index used as the template's data-deck-index, the JS advance target,
      and the TTS slide_index. Never key TTS narration to content-slide indices alone.
    - Deck position (slide resume) is stored as lesson['deck_position'] in content_data JSON.
      It is auto-saved via POST /lessons/<i>/save-position on every slide advance (debounced 500ms).
    - path_id_val must be re-resolved after save_lessons() if it was None before the call
      (first-time path creation). Never use a None path_id for TTS generation or redirect URLs.
    - The audio route `GET /lessons/<i>/audio/<slide_index>` returns a load-bearing status
      triad the JS player (`deck-page.js`) depends on: 200 (file ready), 202 (TTS enabled
      but manifest missing OR file missing on disk — JS retries in ~2s), 404 (TTS disabled,
      module_index out of range, OR manifest present but slide_index has no entry — JS
      stops retrying). Do not collapse 202 into 404 or vice versa; the retry-vs-stop
      decision in deck-page.js keys off this distinction. See `lessons.py:518-553`.
    - Dev server forces `SEND_FILE_MAX_AGE_DEFAULT=0` (`src/__init__.py:84`) to prevent
      stale JS/CSS caching. Never remove or increase this in development — the browser
      will cache old client code and produce phantom bugs (e.g. the premature 10-minute
      hard-timeout redirect that masked earlier TTS fixes) that are invisible on the
      server side. In production, asset hashing or a CDN handles caching instead.

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
