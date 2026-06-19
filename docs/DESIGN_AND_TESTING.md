# Design and Testing Document
# Study-and-Learn

**Version:** 0.7
**Status:** Living document
**Last updated:** June 14, 2026

---

## 1. Architecture Overview

Study-and-Learn is a Flask web application with a Bootstrap-and-retro-CSS frontend and an AI-assisted backend workflow.

```mermaid
flowchart TD
    A["Unified Form: Goal + Files"] --> B["POST /process Route"]
    B --> C["Document Parser: .txt, .md, .pdf, .docx, .pptx"]
    B --> C2["Vision Parser: .png, .jpg, .jpeg"]
    C --> C3["OCR Pipeline: GLM-OCR local + Qwen3.5 cloud"]
    C2 --> C3
    C3 --> D["Chunker: RecursiveCharacterTextSplitter"]
    D --> E["Vector Store: Content-Keyed ChromaDB (doc_{hash})"]
    E --> F["RAG Retriever: Multi-Collection top-k=5 context + sources metadata"]
    F --> G["Summarizer"]
    F --> H["Relevance Checker"]
    F --> I["Curriculum Generator"]
    G --> J["results.html: Summary, Relevance, Study Path"]
    H -->|weak| J
    H -->|partial/strong| J
    I -->|if not weak| J
    J --> K{"Weak match?"}
    K -->|Yes| K2["Weak feedback card: no study path, no lessons"]
    K -->|No| L{"Generate Interactive Lessons?"}
    L --> M["Lesson Generator: slides JSON + sources"]
    L --> N["Quiz Generator: questions + checkpoints"]
    M --> M2["Narration Script Generator (generate_narration_script)"]
    M2 --> M3["Edge-TTS: MP3 per slide → data/tts/<path>/<module>/"]
    M3 --> O
    N --> O
    O["lessons.html: Module Grid with Gating + Export PDF buttons + difficulty/TTS badges"]
    O --> P["lesson_deck.html: Custom Slide Deck + Sources modal + difficulty badge + TTS player bar + Exit & Save + session resume"]
    P --> Q["Inline Checkpoints: block advance"]
    P --> R["Final Quiz: 4 question types"]
    Q --> R
    Q --> G2["POST /grade: AJAX, instant feedback"]
    R --> G2
    G2 --> S["Results Slide: score, pass/fail"]
    S --> T{"Score >= 80%?"}
    T -->|Yes| U["Unlock Next Module"]
    T -->|No| V["Retake: Regenerate Quiz"]
    V --> O
```

Core workflow:

1. User enters a learning goal and uploads study documents in a single unified form.
2. Backend validates and stores uploads.
3. Document parser extracts text from `.txt`, `.md`, `.pdf`, `.docx`, `.pptx`.
4. Vision parser renders pages/images and runs AI-powered OCR (GLM-OCR local, Qwen3.5 cloud) for `.png`, `.jpg`, `.jpeg`, and scanned PDFs.
5. File hashes are computed, ContentRegistry check skips duplicates globally.
6. RAG pipeline chunks, embeds, stores, and retrieves relevant context from content-keyed ChromaDB collections.
7. AI services generate summary and relevance check.
8. If weak match → display alternative feedback card (study path + lesson generation gated). Otherwise → full pipeline.
9. AI generates study path (if not gated).
10. Results page displays structured output: summary, relevance (with partial warning banners or weak feedback card), and study path (if applicable).
11. User clicks "Generate Interactive Lessons" to produce slide-based lessons (if not gated by weak relevance).
12. AI generates lesson slides + inline checkpoints + mixed-type quiz per module.
12a. If TTS is enabled (user opt-in), an AI-generated narration script is produced
     per module (tutor-voice, personalized intro/outro) and converted to per-slide MP3
     files via Edge-TTS (Microsoft Neural voices). Audio files are stored under
     data/tts/<path_id>/<module_index>/ and served via authenticated Flask routes.
12b. Difficulty level (Easy/Normal/Hard, from user settings at generation time) is
     injected into all lesson and quiz prompts and snapshotted into each lesson record.
12c. Deck slide position is auto-saved to DB on every slide change (debounced 500ms),
     enabling session resume on revisit.
13. Source citation metadata (chunk provenance) is preserved through retrieval and stored alongside lesson artifacts.
14. Custom CSS/JS slide deck presents lessons with retro fonts, checkpoint blocking, and a "View Sources" button in the controls bar (opens modal overlay with document excerpts).
15. Learner completes quiz, receives instant grading with per-question feedback.
16. Failed modules can be retaken with fresh regenerated questions.
17. Progression is gated (80% pass threshold required to unlock next module).
18. Passed lessons can be exported to PDF via a per-lesson export button (slides, checkpoints, quiz answers, source materials).

---

## 2. Architecture Decisions

### ADR-001: Use Flask for the MVP

**Decision:** Use Flask for backend development.

**Reason:** Flask is lightweight, Python-based, and suitable for a capstone-scale web application. It allows fast development without imposing a large framework structure.

### ADR-002: Use Bootstrap for the UI

**Decision:** Use Bootstrap 5 for UI styling.

**Reason:** Bootstrap provides responsive layout and common UI components with minimal custom CSS and no complex frontend build process.

### ADR-003: Avoid chat UI in the MVP

**Decision:** Use forms, buttons, and structured result pages.

**Reason:** The project goal is guided learning support, not open-ended chatbot interaction. This also makes the MVP easier to test and demonstrate.

### ADR-004: Use an AI client wrapper

**Decision:** AI calls should go through a service wrapper such as `ai_client.py`.

**Reason:** This makes the application easier to test by allowing mocked AI responses. It also allows Ollama or another model provider to be swapped later.

### ADR-005: Start with simple parsing before advanced retrieval

**Decision:** Implement document parsing and whole-document/section summarization first. Add embeddings/retrieval only after the core workflow works.

**Reason:** The capstone MVP depends on end-to-end functionality. Retrieval adds value but also complexity.

### ADR-006: Implement RAG Pipeline (Chunk → Embed → Retrieve → Generate)
**Decision:** Replace direct document-to-AI prompting with LangChain chunking + ChromaDB retrieval.
**Reason:** Prevents context window overflow, enables source-grounded outputs, scales to multiple documents, and aligns with modern AI engineering standards.
**Tradeoffs:** ✅ Grounded, scalable, traceable • ❌ Adds vector DB dependency, requires embedding strategy

### ADR-007: Configurable AI Model Provider with Mock Fallback

**Decision:** AI services use an environment-variable-driven model configuration (`OLLAMA_MODEL`, `AI_BACKEND`). CI/testing uses `AI_MOCK=true`.

**Reason:** Capstone MVP prioritizes reliability over model routing complexity. A single configurable environment variable allows the developer to switch between small local models, larger local models, or cloud-based models without code changes. Mock fallback guarantees deterministic tests in CI regardless of GPU availability or network access.

**Update:** Sprint 5 introduced the `AI_BACKEND` environment variable (`local` or `cloud`) to make the provider switch explicit and testable. A `ai_client.py` smoke test validates the indirection works correctly.

### ADR-008: Separate Chat and Embedding Model Configuration

**Decision:** Chat uses `OLLAMA_MODEL`, embeddings use `OLLAMA_EMBEDDING_MODEL`.

**Reason:** Chat models typically do not expose embedding endpoints. Separating the two allows independent tuning — a smaller embedding model may suffice for retrieval while a larger chat model can be used for generation. Both are swappable via environment variables.

### ADR-009: Custom CSS/JS Slide Deck Engine (Replaces reveal.js)

**Decision:** Build a custom CSS/JS slide-deck engine instead of using reveal.js.

**Reason:** reveal.js introduced layout overflow bugs, scaling issues on the constrained viewport, and CSS conflicts with the project's retro theme (custom `@font-face` declarations, cyberpunk body styles). A custom engine gives full control over sizing, font application, checkpoint blocking logic, and responsive breakpoints. The custom engine renders slides from JSON, supports title/content/example/summary slide types, inline checkpoint blocking, and final quiz forms — all with Retrograde Bold and BoldPixels pixel fonts. This aligns with the "thin MVP" philosophy (build only what's needed) and avoids dependency bloat.

### ADR-010: Server-Side Session Storage with Flask-Session + cachelib (Phase 1); DB-Backed Lesson Repository (Phase 2)

**Decision (Phase 1):** Use Flask-Session with cachelib's FileSystemCache for session storage.

**Reason:** Flask's default signed-cookie sessions cap at ~4 KB. Full lesson JSON for 5 modules with slides, checkpoints, and quiz questions far exceeds this limit. Flask-Session's server-side storage keeps the per-request cookie small while storing large session data on disk. FileSystemCache was chosen over the deprecated filesystem backend to match Flask-Session 0.8's recommended pattern. Tradeoffs: ✅ No cookie size limits, transparent to app code • ❌ Requires `data/flask_session/` directory, sessions lost on server restart (acceptable for MVP demo).

**Decision (Phase 2 — Sprint 5):** Replace the session-backed lesson storage with a PostgreSQL-backed `LessonRepository` using `StudyPath` and `LessonProgress` models.

**Reason:** User accounts (Sprint 5) introduced persistent identity, making session-only lesson storage insufficient. A DB-backed repository (`lesson_repo.py`) persists lesson content (`StudyPath.content_data`), extracted text corpora (`StudyPath.extracted_texts`), and per-module progress (`LessonProgress` rows) across sessions and server restarts. The repository seam pattern (`get_lessons()` / `save_lessons()`) was retained so that the storage backend can be swapped again in the future without changing route logic.

**Post-Sprint 5 Update:** Multi-path support was added in Sprint 5 bug-fix rounds. Each learning goal creates an independent `StudyPath` row (via `create_study_path()`), enabling users to maintain up to 3 active study paths simultaneously. All lesson routes are path-aware (accept `path_id` query parameter), and the dashboard renders a navigable grid of all active paths with per-path progress bars. `save_lessons()` targets a specific path when `path_id` is provided; without it, falls back to the most recently created active path. Tradeoffs: ✅ Persistent across restarts, enables per-user lesson gating, multi-path navigation, progress tracking • ❌ Adds DB dependency for lesson storage, requires migration.

### ADR-011: Sequential Lesson Generation with Progress Feedback

**Decision:** Generate lessons sequentially (one module at a time) with a visible progress/loading indicator rather than concurrently.

**Reason:** Sequential execution is simpler to debug, logs clearly, avoids overwhelming the local Ollama server with concurrent requests on limited hardware (6GB VRAM), and enables accurate per-module progress reporting. Concurrency was considered but rejected due to: harder error handling, risk of Ollama request queuing and timeouts, and difficulty showing clean progress.

### ADR-013: Cachelib-Backed Progress Tracking (Replaces In-Memory Dict)

**Decision:** Use cachelib's `FileSystemCache` for progress tracking between long-running POST requests and concurrent polling GET requests. The progress key is a client-generated UUID passed as a POST body field and GET query parameter.

**Reason:** Flask-Session only persists data at request-end, making it invisible to concurrent polling. A module-level Python dict is unreliable across threads in Flask's threaded debug server. cachelib's FileSystemCache provides file-backed, thread-safe read/write with immediate visibility to all concurrent requests. Tradeoffs: ✅ Thread-safe, immediate visibility, simple API • ❌ Small disk writes every 2s during generation (acceptable for MVP).

### ADR-014: Mascot Speech Bubble as Progress Indicator

**Decision:** Merge the progress indicator into the existing mascot speech bubble rather than maintaining a separate DOM element.

**Reason:** Eliminates visual overlap between two fixed-position elements (speech bubble and progress indicator both positioned bottom-right). The mascot "speaking" the progress stage is more intuitive and engaging than a separate progress bar. The speech bubble stays persistently visible during generation (no 4-second auto-hide) and reverts to idle chatter after completion. Tradeoffs: ✅ Cleaner UI, no overlap, more engaging • ❌ Speech bubble width increased from 200px to 240px to accommodate progress bar.

### ADR-012: Retake = Regenerate Fresh Questions

**Decision:** On lesson retake, regenerate entirely new quiz questions and checkpoints rather than reusing the originals.

**Reason:** Reusing the same questions on retake allows learners to memorize answers without understanding the material — the worst pedagogical outcome. Regenerating questions each retake tests real comprehension and is pedagogically strongest. The tradeoff is additional Ollama calls and generation time per retake, but this is acceptable on a per-module basis (5 questions + ~2 checkpoints per retake, < 60 seconds each on qwen3:0.6b).

### ADR-015: Multi-Path Study Support (Independent StudyPath per Learning Goal)

**Decision:** Each learning goal processed via `POST /process` creates an independent `StudyPath` row (via `create_study_path()`), enabling up to 3 concurrent active study paths per user.

**Reason:** Sprint 5 testing revealed that the initial single-path architecture overwrote previous learning goals when a new one was processed. Multi-path support allows learners to study multiple subjects simultaneously with independent progress tracking per subject. The dashboard renders all active paths as a navigable grid, and all lesson routes accept a `path_id` query parameter to target specific paths. The session-leak bug (user A's session data appearing for user B) was also fixed by clearing session data on login rather than logout. Tradeoffs: ✅ Multi-subject study, independent progress, cleaner UX • ❌ More DB rows, path-aware routing complexity.

### ADR-016: Admin Panel, Access Control, Password Reset, and Error Handlers

**Decision:** Add an admin-only dashboard (`/admin`), per-user lesson generation toggle, self-service password reset, admin-initiated password reset, custom HTTP error pages, and a 3-tier access model (unauthenticated / privileged / unprivileged).

**Reason:** Sprint 5 introduced user accounts but left admin functionality incomplete. Admins need a centralized view to manage user access (toggle `can_generate_lessons`, reset passwords). The access model was refined to three tiers: unauthenticated users see the login form, privileged users (`can_generate_lessons=True` or `is_admin=True`) see the full learning form, and unprivileged users see an access-denied message. Custom error handlers (400/403/404/500) provide retro-themed error pages instead of raw Werkzeug debug output. Tradeoffs: ✅ Role-based access control, user management, polished error UX • ❌ Removed dead `login.html` template (index.html handles unauthenticated login inline).

### ADR-017: AI-Powered OCR/Vision Integration with Content-Addressable Deduplication

**Decision:** Integrate local GLM-OCR (0.9B, text/table/figure recognition) and cloud Qwen3.5:397b (figure descriptions) as an AI-powered OCR pipeline, coupled with SHA-256 content-addressable deduplication via a `ContentRegistry` database model and content-keyed ChromaDB collections (`doc_{hash}`).

**Reason:** Before Sprint 6, the app only supported text-layer extraction from `.txt`, `.md`, `.pdf`, and `.docx`. Scanned PDFs, embedded images, PowerPoint slides, and raw image files were either rejected or produced empty output. The OCR pipeline enables 8 file types, extracts text from visual content, and generates semantic figure descriptions. Content-addressable deduplication prevents redundant OCR and embedding when identical files are uploaded by different users or in different sessions — ChromaDB collections are named by file hash and shared globally rather than tied to user sessions. Tradeoffs: ✅ 8 file types, global dedup, multi-collection retrieval • ❌ Adds GLM-OCR dependency (~2.2 GB), Poppler system dependency, ~2s/page OCR latency

### ADR-018: Typed Exception Hierarchy with User-Facing Error Messages

**Decision:** Replace generic `RuntimeError` in AI clients with a typed exception hierarchy (`StudyAndLearnError` → `AIServiceError` → `AIModelUnavailableError` / `AICloudAPIError` / `AITimeoutError`), add exponential-backoff retry for transient connection failures, and catch AI errors at the service layer to return user-friendly messages instead of raw error strings.

**Reason:** Before this change, Ollama failures (connection refused, HTTP 500, timeouts) produced raw `RuntimeError` strings shown directly to users: `"Failed to reach Ollama at http://localhost:11434"`. Users had no way to distinguish between a temporary glitch (retryable) and a configuration error (needs human fix). The new hierarchy maps HTTP status codes and exception types to user-actionable messages (`"AI service is currently unavailable. Please verify your AI backend is running and try again."`). Service-layer generators (`summarizer.py`, `relevance_checker.py`, `curriculum_generator.py`) catch `AIServiceError` and either raise `StudyAndLearnError` with a friendly message or gracefully fall back to default content. Lesson/quiz generators fall back to hardcoded content when AI is unavailable rather than crashing. Silent `except Exception: pass` blocks were converted to `logger.warning()` calls. Tradeoffs: ✅ User-visible error clarity, graceful degradation, retry resilience • ❌ 7-class hierarchy, additional `try/except` in each service layer

### ADR-019: Relevance Gating — Weak Match Blocks Downstream Generation

**Decision:** When the relevance checker returns a `weak` match, skip `generate_study_path()` entirely (set `study_path = {}`), display an alternative weak-match feedback card on the results page, and do not render the "Recommended Study Path" card or "Generate Interactive Lessons" button. Partial matches display warning banners on both the relevance card and study path card but allow full access.

**Reason:** Generating a study path and lessons from irrelevant content wastes AI tokens and produces misleading output. The SRS requirement FR-023 ("should identify when uploaded materials are insufficient") is now fulfilled by this gating. The `missing_material` field from the AI serves as the primary content for the weak feedback card, giving learners specific, actionable suggestions for what materials to find. Tradeoffs: ✅ FR-023 fulfilled, token savings, clear UX signal • ❌ AI judgment is opaque (no algorithmic scoring backup), user cannot override

### ADR-020: Source Citation System — Retriever Metadata Preservation

**Decision:** Preserve chunk-level provenance metadata (chunk ID, source hash, filename, full chunk text) from ChromaDB retrieval through the entire pipeline: `retrieve_from_multiple_collections_with_sources()` → `build_rag_context_for_module()` → `generate_lesson()` → `build_module_artifacts()` → `save_lessons()`. Store sources in the lesson JSON alongside slides/quiz/checkpoints. Render them via a "View Sources" button in the slide deck controls bar that opens a modal overlay (not a slide, so it never blocks navigation). A parallel `file_names` JSON column on `StudyPath` provides human-readable filenames for citation display.

**Reason:** The critical provenance break was at `vector_store.py:181` where `retrieve_from_multiple_collections()` discarded all metadata (joining only document text). The function `retrieve_with_scores()` already queried ChromaDB with `include=["documents", "distances", "metadatas"]` — the data was available but thrown away. Adding a parallel `retrieve_from_multiple_collections_with_sources()` that returns `{"context_text": str, "sources": [...]}` required updating the retriever callable signature from `Callable[[str], str]` to `Callable[[str], Dict[str, Any]]` across 6 service files. The `isinstance(result, dict)` fallback in quiz/checkpoint generators maintains backward compatibility with string-only mock retrievers in tests. Tradeoffs: ✅ Deterministic provenance (no LLM hallucination risk), one-click source access, existing `retrieve_with_scores()` infra already in place • ❌ ~6 service file signature changes, `file_names` DB column added, retriever type change ripples to all callers

### ADR-021: Dashboard Tabs + StudyPath Status Lifecycle

**Decision:** Replace the single-status dashboard (`status='active'` only) with three tab pills (Active/Completed/Cancelled) driven by a `?tab=` query parameter. Add a `status='completed'` lifecycle state (user-triggered via "Mark Complete" button, only available when all modules have `passed=True`). Add a `POST /study-path/<id>/delete` route (permanent deletion, only available for completed or cancelled paths with a stern irreversibility warning). The navbar gains a "My Lessons" link for direct access.

**Reason:** Previously, a fully-passed path remained "active" forever with 100% progress — no way to archive it. Cancelled paths simply disappeared from the dashboard — users could not review abandoned work. The three-tab design gives users a clear view of their learning history without adding new navigation pages. The "Mark Complete" action is manual (not automatic) to give users a sense of accomplishment and control. Deletion is restricted to completed/cancelled statuses only — active paths cannot be deleted to prevent accidental data loss. Tradeoffs: ✅ Learning history preserved, clutter control via delete, no new pages/routes (just tabs) • ❌ `status='completed'` is a new VARCHAR value (no schema change needed), delete is irreversible

### ADR-022: Per-Lesson PDF Export via fpdf2

**Decision:** Implement per-lesson PDF export (`GET /lessons/<i>/export?path_id=...`) in `src/routes/dashboard.py` using the fpdf2 library (pure Python, no system dependencies) rather than WeasyPrint (requires GTK system libraries, unavailable on Windows). Each PDF contains: lesson slides, inline checkpoints with correct answers, quiz questions with answers and explanations, and source materials with filenames and chunk text. Export is available for any passed lesson (score ≥ 80%) regardless of the parent StudyPath status (active, completed, or cancelled). All AI-generated/user-provided text passes through a `_clean()` sanitizer (Unicode NFKD normalization + explicit character mapping for en-dash, em-dash, smart quotes, bullets, ellipsis, non-breaking space) — also defined in `dashboard.py` — to ensure Latin-1 compatibility with fpdf2's built-in Helvetica font.

**Reason:** WeasyPrint was attempted first but failed at import time due to missing GTK/pango system libraries on Windows (`libgobject-2.0-0` not found). fpdf2 is already in the project's virtual environment (was a transitive dependency of markdown_pdf) and requires only the Python standard library. Per-lesson granularity (not per-path) allows learners to export individual completed modules even if they abandon the overall study path — analogous to keeping a textbook from a course you didn't finish. Tradeoffs: ✅ Pure Python, no system deps, per-lesson granularity, Latin-1 sanitization • ❌ Limited to built-in Helvetica font (no Unicode), text wrapping is manual, no header/footer page numbering, output is single-page-per-lesson (not multi-page)

### ADR-023: Edge-TTS for Opt-In Audio Narration

**Decision:** Use the `edge-tts` Python library (Microsoft Edge Neural voices) for
opt-in TTS narration. Generate one MP3 per deck slot defined by `build_deck_layout()`
(content slides, inline checkpoints, Final Quiz, Results), plus an intro MP3 at
`slide_index=-1`, at lesson-generation time. The Results slot (last `deck_index`)
narration doubles as the module outro — there is no separate outro MP3 at
`slide_index=N`. The `slide_index` of each narration entry matches the corresponding
`deck_index` in `lesson['lesson']['deck_layout']`, which is the single source of truth
for slot ordering shared by the template's `data-deck-index`, the JS deck engine's
advance target, and the TTS manifest. Store under
data/tts/<path_id>/<module_index>/. Serve via authenticated Flask routes. Delete on
StudyPath cancel/complete/delete. (The legacy `intro=-1, content 0..N-1, outro=N`
contract is a fallback only, used when `deck_layout=None`, and is not exercised in
production.)

**Reason:** edge-tts is zero-cost, requires no API key, produces high-quality Neural voices
(Ava/Emma/Ryan/Andrew), and runs as a pure Python async library. Pre-generating audio at
lesson creation time avoids latency during playback. Per-slide granularity enables the JS
player to sync audio to the current slide via the deckSlideChanged custom event.

**Important constraint:** Custom SSML has been blocked by Microsoft since edge-tts v5.0.0.
Only plain text may be passed to edge_tts.Communicate(). The narration script is therefore
generated as natural prose by a dedicated AI call (generate_narration_script()) rather than
being assembled from raw slide bullets — this produces tutor-voice narration rather than
robotic bullet reading.

**Tradeoffs:** ✅ Zero cost, Neural quality, no API key, pre-generated (no playback lag),
personalized tutor voice ✦ ❌ Requires Microsoft's online service (no offline mode),
speaker change requires retake (audio is snapshotted at generation time).

### ADR-024: Difficulty-Aware Content Generation with Prompt Injection

**Decision:** Inject a `DIFFICULTY_INSTRUCTIONS` profile (Easy/Normal/Hard) into lesson,
quiz, and checkpoint prompts at generation time. Difficulty is read from
`current_user.lesson_difficulty` at generation time and snapshotted into each lesson dict
as `lesson['difficulty']`. It is never re-read from user settings at deck/grade time.

**Reason:** Snapshotting prevents retroactive changes (changing difficulty in Settings
after generation does not alter existing lessons). Age-profile instructions (vocabulary,
sentence complexity, jargon handling) produce measurably different output quality for
different age groups compared to a single generic prompt.

**Tradeoffs:** ✅ Deterministic per-lesson difficulty, profile-based prompts, difficulty
badge visible on lessons list ✦ ❌ Requires retake/regeneration to change difficulty.

### ADR-025: Session Save/Resume via content_data JSON (No Schema Change)

**Decision:** Store the current deck slide index as `lesson['deck_position']` inside the
existing `StudyPath.content_data` JSON blob. A debounced `POST /lessons/<i>/save-position`
route is called on every slide advance (500ms debounce). On page load, deck-engine.js reads
`data-resume-slide` from the container element and seeks to that slide. A "Start Over"
button resets position to 0. Position is never saved on completed lessons.

**Reason:** Adding a new DB column to `LessonProgress` for slide position was rejected
because `content_data` already carries per-lesson JSON state. No migration needed. The
save-position call is fire-and-forget (silent failure) so it never blocks navigation.

**Tradeoffs:** ✅ No schema change, no migration, no new dependencies, auto-saves silently
✦ ❌ content_data blob grows by one small int per lesson per save event (negligible).

### ADR-026: Atomic DB Column as Generation-Completion Redirect Signal (Replaces Cache `mark_done()`)

**Decision:** Replaced the cache-based `progress_tracker.mark_done()` redirect signal with
the atomic `StudyPath.generation_completed_at` DateTime column. The TTS background worker
(a `threading.Thread` daemon spawned by `spawn_tts_background_task()` in
`src/services/tts_worker.py`) runs TTS generation idempotently (skips modules whose
`manifest.json` already exists), isolates per-module failures (a single failed module sets
`tts_audio_status='failed'` and `tts_enabled=False` on that lesson dict and continues to the
next), and sets `generation_completed_at` in its `finally` block so every terminal state
(ready, n/a, failed) triggers the redirect. The request handler sets the same column in its
`else` branch when TTS is disabled (or if the worker thread cannot spawn). The JS results
page (`src/static/js/progress.js`) runs two parallel polls on a single 2-second ticker:
(A) `/progress?task_id=<id>` for cosmetic-only mascot/progress-bar updates (never triggers a
redirect, ignores the legacy `data.done` / `data.stage >= 4` signals); and
(B) `/lessons/generation-status?path_id=<id>&task_id=<id>` for the sole redirect decision
(redirects iff `generation_completed === true`, which is sourced from the
`StudyPath.generation_completed_at` column). A 2-hour hard timeout stops both polls without
redirecting. Alembic migration `d4e5f6a7b8c9` adds the column; `init_db.sql` includes it for
fresh installs.

**Reason:** The previous cache-based `mark_done()` signal was subject to a race condition
when the TTS worker and the request handler shared the same `progress_tracker` key: the TTS
worker's `TTS_STAGES` (max stage 3) overwrote the request handler's `GENERATE_STAGES` (max
stage 4), so the JS redirect condition (`data.stage >= 4`) never fired — or, under other
timing, fired prematurely because the cache write was not atomic with the lesson-dict
persistence. A database column is atomic and ACID, unaffected by shared-cache races, and is
the canonical "navigate now" signal regardless of which component finishes last.

**Tradeoffs:** ✅ Atomic, race-free redirect signal; one source of truth for both TTS-enabled
and TTS-disabled paths; failure of any single TTS module cannot strand the user on the
results page ✦ ❌ Requires an Alembic migration + `init_db.sql` update; the 2-hour hard
timeout is a safety net only (the user must navigate manually if the column is never set).

---

## 4. Software & Architectural Patterns
- Model-View-Controller (MVC): Flask routes (Controller) delegate to `src/services/` (Model/Business Logic) and render Bootstrap templates (View). Separation keeps routing thin and services testable.
- Service Layer Pattern: All AI, parsing, and RAG logic isolated in `src/services/`. Enables independent unit testing, easy mocking, and future provider swaps.
- Repository/DAO Pattern: ChromaDB vector storage abstracted behind `vector_store.py`. Decouples ingestion from retrieval logic.
- Mock Object Pattern: `AI_MOCK=true` and in-memory ChromaDB replace live LLM/vector calls in CI. Guarantees deterministic, zero-cost, GPU-free test execution.

### Route Ownership (`src/routes/`)

The single `main` blueprint is split across five route modules. URL paths do not necessarily map 1:1 to the file that owns them — this split is a code-organization decision, not a URL hierarchy.

| File | Owns |
|---|---|
| `auth.py` | `/signup`, `/login`, `/logout`, `/reset-password`, `/settings` |
| `processing.py` | `/` (unified form), `/process` (POST upload+goal), `/results`, `/progress` (long-running progress polling) |
| `lessons.py` | `/generate-lessons` (POST), `/lessons` (module grid), `/lessons/<i>` (deck), `/lessons/<i>/grade` (POST), `/lessons/<i>/retake` (POST), `/lessons/<i>/save-position` (POST), `/lessons/<i>/audio/<idx>` (GET), `/lessons/generation-status` (GET), `/lessons/<i>/audio/manifest` (GET) |
| `dashboard.py` | `/dashboard`, `/study-path/<id>/complete` (POST), `/study-path/<id>/cancel` (POST), `/study-path/<id>/delete` (POST), `/lessons/<i>/export` (GET, PDF), `/reset` |
| `admin.py` | `/admin`, `/admin/toggle/<user_id>`, `/admin/reset-password/<user_id>` (POST) |

---

## 5. Testing Strategy

### Unit Tests
    Unit tests cover isolated logic:
    - allowed file type validation,
    - parser selection,
    - parser error handling,
    - prompt construction,
    - relevance label parsing,
    - curriculum output parsing,
    - AI client mock mode and live mode,
    - LangChain text splitter output validation,
    - ChromaDB collection creation & persistence checks,
    - ChromaDB uses EphemeralClient when CI=true, PersistentClient otherwise,
    - Similarity search context builder accuracy,
    - Multi-file upload session & cookie size limits,
    - AI calls mocked via AI_MOCK=true,
    - Lesson generator: mock, empty inputs, retriever, slide validation, fallback behavior,
    - Quiz generator: mock, empty inputs, retriever, inline checkpoint, question validation, type mix distribution, fallback quiz structure,
    - Slide validation (only known types accepted),
    - Question validation (all 4 question types: mcq, true_false, multi_select, cloze_dropdown; fill_blank is deprecated legacy),
    - Fallback lesson and quiz generation for error resilience,
    - Vision parser: OCR, file hashing, content registry, dedup, feature gates, concurrent handling (20 tests),
    - Parser expansion: pptx extraction, image files, dedup verification (5 tests),
    - RAG expansion: multi-collection retrieval, metadata propagation, scores (4 tests),
    - TTS service: voice mapping, manifest generation, empty text skipping, directory cleanup (5 tests),
    - Lesson generator: narration script structure, intro username, AI fallback, last-module outro (4 tests),
    - Quiz generator: cloze_dropdown validation and grading, checkpoint type variety (mcq/true_false/cloze_dropdown), humor instructions in prompt, difficulty injection in prompt (8 tests),
    - Routes: TTS enabled/disabled flags in lesson dict, TTS failure graceful degradation, audio 404 when disabled, save-position stores deck_position, completed lesson blocks overwrite, extracted_texts nullified after generation, difficulty snapshotted from user (8 tests).

### Integration Tests

Integration tests cover routes and workflow behavior:
- homepage loads,
- `/process` route with valid data returns results,
- `/process` route rejects empty goal,
- `/process` route rejects empty files,
- `/process` route rejects invalid file types,
- `/process` route enforces max 5 files,
- mocked full workflow: goal + upload → summary → relevance → study path,
- mocked generate-lessons flow: session data → lesson + quiz generation → redirect,
- lesson deck route with pre-populated session lessons returns 200.

Current test suite: 381 tests passing (Sprint 8 active — suite rebuilt from Tasks 1–11).
Sprint 7 test additions cover: TTS service (5), narration script (4), cloze_dropdown grading
(3), checkpoint variety (3), humor/difficulty prompt injection (5), route-level TTS flags (3),
save-position (2), audio routes (2), difficulty snapshotting (1), extracted_texts cleanup (1).
Sprint 8 additions: TTS 404 regression (path_id re-resolved after first save), two-poll
parallel-endpoint assertion, hard-timeout-no-redirect, static-cache disabled, audio-route
path_id fallback (5+ tests).

### Smoke Tests

Smoke tests run before sprint demos and final recording:
- app starts,
- sample document uploads,
- summary displays with markdown rendering,
- relevance result displays with colored indicator,
- study path timeline displays,
- "Generate Interactive Lessons" button triggers generation,
- slide deck renders with retro fonts,
- checkpoints block advance until answered,
- quiz grading returns score and per-question feedback,
- retake regenerates questions,
- module gating enforces 80% pass progression.

---

## 6. CI/CD

Initial GitHub Actions workflow:

- trigger on push and pull request,
- install Python,
- install dependencies,
- run `pytest -v tests/`.

Future additions:
- linting,
- formatting,
- deployment automation,
- security scanning.

---

## 7. AI Tooling Use

AI tooling may be used to:
- refine specifications,
- draft code,
- generate test ideas,
- debug implementation issues,
- improve documentation.

All AI-generated code must be reviewed before commit. Important project behavior should be covered by tests.

---

## 8. Deployment Notes

Deployment target is undecided. Candidate platforms:
- Render,
- Railway,
- PythonAnywhere,
- DigitalOcean,
- AWS EC2.

The deployed version should be stable enough for capstone demonstration and accessible from the final submission link.

---

## 9. Deployment Strategy & Cost Analysis
- Option A: Local-First Demo (Current)
  - Host: Developer laptop running Ollama + Flask
  - Cost: $0 (uses existing hardware)
  - Tradeoff: Not publicly accessible; suitable for sprint demos & local dev
- Option B: Free-Tier Cloud (Recommended for Submission)
  - Host: Render or Railway (Flask web service)
  - Cost: $0/month (free tier supports 512MB–1GB RAM, sufficient for Flask + static assets)
  - AI Strategy: Swap Ollama for cloud API (OpenRouter/Groq) or keep `AI_MOCK=true` for demo
  - Vector DB: ChromaDB runs in-memory or uses persistent volume (~50MB free tier storage)
  - Tradeoff: Requires API key or mocked AI; free tier sleeps after inactivity but wakes on request
- Option C: VPS (DigitalOcean/AWS)
  - Cost: ~$6–12/month (4GB RAM droplet)
  - Tradeoff: Overkill for capstone; adds operational overhead
Recommendation: Deploy to Render/Railway free tier with `AI_MOCK=true` for grading, document swap path to production API in README.

---

## 10. Known Risks

| Risk | Impact | Mitigation |
|---|---|---|
| AI model too slow locally or inconsistent output quality | Demo delay or poor pedagogical value | Use small documents and cached/demo responses; support cloud model fallback via `AI_BACKEND=cloud` |
| File parsing issues | Failed workflow | Start with fewer file types and add more gradually |
| Scope creep | Missed MVP | Keep optional features outside official sprint goals |
| Deployment resource limits | App unavailable | Test deployment early; maintain `AI_MOCK=true` path for free-tier hosting without GPU |
| AI output inconsistency | Poor demo | Use controlled sample documents and structured prompts |
| PostgreSQL privilege issues on live DB | Blocked migrations | Document `init_db.sql` workaround (includes DROP IF EXISTS + full schema + seed accounts) and `GRANT CREATE` procedure |
| Session leakage between users | User A sees User B's data after logout/login swap | Fixed in Sprint 5 bug-fix rounds: clear session-scoped keys on login via `session.pop()` |
| OCR model unavailable (GLM-OCR not pulled) | OCR pipeline fails for scanned PDFs | Graceful fallback to traditional text extraction; clear warning logged |
| Edge-TTS online service dependency | TTS narration unavailable if Microsoft changes the service | TTS is opt-in and gracefully degrades (tts_enabled set to False on failure); lessons remain fully functional without audio |
