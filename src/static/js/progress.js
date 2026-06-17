/**
 * Progress bar, polling, and speech-bubble display.
 */
(function () {
  'use strict';

  window._progressActive = false;
  window._generateRedirectUrl = '/lessons';

  var _progressInterval = null;
  var _progressTimedOut = false;
  var _receivedValidProgress = false;
  var _processPollInterval = null;

  window.generateTaskId = function () {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return 'task-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10);
  };

  window.setBubblePersistent = function (text) {
    window._progressActive = true;
    var bubble = document.getElementById('speech-bubble');
    var bubbleText = document.getElementById('bubble-text');
    if (bubble && bubbleText) {
      bubble.classList.add('active');
      if (typeof window._bubbleTypewrite === 'function') {
        window._bubbleTypewrite(text || 'Working...');
      } else {
        bubbleText.textContent = text || 'Working...';
      }
    }
  };

  window.showBubbleBar = function (pct) {
    var bar = document.getElementById('bubble-progress');
    var fill = document.getElementById('bubble-progress-fill');
    if (bar && fill) {
      bar.style.display = 'block';
      fill.style.width = (pct || 0) + '%';
    }
  };

  window.stopProgressPoll = function () {
    if (_progressInterval) {
      clearInterval(_progressInterval);
      _progressInterval = null;
    }
  };

  window.stopProcessProgressPoll = function () {
    if (_processPollInterval) {
      clearInterval(_processPollInterval);
      _processPollInterval = null;
    }
  };

  window.startProcessProgressPoll = function (taskId) {
    window.stopProcessProgressPoll();
    var startTime = Date.now();
    var STALE_TIMEOUT_MS = 120000;

    _processPollInterval = setInterval(function () {
      var elapsed = Date.now() - startTime;
      if (elapsed > STALE_TIMEOUT_MS) {
        window.stopProcessProgressPoll();
        window.setBubblePersistent('This is taking longer than expected \u2014 hang tight!');
        window.showBubbleBar(50);
        return;
      }
      fetch('/progress?task_id=' + encodeURIComponent(taskId))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.stage === undefined || data.stage < 0) return;
          window.setBubblePersistent(data.mascot || 'Processing your materials...');
          window.showBubbleBar(data.pct);
          window.setMascotState(data.mascot_state || 'busy');
        })
        .catch(function () {});
    }, 2000);
  };

  window.startGenerateLessons = function (url) {
    window.stopProgressPoll();
    _progressTimedOut = false;
    _receivedValidProgress = false;

    var taskId = window.generateTaskId();
    window.setBubblePersistent('Parsing docs...');
    window.showBubbleBar(0);

    var resolvedRedirectUrl = null;
    var resolvedPathId = null;

    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId })
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (resp) {
        if (resp.redirect) {
          resolvedRedirectUrl = resp.redirect;
          // Extract path_id from the redirect URL for the status poll.
          // Format: /lessons?path_id=<uuid>  (or /lessons/<i>?path_id=...)
          try {
            var u = new URL(resp.redirect, window.location.origin);
            resolvedPathId = u.searchParams.get('path_id');
          } catch (e) { /* ignore */ }
        }
      })
      .catch(function () {});

    var startTime = Date.now();
    var STALE_TIMEOUT_MS = 60000;
    // The hard cap was originally 10 minutes (600000ms), then 30
    // minutes (1800000ms). Both were too aggressive for cloud AI:
    // 3+ modules with gemma3:27b-cloud can take 45-90 minutes end-
    // to-end (lessons + checkpoints + quiz + narration script +
    // edge-tts audio generation). The cap is now 2 hours
    // (7,200,000 ms). With this cap the user can reliably wait for
    // the slowest cloud-AI generation without being bounced.
    // If the server is genuinely dead, the user can navigate
    // away manually; the poll will simply stop without redirecting.
    var HARD_TIMEOUT_MS = 7200000;

    // Two parallel polls, two different purposes:
    //
    // (A) ``/progress?task_id=<taskId>`` polls the legacy
    //     progress_tracker cache every 2 seconds for COSMETIC
    //     bubble updates only (mascot text + progress bar fill).
    //     This endpoint is updated by the request handler on every
    //     ``update_progress(task_id, n)`` call so the user sees
    //     real-time stage transitions ("Chunking + indexing...",
    //     "Scanning concepts...", "Generating lesson...", etc.).
    //     Critically, this poll NEVER triggers a redirect — the
    //     legacy ``data.done`` / ``data.stage >= 4`` signals are
    //     ignored entirely. This eliminates the 10-minute hard-
    //     timeout redirect bug while preserving the live cosmetic
    //     feedback the user expects during the 45-90 minute
    //     cloud-AI generation.
    //
    // (B) ``/lessons/generation-status?path_id=<id>&task_id=<id>``
    //     polls the canonical StudyPath.generation_completed_at
    //     column for the REDIRECT DECISION only. This poll cannot
    //     start until the POST response has returned (which sets
    //     resolvedPathId). Until then, the user has already been
    //     receiving cosmetic updates from poll (A), so there is no
    //     visibility gap.
    //
    // Both polls share the same setInterval ticker. Poll (A) always
    // runs. Poll (B) runs only after resolvedPathId is set. The
    // hard timeout (2 hours) applies to the whole ticker and stops
    // BOTH polls with a non-redirecting message.

    _progressInterval = setInterval(function () {
      var elapsed = Date.now() - startTime;

      if (!_receivedValidProgress && elapsed > STALE_TIMEOUT_MS && !_progressTimedOut) {
        _progressTimedOut = true;
        window.setBubblePersistent('This is taking longer than expected \u2014 hang tight!');
        window.showBubbleBar(50);
        // Don't return — keep polling both signals.
      }

      // Hard timeout: stop polling and tell the user we are still
      // working. We do NOT redirect to /lessons here because that
      // would 302-bounce to /results (no lessons yet) and the user
      // would lose their place. The poll simply stops; the lesson
      // generation continues on the server. The user can navigate
      // to /dashboard or refresh /results manually at any time.
      if (elapsed > HARD_TIMEOUT_MS) {
        window.stopProgressPoll();
        window.setBubblePersistent(
          'Still working — generation may take a while. ' +
          'You can navigate away and check back later.'
        );
        return;
      }

      // ── Poll (A): cosmetic updates from /progress ─────────────
      // Always runs. Updates the bubble mascot text + progress bar
      // fill. NEVER triggers a redirect — the legacy data.done /
      // data.stage >= 4 signals are ignored by design.
      fetch('/progress?task_id=' + encodeURIComponent(taskId),
        { headers: { 'Accept': 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data) return;
          if (data.stage === undefined || data.stage < 0) return;
          _receivedValidProgress = true;
          window.setBubblePersistent(data.mascot || 'Working on your lesson...');
          window.showBubbleBar(data.pct || 0);
          if (data.mascot_state) {
            window.setMascotState(data.mascot_state);
          }
        })
        .catch(function () {});

      // ── Poll (B): redirect decision from /lessons/generation-status ─
      // Only runs once resolvedPathId is set. The redirect is the
      // ONLY signal we act on; cosmetic updates from this endpoint
      // are ignored because poll (A) already provides them with
      // lower latency and finer granularity.
      if (!resolvedPathId) return;

      var statusUrl = '/lessons/generation-status?path_id='
        + encodeURIComponent(resolvedPathId)
        + '&task_id=' + encodeURIComponent(taskId);

      fetch(statusUrl, { headers: { 'Accept': 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data) return;

          // Redirect signal ONLY — ``generation_completed`` is
          // sourced from ``StudyPath.generation_completed_at`` (the
          // canonical, atomic, ACID flag set by whichever component
          // finishes last: request handler for TTS-disabled, TTS
          // worker finally block for TTS-enabled). This replaces the
          // previous ``progress_tracker.mark_done()`` cache signal,
          // which had a race condition that caused the redirect to
          // fire prematurely in some environments.
          if (data.generation_completed === true) {
            window.stopProgressPoll();
            var finalUrl = resolvedRedirectUrl || window._generateRedirectUrl;
            window.location.href = finalUrl;
          }
        })
        .catch(function () {});
    }, 2000);
  };
})();
