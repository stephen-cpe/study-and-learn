(function () {
  'use strict';

  /* ── Helpers ─────────────────────────────────────────── */

  var moduleIndex = null;
  var checkpointAnswers = {};

  function getModuleIndex() {
    var el = document.querySelector('.deck-container');
    return el ? parseInt(el.dataset.moduleIndex) : null;
  }

  /* ── Format slide text (lesson_deck) ─────────────────── */

  function formatSlideText() {
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
  }

  /* ── Results markdown (results.html) ─────────────────── */

  function parseMarkdown(elementId) {
    var el = document.getElementById(elementId);
    if (!el || typeof marked === 'undefined') return;
    el.innerHTML = marked.parse(el.innerText.trim());
    el.classList.remove('raw-md');
  }

  /* ── Upload / Index page (index.html) ────────────────── */

  function initUploadPage() {
    var fileInput = document.getElementById('files');
    var fileList = document.getElementById('selected-files-list');
    var form = document.getElementById('unified-form');
    var selectedFiles = [];
    var MAX_FILES = 5;

    function renderFileList() {
      fileList.innerHTML = '';
      if (selectedFiles.length === 0) return;
      selectedFiles.forEach(function (file, index) {
        var li = document.createElement('li');
        li.className = 'file-item d-flex justify-content-between align-items-center p-2 mb-2';
        li.innerHTML =
          '<span class="text-truncate">' +
          '\uD83D\uDCC4 ' + file.name +
          ' <small class="text-muted">(' + (file.size / 1024).toFixed(1) + ' KB)</small></span>' +
          '<button type="button" class="btn btn-sm btn-outline-danger ms-2 remove-btn" data-index="' + index + '">\u2716</button>';
        fileList.appendChild(li);
      });
      document.querySelectorAll('.remove-btn').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          var idx = parseInt(e.currentTarget.dataset.index);
          selectedFiles.splice(idx, 1);
          if (selectedFiles.length < MAX_FILES) {
            fileInput.disabled = false;
            fileInput.title = '';
          }
          renderFileList();
        });
      });
    }

    fileInput.addEventListener('change', function (e) {
      var newFiles = Array.from(e.target.files);
      newFiles.forEach(function (file) {
        var exists = selectedFiles.some(function (f) {
          return f.name === file.name && f.size === file.size;
        });
        if (!exists && selectedFiles.length < MAX_FILES) {
          selectedFiles.push(file);
        }
      });
      if (selectedFiles.length >= MAX_FILES) {
        fileInput.disabled = true;
        fileInput.title = 'Maximum ' + MAX_FILES + ' files reached';
      }
      renderFileList();
      fileInput.value = '';
    });

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var goalInput = document.getElementById('learning_goal');
      if (!goalInput.value.trim()) {
        goalInput.focus();
        return;
      }
      if (selectedFiles.length === 0) {
        fileInput.focus();
        return;
      }
      var taskId = generateTaskId();
      setBubblePersistent('Receiving your study materials...');
      showBubbleBar(0);
      var formData = new FormData();
      formData.append('learning_goal', goalInput.value.trim());
      formData.append('task_id', taskId);
      selectedFiles.forEach(function (file) {
        formData.append('files', file);
      });
      fetch(form.action, { method: 'POST', body: formData })
        .then(function (response) {
          if (response.ok) {
            var ct = (response.headers.get('content-type') || '');
            if (ct.indexOf('application/json') !== -1) {
              return response.json().then(function (data) {
                if (data.redirect) {
                  window.location.href = data.redirect;
                } else if (data.error) {
                  _mascotTalk(data.error);
                  showBubbleBar(0);
                  _progressActive = false;
                }
              });
            }
            window.location.href = response.url;
            return;
          }
          response.json().then(function (data) {
            var msg = (data && data.error) ? data.error : 'Upload failed. Please try again.';
            _mascotTalk(msg);
            showBubbleBar(0);
            _progressActive = false;
          }).catch(function () {
            _mascotTalk('Upload failed. Please try again.');
            showBubbleBar(0);
            _progressActive = false;
          });
        })
        .catch(function () {
          _mascotTalk('Network error. Please try again.');
          showBubbleBar(0);
          _progressActive = false;
        });

      startProcessProgressPoll(taskId);
    });
  }

  /* ── Deck page (lesson_deck.html) ────────────────────── */

  function initDeckPage() {
    moduleIndex = getModuleIndex();
    if (moduleIndex === null) return;

    var deck = new StudyAndLearnDeck({
      onSlideChange: function (event) {
        var state = event.slide.dataset.state;
        if (state === 'checkpoint-blocked' || state === 'quiz-blocked') {
          var sc = event.slide.querySelector('.scroll-container');
          if (sc) sc.scrollTo(0, 0);
        }
      }
    });

    window.gradeCheckpoint = function (slideIndex, userValue, feedbackEl, callback) {
      fetch('/lessons/' + moduleIndex + '/grade', {
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
      fetch('/lessons/' + moduleIndex + '/grade', {
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
  }

  function retakeLesson(mIdx) {
    var btnRetake = document.getElementById('btn-retake');
    btnRetake.disabled = true;
    btnRetake.textContent = 'Regenerating...';

    fetch('/lessons/' + mIdx + '/retake', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
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

  /* ── Results page (results.html) ─────────────────────── */

  function initResultsPage() {
    if (typeof marked !== 'undefined') {
      marked.setOptions({ breaks: true, gfm: true });
    }
    parseMarkdown('summary-content');
    parseMarkdown('relevance-content');

    var suggestedEl = document.getElementById('suggested-materials');
    if (suggestedEl) {
      var t = suggestedEl.innerHTML;
      t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      t = t.replace(/\*(.+?)\*/g, '<em>$1</em>');
      t = t.replace(/__(.+?)__/g, '<u>$1</u>');
      t = t.replace(/`(.+?)`/g, '<code>$1</code>');
      t = t.replace(/^\s*\*\s+/gm, '\u2022 ');
      suggestedEl.innerHTML = t;
    }
    document.querySelectorAll('.module-title.raw-md').forEach(function (el) {
      if (typeof marked !== 'undefined') {
        el.innerHTML = marked.parse(el.innerText);
        el.classList.remove('raw-md');
      }
    });

    var generateBtn = document.getElementById('generate-lessons-btn');
    if (generateBtn) {
      generateBtn.addEventListener('click', function () {
        generateBtn.disabled = true;
        generateBtn.textContent = 'Generating...';
        startGenerateLessons(generateBtn.dataset.generateUrl);
      });
    }
  }

  /* ── Process / Upload with Progress ─────────────────── */

  var _processPollInterval = null;

  function startProcessProgressPoll(taskId) {
    stopProcessProgressPoll();
    var startTime = Date.now();
    var STALE_TIMEOUT_MS = 120000;

    _processPollInterval = setInterval(function () {
      var elapsed = Date.now() - startTime;
      if (elapsed > STALE_TIMEOUT_MS) {
        stopProcessProgressPoll();
        setBubblePersistent('This is taking longer than expected — hang tight!');
        showBubbleBar(50);
        return;
      }

      fetch('/progress?task_id=' + encodeURIComponent(taskId))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.stage === undefined || data.stage < 0) return;
          setBubblePersistent(data.mascot || 'Processing your materials...');
          showBubbleBar(data.pct);
        })
        .catch(function () {});
    }, 2000);
  }

  function stopProcessProgressPoll() {
    if (_processPollInterval) {
      clearInterval(_processPollInterval);
      _processPollInterval = null;
    }
  }

  /* ── Generate Lessons with Progress ─────────────────── */

  var _progressInterval = null;
  var _progressTimedOut = false;
  var _receivedValidProgress = false;
  var _progressActive = false;
  var _mascotIntervalId = null;

  function generateTaskId() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return 'task-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10);
  }

  function stopProgressPoll() {
    if (_progressInterval) {
      clearInterval(_progressInterval);
      _progressInterval = null;
    }
  }

  function setBubblePersistent(text) {
    _progressActive = true;
    var bubble = document.getElementById('speech-bubble');
    var bubbleText = document.getElementById('bubble-text');
    if (bubble && bubbleText) {
      bubbleText.textContent = text;
      bubble.classList.add('active');
    }
  }

  function showBubbleBar(pct) {
    var bar = document.getElementById('bubble-progress');
    var fill = document.getElementById('bubble-progress-fill');
    if (bar && fill) {
      bar.style.display = 'block';
      fill.style.width = (pct || 0) + '%';
    }
  }

  function startGenerateLessons(url) {
    stopProgressPoll();
    _progressTimedOut = false;
    _receivedValidProgress = false;

    var taskId = generateTaskId();
    setBubblePersistent('Reading through your uploaded materials and extracting text...');
    showBubbleBar(0);

    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId })
    }).catch(function () {});

    var startTime = Date.now();
    var STALE_TIMEOUT_MS = 60000;

    _progressInterval = setInterval(function () {
      var elapsed = Date.now() - startTime;

      if (!_receivedValidProgress && elapsed > STALE_TIMEOUT_MS && !_progressTimedOut) {
        _progressTimedOut = true;
        stopProgressPoll();
        setBubblePersistent('This is taking longer than expected \u2014 hang tight!');
        showBubbleBar(50);
        return;
      }

      fetch('/progress?task_id=' + encodeURIComponent(taskId))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.stage === undefined || data.stage < 0) return;
          _receivedValidProgress = true;
          setBubblePersistent(data.mascot || 'Working on your lesson...');
          showBubbleBar(data.pct);
          if (data.stage >= 4) {
            stopProgressPoll();
            window.location.href = '/lessons';
          }
        })
        .catch(function () {});
    }, 2000);
  }

  /* ── Mascot ──────────────────────────────────────────── */

  function initMascot() {
    var mascot = document.getElementById('robot-mascot');
    var bubble = document.getElementById('speech-bubble');
    var bubbleText = document.getElementById('bubble-text');
    if (!mascot || !bubble || !bubbleText) return;

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

    function idleTalk() {
      if (!_progressActive) {
        _mascotTalk(messages[Math.floor(Math.random() * messages.length)]);
      }
    }

    window._mascotTalk = function (customMsg) {
      if (_progressActive) return;
      bubbleText.textContent = customMsg || messages[Math.floor(Math.random() * messages.length)];
      bubble.classList.add('active');
      setTimeout(function () { bubble.classList.remove('active'); }, 4000);
    };

    _mascotIntervalId = setInterval(idleTalk, 15000);
    setTimeout(idleTalk, 1500);
  }

  /* ── Boot ────────────────────────────────────────────── */

  document.addEventListener('DOMContentLoaded', function () {
    if (document.getElementById('unified-form')) {
      initUploadPage();
    }
    if (document.getElementById('summary-content')) {
      initResultsPage();
    }
    if (document.querySelector('.deck-container')) {
      formatSlideText();
      initDeckPage();
    }
    if (document.getElementById('robot-mascot')) {
      initMascot();
    }
  });

})();
