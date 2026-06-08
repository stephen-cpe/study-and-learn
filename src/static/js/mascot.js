/**
 * Mascot manager — idle/state animation, speech bubble, click-to-talk.
 */
(function () {
  'use strict';

  var VALID_MASCOT_STATES = ['idle', 'busy', 'happy'];
  var _currentMascotState = null;
  var _mascotGifFailed = false;
  var _mascotIntervalId = null;

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
      mascot.classList.remove('mascot-state-idle', 'mascot-state-busy', 'mascot-state-happy');
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

    var messages = [
      'Ready to learn something cool today?',
      'Don\'t forget to take breaks \u2014 your brain needs a breather!',
      'I\'m watching your progress... no pressure though.',
      'Upload some materials and I\'ll turn them into pure knowledge!',
      'You got this! ... Whatever \"this\" is.',
      'Need a hint? Just click me. I don\'t bite.',
      'Loading knowledge... 0% complete. Just kidding!',
      'I\'d tell you a joke about AI, but I\'m still learning them.',
      'Fun fact: You\'re smarter than you were 5 minutes ago.',
      'Error 418: I\'m a robot, not a teapot.',
      'My brain is the size of a planet and I use it to help you study.',
      'If knowledge is power, you\'re about to become a superhero.'
    ];

    window._mascotTalk = function (customMsg) {
      if (window._progressActive) return;
      bubbleText.textContent = customMsg || messages[Math.floor(Math.random() * messages.length)];
      bubble.classList.add('active');
      setTimeout(function () { bubble.classList.remove('active'); }, 4000);
    };

    function idleTalk() {
      if (!window._progressActive) {
        window._mascotTalk(messages[Math.floor(Math.random() * messages.length)]);
      }
    }

    _mascotIntervalId = setInterval(idleTalk, 15000);
    setTimeout(idleTalk, 1500);
  };

  document.addEventListener('DOMContentLoaded', function () {
    if (document.getElementById('robot-mascot')) {
      window.initMascot();
    }
  });
})();
