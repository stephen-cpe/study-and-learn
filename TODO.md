# TODO / Product Backlog
# Study-and-Learn

**Purpose:** This document organizes the capstone work into MVP tasks, user stories, sprints, stretch goals, and submission requirements.

---

## 0. Guiding Rule

Build the smallest working version first:

> Learning goal → document upload → text extraction → summary → relevance check → study path → results page.

Everything else is secondary until this workflow works end-to-end.

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

### Suggested Acceptance Criteria

- App can run locally.
- Tests run locally with `pytest -v tests/`.
- GitHub Actions runs tests on push or pull request.
- Documentation files exist in the repository.

---

## 2. Public Static Task Board

### Must Do

- [x] Create `task-board/` folder
- [x] Create `task-board/index.html`
- [x] Create `task-board/styles.css`
- [x] Create `task-board/app.js`
- [x] Add project overview section
- [x] Add sprint summary section
- [x] Add user stories table
- [x] Add task status columns
- [x] Add capstone deliverables checklist
- [x] Publish via GitHub Pages
- [x] Add public task board link to `README.md`

### Suggested Acceptance Criteria

- Task board is publicly viewable.
- Board shows sprint progress.
- Board shows user stories and task status.
- Board is simple enough to update manually.

---

## 3. Sprint Plan

## Sprint 1: Foundation and Upload Workflow

### Goal

Create the basic app foundation and let a user enter a learning goal and upload documents.

### User Stories

- US-001: Developer can run the app locally.
- US-002: CI runs basic automated tests.
- US-003: Reviewer can view public task board.
- US-004: Learner can enter a learning goal.
- US-005: Learner can upload study materials.
- US-006: Learner can see upload status.

### Tasks

- [ ] Build Flask project structure
- [ ] Add homepage
- [ ] Add learning goal input form
- [ ] Add document upload form
- [ ] Add file type validation
- [ ] Add upload storage folder
- [ ] Add upload metadata handling
- [ ] Add success/error flash messages
- [ ] Add Bootstrap layout
- [ ] Add initial retro styling
- [ ] Add unit tests for file validation
- [ ] Add smoke test for homepage
- [ ] Update task board
- [ ] Record short sprint demo for internal review

### Sprint 1 Definition of Done

- App runs locally.
- User can enter a goal.
- User can upload supported file types.
- Unsupported files are rejected.
- Basic tests pass.
- Static task board is published or ready to publish.

---

## Sprint 2: Document Processing and AI Summary

### Goal

Extract text from uploaded documents and generate a useful summary.

### User Stories

- US-007: Learner gets document text extracted for analysis.
- US-008: Parser errors are handled clearly.
- US-009: Learner receives a summary of uploaded materials.

### Tasks

- [ ] Implement `.txt` parser
- [ ] Implement `.md` parser
- [ ] Implement `.pdf` parser
- [ ] Implement `.docx` parser
- [ ] Decide whether `.html` and `.odt` are Sprint 2 or later
- [ ] Create document parser service
- [ ] Add extracted text preview or processing confirmation
- [ ] Create AI client wrapper for Ollama
- [ ] Create summary prompt template
- [ ] Generate summary from extracted text
- [ ] Display summary on results page
- [ ] Add fallback mocked AI client for tests
- [ ] Add parser tests
- [ ] Add mocked summary tests
- [ ] Update task board
- [ ] Record sprint demo

### Sprint 2 Definition of Done

- At least three file types can be parsed.
- Summary generation works with a small sample document.
- AI failures are handled gracefully.
- Tests cover parser and summary workflow basics.

---

## Sprint 3: Relevance Check and Study Path Generation

### Goal

Complete the core learning workflow.

### User Stories

- US-010: Learner sees whether documents match the learning goal.
- US-011: Learner receives a structured study path.
- US-012: Learner experiences a simple guided workflow.
- US-014: Reviewer can see full workflow in demo.

### Tasks

- [ ] Create relevance-check prompt
- [ ] Return relevance label: strong / partial / weak
- [ ] Return relevance explanation
- [ ] Add missing-material suggestions
- [ ] Create curriculum-generation prompt
- [ ] Generate module list
- [ ] Generate lesson list
- [ ] Add estimated effort per module
- [ ] Format study path clearly in UI
- [ ] Store generated outputs
- [ ] Add tests for relevance label parsing
- [ ] Add tests for curriculum output structure
- [ ] Add end-to-end mocked workflow test
- [ ] Polish retro UI
- [ ] Add simple mascot placeholder
- [ ] Update task board
- [ ] Record sprint demo

### Sprint 3 Definition of Done

- Full MVP workflow works end-to-end.
- User can upload documents and receive summary, relevance result, and study path.
- Tests pass.
- Demo script can show the full workflow.

---

## Sprint 4: Polish, Documentation, Deployment

### Goal

Prepare for capstone submission and public demonstration.

### User Stories

- US-013: Learner sees a friendly motivating interface.
- US-014: Reviewer can understand and evaluate the project.

### Tasks

- [ ] Improve results page layout
- [ ] Add demo sample documents
- [ ] Improve README setup instructions
- [ ] Complete `DESIGN_AND_TESTING.md`
- [ ] Document architecture decisions
- [ ] Document AI tooling usage
- [ ] Document test strategy and test results
- [ ] Document deployment choice
- [ ] Deploy web app
- [ ] Add deployed app link to README
- [ ] Confirm GitHub repo access
- [ ] Confirm task board access
- [ ] Prepare final demo script
- [ ] Record final 15–20 minute demo/presentation
- [ ] Verify all submission links are stable

### Sprint 4 Definition of Done

- Deployed app link works.
- Task board link works.
- Repository is documented.
- Design/testing document is complete.
- Final demo can be recorded cleanly.

---

## 4. MVP Feature Backlog

### Core MVP

- [ ] Learning goal form
- [ ] Document upload
- [ ] File validation
- [ ] Text extraction
- [ ] AI summary
- [ ] Relevance check
- [ ] Study path generation
- [ ] Results page
- [ ] Basic persistence
- [ ] Tests
- [ ] CI
- [ ] Deployment
- [ ] Static task board
- [ ] Design/testing document

### Should-Have Polish

- [ ] Retro theme
- [ ] Mascot placeholder
- [ ] Better error messages
- [ ] Output cards
- [ ] Sample demo documents
- [ ] Loading/progress UI
- [ ] Responsive layout
- [ ] Simple app logo/title treatment

---

## 5. Scope-Creep Ladder

Ranked from easiest to hardest. These are not official MVP unless moved into a sprint.

### Easy

- [ ] Static mascot image
- [ ] Better retro colors/fonts
- [ ] Motivational text snippets
- [ ] Better prompt templates
- [ ] Export study path as Markdown
- [ ] Add example goal buttons

### Moderate

- [ ] Editable generated summary
- [ ] Editable generated study path
- [ ] Simple quiz generation
- [ ] Basic progress checklist
- [ ] Save/load previous generated plans
- [ ] Export results as HTML
- [ ] Add difficulty level selector
- [ ] Add admin review page

### Hard

- [ ] Embeddings and retrieval with pgvector or ChromaDB
- [ ] More robust chunking and source referencing
- [ ] OCR for scanned PDFs
- [ ] Better document metadata extraction
- [ ] Multi-document topic map
- [ ] Slide-style lesson viewer
- [ ] Learner profile adaptation

### Very Hard / Future

- [ ] YouTube integration
- [ ] External learning resource search
- [ ] AI-generated slide decks
- [ ] AI-generated subtitles
- [ ] AI-generated TTS narration
- [ ] Adaptive weekly planner
- [ ] Multi-user accounts
- [ ] Authentication
- [ ] Companion that reacts to progress
- [ ] Full teacher/admin content management workflow

---

## 6. AI Tooling Plan

### Allowed / Intended Use

- [ ] Use AI tools to help draft specifications
- [ ] Use AI tools to generate code suggestions
- [ ] Use AI tools to create tests
- [ ] Use AI tools to review bugs
- [ ] Use AI tools to explain architecture tradeoffs
- [ ] Use AI tools to assist with documentation

### Guardrails

- [ ] Keep SRS and TODO updated before major implementation
- [ ] Review generated code before committing
- [ ] Write or verify tests for AI-generated code
- [ ] Commit in small, understandable increments
- [ ] Document AI tooling use in design/testing document
- [ ] Do not commit secrets, private documents, or sensitive uploads

---

## 7. Testing TODO

### Unit Tests

- [ ] Test allowed file extensions
- [ ] Test rejected file extensions
- [ ] Test text parser for `.txt`
- [ ] Test text parser for `.md`
- [ ] Test parser error handling
- [ ] Test summary prompt builder
- [ ] Test relevance label parser
- [ ] Test curriculum output parser

### Integration Tests

- [ ] Test homepage route
- [ ] Test goal submission route
- [ ] Test upload route with valid file
- [ ] Test upload route with invalid file
- [ ] Test mocked AI summary route
- [ ] Test mocked full workflow

### Manual Demo Tests

- [ ] Demo document uploads successfully
- [ ] Summary appears
- [ ] Relevance result appears
- [ ] Study path appears
- [ ] App handles bad file upload correctly
- [ ] App works in deployed environment

---

## 8. Documentation TODO

- [ ] README project overview
- [ ] README local setup
- [ ] README test instructions
- [ ] README deployment link
- [ ] README task board link
- [ ] SRS finalized
- [ ] TODO/backlog finalized
- [ ] Design and testing document
- [ ] Architecture diagram or text explanation
- [ ] AI tooling explanation
- [ ] Sprint summaries
- [ ] Final demo script
