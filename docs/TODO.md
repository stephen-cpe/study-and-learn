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

**Goal:** Polish the retro experience, add mascot interactions, improve loading UX, implement difficulty toggle, and research model/quality improvements for better lesson output.

**User Stories:** US-018, US-019, US-020, US-021, US-022

**Tasks:**
- [ ] Replace full-screen loading overlay with background processing + progress bar / stage indicator
- [ ] Add stage-by-stage progress reporting during lesson generation (e.g., "Generating slides for Module 2 of 5...")
- [ ] Create retro mascot animation frames (idle, waiting/loading, done/success, retry/encourage states)
- [ ] Integrate mascot (`src/static/images/mascot-robot.png`) into UI with simple interactions
- [ ] Research optimal Ollama model for lesson/quiz quality vs speed on target hardware (6GB VRAM)
- [ ] Evaluate and document quality comparison: qwen3:1.7b vs gemma3:4b vs granite4.1:3b for lesson generation
- [ ] Add difficulty level selector (Easy: 10–11 yrs, Moderate: 12–13 yrs, Hard: 14–15 yrs)
- [ ] Adjust lesson/quiz prompts based on selected difficulty level
- [ ] Improve lesson and quiz prompt templates for better pedagogical quality
- [ ] Add loading feedback that is entertaining/retro-themed during long operations
- [ ] Polish responsive layout for slide deck on smaller screens
- [ ] Update unit tests for new prompt logic and difficulty toggle
- [ ] Update task board with sprint progress
- [ ] Record sprint demo

**Sprint 4 Definition of Done:**
- Loading UX uses background progress indicator instead of full-screen block
- Mascot displays idle/waiting/done animation states
- Difficulty toggle functional and reflected in generated content
- Model research documented with recommendation
- Lesson/quiz quality measurably improved over Sprint 3 baseline

---

### Sprint 5: Deployment & Demo Prep ⬜ FUTURE

**Goal:** Deploy to free-tier host, finalize documentation, prepare demo script, record 15–20 min presentation.

**User Stories:** US-014 (extended)

**Tasks:**
- [ ] Finalize README with complete setup and deployment instructions
- [ ] Complete `DESIGN_AND_TESTING.md` with all ADRs and test results
- [ ] Deploy web app (Render or Railway free tier)
- [ ] Configure deployment environment variables for model/API
- [ ] Add deployed app link to README
- [ ] Confirm GitHub repo access for grader
- [ ] Confirm task board access
- [ ] Prepare final demo script (goal → upload → results → generate lessons → slide deck → quiz → grade → retake)
- [ ] Record final 15–20 minute demo/presentation
- [ ] Verify all submission links are stable
- [ ] Final review of all documentation against rubric

**Sprint 5 Definition of Done:**
- Deployed app link works
- Task board link works
- Repository is documented and accessible
- Design/testing document is complete
- Final demo recorded and submission-ready

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
- [ ] Retro mascot with animation frames (Sprint 4)
- [ ] Background progress indicators (Sprint 4)
- [ ] Difficulty level selector (Sprint 4)
- [ ] Model quality/speed research (Sprint 4)
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

### Upcoming (Sprint 4–5)
- [ ] Mascot animation frames with idle/waiting/done states
- [ ] Difficulty level selector (Easy/Moderate/Hard)
- [ ] Background progress reporting during generation
- [ ] Model evaluation and recommendation research
- [ ] Lesson/quiz prompt engineering refinement

### Hard / Future
- [ ] OCR for scanned PDFs
- [ ] YouTube integration
- [ ] External learning resource search
- [ ] Short-answer AI grading
- [ ] Slide deck export (PDF, PPTX)
- [ ] Learner profile adaptation
- [ ] Spaced repetition scheduling

### Very Hard / Post-Capstone
- [ ] Multi-user accounts and authentication
- [ ] AI-generated TTS narration
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

### To Add (Sprint 4)
- [ ] Grade route test (AJAX response, score calculation, pass/fail)
- [ ] Retake route test (quiz regeneration, state reset)
- [ ] Difficulty toggle prompt adjustment tests

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
