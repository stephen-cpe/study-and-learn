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
      document.getElementById('loadingOverlay').classList.add('active');
      var formData = new FormData();
      formData.append('learning_goal', goalInput.value.trim());
      selectedFiles.forEach(function (file) {
        formData.append('files', file);
      });
      fetch(form.action, { method: 'POST', body: formData })
        .then(function (response) {
          if (response.redirected) {
            window.location.href = response.url;
            return;
          }
          window.location.reload();
        })
        .catch(function () {
          alert('Upload failed. Please try again.');
          document.getElementById('loadingOverlay').classList.remove('active');
        });
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

    window.gradeQuiz = function (answers) {
      fetch('/lessons/' + moduleIndex + '/grade', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          answers: answers,
          checkpoint_answers: checkpointAnswers
        })
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
    document.querySelectorAll('.module-title.raw-md').forEach(function (el) {
      if (typeof marked !== 'undefined') {
        el.innerHTML = marked.parse(el.innerText);
        el.classList.remove('raw-md');
      }
    });

    var generateBtn = document.getElementById('generate-lessons-btn');
    if (generateBtn) {
      generateBtn.addEventListener('click', function () {
        document.getElementById('loadingOverlay').classList.add('active');
        document.getElementById('progress-text').textContent =
          'Generating lesson content, quizzes, and checkpoints...';
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = generateBtn.dataset.generateUrl;
        document.body.appendChild(form);
        form.submit();
      });
    }
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
  });

})();
