/**
 * Deck page — checkpoint grading, quiz grading, retake, and answer dump.
 */
(function () {
  'use strict';

  var pathId = null;
  var moduleIndex = null;
  var checkpointAnswers = {};

  function getModuleIndex() {
    var el = document.querySelector('.deck-container');
    return el ? parseInt(el.dataset.moduleIndex) : null;
  }

  function getPathId() {
    var el = document.querySelector('.deck-container');
    return el ? (el.dataset.pathId || null) : null;
  }

  window.formatSlideText = function () {
    document.querySelectorAll(
      '.slide li, ' +
      '.slide .slide-notes, ' +
      '.slide .example-body, ' +
      '.slide .subtitle, ' +
      '.question-prompt, ' +
      '.checkpoint-feedback'
    ).forEach(function (el) {
      var text = el.textContent;
      text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
      text = text.replace(/__(.+?)__/g, '<u>$1</u>');
      text = text.replace(/`(.+?)`/g, '<code>$1</code>');
      text = text.replace(/^\s*\*\s+/gm, '\u2022 ');
      el.innerHTML = text;
    });
  };

  window.initDeckPage = function () {
    moduleIndex = getModuleIndex();
    pathId = getPathId();
    if (moduleIndex === null) return;

    var deck = new window.StudyAndLearnDeck({
      onSlideChange: function (event) {
        var state = event.slide.dataset.state;
        if (state === 'checkpoint-blocked' || state === 'quiz-blocked') {
          var sc = event.slide.querySelector('.scroll-container');
          if (sc) sc.scrollTo(0, 0);
        }
      }
    });

    window.gradeCheckpoint = function (slideIndex, userValue, feedbackEl, callback) {
      var url = '/lessons/' + moduleIndex + '/grade';
      if (pathId) url += '?path_id=' + encodeURIComponent(pathId);
      fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          answers: [],
          checkpoint_answers: Object.fromEntries([[String(slideIndex), userValue]])
        })
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var cpr = data.checkpoint_results || [];
          var result = cpr.find(function (r) { return String(r.slide_index) === String(slideIndex); });
          if (result) {
            feedbackEl.style.display = 'block';
            feedbackEl.className = 'checkpoint-feedback ' + (result.correct ? 'correct' : 'incorrect');
            feedbackEl.textContent = (result.correct ? 'Correct! ' : 'Incorrect. ') + (result.explanation || '');
          }
          checkpointAnswers[slideIndex] = userValue;
          callback();
        })
        .catch(function () {
          checkpointAnswers[slideIndex] = userValue;
          callback();
        });
    };

    window.gradeQuiz = function (answers, fillBlankAnswers) {
      var body = {
        answers: answers,
        checkpoint_answers: checkpointAnswers
      };
      if (fillBlankAnswers && Object.keys(fillBlankAnswers).length > 0) {
        body.fill_blank_answers = fillBlankAnswers;
      }
      var url = '/lessons/' + moduleIndex + '/grade';
      if (pathId) url += '?path_id=' + encodeURIComponent(pathId);
      fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
        .then(function (r) { return r.json(); })
        .then(function (data) { deck.showResults(data); })
        .catch(function () { alert('Error grading quiz. Please try again.'); });
    };

    /* Bind checkpoint Continue buttons */
    document.querySelectorAll('.checkpoint-slide .btn-submit-quiz').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        deck.advanceFromCheckpoint(e.currentTarget);
      });
    });

    /* Bind quiz Submit Answers button */
    var quizSubmit = document.querySelector('.quiz-slide .btn-submit-quiz');
    if (quizSubmit) {
      quizSubmit.addEventListener('click', function () {
        deck.submitFinalQuiz();
      });
    }

    /* Bind retake button */
    var retakeBtn = document.getElementById('btn-retake');
    if (retakeBtn) {
      retakeBtn.addEventListener('click', function () {
        retakeLesson(moduleIndex);
      });
    }

    /* Dump all lesson answers to console for testing */
    var quizData = [], cpData = [];
    document.querySelectorAll('.quiz-question').forEach(function (el) {
      quizData.push({
        id: el.dataset.qid,
        type: el.dataset.qtype,
        answer: el.dataset.answer,
        prompt: (el.querySelector('.q-prompt') || {}).textContent
      });
    });
    document.querySelectorAll('.checkpoint-slide').forEach(function (el) {
      var opts = [];
      el.querySelectorAll('.checkpoint-option').forEach(function (o) { opts.push(o.textContent); });
      cpData.push({
        slide: el.dataset.checkpoint,
        answer: el.dataset.answer,
        correctText: opts[parseInt(el.dataset.answer)] || null,
        prompt: (el.querySelector('.question-prompt') || {}).textContent,
        options: opts
      });
    });
    if (quizData.length || cpData.length) {
      console.log('%c=== LESSON ANSWERS ===', 'font-size:16px;font-weight:bold;color:#00b4d8');
      if (quizData.length) { console.log('%cQuiz:', 'font-weight:bold'); console.table(quizData); }
      if (cpData.length) { console.log('%cCheckpoints:', 'font-weight:bold'); console.table(cpData); }
    }
  };

  function retakeLesson(mIdx) {
    var btnRetake = document.getElementById('btn-retake');
    btnRetake.disabled = true;
    btnRetake.textContent = 'Regenerating...';

    fetch('/lessons/' + mIdx + '/retake', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path_id: pathId })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          window.location.reload();
        } else {
          alert('Error regenerating quiz. Please try again.');
          btnRetake.disabled = false;
          btnRetake.textContent = 'Retake Lesson';
        }
      })
      .catch(function () {
        btnRetake.disabled = false;
        btnRetake.textContent = 'Retake Lesson';
      });
  }

  function initSourceToggles() {
    var overlay = document.getElementById('sources-overlay');
    var openBtn = document.getElementById('sources-btn');
    var closeBtn = document.getElementById('sources-close');

    if (!overlay || !openBtn) return;

    openBtn.addEventListener('click', function () {
      overlay.style.display = 'flex';
    });

    function closeOverlay() {
      overlay.style.display = 'none';
    }

    closeBtn.addEventListener('click', closeOverlay);
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeOverlay();
    });

    overlay.querySelectorAll('.source-toggle-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var entry = btn.closest('.source-entry');
        var preview = entry.querySelector('.source-preview');
        var full = preview.querySelector('.source-full');
        var ellipsis = preview.querySelector('.source-ellipsis');
        var isExpanded = preview.dataset.expanded === 'true';
        if (isExpanded) {
          full.style.display = 'none';
          if (ellipsis) ellipsis.style.display = '';
          preview.dataset.expanded = 'false';
          btn.textContent = 'Show more';
        } else {
          full.style.display = '';
          if (ellipsis) ellipsis.style.display = 'none';
          preview.dataset.expanded = 'true';
          btn.textContent = 'Show less';
        }
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (document.querySelector('.deck-container')) {
      window.formatSlideText();
      window.initDeckPage();
      initSourceToggles();
    }
  });
})();
