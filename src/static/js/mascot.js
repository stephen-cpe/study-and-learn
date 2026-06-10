/**
 * Mascot manager — idle/state animation, CRT speech bubble, click-to-talk.
 *
 * Speech bubble is styled as a 4:3 CRT monitor (see retro.css). Text is
 * rendered with a fast per-character "typewriter" effect using the
 * PressStart2P pixel font, with a blinking underscore caret at the end.
 */
(function () {
  'use strict';

  var VALID_MASCOT_STATES = ['idle', 'busy', 'happy', 'error'];
  var _currentMascotState = null;
  var _mascotGifFailed = false;
  var _mascotIntervalId = null;

  // CRT typewriter settings (kept in one place so progress.js can match).
  var TYPEWRITER_CHAR_DELAY_MS = 25;   // "really quickly" feel
  var TYPEWRITER_CARET_HTML = '<span class="bubble-caret" aria-hidden="true"></span>';

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

    var src = mascot.getAttribute('data-' + normalized + '-src');
    if (src && mascot.src.indexOf(src) === -1) {
      _currentMascotState = normalized;
      mascot.classList.remove(
        'mascot-state-idle',
        'mascot-state-busy',
        'mascot-state-happy',
        'mascot-state-error'
      );
      mascot.classList.add('mascot-state-' + normalized);
      var wrapper = mascot.parentElement;
      if (wrapper) wrapper.setAttribute('data-mascot-state', normalized);
      mascot.src = src;
    }
  };

  window.initMascot = function () {
    var mascot = document.getElementById('robot-mascot');
    var bubble = document.getElementById('speech-bubble');
    var bubbleText = document.getElementById('bubble-text');
    if (!mascot || !bubble || !bubbleText) return;

    if (!_mascotGifFailed) {
      mascot.addEventListener('error', function onMascotErr() {
        var fallback = mascot.getAttribute('data-fallback-src');
        if (fallback && mascot.src.indexOf(fallback) === -1) {
          _mascotGifFailed = true;
          mascot.removeEventListener('error', onMascotErr);
          mascot.src = fallback;
        }
      });
    }

    window.setMascotState('idle');

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
      typewriteInto(els.text, msg).then(function () {
        // Ignore the result if a newer call has started typing.
        if (token !== _typewriterToken) return;
        // Auto-hide after 4s only if no progress has started.
        setTimeout(function () {
          if (token !== _typewriterToken) return;
          if (window._progressActive) return;
          els.bubble.classList.remove('active');
        }, 4000);
      });
    };

    function idleTalk() {
      if (!window._progressActive) {
        window._mascotTalk(messages[Math.floor(Math.random() * messages.length)]);
      }
    }

    _mascotIntervalId = setInterval(idleTalk, 15000);
    setTimeout(idleTalk, 1500);

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
