# Software Requirements Specification (SRS)
# Study-and-Learn

**Version:** 1.1  
**Project type:** AI-assisted learning web application  
**Capstone track:** Software system / AI system  
**Repository name:** `study-and-learn`  
**Primary development approach:** Spec-Driven Development with AI tooling support  
**Last updated:** May 2026

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
3. extract text from those documents, if time permits, do an OCR as well for the documents,
4. generate an AI-assisted summary, relevance check, and recommended study path,
5. generate interactive slide-based lessons with inline comprehension checkpoints,
6. generate mixed-type quizzes (multiple choice, true/false, multi-select, fill-in-the-blank) per module,
7. take quizzes and receive instant grading with per-question feedback,
8. retake lessons with freshly regenerated questions to avoid memorization,
9. progress through gated modules (must pass module N to unlock N+1),
10. view all results in a retro-themed guided web interface,
11. check if learner wants to do the lessons again until they are satisfied with their progress

The MVP will **not** use a chat interface. The user interacts primarily through forms, buttons, and structured result pages.

### 1.4 Intended Users

Primary users:
- self-directed learners,
- students organizing study materials,
- teachers or tutors preparing study outlines,
- capstone evaluators reviewing the software artifact.

Initial target content areas:
- Computer Science,
- Mathematics,
- Fundamental Physics, if time allows.

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

Candidate deployment platforms:
- Render,
- Railway,
- PythonAnywhere,
- DigitalOcean,
- AWS EC2.

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
| Database | SQLite (metadata) + ChromaDB (vectors) | Stores uploads, metadata, outputs, and possibly embeddings |
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
│   ├── routes.py
│   ├── models.py
│   ├── services/
│   │   ├── document_parser.py
│   │   ├── ai_client.py
│   │   ├── summarizer.py
│   │   ├── relevance_checker.py
│   │   └── curriculum_generator.py
│   ├── templates/
│   └── static/
├── tests/
├── docs/
│   ├── SRS.md
│   ├── TODO.md
│   └── DESIGN_AND_TESTING.md
├── .github/
│   └── workflows/
│       └── tests.yml
├── requirements.txt
├── README.md
└── app.py
```
### 4.4 AI Model Specification
| Parameter | Value | Notes |
|---|---|---|
| Serving framework | Ollama | Local-first, REST API compatible |
| Default model | `qwen3:0.6b` (via `OLLAMA_MODEL` env var) | Placeholder model. Upgrade to `qwen3:1.7b`, `gemma3:4b`, or Ollama Cloud models on capable machines. |
| Embedding Model | `qwen3-embedding:0.6b` (via `OLLAMA_EMBEDDING_MODEL` env var) | Used exclusively for ChromaDB vector embeddings. Swappable via env var. |
| Supported small models | `gemma3:4b`, `lfm2.5-thinking:1.2b`, `granite4.1:3b` | Swappable via env var for testing/performance tradeoffs |
| Testing mode | `AI_MOCK=true` returns structured JSON stubs | Ensures deterministic CI/CD without GPU dependency |
| Multimodal capability | Text + image support deferred to post-MVP | OCR for scanned PDFs remains stretch goal |

### 4.5 RAG & Multi-Document Architecture
- **Chunking**: `RecursiveCharacterTextSplitter` (LangChain) with configurable size/overlap
- **Vector Storage**: Persistent ChromaDB (`./data/chroma_db`) for dev; in-memory fallback for CI
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
| FR-005 | The system shall support `.txt`, `.md`, `.pdf`, `.docx`, `.html`, and `.odt` if feasible. | Must |
| FR-006 | The system shall reject unsupported file types with a clear message. | Must |
| FR-007 | The system should show uploaded file names and processing status. | Should |

### 5.3 Document Ingestion and Text Extraction

| ID | Requirement | Priority |
|---|---|---|
| FR-008 | The system shall chunk, embed, and store extracted text in a local vector database using OllamaEmbeddings. | Must |
| FR-009 | The system shall retrieve top-k relevant chunks using goal-aligned similarity search before AI prompt injection. | Must |
| FR-010 | The system should handle extraction failures gracefully. | Should |
| FR-011 | The system may support OCR for scanned PDFs. | Could |

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

### 5.6 Study Path Generation

| ID | Requirement | Priority |
|---|---|---|
| FR-019 | The system shall generate a structured study path based on uploaded materials and learning goal. | Must |
| FR-020 | The study path shall contain modules or lessons in a recommended sequence. | Must |
| FR-021 | The study path shall include estimated effort per module or lesson. | Must |
| FR-022 | The generated plan should target approximately 6–8 hours of study per week. | Should |
| FR-023 | The system should identify when uploaded materials are insufficient for a complete study path. | Should |

### 5.7 User Interface

| ID | Requirement | Priority |
|---|---|---|
| FR-024 | The system shall provide a web-based UI. | Must |
| FR-025 | The MVP shall avoid a chat interface. | Must |
| FR-026 | The UI shall guide the user through goal input, upload, analysis, and results. | Must |
| FR-027 | The UI should use a retro-inspired visual style with custom pixel fonts. | Should |
| FR-028 | The UI may include a pixel companion or mascot with simple idle/waiting/done animations. | Could |
| FR-032 | The system shall combine learning goal entry and file upload into a single unified form submission. | Must |
| FR-033 | The system should display processing progress feedback during long-running AI operations. | Should |

### 5.8 Interactive Lessons

| ID | Requirement | Priority |
|---|---|---|
| FR-034 | The system shall generate structured slide-based lesson content for each module in the study path. | Must |
| FR-035 | The system shall generate mixed-type quizzes per module supporting mcq, true_false, multi_select, and fill_blank question types. | Must |
| FR-036 | The system shall insert inline comprehension checkpoints at regular intervals within lesson slides. | Must |
| FR-037 | The system shall grade quiz answers instantly and return per-question correct/incorrect feedback with explanations. | Must |
| FR-038 | The system shall regenerate fresh questions on lesson retake to prevent answer memorization. | Must |
| FR-039 | The system shall gate module progression so the learner must pass module N before accessing module N+1. | Must |
| FR-040 | The system shall enforce an 80% pass threshold for module completion with a pass/fail verdict. | Must |
| FR-041 | The system should support a difficulty level selector (Easy/Moderate/Hard) mapped to age-appropriate content complexity. | Should |
| FR-042 | The system shall present lessons via a custom CSS/JS slide-deck engine styled with retro fonts and cyberpunk visuals. | Must |

### 5.9 Admin / Editing Features

| ID | Requirement | Priority |
|---|---|---|
| FR-029 | The system may allow an admin to edit generated lesson text. | Could |
| FR-030 | The system may export or display generated lesson content as slides. | Could |
| FR-031 | The system may support AI-generated narration or subtitles. | Won't for MVP |

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
| US-015 | As a learner, I want a final quiz at the end of each module to test my understanding. | 5 mixed-type questions (mcq, true_false, multi_select, fill_blank); instant grading with per-question feedback |
| US-016 | As a learner, I want to retake a failed module with fresh questions to improve my score. | Retake regenerates quiz; 80% threshold required to pass and unlock next module |
| US-017 | As a learner, I want modules gated so I must master one before moving to the next. | Module N+1 locked until module N passed (≥80%); progress bar shown on module listing |

### Epic 6: UX, Polish, and Retro Experience

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| US-018 | As a learner, I want the app to feel simple, guided, and retro-themed. | Unified form; retro fonts applied consistently; cyberpunk visual identity maintained |
| US-019 | As a learner, I want a retro mascot that provides simple visual feedback during my learning journey. | Mascot image displayed with idle/waiting/done states; animations or frames for key moments |
| US-020 | As a learner, I want clear progress feedback during long AI operations so I know the app is working. | Background processing with visible progress bar or stage indicator instead of full-screen overlay |
| US-021 | As a learner, I want the quality of generated lessons and quizzes to be acceptable for high-school to college-level material. | Prompt engineering refined; model research conducted for optimal quality/speed tradeoff on target hardware |
| US-022 | As a learner, I want a difficulty toggle so content matches my age and skill level. | Easy (10–11), Moderate (12–13), Hard (14–15) difficulty options; prompt adjusted accordingly |

---

## 8. MVP Scope

### 8.1 Must-Have MVP

- Flask app skeleton.
- Bootstrap UI + custom retro CSS theme.
- Unified learning goal + document upload form (single submission).
- File type validation.
- Text extraction for `.txt`, `.md`, `.pdf`, and `.docx`.
- Retrieval-Augmented Generation (RAG) pipeline (ChromaDB persistent vector store).
- Multi-file upload (≤5).
- AI summary generation through Ollama.
- Relevance check (strong/partial/weak).
- Study path generation (sequenced modules with effort estimates).
- Interactive slide-based lesson generation per module.
- Mixed-type quiz generation per module (mcq, true_false, multi_select, fill_blank).
- Inline comprehension checkpoints within lessons.
- Instant quiz grading with per-question feedback.
- Retake functionality with fresh question regeneration.
- Gated module progression (80% pass threshold).
- Results page with improved visual hierarchy.
- Lesson listing page with progress bar.
- Server-side session storage (Flask-Session + cachelib).
- Custom CSS/JS slide-deck engine (retro-themed).
- pytest test suite (45 tests).
- GitHub Actions test workflow.
- Static public task board.
- Design and testing document.

### 8.2 Should-Have MVP Polish

- Retro mascot/companion with idle/waiting/done animation frames.
- Loading progress indicators showing current stage during AI operations.
- Difficulty level selector (Easy/Moderate/Hard) mapped to age groups.
- Model performance research for optimal quality/speed on target hardware.
- Upload status messages.
- Generated output formatting and markdown rendering.
- Demo seed files.
- Error handling for AI/model unavailable.
- Responsive mobile layout for slide deck.

### 8.3 Not Official MVP / Stretch

- OCR for scanned PDFs.
- YouTube integration.
- AI-generated TTS narration.
- Export to PDF, PPTX, or SCORM.
- Short-answer (free-text) AI grading.
- Adaptive difficulty based on learner performance.
- Spaced repetition and review scheduling.
- Rich companion behavior and interactive mascot.
- Admin content management workflow.
- Social features (friends, chat, share lessons).
- Full offline mode (C/C++ rewrite without Ollama).

---

## 9. Scope-Creep Ladder

Ranked from easier to harder. Items above the line are implemented; items below are candidates for future sprints.

### ✅ Implemented
1. Static mascot image or pixel avatar — done (mascot-robot.png placed bottom-right with click-to-talk)
2. Retro theme improvements — done (Retrograde Bold, BoldPixels fonts, cyberpunk theme)
3. Better prompt templates — done
4. Simple quiz generation — done (4 question types: mcq, true_false, multi_select, fill_blank)
5. Slide-style lesson pages — done (custom CSS/JS deck engine with inline checkpoints)
6. Cloud model toggle — done (ai_client_cloud.py with import-override pattern)
7. JS refactored into external app.js — done
8. Package renamed app/ → src/ — done
9. Gated module progression with pass/fail — done (80% threshold)
10. Retake with regenerated questions — done
11. Server-side session storage — done (Flask-Session + cachelib FileSystemCache)
12. Loading/progress UI — full-screen spinner implemented; needs incremental improvement

### Sprint 4 (In Progress)
13. Fill-in-the-blank one-word validation with inline inputs
14. Difficulty level selector (Easy/Moderate/Hard)
15. Background progress indicator replacing full-screen overlay
16. Lesson/quiz prompt engineering refinement

### Sprint 5–6 (Planned)
17. Multi-user accounts (Flask-Login + PostgreSQL)
18. Learner dashboard with progress tracking
19. Max 3 active lessons gating
20. Admin access control for lesson generation
21. Text-to-speech narration (opt-in)
22. PDF export for completed lessons
23. Mascot animation frames (idle/waiting/done)
24. Session cleanup (remove extracted_texts after lessons generated)

### Sprint 7–8 (Planned)
25. OCR for scanned PDFs
26. Badges/trophies for completed lessons
27. Source document referencing in lessons
28. Deployment to free-tier host
29. Final documentation and demo recording

### Post-Capstone / Stretch
30. YouTube or external resource integration
31. Short-answer (free-text) AI grading
32. Spaced repetition and review scheduling
33. Full adaptive study planner
34. Social features (friends, chat, share lessons)
35. Full offline mode (C/C++ rewrite without Ollama)

---

## 10. Testing Strategy

### 10.1 Unit Tests

Initial unit tests should cover:
- file extension validation,
- parser selection,
- text extraction helpers,
- prompt formatting,
- relevance label parsing,
- curriculum output schema validation.

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
3. ~~How many file types should be truly supported in the first sprint?~~ → **txt, md, pdf, docx** (implemented)
4. ~~Should OCR be postponed until after the main workflow works?~~ → **Postponed** to Sprint 7
5. ~~Should generated outputs be stored as JSON, Markdown, or database records?~~ → **JSON in Flask session (server-side via cachelib)**
6. ~~Should the companion be purely visual or tied to progress?~~ → Visual feedback with click-to-talk implemented; animation frames deferred to Sprint 6
7. ~~Which deployment platform is easiest for the final capstone demo?~~ → Render or Railway free tier TBD in Sprint 8
8. ~~What is the optimal model for lesson/quiz generation quality vs speed on 6GB VRAM?~~ → qwen3:0.6b chosen as placeholder; upgrade guidance documented (Sprint 4 prompt tuning ongoing)
9. ~~Should loading UI use full-screen overlay or background processing with stage indicator?~~ → Background processing with progress bar preferred (Sprint 4)
10. ~~How many mascot animation frames are needed for adequate visual feedback?~~ → TBD in Sprint 6

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
