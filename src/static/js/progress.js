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
  // Sticky-error window: when an ``error`` mascot_state arrives, we
  // ignore subsequent non-error cosmetic polls for this many ms so the
  // mascot-error.gif stays visible long enough for the user to read the
  // bubble message. Without this, a background worker (e.g. TTS) could
  // clobber the error state with a ``busy`` update on the very next
  // 2-second tick, making the error GIF flash and vanish instantly.
  var ERROR_STICKY_MS = 8000;
  var _errorShownAt = 0;

  window.generateTaskId = function () {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return 'task-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10);
  };

  // Phase 0 background resume (no backend change): the in-flight task_id
  // is persisted in sessionStorage so a refresh resumes the cosmetic poll
  // instead of losing everything. The server-side POST keeps running
  // regardless; completion is signaled durably via GET /tasks (the bell).
  var BG_KEY = 'sal_bg_task';
  window.saveBackgroundTask = function (kind, taskId) {
    try {
      sessionStorage.setItem(BG_KEY, JSON.stringify({
        kind: kind, taskId: taskId, startedAt: Date.now()
      }));
    } catch (e) { /* private mode — resume unavailable */ }
  };

  window.loadBackgroundTask = function () {
    try {
      var raw = sessionStorage.getItem(BG_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  };

  window.clearBackgroundTask = function () {
    try { sessionStorage.removeItem(BG_KEY); } catch (e) {}
  };

  // Resume a stored task after a refresh. The durable /tasks row is
  // authoritative: we only restart the cosmetic poll when the server
  // still reports the task as running. Finished, failed, or unknown
  // tasks clear the stored entry instead of polling a dead task forever
  // (the orphaned-poll bug: after a server restart the POST is gone but
  // the stored task_id + filesystem progress cache outlive it).
  // Mascot speech stays plain retro text — no emoji, no icons.
  window.resumeBackgroundTask = function () {
    var stored = window.loadBackgroundTask();
    if (!stored || !stored.taskId) return false;
    // Stale entries (older than 2h, the server hard-timeout) are dropped.
    if (Date.now() - (stored.startedAt || 0) > 7200000) {
      window.clearBackgroundTask();
      return false;
    }
    var onUploadPage = stored.kind === 'process' && document.getElementById('unified-form');
    var onResultsPage = stored.kind === 'generate' && document.getElementById('generate-lessons-btn');
    if (!onUploadPage && !onResultsPage) return false;

    function openButton(label, url) {
      if (!onResultsPage) return;
      var btn = document.getElementById('generate-lessons-btn');
      btn.textContent = label;
      btn.disabled = false;
      btn.addEventListener('click', function () {
        window.location.href = url;
      });
    }

    function startLivePoll() {
      window.setBubblePersistent('Resuming — still working...');
      window.showBubbleBar(0);
      window.startProcessProgressPoll(stored.taskId);
      if (onResultsPage) {
        var btn = document.getElementById('generate-lessons-btn');
        btn.disabled = true;
        btn.textContent = 'Working in background...';
      }
    }

    fetch('/tasks', { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var row = null;
        (data && data.tasks || []).forEach(function (t) {
          if (t.task_id === stored.taskId) row = t;
        });
        if (!row) {
          // Unknown to the server (DB reset, or never recorded) —
          // drop it rather than polling a task that can never resolve.
          window.clearBackgroundTask();
          return;
        }
        if (row.status !== 'running') {
          window.clearBackgroundTask();
          if (row.result_url && (onResultsPage || onUploadPage)) {
            window.setBubblePersistent(row.status === 'ready'
              ? 'Previous task finished — opening it now...'
              : 'Previous task did not finish — please retry.');
            if (row.status === 'ready') {
              if (onResultsPage) {
                openButton(stored.kind === 'generate' ? 'Open Lessons' : 'Open Results', row.result_url);
              } else {
                window.location.href = row.result_url;
              }
            }
          } else {
            window.setBubblePersistent(row.status === 'ready'
              ? 'Previous task finished — see Tasks up top.'
              : 'Previous task did not finish — please retry.');
          }
          return;
        }
        startLivePoll();
      })
      .catch(function () {
        // Offline/transient: fall back to the cosmetic poll; its
        // no-task auto-stop still bounds the damage.
        startLivePoll();
      });
    return true;
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
    var processErrorShownAt = 0;
    var PROCESS_ERROR_STICKY_MS = 8000;
    var _lastPct = 0;
    var _lastActivityAt = Date.now();  // reset whenever pct changes
    // Dead-task guard: the server deletes progress entries on completion
    // and a restarted server has no record of in-flight POSTs at all.
    // After several straight 'No task' answers, stop polling and drop a
    // matching stored entry instead of hitting /progress forever.
    var _noTaskStreak = 0;

    _processPollInterval = setInterval(function () {
      var elapsed = Date.now() - startTime;
      var idleMs = Date.now() - _lastActivityAt;
      // Stale hint only when the task has gone quiet for a while.  It is a
      // transient *hint*, not a permanent overwrite — as soon as the next
      // real progress update arrives it is replaced.
      if (elapsed > STALE_TIMEOUT_MS && idleMs > 30000) {
        window.setBubblePersistent('This is taking longer than expected \u2014 hang tight!');
        window.showBubbleBar(_lastPct >= 0 ? _lastPct : 50);
        // keep polling; do NOT return, so the very next real update replaces it
      }
      fetch('/progress?task_id=' + encodeURIComponent(taskId))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.stage === undefined || data.stage < 0) {
            _noTaskStreak += 1;
            if (_noTaskStreak >= 5) {
              window.stopProcessProgressPoll();
              try {
                var stored = window.loadBackgroundTask
                  ? window.loadBackgroundTask() : null;
                if (stored && stored.taskId === taskId) window.clearBackgroundTask();
              } catch (e) {}
            }
            return;
          }
          _noTaskStreak = 0;
          // Sticky-error for the process poll (upload/parse flow),
          // mirroring the generate-lessons poll. Prevents a
          // background task from clobbering mascot-error.gif.
          if (processErrorShownAt > 0) {
            var sinceError = Date.now() - processErrorShownAt;
            if (sinceError < PROCESS_ERROR_STICKY_MS && data.mascot_state !== 'error') {
              return;
            }
            if (data.mascot_state !== 'error') {
              processErrorShownAt = 0;
            }
          }
          if (data.mascot_state === 'error') {
            processErrorShownAt = Date.now();
          }

          // Real activity — reset the idle clock so the stale hint clears.
          var pct = (typeof data.pct === 'number') ? data.pct : _lastPct;
          if (pct !== _lastPct) { _lastActivityAt = Date.now(); }
          _lastPct = pct;

          window.setBubblePersistent(data.mascot || 'Processing your materials...');
          window.showBubbleBar(pct);
          // Map busy → variant A/B/C by progress % (same as generate poll).
          // Always force a busy/happy/error state while the task is running
          // so the sprite never falls back to idle mid-process.
          var procState = data.mascot_state || 'busy';
          if (procState === 'busy') {
            var procPct = pct;
            if (procPct >= 75) procState = 'busyC';
            else if (procPct >= 40) procState = 'busyB';
          }
          window.setMascotState(procState);
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
    // Phase 0: persist so a refresh resumes instead of losing the task.
    window.saveBackgroundTask('generate', taskId);

    var resolvedRedirectUrl = null;
    var resolvedPathId = null;

    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId }),
      keepalive: true
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (resp) {
        if (resp.redirect) {
          window.clearBackgroundTask();
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
    // 3+ modules with a cloud chat model can take 45-90 minutes end-
    // to-end (lessons + checkpoints + quiz + narration script +
    // edge-tts audio generation). The cap is now 2 hours
    // (7,200,000 ms). With this cap the user can reliably wait for
    // the slowest cloud-AI generation without being bounced.
    // If the server is genuinely dead, the user can navigate
    // away manually; the poll will simply stop without redirecting.
    var HARD_TIMEOUT_MS = 7200000;

    var _lastGenPct = 0;
    var _lastActivityAt = Date.now();  // reset whenever pct changes, below

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
    //     ignored entirely. (Historical note: this design replaced the
    //     removed 10-minute hard-timeout redirect; see ADR-026.) This
    //     preserves the live cosmetic
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
      var idleMs = Date.now() - _lastActivityAt;

      // Stale hint only when we have never received any progress AND the
      // task has gone quiet for a while.  It is a transient hint — the very
      // next real cosmetic update replaces it, so it never gets stuck.
      if (!_receivedValidProgress && elapsed > STALE_TIMEOUT_MS && idleMs > 30000 && !_progressTimedOut) {
        _progressTimedOut = true;
        window.setBubblePersistent('This is taking longer than expected \u2014 hang tight!');
        window.showBubbleBar(_lastGenPct >= 0 ? _lastGenPct : 50);
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

          // Real activity — reset the idle clock so the stale hint clears.
          var pctNow = (typeof data.pct === 'number') ? data.pct : _lastGenPct;
          if (pctNow !== _lastGenPct) { _lastActivityAt = Date.now(); }
          _lastGenPct = pctNow;

          // Sticky-error: if we showed an error recently, ignore
          // non-error cosmetic updates until the sticky window
          // expires. This prevents a background worker (e.g. TTS
          // processing the next module) from immediately overwriting
          // the mascot-error.gif with a busy update, which would make
          // the error flash and vanish before the user can read it.
          if (_errorShownAt > 0) {
            var sinceError = Date.now() - _errorShownAt;
            if (sinceError < ERROR_STICKY_MS && data.mascot_state !== 'error') {
              // Still inside the sticky window and this is a non-error
              // update — skip the mascot swap but keep polling.
              return;
            }
            // Window expired or a new error arrived — reset so future
            // busy/happy updates are honored normally.
            if (data.mascot_state !== 'error') {
              _errorShownAt = 0;
            }
          }
          if (data.mascot_state === 'error') {
            _errorShownAt = Date.now();
          }
          window.setBubblePersistent(data.mascot || 'Working on your lesson...');
          window.showBubbleBar(pctNow);
          if (data.mascot_state) {
            // Map busy → variant A/B/C by progress % so the 45-90 min
            // generation doesn't look frozen on one loop.  The backend
            // only sends 'busy'; the variant is a client-side refinement.
            // Always force a busy/happy/error state while generation runs
            // so the sprite never falls back to idle mid-task.
            var state = data.mascot_state;
            if (state === 'busy') {
              var pct = pctNow;
              if (pct >= 75) state = 'busyC';
              else if (pct >= 40) state = 'busyB';
              else state = 'busy';
            }
            window.setMascotState(state);
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
          // previous cache-based signal (JS checking ``data.done`` /
          // ``data.stage >= 4``),
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
