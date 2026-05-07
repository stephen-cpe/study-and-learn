# Software Requirements Specification (SRS)
# Study-and-Learn

**Version:** 1.0-draft  
**Project type:** AI-assisted learning web application  
**Capstone track:** Software system / AI system  
**Repository name:** `study-and-learn`  
**Primary development approach:** Spec-Driven Development with AI tooling support

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

1. enter a learning goal,
2. upload one or more supported study documents,
3. extract text from those documents, if time permits, do an OCR as well for complete understanding of the documents.
4. generate an AI-assisted lessons with summary at the end,
5. make sure lessons are properly cited based on the materials and documents so the learner could verify by reading and reviewing the documents.
5. check whether the uploaded documents match the learning goal.
6. generate a structured study path.
7. generate questions, tests, and quizzes to test learner's understanding.
8. view the results in a guided web interface.
9. check if learner wants to do the lessons again until they are satisfied with their progress

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
| Embeddings / retrieval | pgvector or ChromaDB | Decide during implementation spike |
| Database | PostgreSQL preferred if using pgvector | Stores uploads, metadata, outputs, and possibly embeddings |
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
├── app/
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
├── task-board/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── .github/
│   └── workflows/
│       └── tests.yml
├── requirements.txt
├── README.md
└── run.py
```

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
| FR-004 | The system shall allow the user to upload one or more documents. | Must |
| FR-005 | The system shall support `.txt`, `.md`, `.pdf`, `.docx`, `.html`, and `.odt` if feasible. | Must |
| FR-006 | The system shall reject unsupported file types with a clear message. | Must |
| FR-007 | The system should show uploaded file names and processing status. | Should |

### 5.3 Document Ingestion and Text Extraction

| ID | Requirement | Priority |
|---|---|---|
| FR-008 | The system shall extract readable text from supported documents. | Must |
| FR-009 | The system shall store extracted text or processed text metadata. | Must |
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
| FR-027 | The UI should use a retro-inspired visual style. | Should |
| FR-028 | The UI may include a pixel companion or mascot. | Could |

### 5.8 Admin / Editing Features

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

### Epic 5: UX and Demo Polish

| Story ID | User Story | Acceptance Criteria |
|---|---|---|
| US-012 | As a learner, I want the app to feel simple and guided. | UI has clear step-by-step flow |
| US-013 | As a learner, I want the product to feel friendly and motivating. | Retro theme is visible and not distracting |
| US-014 | As a reviewer, I want the demo to show the full workflow. | Demo data and script cover goal input → upload → summary → relevance → study path |

---

## 8. MVP Scope

### 8.1 Must-Have MVP

- Flask app skeleton.
- Bootstrap UI.
- Learning goal form.
- Document upload.
- File type validation.
- Text extraction for at least `.txt`, `.md`, `.pdf`, and `.docx`.
- AI summary generation through Ollama or a replaceable AI client.
- Relevance check.
- Study path generation.
- Results page.
- Basic persistence for uploaded metadata and generated outputs.
- pytest test suite.
- GitHub Actions test workflow.
- Static public task board.
- Design and testing document.

### 8.2 Should-Have MVP Polish

- Retro visual theme.
- Simple mascot/companion graphic or placeholder.
- Upload status messages.
- Generated output formatting.
- Demo seed files.
- Error handling for AI/model unavailable.
- Basic smoke tests.

### 8.3 Not Official MVP / Stretch

- Quizzes.
- Progress tracking.
- YouTube integration.
- AI-generated slides.
- AI-generated TTS narration.
- Full OCR for scanned PDFs.
- Adaptive difficulty by age group.
- Multi-user accounts.
- Rich companion behavior.
- Export to PDF or presentation.

---

## 9. Scope-Creep Ladder

Ranked from easier to harder:

1. Static mascot image or pixel avatar.
2. Retro theme improvements.
3. Better prompt templates.
4. Editable generated output fields.
5. Simple quiz generation.
6. Basic progress checklist.
7. Export generated plan as Markdown.
8. Export generated plan as HTML.
9. Admin review/edit screen.
10. Simple slide-style lesson pages.
11. More file formats and robust parsing.
12. Embeddings/retrieval with pgvector or ChromaDB.
13. OCR for scanned PDFs.
14. Learner profile / difficulty level adaptation.
15. YouTube or external resource integration.
16. AI-generated presentation deck.
17. AI-generated subtitles.
18. AI-generated TTS narration.
19. Full adaptive study planner.
20. Multi-user accounts and authentication.

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

1. Should the first prototype use pgvector or ChromaDB?
2. Which Ollama model gives acceptable local results on the target hardware?
3. How many file types should be truly supported in the first sprint?
4. Should OCR be postponed until after the main workflow works?
5. Should generated outputs be stored as JSON, Markdown, or database records?
6. Should the companion be purely visual or tied to progress?
7. Which deployment platform is easiest for the final capstone demo?

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
