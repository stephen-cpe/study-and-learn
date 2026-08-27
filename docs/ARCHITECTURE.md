# Architecture

> **The source code is the source of truth.** This document is an orientation
> map only and may lag behind the code. For anything specific, read the code.
> No line-number references are maintained here by design.

---

## 1. Overview

Study-and-Learn is an AI-powered educational web application that transforms uploaded study materials (PDFs, DOCX, PPTX, images, and text) into structured, interactive learning pathways. Using a Retrieval-Augmented Generation (RAG) architecture, the system grounds generated lessons, quizzes, and summaries in the user's documents rather than the AI's general training data.

The application features a retro-cyberpunk themed custom slide-deck engine, inline comprehension checkpoints, opt-in neural text-to-speech (TTS) narration, and global content-addressable deduplication.

---

## 2. High-Level Architecture

The application follows a service-oriented web architecture that separates HTTP routing from complex AI and document-processing logic.

* **Frontend:** Bootstrap 5 paired with a custom CSS/JS retro-themed slide-deck engine.
* **Backend:** Flask (Python 3.14) utilizing a strict Service Layer and Repository pattern.
* **Data Layer:** PostgreSQL for relational data (users, study paths, progress) and ChromaDB (local or cloud) for vector storage.
* **AI Integration:** Configurable local (Ollama) or cloud-based LLMs for summarization, curriculum generation, and OCR. A deterministic mock mode guarantees reliable offline testing.

### Core Workflow
1. **Ingestion & Deduplication:** A user submits a learning goal and up to five files. The system computes SHA-256 hashes to bypass redundant processing for previously seen documents.
2. **Extraction & OCR:** Text is extracted via standard parsers. If documents are scanned or image-based, an AI-powered local OCR pipeline extracts text, tables, and figures.
3. **RAG Indexing:** Extracted text is chunked, embedded, and stored in content-addressed vector collections.
4. **AI Analysis:** The system generates a summary and performs a relevance check. Weak matches gate further generation to save compute and prevent hallucinations — relevance gating blocks lesson generation for documents that do not match the learning goal, avoiding hallucinated study paths.
5. **Lesson Generation:** For valid matches, the system sequentially generates slide decks, inline checkpoints, and mixed-type quizzes. Opt-in TTS narration is generated asynchronously in a background worker.
6. **Interactive Learning:** Learners navigate the custom slide deck. Progression is gated by an 80% pass threshold on final quizzes.

---

## 3. Architecture Diagram

The following diagram illustrates the end-to-end processing pipeline, highlighting deduplication logic, OCR gating, and asynchronous TTS processing.

```mermaid
flowchart TD
A["Unified Form: Goal + Files"] --> B["POST /process Route"]
B --> BCHK{"File hash in<br/>ContentRegistry?<br/>(route-level dedup)"}
BCHK -->|Yes| D["Chunker: LangChain Splitter"]
BCHK -->|No| EXT["extract_text_with_vision()"]
EXT -->|.txt / .md| BASIC["Basic raw-text read"]
BASIC --> REG["register_content(hash, text)"]
REG --> D
EXT -->|.pdf / .docx / .pptx / images| CACHE{"Cached in<br/>ContentRegistry?<br/>(parser-level dedup)"}
CACHE -->|Yes| D
CACHE -->|No| TXT["Basic text-layer extraction"]
TXT --> VMODE{"File type?"}
VMODE -->|.png / .jpg / .jpeg| IMG["Images ALWAYS enter OCR loop"]
VMODE -->|.pdf / .docx / .pptx| OFULL{"OCR Config Enabled?"}
OFULL -->|No: Default| SKIP["Early return: basic text only"]
SKIP --> REG
OFULL -->|Yes| IMG
IMG --> OLOOP["OCR loop (per page/image)"]
OLOOP --> OMULT{"Full OCR Enabled?"}
OMULT -->|No| OTEXT["Local OCR: text mode only"]
OMULT -->|Yes| OALL["Local OCR: text + table + figure"]
OTEXT --> FMERGE
OALL --> FMERGE
FMERGE["merge OCR output"]
FMERGE --> FDESC{"Figure Desc Enabled?"}
FDESC -->|No| FSKIP["Cloud Vision SKIPPED"]
FSKIP --> DONE
FDESC -->|Yes| FIG["Cloud Vision: figure descriptions"]
FIG --> DONE["register_content & cleanup"]
DONE --> D
D --> E["Vector Store: Content-Keyed ChromaDB"]
E --> F["RAG Retriever: Multi-Collection top-k context + sources"]
F --> G["Summarizer"]
F --> H["Relevance Checker"]
F --> I["Curriculum Generator"]
G --> J["results.html: Summary, Relevance, Study Path"]
H -->|weak| J
H -->|partial/strong| J
I -->|if not weak| J
J --> K{"Weak match?"}
K -->|Yes| K2["Weak feedback card: gated"]
K -->|No| L{"Generate Interactive Lessons?"}
L --> M["Lesson Generator: slides + sources"]
L --> N["Quiz Generator: questions + checkpoints"]
M --> M2["Narration Script Generator"]
M2 --> M2b["Background TTS worker thread"]
M2b -->|"sets completion signal"| O
M2 -->|"if TTS disabled"| O
N --> O
O --> lessons.html
O["lessons.html: Module Grid + Gating"]
O --> P["lesson_deck.html: Custom Slide Deck + TTS Player"]
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

---

## 4. Software & Architectural Patterns

* **Model-View-Controller (MVC):** Flask routes act as thin controllers, delegating business logic to service modules and rendering Jinja/Bootstrap views.
* **Service Layer Pattern:** All AI, parsing, and RAG logic is isolated in `src/services/`. This enables independent unit testing, easy mocking, and provider swapping.
* **Repository / DAO Pattern:** Vector storage and database interactions are abstracted, decoupling ingestion from retrieval logic.
* **Content-Addressable Storage:** File hashes act as primary keys for vector collections, enabling global deduplication across users.
* **Mock Object Pattern:** Environment flags (`AI_MOCK=true`, `CI=true`) replace live LLM and vector calls in CI, guaranteeing deterministic, zero-cost, GPU-free test execution.

---

## 5. Key Engineering Highlights

### 5.1 Global Content-Addressable Deduplication
To prevent redundant, expensive OCR and embedding operations, the system computes SHA-256 hashes of all uploaded files. These hashes map to a `ContentRegistry` and dictate the naming convention of ChromaDB collections. If two users upload the same proprietary manual, the system processes it once and shares the vector index, drastically reducing latency and compute costs.

On-disk deduplication is enforced at the upload layer: files are saved with a hash-based filename (`<hash_prefix>_<safe_name>`), so a re-upload of the same content overwrites the same path rather than accumulating duplicate copies. If the hash is already registered in `ContentRegistry`, the uploaded file is deleted immediately and the cached extracted text is reused — no extraction, chunking, or embedding runs for duplicate uploads.

### 5.2 Source Provenance Pipeline & Cross-Module Chunk Dedup
A common failure mode in RAG systems is "lost provenance," where retrieved text is stripped of its metadata before reaching the LLM. A pipeline preserves chunk-level metadata (source hash, filename, chunk ID) through the LangChain retriever, into the lesson JSON, and finally to the frontend. This allows the "View Sources" modal to display exact document excerpts with zero risk of LLM hallucination.

To prevent content repetition across modules, a cross-module chunk dedup mechanism tracks which chunk IDs have been used by earlier modules. When generating lesson N+1, the retriever excludes chunks already consumed by modules 1..N, forcing each module to cover different document content. This directly addresses the problem of modules overlapping or repeating verbatim.

The RAG retrieval depth is configurable via the `RAG_TOP_K` environment variable (default 20 chunks per retrieval). The processing route uses a higher value (40) for summary and curriculum generation to give the model a broader view of the document's scope when deciding how many modules to create.

### 5.3 Configurable Context Window
The local Ollama API context window is configurable via the `OLLAMA_NUM_CTX` environment variable (default 131072, i.e. 128K tokens). This works across all Ollama Cloud models, which range from 128K to 1M context windows. The value controls how much document text the model can process per call.

### 5.4 Asynchronous TTS & Atomic Redirects
Generating neural audio for 5+ modules can take 45–90 minutes. Running this in the HTTP request thread causes timeouts; running it in a background thread requires a reliable completion signal so the frontend knows when to redirect.

The resolution is an **atomic database signal**. The background worker updates lesson statuses idempotently and sets a `generation_completed_at` timestamp in its `finally` block. The frontend polls this specific DB column via a dedicated endpoint, entirely decoupling the UI redirect logic from any shared cache state. This ensures the user is never stranded on a loading screen.

### 5.5 Configuration-Gated OCR Pipeline
Running local Vision models on every PDF page is memory-prohibitive in production. The extraction pipeline is multi-tiered: standard text-layer extraction runs universally, while AI-powered OCR (GLM-OCR) and Cloud Figure Description (Qwen3.5) are strictly gated behind environment flags. OCR images are passed to the model as base64-encoded `images` arrays in the Ollama API payload — not as file paths in the prompt text — ensuring the vision model actually receives the image content. ChromaDB cloud storage uses a fallback-tolerant toggle that reverts to local storage if cloud credentials fail, enabling cloud deployment without sacrificing local reliability.

---

## 6. Testing

The test suite is organized into three categories:

* **Unit Tests** verify isolated components such as file validation, document parsing, LangChain text splitting, prompt construction, AI client behavior, quiz generation, retrieval logic, and text-to-speech utilities.
* **Integration Tests** exercise Flask routes, form submissions, session management, SQLAlchemy models, and database transactions through the Flask test client. Each test replaces the production PostgreSQL database with an in-memory SQLite database, allowing the application to be tested without external infrastructure while still validating real database behavior.
* **Smoke Tests** verify that the application can complete its primary workflow, including document upload, lesson generation, quiz completion, grading, retake functionality, deck rendering, and the `/health` endpoint.

The test environment is fully isolated from production services. `AI_MOCK=true` replaces AI responses with deterministic mock data, while `CI=true` configures ChromaDB to use an ephemeral in-memory client. As a result, the complete test suite runs without GPUs, local Ollama models, external databases, or network access, making execution reproducible in CI. Regression tests guard known production defects (login GET redirect crash, TTS file-descriptor exhaustion, missing embedding-model detection, `/health` endpoint, etc.).

---

## 7. Known Risks & Mitigations

| Risk | Impact | Mitigation |
| :--- | :--- | :--- |
| **AI Output Inconsistency** | Poor pedagogical value | Strict RAG grounding; relevance gating; structured JSON prompting with fallbacks. |
| **Resource Limits (RAM)** | App crashes during OCR | Configuration-gated OCR pipeline; cloud-offloading for production. |
| **Session Leakage** | User A sees User B's data | Explicit session clearing on login; DB-backed multi-path isolation. |
| **TTS Service Dependency** | Narration fails | Graceful degradation; lessons remain fully functional without audio. |
| **Long-Running Generation** | User stranded on loading screen | Atomic DB redirect signals; 2-hour hard timeouts; background workers. |