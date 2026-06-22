# Software Requirements Specification (SRS)
# Study-and-Learn

**Version:** 1.4  
**Project type:** AI-assisted learning web application  
**Capstone track:** Software system / AI system  
**Repository name:** `study-and-learn`  
**Primary development approach:** Spec-Driven Development with AI tooling support  
**Last updated:** June 19, 2026

---

## 1. Introduction

### 1.1 Purpose

This Software Requirements Specification defines the initial scope, requirements, assumptions, constraints, and success criteria for **Study-and-Learn**, a capstone web application that helps learners convert uploaded study materials into a structured, manageable study path.

The document is intended to guide development, sprint planning, testing, documentation, and final capstone demonstration.

### 1.2 Product Vision

Study-and-Learn helps a learner answer the question:

> “I have materials and a learning goal. What should I study, in what order, and how much should I do each week?”

The system should reduce the friction of studying by turning documents into:
- a summary of the material,
- a relevance check against the learner’s goal,
- a structured study plan,
- bite-sized modules or lessons.

The product should feel simple, fun, addicting, guided, motivating, and approachable rather than like a complex AI chat tool.

### 1.3 Scope

The MVP is a web application that allows a learner or admin user to:

1. enter a learning goal and upload documents in a single unified form,
2. upload one or more supported study documents,
3. extract text from those documents using both traditional parsers and AI-powered OCR for images and scanned content,
4. generate an AI-assisted summary, relevance check, and recommended study path,
5. generate interactive slide-based lessons with inline comprehension checkpoints,
6. generate mixed-type quizzes (multiple choice, true/false, multi-select, cloze-dropdown) per module,
7. take quizzes and receive instant grading with per-question feedback,
8. retake lessons with freshly regenerated questions to avoid memorization,
9. progress through gated modules (must pass module N to unlock N+1),
10. view all results in a retro-themed guided web interface,
11. receive personalized AI-narrated audio lessons via opt-in TTS (Edge-TTS Neural voices),
12. generate lessons at a chosen difficulty level (Easy/Normal/Hard) with age-appropriate content complexity.

The MVP will **not** use a chat interface. The user interacts primarily through forms, buttons, and structured result pages.

### 1.4 Intended Users

Primary users:
- self-directed learners,
- students organizing study materials,
- teachers or tutors preparing study outlines,
- capstone evaluators reviewing the software artifact.

Initial target content areas:
- Company Onboarding Documents,
- Company Proprietary Training Manuals,
- Other organization-specific, instructor-specific, or otherwise non-public knowledge sources that public foundation models were not trained on.

### 1.5 Definitions

| Term | Meaning |
|---|---|
| Learner | The person using the app to generate a study plan |
| Learning goal | A short description of what the learner wants to study |
| Uploaded materials | Documents submitted by the learner |
| Ingestion | Extracting and preparing document text for analysis |
| Relevance check | AI-assisted assessment of how well materials match the learning goal |
| Study path | A generated curriculum-style sequence of modules or lessons |
| MVP | Minimum viable product for capstone demonstration |
| Companion / mascot | Optional retro pixel-art guide or progress indicator |
| Spec-Driven Development | Development approach where SRS, user stories, TODOs, tests, and implementation are kept aligned |

---

## 2. Overall Description

### 2.1 Product Perspective

Study-and-Learn is a local-first AI-assisted learning web application. It should be simple enough to build and demonstrate within a capstone timeline while still showing real software engineering value.

The project should demonstrate:
- requirements engineering,
- web application development,
- document processing,
- AI/LLM integration,
- retrieval or embeddings, if feasible,
- testing,
- deployment,
- CI/CD,
- agile project management,
- design and architecture documentation.

### 2.2 Product Goals

The system should:

1. help learners organize study materials,
2. reduce the effort required to plan what to study,
3. make learning feel manageable through smaller units,
4. provide clear summaries and topic alignment feedback,
5. generate a realistic weekly learning plan,
6. remain lightweight enough for local development and modest deployment,
7. support a clean capstone demonstration.

### 2.3 Design Principles

- **Guided over open-ended:** avoid chat as the primary interaction model.
- **MVP first:** implement the core pipeline before advanced features.
- **Transparent outputs:** show summaries, relevance reasoning, and generated plan clearly.
- **Editable later:** generated outputs should be structured so future admin editing is possible.
- **Lightweight architecture:** avoid unnecessary frameworks unless they solve a real problem.
- **Retro-friendly UX:** use a playful visual identity without letting it distract from functionality.

---

## 3. Assumptions and Constraints

### 3.1 Assumptions

- The learner has a rough idea of what they want to learn.
- The learner can provide study documents.
- The MVP can initially support a small number of subjects.
- AI output may need guardrails, formatting, and validation.
- Some documents may be imperfect, incomplete, or only partially relevant.

### 3.2 Technical Constraints

Local development target:
- Intel Core i5-11400H,
- RTX 3060 6GB laptop GPU,
- 16 GB RAM,
- optional upgrade to 32 GB RAM.

Preferred deployment target:
- 8 GB RAM,
- 4 CPU VM or lower if possible.

Deployment platform (decided):
- DigitalOcean (4 vCPU / 8 GB RAM / 160 GB disk, $48/month).

### 3.3 Project Constraints

- Must be feasible within the capstone timeline.
- Must support at least three agile sprints.
- Must include an accessible GitHub repository.
- Must include an accessible task board.
- Must include a design and testing document.
- Must include CI/CD or documented automated testing.
- Must include a deployed web app if submitted as a web application.
- Must support a final 15–20 minute recorded demo/presentation.

---

## 4. Proposed Technical Architecture

### 4.1 Candidate Stack

| Layer | MVP Choice | Notes |
|---|---|---|
| Backend | Flask | Simple Python web framework suitable for rapid capstone development |
| Frontend | Bootstrap 5 | Simple, responsive UI with minimal build tooling |
| AI serving | Ollama | Local model serving for development |
| Embeddings / retrieval | ChromaDB |
| Database | PostgreSQL (metadata) + ChromaDB (vectors) | Stores uploads, metadata, outputs, and possibly embeddings |
| Testing | pytest | Start simple and expand |
| CI/CD | GitHub Actions | Run tests automatically on push / pull request |
| Task board | Static GitHub Pages site | Simple public project board without bloated tools |

### 4.2 Initial Architecture Flow

1. User enters learning goal.
2. User uploads supported documents.
3. Backend validates file type and stores upload metadata.
4. Text extraction pipeline extracts readable text.
5. Extracted text is chunked or prepared for AI analysis.
6. AI generates material summary.
7. AI checks relevance between the learning goal and document content.
8. AI generates a structured study path.
9. App stores generated outputs.
10. UI displays summary, relevance result, and study path.

### 4.3 Suggested Directory Structure

```text
study-and-learn/
├── src/
│   ├── __init__.py
│   ├── models.py
│   ├── utils.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── _helpers.py
│   │   ├── auth.py
│   │   ├── admin.py
│   │   ├── processing.py
│   │   ├── lessons.py
│   │   └── dashboard.py
│   ├── repositories/
│   │   └── lesson_repo.py
│   ├── services/
│   │   ├── ai_client.py
│   │   ├── ai_client_cloud.py
│   │   ├── chunker.py
│   │   ├── curriculum_generator.py
│   │   ├── document_parser.py
│   │   ├── exceptions.py
│   │   ├── grader.py
│   │   ├── lesson_generator.py
│   │   ├── lesson_orchestrator.py
│   │   ├── progress_tracker.py
│   │   ├── quiz_generator.py
│   │   ├── rag_retriever.py
│   │   ├── relevance_checker.py
│   │   ├── settings_service.py
│   │   ├── summarizer.py
│   │   ├── tts_service.py
│   │   ├── tts_worker.py
│   │   ├── vector_store.py
│   │   └── vision_parser.py
│   ├── templates/
│   └── static/
│       ├── js/   (mascot, progress, upload, deck-engine, deck-page, results, settings)
│       ├── css/
│       ├── fonts/
│       └── img/
├── tests/
├── docs/
│   ├── SRS.md
│   ├── TODO.md
│   ├── STATUS.md
│   ├── AI_AGENT_PROTOCOL.md
│   └── DESIGN_AND_TESTING.md
├── migrations/
│   └── versions/
├── .github/
│   └── workflows/
│       └── tests.yml
├── requirements.txt
├── init_db.sql
├── config.py
├── app.py
└── README.md
```
### 4.4 AI Model Configuration

| Parameter | Description | Notes |
|---|---|---|
| Serving framework | Ollama (default) | Local-first via Ollama; cloud API selected via the `AI_BACKEND=cloud` env var (the Sprint-5 "import toggle" pattern has been removed — backend selection is exclusively env-var-driven in `ai_client.py::call_ollama`) |
| Chat model | Configured via `OLLAMA_MODEL` env var | `config.py` ships `gemma3:27b-cloud` as the single package default (used by `Config.summary()` only). When `AI_BACKEND=local` and `OLLAMA_MODEL` is unset at call time, `ai_client.py` falls back to `qwen3:0.6b` (suitable for 6GB VRAM). For local dev without cloud credentials, set `OLLAMA_MODEL=qwen3:0.6b` and `AI_BACKEND=local` in `.env`. |
| Embedding model | Configured via `OLLAMA_EMBEDDING_MODEL` env var | Used exclusively for ChromaDB vector embeddings. Swappable via env var. |
| Testing mode | `AI_MOCK=true` returns a deterministic plain-text stub string (e.g. `Mock response for prompt: <first 50 chars>...`), NOT structured JSON. Downstream services must parse defensively and fall back to defaults when the mock string is returned. | Ensures deterministic CI/CD without GPU or cloud dependency |
| OCR model | GLM-OCR (0.9B, local-only) | AI-powered text/table/figure recognition for scanned PDFs and images |

### 4.5 RAG & Multi-Document Architecture
- **Chunking**: `RecursiveCharacterTextSplitter` (LangChain) with hardcoded `chunk_size=1000`, `chunk_overlap=200` (no env vars or config settings expose these — see `src/services/chunker.py:20-25`)
- **Vector Storage**: Persistent ChromaDB (`./data/chroma_db`) for dev (default); optional Chroma Cloud via `CHROMA_DB=cloud` (see ADR-027); in-memory fallback for CI
- **Multi-Upload**: Route accepts `request.files.getlist('files')` with max 5 files per submission
- **Retrieval**: Top-k similarity search against goal-aligned chunks before AI prompt injection
- **Context Flow**: Goal → Upload → Parse → Chunk → Embed → Store → Retrieve → Generate AI Outputs

---

## 5. Functional Requirements

### 5.1 Learning Goal Input

| ID | Requirement | Priority |
|---|---|---|
| FR-001 | The system shall allow the user to enter a learning goal. | Must |
| FR-002 | The system shall validate that the learning goal is not empty. | Must |
| FR-003 | The system should provide example learning goal prompts. | Should |

### 5.2 Document Upload

| ID | Requirement | Priority |
|---|---|---|
| FR-004 | The system shall allow the user to upload up to 5 documents simultaneously. | Must |
| FR-005 | The system shall support `.txt`, `.md`, `.pdf`, `.docx`, `.pptx`, `.png`, `.jpg`, and `.jpeg` file uploads. | Must |
| FR-006 | The system shall reject unsupported file types with a clear message. | Must |
| FR-007 | The system should show uploaded file names and processing status. | Should |

### 5.3 Document Ingestion and Text Extraction

| ID | Requirement | Priority |
|---|---|---|
| FR-008 | The system shall chunk, embed, and store extracted text in a local vector database using OllamaEmbeddings. | Must |
| FR-009 | The system shall retrieve top-k relevant chunks using goal-aligned similarity search before AI prompt injection. | Must |
| FR-010 | The system should handle extraction failures gracefully. | Should |
| FR-011 | The system shall perform AI-powered OCR on uploaded images, scanned PDFs, and embedded document images using local vision models, with graceful fallback to traditional text extraction. | Must |

### 5.4 AI Summary Generation

| ID | Requirement | Priority |
|---|---|---|
| FR-012 | The system shall generate a summary of uploaded materials. | Must |
| FR-013 | The summary shall identify main topics covered by the materials. | Must |
| FR-014 | The summary should identify possible prerequisites or difficulty level. | Should |

### 5.5 Relevance Checking

| ID | Requirement | Priority |
|---|---|---|
| FR-015 | The system shall compare the learning goal with extracted content. | Must |
| FR-016 | The system shall return a relevance label: strong match, partial match, or weak match. | Must |
| FR-017 | The system shall provide a brief explanation for the relevance result. | Must |
| FR-018 | The system should suggest what kind of missing material would improve the match. | Should |
| FR-018a | The system shall gate study path generation and lesson generation when a weak match is detected, displaying alternative feedback with material suggestions. | Must |
| FR-018b | The system shall display warning banners on the relevance card and study path card when a partial match is detected. | Must |

### 5.6 Study Path Generation

| ID | Requirement | Priority |
|---|---|---|
| FR-019 | The system shall generate a structured study path based on uploaded materials and learning goal. | Must |
| FR-020 | The study path shall contain modules or lessons in a recommended sequence. | Must |
| FR-021 | The study path shall include estimated effort per module or lesson. | Must |
| FR-022 | The generated plan should target approximately 6–8 hours of study per week. | Should |
| FR-023 | The system should identify when uploaded materials are insufficient for a complete study path. | Should — Implemented (weak match gates study path + lesson generation, displays alternative feedback card) |

### 5.7 User Interface

| ID | Requirement | Priority |
|---|---|---|
| FR-024 | The system shall provide a web-based UI. | Must |
| FR-025 | The MVP shall avoid a chat interface. | Must |
| FR-026 | The UI shall guide the user through goal input, upload, analysis, and results. | Must |
| FR-027 | The UI should use a retro-inspired visual style with custom pixel fonts. | Should |
| FR-028 | The UI may include a pixel companion or mascot with idle/waiting/done animations. | Implemented (idle/busy/happy animated GIFs with progress-driven state switching) |
| FR-032 | The system shall combine learning goal entry and file upload into a single unified form submission. | Must |
| FR-033 | The system should display processing progress feedback during long-running AI operations. | Should |

### 5.8 Interactive Lessons

| ID | Requirement | Priority |
|---|---|---|
| FR-034 | The system shall generate structured slide-based lesson content for each module in the study path. | Must |
| FR-035 | The system shall generate mixed-type quizzes per module supporting mcq, true_false, multi_select, and cloze_dropdown question types. | Must |
| FR-036 | The system shall insert inline comprehension checkpoints at regular intervals within lesson slides. | Must |
| FR-037 | The system shall grade quiz answers instantly and return per-question correct/incorrect feedback with explanations. | Must |
| FR-038 | The system shall regenerate fresh questions on lesson retake to prevent answer memorization. | Must |
| FR-039 | The system shall gate module progression so the learner must pass module N before accessing module N+1. | Must |
| FR-040 | The system shall enforce an 80% pass threshold for module completion with a pass/fail verdict. | Must |
| FR-041 | The system shall support a difficulty level selector (Easy/Normal/Hard) that maps to age-appropriate content complexity. Difficulty is snapshotted at generation time. | Must — Implemented |
| FR-042 | The system shall present lessons via a custom CSS/JS slide-deck engine styled with retro fonts and cyberpunk visuals. | Must |
| FR-043 | The system shall allow the learner to view source document text excerpts that informed the generated lesson content via a modal overlay in the slide deck. | Must |
| FR-044 | The system shall allow the learner to export a passed lesson (≥80% score) to PDF containing all slides, checkpoints with answers, quiz questions with answers and explanations, and source materials. | Must |
| FR-045 | The system shall support opt-in TTS audio narration for lessons using Edge-TTS Neural voices (Ava/Emma/Ryan/Andrew). Audio is generated at lesson-creation time, stored per deck slot (content slides, inline checkpoints, Final Quiz, Results) keyed by `deck_index`, plus an intro MP3 at `slide_index=-1`; the Results slot narration doubles as the module outro. `lesson['lesson']['deck_layout']` (built by `build_deck_layout()`) is the single source of truth for slot ordering and TTS `slide_index` keys. TTS is snapshotted at generation time; disabling TTS after generation does not affect already-generated lessons. | Must — Implemented |
| FR-046 | The system shall save the learner's current slide position automatically (debounced 500ms) and restore it on revisit, with an explicit "Exit & Save" button and a "Start Over" option. | Must — Implemented |

### 5.9 Admin / Editing Features

| ID | Requirement | Priority |
|---|---|---|
| FR-029 | The system may allow an admin to edit generated lesson text. | Could |
| FR-030 | The system may export or display generated lesson content as slides. | Could |
| FR-031 | The system may support AI-generated narration or subtitles. | Implemented — Edge-TTS opt-in narration with AI-generated tutor-voice scripts. See FR-045. |

---

## 6. Non-Functional Requirements

### 6.1 Usability

| ID | Requirement | Priority |
|---|---|---|
| NFR-001 | The system should be understandable without prompt engineering knowledge. | Must |
| NFR-002 | The system should use clear labels, buttons, and result sections. | Must |
| NFR-003 | The system should minimize user decision overload. | Should |

### 6.2 Performance

| ID | Requirement | Priority |
|---|---|---|
| NFR-004 | The system should run locally on the target development laptop. | Must |
| NFR-005 | The system should process small-to-medium study documents within an acceptable demo timeframe. | Must |
| NFR-006 | The system should degrade gracefully when documents are too large or processing fails. | Should |

### 6.3 Reliability

| ID | Requirement | Priority |
|---|---|---|
| NFR-007 | The system shall validate user inputs. | Must |
| NFR-008 | The system shall handle AI service failures with clear error messages. | Must |
| NFR-009 | The system should log major processing steps for debugging. | Should |

### 6.4 Maintainability

| ID | Requirement | Priority |
|---|---|---|
| NFR-010 | The codebase shall be organized into clear modules or services. | Must |
| NFR-011 | The repository shall include setup instructions. | Must |
| NFR-012 | Core logic shall have automated tests where feasible. | Must |
| NFR-013 | The design and testing document shall explain architecture and test strategy. | Must |

### 6.5 Security and Privacy

| ID | Requirement | Priority |
|---|---|---|
| NFR-014 | The system shall restrict accepted upload file types. | Must |
| NFR-015 | The system shall avoid executing uploaded content. | Must |
| NFR-016 | The system should document how uploaded files are stored and handled. | Should |
| NFR-017 | The system should avoid publishing user-uploaded content in the public task board or repo. | Must |

---

## 7. User Stories

### Epic 1: Project Foundation

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| US-001 | As a developer, I want a documented project setup so I can run the app locally. | README includes setup steps; app runs locally; dependencies documented |
| US-002 | As a developer, I want automated tests in CI so I can prove basic reliability. | GitHub Actions runs pytest on push/PR |
| US-003 | As a reviewer, I want a public task board so I can see project progress. | Static task board is publicly accessible |

### Epic 2: Learner Workflow

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| US-004 | As a learner, I want to enter a learning goal so the app knows what I want to study. | Goal form accepts non-empty input and saves/submits it |
| US-005 | As a learner, I want to upload study materials so the app can analyze them. | Supported files upload successfully; unsupported files are rejected |
| US-006 | As a learner, I want to see upload status so I know whether my files were accepted. | UI lists uploaded files and status |

### Epic 3: Document Processing

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| US-007 | As a learner, I want uploaded documents converted into text so the app can analyze them. | Text extraction works for initial supported file types |
| US-008 | As a developer, I want parser errors handled clearly so failed documents do not crash the app. | Failed extraction returns user-friendly message and logs error |

### Epic 4: AI Analysis

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| US-009 | As a learner, I want a summary of my materials so I can understand what they contain. | App displays generated summary with key topics |
| US-010 | As a learner, I want to know whether my documents match my goal. | App displays strong/partial/weak relevance result with explanation |
| US-011 | As a learner, I want a structured study path so I know what to study next. | App displays ordered modules/lessons with estimated effort |

### Epic 5: Interactive Lessons

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| US-012 | As a learner, I want to generate interactive lessons from my study path so I can learn in a structured way. | "Generate Interactive Lessons" button triggers slide + quiz generation; loading indicator shown |
| US-013 | As a learner, I want lessons presented as slides with retro fonts and visual styling. | Custom slide-deck renders title/content/example/summary slide types with Retrograde Bold and BoldPixels fonts |
| US-014 | As a learner, I want comprehension checkpoints during my lesson so I stay engaged. | Inline checkpoint slides appear every N slides with a multiple-choice question; advance blocked until answered |
| US-015 | As a learner, I want a final quiz at the end of each module to test my understanding. | 5 mixed-type questions (mcq, true_false, multi_select, cloze_dropdown); instant grading with per-question feedback |
| US-016 | As a learner, I want to retake a failed module with fresh questions to improve my score. | Retake regenerates quiz; 80% threshold required to pass and unlock next module |
| US-017 | As a learner, I want modules gated so I must master one before moving to the next. | Module N+1 locked until module N passed (≥80%); progress bar shown on module listing |

### Epic 6: UX, Polish, and Retro Experience

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| US-018 | As a learner, I want the app to feel simple, guided, and retro-themed. | Unified form; retro fonts applied consistently; cyberpunk visual identity maintained |
| US-019 | As a learner, I want a retro mascot that provides simple visual feedback during my learning journey. | Mascot image displayed with idle/busy/happy animated GIF states; state-driven glow tints; progress-aware state switching via polling |
| US-020 | As a learner, I want clear progress feedback during long AI operations so I know the app is working. | Background processing with visible progress bar or stage indicator instead of full-screen overlay |
| US-021 | As a learner, I want the quality of generated lessons and quizzes to be acceptable for high-school to college-level material. | Prompt engineering refined; model research conducted for optimal quality/speed tradeoff on target hardware |
| US-022 | As a learner, I want a difficulty toggle so content matches my age and skill level. | Easy (10–11), Normal (12–13), Hard (14–15) difficulty options; prompt adjusted accordingly; difficulty snapshotted at generation time |

### Epic 7: User Accounts & Admin (Sprint 5)

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| US-023 | As a learner, I want to register and log in so my study paths are saved across sessions. | Registration, login, logout work via Flask-Login; passwords hashed; session cleared on login to prevent leakage |
| US-024 | As an admin, I want to toggle lesson-generation access per user so I can control who can create study paths. | Admin panel at `/admin` lists users with per-user toggle and password reset; new signups default to denied |
| US-025 | As a learner, I want a dashboard showing my active, completed, and cancelled study paths so I can manage my learning history. | Dashboard with Active/Completed/Cancelled tab pills; Mark Complete action (only when all modules passed); Delete action (completed/cancelled only, irreversibility warning) |
| US-026 | As a learner, I want to maintain up to 3 concurrent study paths so I can study multiple subjects simultaneously. | Each learning goal creates an independent StudyPath; max 3 active paths enforced; cap warning banner shown when at limit |
| US-027 | As an admin, I want self-service and admin-initiated password reset so users can recover access without my intervention. | `/reset-password` for self-service; `/admin/reset-password/<user_id>` for admin-initiated; retro-themed error pages (400/403/404/500) |
| US-028 | As a learner, I want my study paths to persist across server restarts so I don't lose progress. | Lesson content, extracted texts, and per-module progress stored in PostgreSQL (StudyPath + LessonProgress); DB-backed repository seam |
| US-029 | As a learner, I want access control to clearly tell me when I lack privileges so I'm not confused by missing features. | 3-tier access model: unauthenticated → login form; privileged → full form; unprivileged → access-denied message |
| US-030 | As a developer, I want seeded demo accounts so I can test the app without manual setup. | init_db.sql seeds admin/bob/alice with documented passwords; all seeded users have can_generate_lessons=True |
| US-031 | As a developer, I want PostgreSQL-only storage so the schema is portable to production. | All SQLite references purged; DATABASE_URL validated to begin with `postgresql://`; migrations and tests aligned |

### Epic 8: OCR/Vision & Content Deduplication (Sprint 6)

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| US-032 | As a learner, I want to upload scanned PDFs and images so the app can extract text from visual content. | GLM-OCR (local, 0.9B) runs text/table/figure recognition; pdf2image renders PDF pages via Poppler; DOCX embedded images and PPTX files extracted; 8 file types supported |
| US-033 | As a developer, I want content-addressable deduplication so identical files uploaded by different users aren't re-processed. | SHA-256 ContentRegistry model; ChromaDB collections named by file hash (doc_<hash>); shared globally across users |
| US-034 | As a learner, I want support for `.docx`, `.pptx`, `.png`, `.jpg`, `.jpeg` files so I can study from varied sources. | Allowed extensions include all 8 types; unsupported types rejected with clear message |
| US-035 | As a developer, I want multi-collection retrieval so context is merged across all uploaded documents. | retrieve_from_multiple_collections merges results across per-file collections with score-based merging; chunk metadata (source_hash, content_type) preserved |

### Epic 9: Mascot Animation, TTS & PDF Export (Sprint 7)

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| US-036 | As a learner, I want an animated mascot with idle/busy/happy/error states so the UI feels alive during long operations. | idle 14f@250ms, busy 16f@140ms, happy 14f@220ms, error 14f@220ms; transparent backgrounds; state-driven switching via polling |
| US-037 | As a learner, I want opt-in TTS audio narration so I can listen to lessons instead of reading. | Edge-TTS Neural voices (Ava/Emma/Ryan/Andrew); AI-generated narration scripts; per-slide MP3 keyed by deck_index; audio generated at lesson-creation time; toggle in settings; graceful failure on network error |
| US-038 | As a learner, I want to export a passed lesson to PDF so I can review it offline. | fpdf2 per-lesson PDF (slides, checkpoints with answers, quiz with answers/explanations, source materials); available for any passed lesson regardless of parent path status; _clean() sanitizer for Latin-1 compatibility |
| US-039 | As a learner, I want to see which source document a slide references so I can verify the AI's grounding. | Chunk-level provenance preserved through retrieval pipeline; "View Sources" button in slide deck controls opens modal overlay with document excerpts; parallel file_names JSON column on StudyPath |
| US-040 | As a learner, I want my lesson session to be cleaned up after generation so the server doesn't accumulate stale data. | extracted_texts nullified after generate_lessons completes; session bloat prevented |
| US-041 | As a learner, I want to save my slide position and resume where I left off so I don't lose my place. | deck_position auto-saved to content_data JSON on every slide advance (debounced 500ms); restored on revisit; "Start Over" button resets to 0; "Exit & Save" button explicit |

### Epic 10: Final Deployment & Capstone Submission (Sprint 8)

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| US-042 | As a reviewer, I want a deployed web app link so I can evaluate the capstone without local setup. | Deployed to DigitalOcean cloud VPS; all routes and features functional in production; demo link in README |
| US-043 | As a developer, I want production environment variables configured so the deployed app runs the correct AI and DB backends. | AI_BACKEND, DATABASE_URL, SECRET_KEY, OLLAMA_MODEL set in production; AI_MOCK=true documented as demo fallback |
| US-044 | As a reviewer, I want a recorded 15–20 minute demo so I can evaluate the full workflow. | Demo script covers goal → upload → results → lessons → quiz → grade → retake; recording submission-ready |
| US-045 | As a developer, I want all documentation finalized and CI passing so the capstone submission is complete. | DESIGN_AND_TESTING.md, AI_AGENT_PROTOCOL.md, task board all reflect final Sprint 8 state; CI pipeline green; grader GitHub access confirmed |

---

## 8. MVP Scope

### 8.1 Must-Have MVP

- Flask app skeleton.
- Bootstrap UI + custom retro CSS theme.
- Unified learning goal + document upload form (single submission).
- File type validation.
- Text extraction for `.txt`, `.md`, `.pdf`, `.docx`, `.pptx`, `.png`, `.jpg`, `.jpeg`.
- AI-powered OCR for scanned PDFs and images (GLM-OCR local + Qwen3.5 cloud).
- Retrieval-Augmented Generation (RAG) pipeline (ChromaDB persistent vector store).
- Multi-file upload (≤5).
- AI summary generation through Ollama.
- Relevance check (strong/partial/weak).
- Study path generation (sequenced modules with effort estimates).
- Interactive slide-based lesson generation per module.
- Mixed-type quiz generation per module (mcq, true_false, multi_select, cloze_dropdown).
- Inline comprehension checkpoints within lessons.
- Instant quiz grading with per-question feedback.
- Retake functionality with fresh question regeneration.
- Gated module progression (80% pass threshold).
- Results page with improved visual hierarchy.
- Lesson listing page with progress bar.
- Server-side session storage (Flask-Session + cachelib).
- Custom CSS/JS slide-deck engine (retro-themed).
- Content-addressable global deduplication (SHA-256 + ContentRegistry).
- pytest test suite (421 tests).
- GitHub Actions test workflow.
- Static public task board.
- Design and testing document.
- Opt-in TTS audio narration (Edge-TTS Neural voices, AI-generated narration scripts).
- Difficulty-aware content generation (Easy/Normal/Hard, prompt injection + snapshotting).
- Session save/resume (deck position auto-saved to DB, Exit & Save button).

### 8.2 Should-Have MVP Polish

- Retro mascot/companion with idle/busy/happy animation frames.
- Loading progress indicators showing current stage during AI operations.
- Non-blocking background progress indicator during document processing.
- Upload status messages.
- Generated output formatting and markdown rendering.
- Demo seed files — done (Sprint 8; proprietary demo document set kept privately outside the repo for the live demo).
- Error handling for AI/model unavailable.

### 8.3 Deferred / Stretch

- YouTube integration.
- Export to PPTX or SCORM.
- Adaptive difficulty based on learner performance.
- Rich companion behavior and interactive mascot.
- Admin content management workflow.
- Social features (friends, chat, share lessons).
- Full offline mode (C/C++ rewrite without Ollama).

---

## 9. Scope-Creep Ladder

Ranked from easier to harder. Items above the line are implemented; items below are candidates for future sprints.

### ✅ Implemented
1. Multi-user accounts (Flask-Login + PostgreSQL) — done (User model, sign-up, login, logout, hashed passwords)
2. Learner dashboard with progress tracking — done (DB-backed lesson repository, StudyPath/LessonProgress models, progress bars)
3. Max 3 active lessons gating — done (active_lesson_count, cap warning banner, blocked generation)
4. Admin access control for lesson generation — done (is_admin flag, can_generate_lessons toggle, /admin/toggle route)
5. Bob/Alice demo account seeding — removed (superseded by init_db.sql seed; see README.md)
6. Static mascot image with progress-aware speech bubble — done (mascot-robot.png, click-to-talk, progress bar)
7. Retro theme improvements — done (Retrograde Bold, BoldPixels fonts, cyberpunk theme)
8. Better prompt templates — done
9. Simple quiz generation — done (4 question types: mcq, true_false, multi_select, cloze_dropdown)
10. Slide-style lesson pages — done (custom CSS/JS deck engine with inline checkpoints)
11. Cloud model toggle — done (env-var-driven backend dispatch via `AI_BACKEND=cloud` in `ai_client.py::call_ollama`; the old uncomment-an-import pattern has been removed)
12. JS refactored into domain modules (mascot, progress, upload, deck-engine, deck-page, results) — done
13. Gated module progression with pass/fail — done (80% threshold)
14. Retake with regenerated questions — done
15. Server-side session storage — done (Flask-Session + cachelib FileSystemCache)
16. Loading/progress UI — full-screen spinner replaced with background progress bar in mascot speech bubble
17. Fill-in-the-blank one-word validation — done (inline inputs, per-blank grading, case-insensitive)
18. Lesson/quiz prompt engineering refinement — done
19. Non-blocking progress on `/process` route — done
20. PostgreSQL-only migration — done (schemas, docs, configs, tests)
21. Codebase refactoring (orchestrator/grader/repo seams) — done
22. AI_BACKEND env var indirection — done

23. Admin panel with user management — done (admin.html, per-user toggle, password reset)
24. Access-denied page for unprivileged users — done (3-tier access model on index.html)
25. Custom error handlers (400/403/404/500) — done (error.html with retro theme)
26. Password reset (self-service + admin-initiated) — done (/reset-password, /admin/reset-password)
27. Multi-path study support — done (independent StudyPath per learning goal, up to 3 concurrent)
28. Session leakage fix (user A's data appearing for user B) — done (session.pop on login)
29. AI-powered OCR/vision integration — done (GLM-OCR local for text/table/figure recognition, Qwen3.5 cloud for figure descriptions, pdf2image page rendering, DOCX/PPTX image extraction, image file support)
30. Global content-addressable deduplication — done (SHA-256 ContentRegistry, content-keyed ChromaDB collections, multi-collection retrieval)
31. Relevance gating for weak matches — done (weak match blocks study path + lesson generation, partial match shows warning banners)
32. Source document citations in lessons — done (ChromaDB metadata preserved through retrieval pipeline, "View Sources" modal in slide deck)
33. Dashboard with Active/Completed/Cancelled tabs — done (tab pills, Mark Complete, Delete with irreversibility warning, My Lessons navbar link)
34. Per-lesson PDF export — done (fpdf2, passed lessons only, includes slides/checkpoints/quiz/sources)

### Sprint 7 (Completed)
35. Mascot animation frames (idle/busy/happy) — done (idle 14f@250ms, busy 16f@140ms, happy 14f@220ms, error 14f@220ms)
36. Text-to-speech narration — done (Edge-TTS opt-in, AI narration scripts, per-slide MP3, deck player)
37. PDF export for completed lessons — done (fpdf2, per-lesson, slides/checkpoints/quiz/sources)
38. Session cleanup (extracted_texts) — done (nullified after generate_lessons completes)
39. Badges/trophies for completed lessons — NOT done (moved out of the capstone timeline to Post-Capstone; see Post-Capstone / Stretch below)
40. Source document referencing — done (citation modal in deck)
41. Cloud ChromaDB and cloud AI provider testing — DONE (CHROMA_DB=cloud toggle added, verified against Chroma Cloud; AI_BACKEND=cloud verified against cloud Ollama)
42. Difficulty level selector — done (Easy/Normal/Hard, prompt injection, badges)
43. Session save/resume with Exit & Save — done (deck position auto-saved)
44. Checkpoint question variety — done (mcq/true_false/cloze_dropdown)
45. cloze_dropdown replaces fill_blank — done (legacy compat preserved)
46. Humor injection in quiz distractors — done (HUMOR_INSTRUCTIONS in quiz prompt)

### Sprint 8 (Active)
47. Deployment to a cloud VPS (DigitalOcean)
48. Final documentation and demo recording
49. Capstone submission

### Post-Capstone / Stretch
- Badge/trophy system for completed modules (moved out of the capstone timeline; nice-to-have, not planned for Sprint 8)
- Matching question type for quizzes (future quiz variety expansion)
- Speaker change without retake (pre-generate all 4 speakers at lesson time)
- Extended file type support (.docx, .html, .odt) — limited practical benefit for demo
- YouTube or external resource integration
- Full adaptive study planner
- Social features (friends, chat, share lessons)
- Full offline mode (C/C++ rewrite without Ollama)

---

## 10. Testing Strategy

### 10.1 Unit Tests

Initial unit tests should cover:
- file extension validation,
- parser selection,
- text extraction helpers,
- prompt formatting,
- relevance label parsing,
- curriculum output schema validation,
- TTS service: voice mapping, manifest structure, empty text handling, cleanup,
- Quiz generator: cloze_dropdown type, checkpoint type variety, humor injection, difficulty injection,
- Narration script: structure, personalization, fallback, last-module outro,
- Route-level: TTS snapshotting, graceful TTS failure, save-position, audio routes.

### 10.2 Integration Tests

Initial integration tests should cover:
- app starts successfully,
- upload route accepts valid files,
- upload route rejects invalid files,
- workflow route returns result page using mocked AI responses.

### 10.3 Smoke Tests

Before demo:
- app loads,
- sample document can be uploaded,
- summary displays,
- relevance result displays,
- study path displays.

### 10.4 Manual Demo Tests

Use a fixed demo script with known input documents so the capstone presentation is predictable.

---

## 11. CI/CD Strategy

The initial CI/CD target is intentionally simple:

1. On push or pull request:
   - check out repository,
   - install Python,
   - install dependencies,
   - run `pytest -v tests/`.

Later additions:
- linting,
- formatting checks,
- security checks,
- deployment workflow.

---

## 12. Open Questions

1. ~~Should the first prototype use pgvector or ChromaDB?~~ → **ChromaDB** (chosen, implemented)
2. ~~Which Ollama model gives acceptable local results on the target hardware?~~ → **qwen3:0.6b (chat) + qwen3-embedding:0.6b (embeddings)** (placeholder; upgrade path: `qwen3:1.7b`, `gemma3:4b`, or Ollama Cloud)
3. ~~How many file types should be truly supported in the first sprint?~~ → **txt, md, pdf** (initial MVP); **docx, pptx, png, jpg, jpeg** added in Sprint 6 (OCR/vision integration with content-addressable dedup). Final supported set: `txt, md, pdf, docx, pptx, png, jpg, jpeg` (8 types — see `src/utils.py:ALLOWED_EXTENSIONS`).
4. ~~Should OCR be postponed until after the main workflow works?~~ → **Implemented in Sprint 6** (GLM-OCR local + Qwen3.5 cloud, content-addressable dedup)
5. ~~Should generated outputs be stored as JSON, Markdown, or database records?~~ → **JSON in Flask session (server-side via cachelib)**
6. ~~Should the companion be purely visual or tied to progress?~~ → Visual feedback with click-to-talk implemented; animated GIF states (idle/busy/happy) with progress-driven switching implemented
7. ~~Which deployment platform is easiest for the final capstone demo?~~ → **DigitalOcean** (cloud VPS, 4 vCPU / 8 GB RAM / 160 GB disk, $48/month). The 8 vCPU / 16 GB RAM / 320 GB SSD tier ($96/month) was rejected — DigitalOcean requires a $50 prepayment to unlock it, which is not practical for a temporary capstone deployment. The 4 vCPU / 8 GB tier is sufficient because AI inference is offloaded to Ollama Cloud (`AI_BACKEND=cloud`) and vector storage to Chroma Cloud (`CHROMA_DB=cloud`). Free-tier PaaS hosts (Render/Railway) were evaluated and rejected — the stack (PostgreSQL + ChromaDB + Ollama + Poppler + GLM-OCR) does not fit a 512 MB–1 GB container.
8. ~~What is the optimal model for lesson/quiz generation quality vs speed on 6GB VRAM?~~ → qwen3:0.6b chosen as placeholder; upgrade guidance documented (Sprint 4 prompt tuning ongoing)
9. ~~Should loading UI use full-screen overlay or background processing with stage indicator?~~ → Background processing with progress bar + mascot speech bubble (implemented Sprint 4)
10. ~~How many mascot animation frames are needed for adequate visual feedback?~~ → idle 14f@250ms, busy 16f@140ms, happy 14f@220ms, error 14f@220ms (all implemented)
11. ~~Which TTS provider to use?~~ → Edge-TTS (edge-tts>=7.2.8), Microsoft Neural voices. Custom SSML blocked by Microsoft — plain text only. AI-generated narration scripts produce tutor-voice quality.

---

## 13. Capstone Submission Alignment

The project should produce:

- GitHub repository shared with the required grader account.
- Deployed web application link.
- Public static task board link.
- `docs/SRS.md`.
- `docs/TODO.md`.
- `docs/DESIGN_AND_TESTING.md`.
- CI/CD workflow evidence.
- At least three completed sprints.
- Final recorded 15–20 minute demo/presentation.
