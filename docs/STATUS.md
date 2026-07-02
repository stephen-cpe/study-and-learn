# STATUS.md
Last Updated: 2026-06-27
Sprint: 8 (COMPLETE / SUBMISSION READY)
Last Task Completed: Sprint 8 cloud deployment to DigitalOcean (4 vCPU / 8 GB / 160 GB, $48/month) — Gunicorn (gthread, 1 worker, 8 threads) + Nginx + systemd + Let's Encrypt SSL + DuckDNS + CI/CD pipeline (test → deploy → smoke-test via GitHub Actions). Production bug fixes: (1) GET /login returning None (redirect to index); (2) TTS OSError [Errno 24] Too many open files (LimitNOFILE=65536 + loop.shutdown_asyncgens()); (3) Gunicorn max_requests=1000 killing TTS thread mid-generation (removed max_requests); (4) missing local Ollama embedding model on droplet (installed qwen3-embedding:0.6b for ChromaDB RAG retrieval); (5) empty ChromaDB Cloud collections from earlier failed generation (deleted + re-ingested); (6) /health endpoint added for CI/CD smoke-test. RAG retrieval with sources + TTS audio both verified working in production. Test suite: 445 passed (was 421; +24 tests across login GET redirect, /health endpoint, asyncgens drain, plus Sprint 8 final sweep).
Commit Message Suggestion: feat: cloud deployment to DigitalOcean + production bug fixes (login GET, TTS FD leak, max_requests, embedding model, /health endpoint)
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; use cloud models (gemma4:31b-cloud)
    for production quality
  - Session storage uses Flask-Session (cachelib FileSystemCache) by design — single-worker Gunicorn keeps all caching in one process. DB-backed session store is a future optimization, not a bug.
  - fpdf2 Latin-1 limitation: all AI-generated text in PDF export must pass through _clean()
    sanitizer (Unicode NFKD + explicit char mapping). WeasyPrint unavailable on Windows.
  - Edge-TTS requires Microsoft's online service; no offline fallback. Graceful failure
    already implemented (tts_enabled set to False on network error).
  - Speaker change in deck UI is cosmetic only — retake required to regenerate audio
    with new speaker. Labeled clearly in UI.
  - TTS bug-fix plan: all 11 items complete (path_id transport, audio-route fallback, retake
    redirect UX, flattened deck layout + narration regen, background TTS worker, checkpoint-
    before-narration ordering, removed auto-advance after Quick Check, cache→DB atomic redirect
    signal via generation_completed_at, 2-hour hard-timeout-no-redirect, two-poll parallel JS
    design, sticky-error window). See ADR-026 and DESIGN_AND_TESTING.md for the atomic DB-column
    redirect signal. Full debugging history is in git log (Sprint 7–8 commits).
  - ChromaDB backend is toggleable via CHROMA_DB env var (local default / cloud opt-in).
Pending Decisions:
   - none (deployment target locked: DigitalOcean, 4 vCPU / 8 GB RAM / 160 GB disk, $48/month; the 8 vCPU / 16 GB RAM / 320 GB SSD tier was rejected — DigitalOcean requires a $50 prepayment to unlock it)
Next 3 Tasks (Sprint 8):
   1. Submit capstone project.
   2. Present final demo.
   3. Post-capstone shutdown (destroy droplet/revoke keys).
