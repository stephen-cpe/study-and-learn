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
      bubbleText.textContent = text;
      bubble.classList.add('active');
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
    window.setBubblePersistent('Reading through your uploaded materials and extracting text...');
    window.showBubbleBar(0);

    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId })
    })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (resp) {
        if (resp.redirect) {
          window._generateRedirectUrl = resp.redirect;
        }
      })
      .catch(function () {});

    var startTime = Date.now();
    var STALE_TIMEOUT_MS = 60000;

    _progressInterval = setInterval(function () {
      var elapsed = Date.now() - startTime;

      if (!_receivedValidProgress && elapsed > STALE_TIMEOUT_MS && !_progressTimedOut) {
        _progressTimedOut = true;
        window.stopProgressPoll();
        window.setBubblePersistent('This is taking longer than expected \u2014 hang tight!');
        window.showBubbleBar(50);
        return;
      }

      fetch('/progress?task_id=' + encodeURIComponent(taskId))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.stage === undefined || data.stage < 0) return;
          _receivedValidProgress = true;
          window.setBubblePersistent(data.mascot || 'Working on your lesson...');
          window.showBubbleBar(data.pct);
          window.setMascotState(data.mascot_state || 'busy');
          if (data.stage >= 4) {
            window.stopProgressPoll();
            window.location.href = window._generateRedirectUrl;
          }
        })
        .catch(function () {});
    }, 2000);
  };
})();
