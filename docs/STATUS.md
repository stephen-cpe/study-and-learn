# STATUS.md
Last Updated: 2026-06-15
Sprint: 8 (ACTIVE)
Last Task Completed: Remove 3-second auto-advance timer on Quick Check slides; user clicks Continue twice (first to see feedback, second to advance) or uses the right-arrow key
Commit Message Suggestion: fix(deck): remove 3s auto-advance on Quick Check; user controls progression
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
  - TTS bug-fix plan: ALL 5 TASKS COMPLETE + 2 follow-up fixes landed.
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
Pending Decisions:
  - Deployment target: Confirm Render vs Railway for final submission (Sprint 8)
  - Badge/trophy design: deferred to Sprint 8 (lower priority than deployment)
  - Demo document set: content and domain TBD
Next 3 Tasks (Sprint 8):
  1. General QA pass: manual smoke test of all user flows; log defects
  2. Deploy to Render or Railway free tier with AI_MOCK=true fallback
