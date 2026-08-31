/**
 * Mascot manager — sprite-sheet state animation, CRT speech bubble,
 * click-to-talk, greeting wave on load.
 *
 * The mascot is a <div class="mascot-sprite"> whose background-image is
 * a 1-row sprite sheet animated via CSS steps().  Switching states is
 * just a CSS class swap — no <img src> change, no GIF-restart jank.
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

    // Short, witty idle/click lines that read well in a 4:3 CRT frame.
    var messages = [
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

    var _typewriterToken = 0;

    window._mascotTalk = function (customMsg) {
      if (window._progressActive) return;
      var els = getBubbleEls();
      if (!els.bubble || !els.text) return;
      var msg = customMsg || messages[Math.floor(Math.random() * messages.length)];
      var token = ++_typewriterToken;
      els.bubble.classList.add('active');
      // Switch to talk state while typing (syncs the robot's body language)
      window.setMascotState('talk');
      typewriteInto(els.text, msg).then(function () {
        if (token !== _typewriterToken) return;
        // After typing finishes, return to idle (or the previous state)
        setTimeout(function () {
          if (token !== _typewriterToken) return;
          if (window._progressActive) return;
          els.bubble.classList.remove('active');
          window.setMascotState('idle');
        }, 4000);
      });
    };

    function idleTalk() {
      if (!window._progressActive) {
        window._mascotTalk(messages[Math.floor(Math.random() * messages.length)]);
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
