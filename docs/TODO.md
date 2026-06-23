# TODO / Product Backlog
# Study-and-Learn
### *Turn Any Documents into Interactive, Personalized Learning Experiences*

**Purpose:** This document organizes the capstone work into MVP tasks, user stories, sprints, stretch goals, and submission requirements.  
**Last updated:** June 19, 2026

---

## 0. Guiding Rule

Build the smallest working version first, then iterate:

> Goal + upload → parse → chunk → embed → retrieve → summary → relevance → study path → **generate lessons** → **interactive slide deck** → **quiz + grade** → **retake** → results.

**Core insight:** The AI is not the source of truth — the uploaded documents are. The system transforms proprietary, unseen, or dense documents into scaffolded, gamified learning pathways. RAG grounds every generated lesson and quiz in the user's own materials, enabling knowledge domains that no public AI was trained on.

---

## 1. Project Setup

### Must Do

- [x] Create GitHub repository: `study-and-learn`
- [x] Add `README.md` with project overview and setup instructions
- [x] Add `SRS.md`
- [x] Add `TODO.md`
- [x] Add `DESIGN_AND_TESTING.md`
- [x] Add `.gitignore`
- [x] Add Python virtual environment instructions
- [x] Add `requirements.txt`
- [x] Create initial Flask app skeleton
- [x] Create `tests/` directory
- [x] Add first basic pytest test
- [x] Add GitHub Actions workflow for tests

---

## 2. Public Static Task Board

- [x] Create `task-board-v1/` folder (separate public repo: https://github.com/stephen-cpe/task-board-v1/)
- [x] Create `task-board-v1/index.html`
- [x] Create `task-board-v1/assets/css/styles.css`
- [x] Create `task-board-v1/assets/js/app.js` (rendering) + `task-board-v1/assets/js/data.js` (CONFIG + SNAPSHOTS data)
- [x] Publish via GitHub Pages
- [x] Add public task board link to `README.md`

---

## 3. Sprint Plan

### Sprint 1: Foundation and Upload Workflow ✅ COMPLETE

**Goal:** Create the basic app foundation and let a user enter a learning goal and upload documents.

**User Stories:** US-001, US-002, US-003, US-004, US-005, US-006

**Tasks:**
- [x] Build Flask project structure
- [x] Add homepage
- [x] Add learning goal input form
- [x] Add document upload form
- [x] Add file type validation
- [x] Add upload storage folder
- [x] Add success/error flash messages
- [x] Add Bootstrap layout
- [x] Add initial retro styling (cyberpunk theme, Retrograde Bold, BoldPixels fonts)
- [x] Add unit tests for file validation
- [x] Add smoke test for homepage
- [x] Update task board

---

### Sprint 2: Document Processing, RAG, and AI Analysis ✅ COMPLETE

**Goal:** Implement RAG pipeline (chunking, vector storage, retrieval), support multi-file uploads (≤5), and generate AI summary, relevance check, and study path.

**User Stories:** US-007, US-008, US-009, US-010, US-011

**Tasks:**
- [x] Integrate LangChain `RecursiveCharacterTextSplitter` for document chunking
- [x] Set up persistent ChromaDB client service (`./data/chroma_db`)
- [x] Implement chunk → embed → store pipeline per uploaded file
- [x] Implement `.txt`, `.md`, `.pdf`, `.docx` parsers
- [x] Implement similarity search & context builder for AI prompts
- [x] Update `/upload` route to accept `request.files.getlist()` (max 5 files)
- [x] Add multi-file session handling & collection naming
- [x] Configure dual Ollama model env vars (OLLAMA_MODEL + OLLAMA_EMBEDDING_MODEL)
- [x] Create AI client wrapper for Ollama with `AI_MOCK` fallback
- [x] Create summary prompt template + generation service
- [x] Create relevance check prompt template + label/explanation/missing-material
- [x] Create curriculum-generation prompt → module list with effort estimates
- [x] Display summary, relevance, and study path on results page
- [x] Add markdown rendering (marked.js) for AI outputs
- [x] Add unit tests for chunking, vector storage, all AI services
- [x] Add mocked RAG/AI tests for CI
- [x] Add end-to-end workflow integration test

---

### Sprint 3: Interactive Lessons Generation ✅ COMPLETE

**Goal:** Implement the full interactive lesson generation loop — slide-based lessons with inline checkpoints, final quiz per module, grading with pass/fail gating, and retake with fresh questions.

**User Stories:** US-012, US-013, US-014, US-015, US-016, US-017

**Tasks:**
- [x] Create `src/services/lesson_generator.py` (title/content/example/summary slide types, RAG-grounded)
- [x] Create `src/services/quiz_generator.py` (mcq, true_false, multi_select, cloze_dropdown question types)
- [x] Add `POST /generate-lessons` — loop over modules, sequential generation with loading UI
- [x] Add `GET /lessons` — module list page with progress bar, gated locks, score badges
- [x] Add `GET /lessons/<i>` — custom CSS/JS slide deck rendering lesson slides + checkpoints + quiz
- [x] Implement inline checkpoint slides (block advance until answered, show correct/incorrect)
- [x] Implement final quiz form with all 4 question types rendered interactively
- [x] Add `POST /lessons/<i>/grade` — AJAX endpoint, instant grading, per-question feedback
- [x] Add `POST /lessons/<i>/retake` — regenerate quiz + checkpoints, reset attempt state
- [x] Implement gated progression (must pass module N at ≥80% to unlock N+1)
- [x] Add final results slide with score circle, pass/fail verdict, retake button
- [x] Consolidate learning goal + file upload into single unified form (`POST /process`)
- [x] Improve results page visual hierarchy (timeline, relevance dots, accent button)
- [x] Add server-side session storage (Flask-Session + cachelib FileSystemCache)
- [x] Vendor fonts (Retrograde Bold, BoldPixels) for slide deck retro theming
- [x] Write unit tests for lesson_generator + quiz_generator (17 new tests)
- [x] Run full test suite — 45+ tests passing

---

### Sprint 4: UX Polish, Mascot, and Quality Improvements ✅ COMPLETE

**Goal:** Polish the retro experience, integrate mascot into UI, improve loading UX, fix bugs, and tune prompts for better lesson output.

**User Stories:** US-018, US-019, US-020, US-021, US-022

**Tasks:**
- [x] Integrate mascot (`mascot-robot.png`) into bottom-right corner of UI (index + results pages)
- [x] Add click-to-talk mascot with random encouraging messages
- [x] Add mascot idle message on interval timer
- [x] Extract all inline JS from templates into `app.js`
- [x] Consolidate study-and-learn.js (deck class) + app.js (logic)
- [x] Rename `run.py` → `app.py` per user convention
- [x] Rename `app/` package → `src/`
- [x] Add cloud model toggle via `AI_BACKEND=cloud` env var (env-var-driven backend dispatch in `ai_client.py`; the old uncomment-an-import pattern has been removed)
- [x] Fix title slide text overflow (long titles breaking out of card)
- [x] Fix results-detail font size (inheriting 42px base)
- [x] Fix score-circle overflow (100% text breaking out of circle)
- [x] Fix file list overflow (long filenames as single line)
- [x] Fix markdown rendering (asterisks/bold not rendering in lesson slides + results)
- [x] Fix suggested materials list (asterisk bullets not rendered)
- [x] Add console debug dump for lesson answers (F12 testing)
- [x] Fix fill-in-the-blank: one-word-only input per blank, inline placement, per-blank grading
- [x] Replace full-screen loading overlay on results page with background progress bar in mascot speech bubble
- [x] Add stage-by-stage progress reporting during lesson generation
- [x] Improve lesson and quiz prompt templates (active-working mascot messages)
- [x] Merge progress indicator into mascot speech bubble (non-overlapping, persistent visibility)
- [x] Replace full-screen loading overlay on `/process` route with non-blocking background progress indicator
- [x] Polish responsive layout for slide deck on smaller screens [SCOPE: OUT — mobile/responsive layout removed per SRS product owner directive]
- [x] Update unit tests for progress tracker

**Sprint 4 Definition of Done:**
- Fill-in-the-blank uses one-word inline inputs with per-blank validation
- Loading UX on results page uses mascot speech bubble progress bar (persistent, non-overlapping)
- Mascot placed and interactive with funnier idle messages and progress-aware behavior
- Lesson generation progress visible through mascot (text + bar)
- All documentation updated to reflect current state

---

### Sprint 5: User Accounts & Session Persistence ✅ COMPLETE

**Goal:** Add learner accounts (Flask-Login + PostgreSQL), dashboard with progress tracking, max 3 active lessons gating, admin access control, and demo accounts.

**User Stories:** US-023, US-024, US-025, US-026, US-027, US-028, US-029, US-030, US-031

**Tasks:**
- [x] Purge all SQLite references; lock PostgreSQL-only (schemas, docs, configs, tests)
- [x] Extract lesson orchestrator, grader, and session repository seam (Phase 0.2 refactors)
- [x] Fix ai_client.py indirection (env AI_BACKEND) and add happy-path smoke test (Phase 0.3)
- [x] Integrate Flask-Login, Flask-SQLAlchemy, PostgreSQL only
- [x] Build sign-up, sign-in, logout routes and templates
- [x] Store user credentials securely (hashed passwords)
- [x] Build learner dashboard showing active lessons and completion status
- [x] Track completed vs abandoned/cancelled lessons
- [x] Enforce max 3 active lessons per user
- [x] Require abandon/cancel before creating new lesson when at limit
- [x] Create super admin role with per-user lesson generation toggle
- [x] Deny lesson generation by default for new registrations
- [x] Landing page shows access-denied message for unauthorized users
- [~] Seed demo accounts (Bob, Alice) with lesson generation access — superseded by init_db.sql seed (runtime seed-demo route removed in Sprint 8; see STATUS.md)
- [x] Allow public registration but auto-deny lesson access
- [x] Write unit and integration tests for auth flow
- [x] Update task board with sprint progress

**Sprint 5 Definition of Done:**
- Registration, login, logout working with Flask-Login
- Dashboard displays active lessons and progress
- Max 3 lesson limit enforced
- Admin can toggle user access
- Demo accounts (Bob, Alice) functional
- Tests cover auth routes and access control

---

### Sprint 6: OCR/Vision Integration & Global Content Deduplication ✅ COMPLETE

**Goal:** Integrate AI-powered OCR for scanned PDFs and images, implement global content-addressable deduplication, extend file type support, and transition to content-keyed multi-collection ChromaDB retrieval.

**User Stories:** US-032, US-033, US-034, US-035

**Tasks:**
- [x] Pull GLM-OCR model (local, 0.9B) for page-level text/table/figure OCR
- [x] Integrate pdf2image for PDF page-to-image rendering via Poppler
- [x] Implement DOCX embedded image extraction via python-docx inline shapes
- [x] Implement PPTX text extraction via python-pptx
- [x] Add `.docx`, `.pptx`, `.png`, `.jpg`, `.jpeg` to allowed extensions
- [x] Build `src/services/vision_parser.py` — OCR pipeline with file hashing, content registry, page rendering, and Qwen3.5 cloud figure descriptions
- [x] Add SHA-256 content-addressable deduplication via `ContentRegistry` DB model
- [x] Transition ChromaDB from session-keyed (`study_{uuid}`) to content-keyed (`doc_{hash[:59]}`) collections shared across users
- [x] Implement multi-collection retrieval with score-based merging (`retrieve_from_multiple_collections`)
- [x] Add metadata propagation to chunk storage (source_hash, content_type)
- [x] Extend progress tracking to 9 stages (added OCR scanning + figure analysis stages)
- [x] Add `force_local` parameter to `call_ollama` for OCR models with no cloud variant
- [x] Write 20 test cases in `tests/test_vision_parser.py` (all pass with `AI_MOCK=true`)
- [x] Write 5 additional parser tests (pptx, image, dedup)
- [x] Write 4 additional RAG tests (multi-collection retrieval, metadata)
- [x] Add `ollama pull glm-ocr` to README setup instructions
- [x] Run full test suite — 172 passing tests at Sprint 6 close (143 original + 29 new); suite has since grown to 427 tests by Sprint 8

**Sprint 6 Definition of Done:**
- OCR pipeline processes scanned PDFs with text/table/figure recognition
- DOCX embedded images and PPTX files extracted and processed
- Global content deduplication prevents redundant OCR/embedding for identical files
- Multi-collection retrieval merges results across all uploaded documents
- Progress bar shows 9 stages including OCR progress
- All new features gated behind env vars (OCR_FULL, OCR_FIGURE_DESCRIPTION, AI_MOCK)
- 172 tests passing at Sprint 6 close (suite is now 427 tests as of Sprint 8)
- README updated with OCR setup instructions

---

### Sprint 7: Polish, Mascot Animation, TTS & PDF Export ✅ COMPLETE

**Goal:** Add mascot animation frames, TTS narration, PDF export, session cleanup, source citations, difficulty selector, and sample demo document set.

**User Stories:** US-022, US-036, US-037, US-038, US-039, US-040, US-041

**Tasks:**
- [x] Add mascot basic animation frames (idle/waiting/done)
- [x] Display mascot state changes during loading operations
- [x] Expand mascot animations to 14/16/14 distinct frames per status with transparent background (idle 14@250ms, busy 16@140ms, happy 14@220ms; gear-orbit + chest-chase for busy, rising particles + bounce for happy) + 26 pytest tests
- [x] Add mascot error/failure state (mascot-error.gif, 14f @ 220ms, X-eyes + drooping bob + dimmed chest + red '!' banner + slow red/orange warning particles, base artwork preserved) + 11 pytest tests + template/JS/CSS wiring
- [x] Create proprietary demo document set (non-public, niche knowledge) — done (Sprint 8; documents kept privately outside the repo for the live demo)
- [x] Integrate Web Speech API or TTS library for lesson narration
- [x] Add TTS toggle button on slide deck (disabled by default)
- [x] Generate PDF from completed lesson slides and quiz results
- [x] Add PDF export button on completed lesson page (per-lesson granularity)
- [x] Remove `extracted_texts` from session after lessons generated
- [x] Add difficulty/age-level selector on upload form (Easy/Normal/Hard)
- [x] Inject difficulty level into lesson and quiz generation prompts
- [x] Link generated lesson content back to source PDF/document
- [x] Add citations showing which document a slide references (modal overlay)
- [x] Track abandoned lessons separately from completions (Dashboard tabs: Active/Completed/Cancelled)
- [x] Add Mark Complete lifecycle action (user-triggered when 100% passed)
- [x] Add Delete action for completed/cancelled paths (irreversibility warning)
- [x] Test cloud ChromaDB (optional parallel track)
- [x] Test cloud AI model providers (optional parallel track)

**Sprint 7 Definition of Done:**
- Mascot animation frames working (idle/waiting/done states)
- Sample demo documents created and tested end-to-end
- TTS functional (opt-in)
- PDF export working for completed lessons
- Session bloat fixed (extracted_texts cleaned up)
- Difficulty selector working with age-appropriate output differences
- Source document citations visible on slides
- Cloud deployment dependencies identified and tested

**Sprint 7 Status (as of 2026-06-14):** Core features complete (TTS narration, difficulty
selector, session cleanup, cloze_dropdown, checkpoint variety, session resume, humor
injection, narration scripts). The badge/trophy system was deferred out of the capstone
timeline (moved to Post-Capstone; see §5 Scope-Creep Ladder). The demo document set was
deferred to Sprint 8 and completed there (kept privately outside the repo for the live demo).

---

### Sprint 8: Final Deployment & Capstone Demo 🟡 CURRENT FOCUS

**Goal:** Deploy to a cloud VPS (DigitalOcean), finalize documentation, record demo, fix remaining bugs, and submit capstone.

**User Stories:** US-042, US-043, US-044, US-045

**Bug Fixes & Defects (Priority: High — Fix Before Demo):**
- [x] TTS bug-fix items #1-#11 (see STATUS.md lines 16-72 for the full list; covers path_id transport, audio-route fallback, retake redirect UX, flattened deck layout + narration regen, background TTS worker idempotency/failure-resilience/generation-status polling, checkpoint-before-narration ordering, removal of auto-advance after Quick Check, cache→DB redirect signal, 2-hour hard-timeout-no-redirect, two-poll parallel design)
- [x] Fix TTS 404 bug — path_id not propagated to lesson deck for first-time path (Task 11)
- [ ] General QA pass: run full manual smoke test on all user flows
- [ ] Fix any additional defects discovered during QA pass

**UX/UI Polish:**
- [ ] General UX/UI refinement, visual consistency pass
- [ ] Review and polish settings page (TTS speaker preview, difficulty preview)

**Demo & Content:**
- [x] Create proprietary demo document set (non-public, niche knowledge domain) — done (Sprint 8; documents kept privately outside the repo for the live demo)
- [ ] Write demo script covering full workflow (goal → upload → results → lessons → quiz → grade → retake)

**Deployment:**
- [x] Deploy web app to DigitalOcean (4 vCPU / 8 GB RAM / 160 GB disk, $48/month)
- [x] Configure production environment variables (AI_BACKEND=cloud, CHROMA_DB=cloud, DATABASE_URL, SECRET_KEY)
- [x] Gunicorn (gthread, 1 worker, 8 threads) + Nginx reverse proxy + systemd + Let's Encrypt SSL + DuckDNS
- [x] CI/CD pipeline (test → deploy → smoke-test) via GitHub Actions
- [x] GET /health endpoint for smoke-test
- [x] Versioned deployment configs in deploy/ directory (nginx.conf, study-and-learn.service, gunicorn.conf.py)
- [x] DigitalOcean deployment guide (digitalocean-deployment-guide.md)
- [ ] Verify all routes and features work in production
- [x] Document AI swap path in README (Ollama local → cloud API for deployment)

**Documentation & Submission:**
- [ ] Complete DESIGN_AND_TESTING.md final review for capstone rubric alignment
- [ ] Ensure AI_AGENT_PROTOCOL.md reflects final Sprint 8 state
- [ ] Update task board to reflect final sprint status
- [ ] Add demo link to README
- [ ] Run full CI pipeline one final time
- [ ] Confirm GitHub repo access for grader
- [ ] Confirm task board access
- [ ] Final review of all documentation against rubric
- [ ] Record walkthrough of the app (15–20 minutes)
- [ ] Submit capstone project

**Sprint 8 Definition of Done:**
- Deployed app link works (or AI_MOCK=true demo is documented and functional)
- Task board link works
- Repository is documented and accessible
- DESIGN_AND_TESTING.md is complete and up to date
- Demo script recorded and submission-ready
- All Sprint 8 bug fixes and UX polish items resolved
- Capstone submitted

---

## 4. MVP Feature Backlog

### Core MVP (Implemented ✅)

- [x] Learning goal form
- [x] Document upload (≤5 files)
- [x] File validation
- [x] Text extraction (.txt, .md, .pdf, .docx, .pptx, .png, .jpg, .jpeg)
- [x] RAG pipeline (chunk → embed → store → retrieve)
- [x] AI summary generation
- [x] Relevance check (strong/partial/weak)
- [x] Study path generation (modules + effort)
- [x] Interactive slide-based lesson generation
- [x] Mixed-type quiz generation (4 question types: mcq, true_false, multi_select, cloze_dropdown)
- [x] Inline comprehension checkpoints
- [x] Instant quiz grading with feedback
- [x] Retake with fresh questions
- [x] Gated module progression (80% threshold)
- [x] Custom CSS/JS slide deck (retro themed)
- [x] Server-side session storage (Flask-Session + cachelib)
- [x] Results page with improved hierarchy
- [x] Lesson listing page with progress bar
- [x] Markdown rendering for AI outputs
- [x] AI-powered OCR/vision (GLM-OCR local + Qwen3.5 cloud)
- [x] Content-addressable global deduplication
- [x] Multi-collection ChromaDB retrieval
- [x] 427 automated tests (Sprint 8 active; suite rebuilt from Tasks 1–11 + deployment bug fixes)
- [x] GitHub Actions CI
- [x] Static task board
- [x] Design/testing document

### Should-Have Polish (Complete)

- [x] Retro theme with custom pixel fonts
- [x] Bootstrap 5 layout with cyberpunk styling
- [x] App logo and title treatment
- [x] Flash messages for feedback
- [x] Mascot placed in bottom-right corner with click-to-talk
- [x] Cloud model testing infrastructure (`ai_client_cloud.py`)
- [x] JS refactored into external `app.js`
- [x] Package renamed `app/` → `src/`
- [x] Fill-in-the-blank one-word-per-input fix (Sprint 4)
- [x] Background progress indicators in mascot speech bubble (Sprint 4)
- [x] Non-blocking loading indicator on `/process` route (Sprint 4)
- [x] Responsive slide deck layout [SCOPE: OUT — mobile/responsive layout removed per SRS product owner directive]
- [x] TTS narration (Edge-TTS, opt-in, AI narration scripts)
- [x] Difficulty selector (Easy/Normal/Hard)
- [x] Session save/resume (deck position)
- [x] Sample demo documents for consistent presentation — done (Sprint 8; kept privately outside the repo for the live demo)

---

## 5. Scope-Creep Ladder

### Implemented ✅
- [x] Retro colors/fonts/cyberpunk theme
- [x] Better prompt templates
- [x] Static mascot image with progress-aware speech bubble
- [x] Simple quiz generation (4 question types: mcq, true_false, multi_select, cloze_dropdown)
- [x] Slide-style lesson viewer (custom CSS/JS)
- [x] Editable generated summary
- [x] Saved/loaded generated outputs in session
- [x] Export results as HTML (rendered on results page)
- [x] Gated module progression with pass/fail
- [x] One-word fill-in-the-blank inputs with per-blank grading
- [x] Background progress reporting via mascot speech bubble

### Completed (Sprint 4–7)
- [x] Non-blocking progress on `/process` route (Sprint 4)
- [x] Lesson/quiz prompt engineering refinement (Sprint 4)
- [x] User accounts (Flask-Login + PostgreSQL) (Sprint 5)
- [x] Learner dashboard with progress tracking (Sprint 5)
- [x] Max 3 active lessons gating (Sprint 5)
- [x] Admin access control (Sprint 5)
- [x] UI and UX refinement (Sprint 6)
- [x] Defect remediation and performance optimization (Sprint 6)
- [x] Expanded test coverage (Sprint 6)
- [x] OCR/Vision integration with content deduplication (Sprint 6)
- [x] Mascot animation frames (Sprint 7)
- [x] Proprietary demo document set (Sprint 7 — deferred to Sprint 8) — done (Sprint 8; kept privately outside the repo for the live demo)
- [x] Difficulty/age-level selector (Easy/Normal/Hard) (Sprint 7)
- [x] TTS narration (opt-in) (Sprint 7)
- [x] Session cleanup (Sprint 7)
- [x] Source document citations in lessons (Sprint 7)

### Sprint 8 (In Progress)
- [ ] Deployment, demo recording, and capstone submission (Sprint 8)

### Post-Capstone
- [ ] Badge/trophy system for completed lessons (moved out of the capstone timeline; nice-to-have)
- [ ] Extended file type support (.html, .odt)
- [ ] YouTube/video transcript integration
- [ ] External learning resource search
- [ ] Learner profile adaptation

### Very Hard / Post-Capstone
- [ ] Social features (friends, chat, share lessons)
- [ ] Full offline mode (C/C++ rewrite without Ollama)
- [ ] Adaptive difficulty based on performance
- [ ] Companion that reacts to progress
- [ ] Full teacher/admin content management workflow

---

## 6. Testing TODO

### Unit Tests
- [x] Allowed file extensions
- [x] Rejected file extensions
- [x] Text parser for .txt, .md
- [x] Parser error handling (empty, nonexistent)
- [x] Summary prompt builder
- [x] Relevance label parser
- [x] Curriculum output parser
- [x] AI client mock mode
- [x] Chunking logic validation
- [x] Vector store imports
- [x] RAG context builder
- [x] Lesson generator (mock, empty inputs, retriever, validation, fallback)
- [x] Quiz generator (mock, empty, retriever, checkpoints, validation, fallbacks, type mix)

### Integration Tests
- [x] Homepage route
- [x] Process route with valid data
- [x] Process route with empty goal
- [x] Process route with no files
- [x] Process route with invalid file type
- [x] Process route exceeding max files
- [x] Full mocked workflow
- [x] Generate lessons flow
- [x] Lesson deck route

### Added (Sprint 4)
- [x] Fill-in-the-blank one-word validation tests (validation, fallback, integration)
- [x] Grade route test with fill_blank_answers dict (case-insensitive, one-word rejection)
- [x] Progress tracker unit tests (stages, create/update/get/complete/cleanup, bounds)
- [x] Progress integration tests (endpoint, generate-lessons progress flow)

### Added (Sprint 5–6)
- [x] Auth route tests (Sprint 5)
- [x] User model tests (Sprint 5)
- [x] Dashboard route and access control tests (Sprint 5)
- [x] Lesson repository unit and integration tests (Sprint 5)
- [x] Admin role tests (Sprint 5)
- [x] seed-demo endpoint — removed (redundant; init_db.sql handles seeding; see STATUS.md Sprint 8)
- [x] OCR/vision parser tests (Sprint 6 — 20 tests)
- [x] Parser expansion tests (Sprint 6 — 5 tests for pptx, image, dedup)
- [x] RAG service expansion tests (Sprint 6 — 4 tests for multi-collection, metadata)
- [x] Retake route test (quiz regeneration, state reset)

### Added (Sprint 7)
- [x] TTS service tests (5 tests: voice mapping, manifest, empty text, cleanup)
- [x] Narration script tests (4 tests: structure, username, fallback, outro)
- [x] cloze_dropdown validation and grading tests
- [x] Checkpoint variety tests (mcq/true_false/cloze_dropdown)
- [x] Humor and difficulty prompt injection tests
- [x] Route-level TTS flag tests and graceful failure
- [x] Save-position and audio route tests
- [x] extracted_texts cleanup test

### To Add (Sprint 8)
- [x] End-to-end deployment smoke test (GET /health endpoint for CI/CD smoke-test job)
- [x] TTS 404 regression test (path_id re-resolved after first save) — added in Task 11
- [x] GET /login redirect fix test (was returning None, crashing Gunicorn)
- [x] TTS asyncgens drain test (loop.shutdown_asyncgens before loop.close to prevent FD leak)

### Manual Demo Tests
- [ ] Demo document uploads successfully
- [ ] Summary appears with markdown rendering
- [ ] Relevance result appears with colored indicator
- [ ] Study path timeline displays
- [ ] Generate Lessons button works
- [ ] Slide deck renders with retro fonts
- [ ] Checkpoints block advance until answered
- [ ] Quiz grading returns score and feedback
- [ ] Retake regenerates questions
- [ ] Module gating enforces progression
