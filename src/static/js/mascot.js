/**
 * Mascot manager — sprite-sheet state animation, CRT speech bubble,
 * click-to-talk, greeting wave on load, context-aware lines.
 *
 * The mascot is a <div class="mascot-sprite"> whose background-image is
 * a 1-row sprite sheet animated via CSS steps().  Switching states is
 * just a CSS class swap — no <img src> change, no GIF-restart jank.
 *
 * Idle chatter and click-to-talk lines are fetched from the backend
 * endpoint ``GET /mascot/line?context=<event>`` which calls the LLM
 * with the learner's memories + current study context.  On any fetch
 * error, the mascot falls back to a short static array so the robot
 * always has something to say.
 *
 * Speech bubble is styled as a 4:3 CRT monitor (see retro.css). Text is
 * rendered with a fast per-character "typewriter" effect using the
 * PressStart2P pixel font, with a blinking underscore caret at the end.
 */
(function () {
  'use strict';

  var VALID_MASCOT_STATES = [
    'idle', 'busy', 'busyB', 'busyC', 'happy', 'error', 'talk', 'wave'
  ];
  var _currentMascotState = null;
  var _mascotIntervalId = null;
  var _wavePlayed = false;

  // CRT typewriter settings (kept in one place so progress.js can match).
  var TYPEWRITER_CHAR_DELAY_MS = 25;   // "really quickly" feel

  // Static fallback lines — used when the /mascot/line endpoint fails.
  // These are generic enough to work without server context.
  var FALLBACK_MESSAGES = [
    'Ready to learn?',
    'Take a break!',
    'I see you studying...',
    'Upload & go!',
    'You got this!',
    'Need a hint? Click me.',
    'Knowledge: 0% (jk)',
    'I tell bad AI jokes.',
    'You are smarter!',
    '418: not a teapot.',
    'Big brain. Ready.',
    'Knowledge = power!'
  ];

  // Determine the page context for /mascot/line based on the current URL.
  function _detectContext() {
    var path = window.location.pathname;
    if (path === '/' || path === '/index') return 'idle';
    if (path.indexOf('/dashboard') !== -1) return 'dashboard';
    if (path.indexOf('/lessons') !== -1) return 'lessons';
    if (path.indexOf('/results') !== -1) return 'results';
    return 'idle';
  }

  // Fetch a personalized line from the server.  Returns a Promise that
  // resolves to a string — never rejects (falls back to a static line).
  function _fetchMascotLine(context) {
    return fetch('/mascot/line?context=' + encodeURIComponent(context),
                  { headers: { 'Accept': 'application/json' } })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        var text = (data && data.text) || '';
        if (!text) throw new Error('Empty response');
        // If the server says a specific mascot state, apply it
        if (data.state && data.state !== 'talk') {
          // Error context keeps the error state; others fall through
          // to the talk state which _mascotTalk sets anyway.
        }
        return text;
      })
      .catch(function () {
        // Fallback: pick a random static line
        return FALLBACK_MESSAGES[
          Math.floor(Math.random() * FALLBACK_MESSAGES.length)
        ];
      });
  }

  function typewriteInto(el, text) {
    if (!el) return Promise.resolve();
    if (!text) {
      el.textContent = '';
      return Promise.resolve();
    }
    el.textContent = '';
    el.setAttribute('data-bubble-text', text);
    return new Promise(function (resolve) {
      var i = 0;
      var caret = document.createElement('span');
      caret.className = 'bubble-caret';
      caret.setAttribute('aria-hidden', 'true');
      el.appendChild(caret);

      function step() {
        if (i >= text.length) {
          resolve();
          return;
        }
        var ch = text.charAt(i++);
        caret.insertAdjacentText('beforebegin', ch);
        setTimeout(step, TYPEWRITER_CHAR_DELAY_MS);
      }
      step();
    });
  }

  function getBubbleEls() {
    return {
      bubble: document.getElementById('speech-bubble'),
      text: document.getElementById('bubble-text')
    };
  }

  window.setMascotState = function (state) {
    var mascot = document.getElementById('robot-mascot');
    if (!mascot) return;

    var normalized = (state || 'idle').toLowerCase();
    if (VALID_MASCOT_STATES.indexOf(normalized) === -1) {
      normalized = 'idle';
    }
    if (_currentMascotState === normalized) return;

    _currentMascotState = normalized;
    // Remove all state classes
    var states = VALID_MASCOT_STATES;
    for (var s = 0; s < states.length; s++) {
      mascot.classList.remove('mascot-state-' + states[s]);
    }
    // Add the new one
    mascot.classList.add('mascot-state-' + normalized);
    var wrapper = mascot.parentElement;
    if (wrapper) wrapper.setAttribute('data-mascot-state', normalized);

    // Wave is a one-shot: when it finishes, fall back to idle.
    if (normalized === 'wave') {
      var onEnd = function () {
        mascot.removeEventListener('animationend', onEnd);
        if (_currentMascotState === 'wave') {
          window.setMascotState('idle');
        }
      };
      mascot.addEventListener('animationend', onEnd);
    }
  };

  window.initMascot = function () {
    var mascot = document.getElementById('robot-mascot');
    var bubble = document.getElementById('speech-bubble');
    var bubbleText = document.getElementById('bubble-text');
    if (!mascot || !bubble || !bubbleText) return;

    var _typewriterToken = 0;
    var _pageContext = _detectContext();

    window._mascotTalk = function (customMsg) {
      if (window._progressActive) return;
      var els = getBubbleEls();
      if (!els.bubble || !els.text) return;
      var token = ++_typewriterToken;
      els.bubble.classList.add('active');
      // Switch to talk state while typing (syncs the robot's body language)
      window.setMascotState('talk');

      // If a custom message was passed (e.g. from upload.js error handler),
      // use it directly — no fetch needed.
      if (customMsg) {
        typewriteInto(els.text, customMsg).then(function () {
          if (token !== _typewriterToken) return;
          setTimeout(function () {
            if (token !== _typewriterToken) return;
            if (window._progressActive) return;
            els.bubble.classList.remove('active');
            window.setMascotState('idle');
          }, 4000);
        });
        return;
      }

      // No custom message — fetch a personalized line from the server.
      _fetchMascotLine(_pageContext).then(function (line) {
        if (token !== _typewriterToken) return;  // a newer call superseded us
        typewriteInto(els.text, line).then(function () {
          if (token !== _typewriterToken) return;
          setTimeout(function () {
            if (token !== _typewriterToken) return;
            if (window._progressActive) return;
            els.bubble.classList.remove('active');
            window.setMascotState('idle');
          }, 4000);
        });
      });
    };

    function idleTalk() {
      if (!window._progressActive) {
        window._mascotTalk();
      }
    }

    // Greeting: play the wave one-shot on page load, then settle to idle.
    if (!_wavePlayed) {
      _wavePlayed = true;
      window.setMascotState('wave');
    } else {
      window.setMascotState('idle');
    }

    // Idle chatter after the wave settles
    _mascotIntervalId = setInterval(idleTalk, 15000);
    setTimeout(function () {
      if (!_wavePlayed) _wavePlayed = true;
      idleTalk();
    }, 3500);

    // Expose the typewriter so progress.js can reuse it.
    window._bubbleTypewrite = function (text) { return typewriteInto(bubbleText, text); };
    window._BUBBLE_TYPEWRITER_CHAR_DELAY_MS = TYPEWRITER_CHAR_DELAY_MS;
  };

  document.addEventListener('DOMContentLoaded', function () {
    if (document.getElementById('robot-mascot')) {
      window.initMascot();
    }
  });
})();
