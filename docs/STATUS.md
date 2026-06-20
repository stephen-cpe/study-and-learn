# STATUS.md
Last Updated: 2026-06-20
Sprint: 8 (ACTIVE)
Last Task Completed: Final doc sweep fixes — (1) updated test count from 381 to 406 across SRS.md (§8.1), DESIGN_AND_TESTING.md (§5), and TODO.md (Sprint 6 DoD line, Sprint 6 task line, Core MVP Backlog line) to match actual pytest output (406 passed, verified by running full suite); (2) aligned TODO.md sprint User Story headers to match SRS §7 epic assignments — Sprint 4 now lists US-018..US-022 (was US-018..US-020), Sprint 5 now lists US-023..US-031 (was US-027..US-031), Sprint 7 now lists US-022+US-036..US-041 (was US-036..US-038). All 8 sprint headers verified to match SRS §7 epics exactly.
Commit Message Suggestion: docs: update test count to 406 and align TODO sprint headers with SRS §7 epics
Known Issues:
  - AI output consistency: qwen3:0.6b is placeholder-only; use cloud models (gemma3:27b-cloud)
    for production quality
  - Session storage still FileSystemCache (DB-backed migration planned post-capstone)
  - fpdf2 Latin-1 limitation: all AI-generated text in PDF export must pass through _clean()
    sanitizer (Unicode NFKD + explicit char mapping). WeasyPrint unavailable on Windows.
  - Edge-TTS requires Microsoft's online service; no offline fallback. Graceful failure
    already implemented (tts_enabled set to False on network error).
  - Speaker change in deck UI is cosmetic only — retake required to regenerate audio
    with new speaker. Labeled clearly in UI.
  - TTS bug-fix plan: ALL 5 TASKS COMPLETE + 2 follow-up fixes + 3 race-condition/timeout fixes landed.
      1. path_id transport contract (query string OR body) — DONE
      2. audio-route path_id fallback to most recent active path — DONE
      3. retake redirect UX (server returns redirect URL; client navigates) — DONE
      4. flattened deck layout with unique data-deck-index per slide;
         narration script regenerated to include checkpoint/quiz/results entries — DONE
      5. background TTS worker with idempotency, failure resilience, and
         /lessons/generation-status polling; per-card audio badges; audio
         route returns 202 (pending) vs 200 (ready) vs 404 (disabled) — DONE
      6. (follow-up) orchestrator now builds checkpoints BEFORE narration so
         the TTS manifest's slide_index keys actually correspond to the
         deck's deck_index values for Quick Check / Final Quiz / Results
         slots. — DONE
      7. (follow-up) removed the 3-second setTimeout that auto-advanced the
         deck after a Quick Check answer. The user is now in full control:
         first Continue click shows feedback, second click (or right-arrow
         key) advances. — DONE
      8. (race-condition fix, attempt 1) progress_tracker gained mark_done()
         and update_cosmetic() helpers; the JS poll fired the redirect on
         data.done === true. THIS FIX WAS INCOMPLETE — the redirect
         still fired prematurely under TTS-enabled paths because the
         cache-based signal was subject to timing-dependent races. — DONE
         but superseded by fix #9
      9. (race-condition fix, attempt 2 — the permanent fix) Replaced the
         cache-based data.done signal with an atomic database column
         StudyPath.generation_completed_at. The TTS worker's finally
         block, the route's else branch (TTS disabled), and the spawn
         wrapper's defensive catch all set this column. The JS polls
         /lessons/generation-status (which reads the column) and
         redirects when generation_completed === true. No shared cache
         state, no race conditions, atomic with the lesson-dict
         persistence. Alembic migration d4e5f6a7b8c9 adds the column;
         init_db.sql updated for fresh installs. — DONE
     10. (premature-redirect root cause — finally) progress.js had a
         10-minute HARD_TIMEOUT_MS safety net that called
         window.location.href = '/lessons' on expiry — which 302-bounced
         to /results because lessons were not yet saved. With cloud AI
         (gemma3:27b-cloud) and 3+ modules, full generation can take
         45-90 minutes end-to-end (lessons + checkpoints + quiz +
         narration script + edge-tts audio). The cap is now 2 hours
         (7,200,000 ms) AND the hard-timeout block no longer
         redirects — it simply stops polling and shows a "still
         working" message. Additionally, SEND_FILE_MAX_AGE_DEFAULT=0
         is set in src/__init__.py so the dev server no longer serves
         stale static files (which had masked previous fixes as the
         browser kept using the old cached JS). — DONE
     11. (UX polish — two-poll design) After fix #10, the JS no
         longer updated the bubble mascot text during the 45-90
         minute wait because the resolvedPathId gate suppressed
         the only remaining poll. Restored a parallel /progress?
         task_id=<id> poll that runs on every tick for COSMETIC
         bubble updates (mascot text + progress bar) only. The
         redirect decision lives exclusively on /lessons/generation-
         status and is the only path that can call
          window.location.href. Two polls, two purposes, no shared
          state. Tests assert both endpoints are polled AND that
          the /progress poll never triggers a redirect. — DONE
  - ChromaDB backend is now toggleable via CHROMA_DB env var (local default
    / cloud opt-in). CHROMA_DB=cloud uses chromadb.CloudClient with three
    credentials: CHROMA_CLOUD_API_KEY, CHROMA_CLOUD_CONNECTION_STRING
    (Chroma tenant ID), and CHROMA_COLLECTION_NAME (Chroma Cloud database
    name — the app's per-file doc_<hash> collections live inside it). On
    ANY cloud failure (missing/empty/invalid credential, CloudClient
    constructor error, or heartbeat() connectivity probe failure),
    get_chroma_client() logs a clear actionable error and reverts to the
    local PersistentClient. CI=true ALWAYS overrides CHROMA_DB to force
    in-memory EphemeralClient (tests stay isolated/offline). Verified
    against live Chroma Cloud (Sprint 8). See ADR-027 for the full
    decision/tradeoff analysis. NOTE: AI_BACKEND=cloud (cloud Ollama)
    was also verified separately — these are independent toggles.
Pending Decisions:
   - none (deployment target locked: DigitalOcean primary, AWS EC2 secondary)
Next 3 Tasks (Sprint 8):
   1. General QA pass: manual smoke test of all user flows; log defects
   2. Deploy to DigitalOcean (or AWS EC2) cloud VPS
   3. Final documentation review, demo recording, and capstone submission
