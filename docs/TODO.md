# TODO / Product Backlog
# Study-and-Learn

**Purpose:** This document organizes the capstone work into MVP tasks, user stories, sprints, stretch goals, and submission requirements.  
**Last updated:** May 2026

---

## 0. Guiding Rule

Build the smallest working version first, then iterate:

> Goal + upload → parse → chunk → embed → retrieve → summary → relevance → study path → **generate lessons** → **interactive slide deck** → **quiz + grade** → **retake** → results.

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

- [x] Create `task-board/` folder
- [x] Create `task-board/index.html`
- [x] Create `task-board/styles.css`
- [x] Create `task-board/app.js`
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
- [x] Create `src/services/quiz_generator.py` (mcq, true_false, multi_select, fill_blank question types)
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
- [x] Run full test suite — 45 tests passing

---

### Sprint 4: UX Polish, Mascot, and Quality Improvements ⬜ CURRENT

**Goal:** Polish the retro experience, integrate mascot into UI, improve loading UX, implement difficulty toggle, fix bugs, and tune prompts for better lesson output.

**User Stories:** US-018, US-019, US-020, US-021, US-022, US-025

**Tasks:**
- [x] Integrate mascot (`mascot-robot.png`) into bottom-right corner of UI (index + results pages)
- [x] Add click-to-talk mascot with random encouraging messages
- [x] Add mascot idle message on interval timer
- [x] Extract all inline JS from templates into `app.js`
- [x] Consolidate study-and-learn.js (deck class) + app.js (logic)
- [x] Rename `run.py` → `app.py` per user convention
- [x] Rename `app/` package → `src/`
- [x] Add cloud model toggle via `ai_client_cloud.py` import pattern
- [x] Fix title slide text overflow (long titles breaking out of card)
- [x] Fix results-detail font size (inheriting 42px base)
- [x] Fix score-circle overflow (100% text breaking out of circle)
- [x] Fix file list overflow (long filenames as single line)
- [x] Fix markdown rendering (asterisks/bold not rendering in lesson slides + results)
- [x] Fix suggested materials list (asterisk bullets not rendered)
- [x] Add console debug dump for lesson answers (F12 testing)
- [ ] Fix fill-in-the-blank: one-word-only input per blank, inline placement, per-blank grading
- [ ] Replace full-screen loading overlay with background processing + progress bar / stage indicator
- [ ] Add stage-by-stage progress reporting during lesson generation
- [ ] Add difficulty level selector (Easy: 10–11 yrs, Moderate: 12–13 yrs, Hard: 14–15 yrs)
- [ ] Adjust lesson/quiz prompts based on selected difficulty level
- [ ] Improve lesson and quiz prompt templates for better pedagogical quality
- [ ] Polish responsive layout for slide deck on smaller screens
- [ ] Update unit tests for new prompt logic and difficulty toggle

**Sprint 4 Definition of Done:**
- Fill-in-the-blank uses one-word inline inputs with per-blank validation
- Loading UX uses background progress indicator
- Mascot placed and interactive (animation frames deferred)
- Difficulty toggle functional and reflected in generated content
- Lesson/quiz quality measurably improved over Sprint 3 baseline

---

### Sprint 5: User Accounts & Session Persistence ⬜ FUTURE

**Goal:** Add learner accounts (Flask-Login + PostgreSQL), dashboard with progress tracking, max 3 active lessons gating, admin access control, and demo accounts.

**User Stories:** US-027, US-028, US-029, US-030, US-031

**Tasks:**
- [ ] Integrate Flask-Login, Flask-SQLAlchemy, PostgreSQL (SQLite for local demo)
- [ ] Build sign-up, sign-in, logout routes and templates
- [ ] Store user credentials securely (hashed passwords)
- [ ] Build learner dashboard showing active lessons and completion status
- [ ] Track completed vs abandoned/cancelled lessons
- [ ] Enforce max 3 active lessons per user
- [ ] Require abandon/cancel before creating new lesson when at limit
- [ ] Create super admin role with per-user lesson generation toggle
- [ ] Deny lesson generation by default for new registrations
- [ ] Landing page shows access-denied message for unauthorized users
- [ ] Seed demo accounts (Bob, Alice) with lesson generation access
- [ ] Allow public registration but auto-deny lesson access
- [ ] Write unit and integration tests for auth flow
- [ ] Update task board with sprint progress

**Sprint 5 Definition of Done:**
- Registration, login, logout working with Flask-Login
- Dashboard displays active lessons and progress
- Max 3 lesson limit enforced
- Admin can toggle user access
- Demo accounts (Bob, Alice) functional
- Tests cover auth routes and access control

---

### Sprint 6: Polish, Maintenance & Enhancement ⬜ FUTURE

**Goal:** Stabilize Sprint 5 work, add refinements, fix bugs, and enhance with TTS + PDF export.

**User Stories:** US-032, US-033, US-034, US-035

**Tasks:**
- [ ] Polish dashboard UI with mascot placeholder
- [ ] Add mascot basic animation frames (idle/waiting/done) — if feasible
- [ ] Display mascot state changes during loading operations
- [ ] Integrate Web Speech API or TTS library for lesson narration
- [ ] Add TTS toggle button on slide deck (disabled by default)
- [ ] Generate PDF from completed lesson slides and quiz results
- [ ] Add PDF export button on completed lesson page
- [ ] Remove `extracted_texts` from session after lessons generated
- [ ] Fix bugs discovered during Sprint 5 testing
- [ ] Run full test suite and maintain 45+ passing tests
- [ ] Update task board with sprint progress

**Sprint 6 Definition of Done:**
- Dashboard polished with mascot
- TTS functional (opt-in)
- PDF export working for completed lessons
- Session bloat fixed (extracted_texts cleaned up)
- All existing tests pass

---

### Sprint 7: Advanced Features & OCR ⬜ FUTURE

**Goal:** OCR for scanned documents, achievement badges, source document references, and cloud deployment preparation.

**User Stories:** US-036, US-037, US-038

**Tasks:**
- [ ] Integrate OCR engine (Tesseract or similar)
- [ ] Detect images in uploaded documents and run OCR analysis
- [ ] Feed OCR output into chunking pipeline after text extraction
- [ ] Design badge/trophy system for completed modules
- [ ] Track abandoned lessons separately from completions
- [ ] Display achievement badges on dashboard
- [ ] Link generated lesson content back to source PDF/document
- [ ] Add citations showing which document a slide references
- [ ] Test cloud ChromaDB (optional parallel track)
- [ ] Test cloud Ollama models (optional parallel track)
- [ ] Write tests for OCR integration
- [ ] Update task board with sprint progress

**Sprint 7 Definition of Done:**
- OCR pipeline processes scanned PDFs
- Badges displayed for completed lessons
- Source document references visible in lessons
- Cloud deployment dependencies identified and tested

---

### Sprint 8: Final Deployment & Demo ⬜ FUTURE

**Goal:** Deploy to free-tier host (Render or Railway), finalize documentation, prepare demo script, record 15-min presentation, and submit capstone.

**User Stories:** US-040, US-041, US-042, US-043

**Tasks:**
- [ ] Deploy web app to Render or Railway free tier
- [ ] Configure production environment variables
- [ ] Verify all routes and features work in production
- [ ] Finalize README with complete setup and deployment instructions
- [ ] Complete `DESIGN_AND_TESTING.md` with all ADRs and test results
- [ ] Ensure `AI_AGENT_PROTOCOL.md` is current
- [ ] Update task board to reflect final sprint status
- [ ] Write demo script covering full workflow (goal → upload → results → lessons → quiz → grade)
- [ ] Record 15-minute walkthrough of the app
- [ ] Add demo link to README
- [ ] Triage and fix any remaining production bugs
- [ ] Run full CI pipeline one final time
- [ ] Confirm GitHub repo access for grader
- [ ] Confirm task board access
- [ ] Final review of all documentation against rubric
- [ ] Submit capstone project

**Sprint 8 Definition of Done:**
- Deployed app link works
- Task board link works
- Repository is documented and accessible
- Design/testing document is complete
- Final demo recorded and submission-ready
- Capstone submitted

---

## 4. MVP Feature Backlog

### Core MVP (Implemented ✅)

- [x] Learning goal form
- [x] Document upload (≤5 files)
- [x] File validation
- [x] Text extraction (.txt, .md, .pdf, .docx)
- [x] RAG pipeline (chunk → embed → store → retrieve)
- [x] AI summary generation
- [x] Relevance check (strong/partial/weak)
- [x] Study path generation (modules + effort)
- [x] Interactive slide-based lesson generation
- [x] Mixed-type quiz generation (4 question types)
- [x] Inline comprehension checkpoints
- [x] Instant quiz grading with feedback
- [x] Retake with fresh questions
- [x] Gated module progression (80% threshold)
- [x] Custom CSS/JS slide deck (retro themed)
- [x] Server-side session storage (Flask-Session + cachelib)
- [x] Results page with improved hierarchy
- [x] Lesson listing page with progress bar
- [x] Markdown rendering for AI outputs
- [x] 45 automated tests
- [x] GitHub Actions CI
- [x] Static task board
- [x] Design/testing document

### Should-Have Polish (In Progress / Upcoming)

- [x] Retro theme with custom pixel fonts
- [x] Bootstrap 5 layout with cyberpunk styling
- [x] App logo and title treatment
- [x] Flash messages for feedback
- [x] Mascot placed in bottom-right corner with click-to-talk
- [x] Cloud model testing infrastructure (`ai_client_cloud.py`)
- [x] JS refactored into external `app.js`
- [x] Package renamed `app/` → `src/`
- [ ] Fill-in-the-blank one-word-per-input fix (Sprint 4)
- [ ] Background progress indicators (Sprint 4)
- [ ] Difficulty level selector (Sprint 4)
- [ ] Responsive slide deck layout
- [ ] Sample demo documents for consistent presentation

---

## 5. Scope-Creep Ladder

### Implemented ✅
- [x] Retro colors/fonts/cyberpunk theme
- [x] Better prompt templates
- [x] Static mascot image
- [x] Simple quiz generation (4 question types)
- [x] Slide-style lesson viewer (custom CSS/JS)
- [x] Editable generated summary
- [x] Saved/loaded generated outputs in session
- [x] Export results as HTML (rendered on results page)
- [x] Gated module progression with pass/fail

### Upcoming (Sprint 4–8)
- [ ] One-word fill-in-the-blank inputs with per-blank grading (Sprint 4)
- [ ] Background progress reporting during generation (Sprint 4)
- [ ] Difficulty level selector (Easy/Moderate/Hard) (Sprint 4)
- [ ] Lesson/quiz prompt engineering refinement (Sprint 4)
- [ ] User accounts (Flask-Login + PostgreSQL) (Sprint 5)
- [ ] Learner dashboard with progress tracking (Sprint 5)
- [ ] Max 3 active lessons gating (Sprint 5)
- [ ] Admin access control (Sprint 5)
- [ ] TTS narration (opt-in) (Sprint 6)
- [ ] PDF export for completed lessons (Sprint 6)
- [ ] Mascot animation frames (Sprint 6)
- [ ] OCR for scanned PDFs (Sprint 7)
- [ ] Badges/trophies for completed lessons (Sprint 7)
- [ ] Source document referencing in lessons (Sprint 7)
- [ ] Deployment, demo, and capstone submission (Sprint 8)

### Hard / Future
- [ ] YouTube/video transcript integration
- [ ] External learning resource search
- [ ] Short-answer AI grading
- [ ] Spaced repetition scheduling
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

### To Add (Sprint 4+)
- [ ] Fill-in-the-blank one-word validation tests
- [ ] Grade route test (AJAX response, score calculation, pass/fail)
- [ ] Retake route test (quiz regeneration, state reset)
- [ ] Difficulty toggle prompt adjustment tests
- [ ] Auth route tests (Sprint 5)

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
