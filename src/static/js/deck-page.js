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
    // NOTE: this formatter rewrites elements via textContent → innerHTML,
    // which DESTROYS any child <input>/<select> elements. It must only
    // ever target text-only elements — never .q-option labels (they wrap
    // the quiz radio/checkbox inputs) and never .results-detail (its
    // graded HTML is injected after formatting runs).
    document.querySelectorAll(
      '.slide li, ' +
      '.slide .slide-notes, ' +
      '.slide .example-body, ' +
      '.slide .subtitle, ' +
      '.question-prompt, ' +
      '.checkpoint-feedback, ' +
      '.q-prompt, ' +
      '.checkpoint-option, ' +
      '.q-ordering-item, ' +
      '.q-matching-left'
    ).forEach(function (el) {
      var text = el.textContent;
      // Protect LaTeX math spans BEFORE the lightweight markdown regexes
      // run — `*`/`__` patterns would otherwise corrupt expressions like
      // `$a*b$` or `$x_{i}$`. Placeholders are restored before sanitize so
      // KaTeX auto-render sees the original `$...$` in the text nodes.
      var mathStore = [];
      function stash(m) {
        mathStore.push(m);
        return '@@DECKMATH' + (mathStore.length - 1) + '@@';
      }
      text = text.replace(/\$\$[\s\S]+?\$\$/g, stash);
      text = text.replace(/\\\[[\s\S]+?\\\]/g, stash);
      text = text.replace(/\\\((.+?)\\\)/g, stash);
      text = text.replace(/\$[^$\n]+?\$/g, stash);
      text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
      text = text.replace(/__(.+?)__/g, '<u>$1</u>');
      text = text.replace(/`(.+?)`/g, '<code>$1</code>');
      text = text.replace(/^\s*\*\s+/gm, '\u2022 ');
      text = text.replace(/@@DECKMATH(\d+)@@/g, function (m, i) {
        return mathStore[parseInt(i, 10)] || m;
      });
      el.innerHTML = (typeof DOMPurify !== 'undefined')
        ? DOMPurify.sanitize(text)
        : text;
    });
    // Render math AFTER sanitize+insert: KaTeX writes its own DOM directly
    // so its output never passes through the sanitizer.
    window.renderDeckMath(document.body);
  };

  // Render `$...$` / `$$...$$` / `\(...\)` / `\[...\]` math via KaTeX
  // auto-render. Decorative only — never throws, never blocks the deck.
  window.renderDeckMath = function (root) {
    if (typeof renderMathInElement === 'undefined') return;
    try {
      renderMathInElement(root || document.body, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '$', right: '$', display: false },
          { left: '\\(', right: '\\)', display: false },
          { left: '\\[', right: '\\]', display: true }
        ],
        throwOnError: false
      });
    } catch (e) { /* math must never break the lesson */ }
  };

  window.initDeckPage = function () {
    moduleIndex = getModuleIndex();
    pathId = getPathId();
    if (moduleIndex === null) return;

    // Hydrate checkpointAnswers from any persisted answers on the lesson
    // dict so a resumed session credits the user for checkpoints they
    // answered in a prior visit. The deck container carries these as a
    // JSON data-checkpoint-answers attribute ({} when none). Keys are
    // checkpoint slide_indices (strings) and values are the user's
    // selections (ints for mcq/cloze, booleans for true_false).
    var containerEl = document.querySelector('.deck-container');
    if (containerEl) {
      try {
        var raw = containerEl.dataset.checkpointAnswers;
        if (raw) {
          var parsed = JSON.parse(raw);
          if (parsed && typeof parsed === 'object') {
            Object.keys(parsed).forEach(function (k) {
              checkpointAnswers[String(k)] = parsed[k];
            });
          }
        }
      } catch (e) { /* malformed attribute — start empty */ }
    }

    var deck = new window.StudyAndLearnDeck({
      onSlideChange: function (event) {
        var state = event.slide.dataset.state;
        if (state === 'checkpoint-blocked' || state === 'quiz-blocked') {
          var sc = event.slide.querySelector('.scroll-container');
          if (sc) sc.scrollTo(0, 0);
        }
      }
    });

    window.deckGoToSlide = function(idx) {
      deck.goToSlide(idx);
    };

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
            if (window.renderDeckMath) window.renderDeckMath(feedbackEl);
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
        .then(function (data) {
          // Stage 2 spoken results: the announcement replaces the generic
          // results-slot narration (same voice, no overlap). Suppress the
          // results audio that showResults() would otherwise trigger via
          // deckSlideChanged, then play the announcement when ready. If
          // synthesis fails, fall back to the results-slot audio so the
          // learner is never left in silence.
          var wantAnnounce = !!(data && data.announcement && data.announcement.available);
          if (wantAnnounce) { window.__ttsSuppressNext = true; }
          deck.showResults(data);
          if (window.renderDeckMath) window.renderDeckMath(document.body);
          // Inline fast-path: grade may already carry a synthesized
          // audio_url (zero gap). Otherwise fetch POST /tts/announce,
          // else fall back to the results-slot audio.
          function playUrl(url) {
            if (!url) return false;
            if (typeof window.__ttsPlayUrl === 'function') {
              window.__ttsPlayUrl(url);
            } else {
              var p = document.getElementById('tts-player');
              if (!p) return false;
              p.src = url; p.load(); p.play().catch(function () {});
            }
            return true;
          }
          function playResultsFallback() {
            if (typeof window.__ttsPlayResultsFallback === 'function') {
              window.__ttsPlayResultsFallback();
            }
          }
          try {
            if (wantAnnounce) {
              if (data.announcement.audio_url) {
                playUrl(data.announcement.audio_url);
              } else {
                fetch('/tts/announce', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    path_id: pathId,
                    module_index: moduleIndex,
                    kind: 'lesson_complete'
                  })
                }).then(function (r) { return r.json(); }).then(function (a) {
                  if (a && a.ok && a.audio_url) {
                    playUrl(a.audio_url);
                  } else {
                    playResultsFallback();
                  }
                }).catch(function () {
                  playResultsFallback();
                });
              }
            }
          } catch (e) { /* announcements must never break grading */ }
        })
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

    /* Bind Start Over button */
    var restartBtn = document.getElementById('restart-deck-btn');
    if (restartBtn) {
      restartBtn.addEventListener('click', function(e) {
        e.preventDefault();
        if (window.deckGoToSlide) window.deckGoToSlide(0);
        var saveUrl = restartBtn.dataset.saveUrl || '';
        if (saveUrl) {
          fetch(saveUrl, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({slide_index: 0})
          }).catch(function() {});
        }
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
          // Server tells us where to go: the deck for the retaken module,
          // starting from slide 0. The server has already reset deck_position
          // and persisted the regenerated quiz/checkpoints/slides.
          var target = data.redirect ||
            ('/lessons/' + mIdx + (pathId ? '?path_id=' + encodeURIComponent(pathId) : ''));
          window.location.href = target;
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

  function initClozeSelects() {
    document.querySelectorAll('.cloze-select, .checkpoint-select, .q-matching-select').forEach(function (select) {
      // Matching selects arrive pre-matched server-side; reflect that
      // immediately so the answered styling is truthful on load.
      // (Ordering ranks are hidden inputs — no change listener needed.)
      if (select.value !== '') select.classList.add('has-value');
      select.addEventListener('change', function () {
        select.classList.toggle('has-value', select.value !== '');
      });
    });
  }

  /* Touch (finger) drag for reorder controls — mobile-safe complement to
     the HTML5 mouse drag above and the up/down buttons. Pointer Events
     carry touch/pen drags; a touchstart fallback covers older browsers.
     Mouse pointers are ignored here so laptop/desktop behavior is
     byte-for-byte unchanged (HTML5 DnD path above). Buttons remain the
     precise path on every device; finger-drag is the fast path. */
  function enableTouchDrag(list, rowSelector, onDrop) {
    var dragRow = null;

    function clearTarget() {
      list.querySelectorAll('.drag-over').forEach(function (el) { el.classList.remove('drag-over'); });
    }

    function targetFromPoint(x, y) {
      var el = null;
      try { el = document.elementFromPoint(x, y); } catch (err) { return null; }
      if (!el || !el.closest) return null;
      var row = el.closest(rowSelector);
      return (row && list.contains(row)) ? row : null;
    }

    function autoScroll(y) {
      var scroller = list.closest('.scroll-container');
      if (!scroller) return;
      var r = scroller.getBoundingClientRect();
      if (y < r.top + 56) scroller.scrollTop -= 14;
      else if (y > r.bottom - 56) scroller.scrollTop += 14;
    }

    function start(row) {
      if (!row || dragRow) return;
      dragRow = row;
      requestAnimationFrame(function () { if (dragRow) dragRow.classList.add('dragging'); });
    }

    function move(x, y) {
      if (!dragRow) return;
      clearTarget();
      var t = targetFromPoint(x, y);
      if (t && t !== dragRow) t.classList.add('drag-over');
      autoScroll(y);
    }

    function end(x, y) {
      if (!dragRow) return;
      var src = dragRow;
      dragRow = null;
      src.classList.remove('dragging');
      var t = (x === undefined) ? null : targetFromPoint(x, y);
      clearTarget();
      if (t && t !== src) onDrop(src, t, y);
    }

    var usePointer = ('PointerEvent' in window);
    list.querySelectorAll('.q-drag-handle').forEach(function (handle) {
      if (usePointer) {
        handle.addEventListener('pointerdown', function (e) {
          if (e.pointerType === 'mouse') return;
          e.preventDefault();
          start(handle.closest(rowSelector));
        });
      } else {
        handle.addEventListener('touchstart', function (e) {
          if (e.touches.length !== 1) return;
          e.preventDefault();
          start(handle.closest(rowSelector));
        }, { passive: false });
      }
    });
    if (usePointer) {
      document.addEventListener('pointermove', function (e) {
        if (!dragRow) return;
        move(e.clientX, e.clientY);
      });
      document.addEventListener('pointerup', function (e) {
        if (!dragRow) return;
        end(e.clientX, e.clientY);
      });
      document.addEventListener('pointercancel', function () { end(); });
    } else {
      document.addEventListener('touchmove', function (e) {
        if (!dragRow || e.touches.length !== 1) return;
        e.preventDefault();
        move(e.touches[0].clientX, e.touches[0].clientY);
      }, { passive: false });
      document.addEventListener('touchend', function (e) {
        if (!dragRow) return;
        var t = e.changedTouches[0];
        end(t.clientX, t.clientY);
      });
      document.addEventListener('touchcancel', function () { end(); });
    }
  }

  /* Ordering: drag handle + up/down buttons reorder rows in the DOM.
     Rank = DOM position (badge + hidden .q-order-select value stay in
     sync). data-item (original display index) never changes, so the
     deck-engine grading mapping is untouched. Buttons are the
     touch/keyboard-safe path; drag handles serve mouse users. */
  function reindexOrderingList(list) {
    var rows = list.querySelectorAll('.q-ordering-row');
    rows.forEach(function (row, pos) {
      var hidden = row.querySelector('.q-order-select');
      if (hidden) hidden.value = String(pos + 1);
      var badge = row.querySelector('.q-position-badge');
      if (badge) badge.textContent = String(pos + 1);
      var up = row.querySelector('.q-move-up');
      var down = row.querySelector('.q-move-down');
      if (up) up.disabled = (pos === 0);
      if (down) down.disabled = (pos === rows.length - 1);
    });
  }

  function initOrderingControls() {
    var draggedRow = null;
    document.querySelectorAll('.ordering-list').forEach(function (list) {
      reindexOrderingList(list);
      list.addEventListener('click', function (e) {
        var btn = e.target.closest('.q-move-btn');
        if (!btn || btn.disabled) return;
        var row = btn.closest('.q-ordering-row');
        if (!row) return;
        var dir = parseInt(btn.dataset.move, 10) || 0;
        var sibling = dir < 0 ? row.previousElementSibling : row.nextElementSibling;
        while (sibling && !sibling.classList.contains('q-ordering-row')) {
          sibling = dir < 0 ? sibling.previousElementSibling : sibling.nextElementSibling;
        }
        if (!sibling) return;
        if (dir < 0) list.insertBefore(row, sibling);
        else list.insertBefore(row, sibling.nextElementSibling);
        reindexOrderingList(list);
      });
      list.querySelectorAll('.q-drag-handle').forEach(function (handle) {
        handle.addEventListener('dragstart', function (e) {
          draggedRow = handle.closest('.q-ordering-row');
          try { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', ''); } catch (err) {}
          requestAnimationFrame(function () { if (draggedRow) draggedRow.classList.add('dragging'); });
        });
        handle.addEventListener('dragend', function () {
          if (draggedRow) draggedRow.classList.remove('dragging');
          draggedRow = null;
          list.querySelectorAll('.drag-over').forEach(function (el) { el.classList.remove('drag-over'); });
        });
      });
      list.querySelectorAll('.q-ordering-row').forEach(function (row) {
        row.addEventListener('dragover', function (e) {
          if (!draggedRow || draggedRow === row) return;
          e.preventDefault();
          row.classList.add('drag-over');
        });
        row.addEventListener('dragleave', function () { row.classList.remove('drag-over'); });
        row.addEventListener('drop', function (e) {
          if (!draggedRow || draggedRow === row) return;
          e.preventDefault();
          var rect = row.getBoundingClientRect();
          var after = (e.clientY - rect.top) > rect.height / 2;
          list.insertBefore(draggedRow, after ? row.nextElementSibling : row);
          row.classList.remove('drag-over');
          reindexOrderingList(list);
        });
      });
      // Finger-drag (touch/pen only; mouse keeps the HTML5 path above).
      enableTouchDrag(list, '.q-ordering-row', function (src, target, y) {
        var rect = target.getBoundingClientRect();
        var after = (y - rect.top) > rect.height / 2;
        list.insertBefore(src, after ? target.nextElementSibling : target);
        reindexOrderingList(list);
      });
    });
  }

  /* Matching: rows stay fixed (lefts), the right-side answers move.
     Up/down buttons and drag-swap exchange two rows' select values, so
     the deck-engine collector (reads .q-matching-select values) and
     screen-reader semantics are unchanged. */
  function swapMatchingRows(rowA, rowB) {
    if (!rowA || !rowB || rowA === rowB) return;
    var selA = rowA.querySelector('.q-matching-select');
    var selB = rowB.querySelector('.q-matching-select');
    if (!selA || !selB) return;
    var tmp = selA.value;
    selA.value = selB.value;
    selB.value = tmp;
    selA.classList.add('has-value');
    selB.classList.add('has-value');
  }

  function initMatchingControls() {
    var dragSrcRow = null;
    document.querySelectorAll('.matching-list').forEach(function (list) {
      list.addEventListener('click', function (e) {
        var btn = e.target.closest('.q-move-btn');
        if (!btn || btn.disabled) return;
        var row = btn.closest('.q-matching-row');
        if (!row) return;
        var dir = parseInt(btn.dataset.move, 10) || 0;
        var sibling = dir < 0 ? row.previousElementSibling : row.nextElementSibling;
        while (sibling && !sibling.classList.contains('q-matching-row')) {
          sibling = dir < 0 ? sibling.previousElementSibling : sibling.nextElementSibling;
        }
        if (!sibling) return;
        swapMatchingRows(row, sibling);
      });
      list.querySelectorAll('.q-drag-handle').forEach(function (handle) {
        handle.addEventListener('dragstart', function (e) {
          dragSrcRow = handle.closest('.q-matching-row');
          try { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', ''); } catch (err) {}
          requestAnimationFrame(function () { if (dragSrcRow) dragSrcRow.classList.add('dragging'); });
        });
        handle.addEventListener('dragend', function () {
          if (dragSrcRow) dragSrcRow.classList.remove('dragging');
          dragSrcRow = null;
          list.querySelectorAll('.drag-over').forEach(function (el) { el.classList.remove('drag-over'); });
        });
      });
      list.querySelectorAll('.q-matching-row').forEach(function (row) {
        row.addEventListener('dragover', function (e) {
          if (!dragSrcRow || dragSrcRow === row) return;
          e.preventDefault();
          row.classList.add('drag-over');
        });
        row.addEventListener('dragleave', function () { row.classList.remove('drag-over'); });
        row.addEventListener('drop', function (e) {
          if (!dragSrcRow || dragSrcRow === row) return;
          e.preventDefault();
          swapMatchingRows(dragSrcRow, row);
          row.classList.remove('drag-over');
        });
      });
      // Finger-drag swap (touch/pen only; mouse keeps the HTML5 path above).
      enableTouchDrag(list, '.q-matching-row', function (src, target) {
        swapMatchingRows(src, target);
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (document.querySelector('.deck-container')) {
      window.formatSlideText();
      window.initDeckPage();
      initSourceToggles();
      initClozeSelects();
      initOrderingControls();
      initMatchingControls();
    }
  });

  (function initTTSPlayer() {
    var container = document.querySelector('.deck-container');
    if (!container || container.dataset.ttsEnabled !== 'true') return;

    var player   = document.getElementById('tts-player');
    var toggle   = document.getElementById('tts-toggle-btn');
    var label    = document.getElementById('tts-label');
    var muted    = false;
    var moduleIndex = container.dataset.moduleIndex;
    var pathId   = container.dataset.pathId || '';

    function audioUrl(deckIndex) {
      return '/lessons/' + moduleIndex + '/audio/' + deckIndex
             + '?path_id=' + encodeURIComponent(pathId);
    }

    function playSlide(deckIndex) {
      // Suppressed once when a lesson_complete announcement replaces the
      // generic results-slot narration (set by gradeQuiz before
      // showResults triggers this via deckSlideChanged). Consumed even
      // when muted so the flag never leaks into later navigation.
      if (window.__ttsSuppressNext) {
        window.__ttsSuppressNext = false;
        return;
      }
      if (muted || !player) return;
      player.src = audioUrl(deckIndex);
      player.load();
      player.play().catch(function() {});
    }

    // Stage 2 hook: gradeQuiz plays announcement clips through the same
    // player so mute + single-audio-element semantics hold.
    window.__ttsSuppressNext = false;
    window.__ttsPlayResultsFallback = function () {
      var resultsEl = document.querySelector('.results-slide');
      var di = resultsEl ? parseInt(resultsEl.dataset.deckIndex) : NaN;
      if (isNaN(di)) {
        var slides = document.querySelectorAll('.deck-container .slide');
        di = slides.length ? slides.length - 1 : 0;
      }
      playSlide(di);
    };
    window.__ttsIsMuted = function () { return muted; };
    window.__ttsPlayUrl = function (url) {
      if (muted || !player || !url) return;
      try { player.pause(); } catch (e) {}
      player.src = url;
      player.load();
      player.play().catch(function() {});
    };

    // Play the intro (slide_index -1) after a short delay so the deck's
    // goToSlide(0) doesn't preempt it with the first content slide's audio.
    function playIntro() { playSlide(-1); }
    setTimeout(playIntro, 200);

    document.addEventListener('deckSlideChanged', function(e) {
      // Task 4: use the deck's own deckIndex (not the array position) so
      // the TTS manifest stays in sync with the visible deck layout.
      var di = e.detail.deckIndex;
      if (typeof di !== 'number') di = e.detail.slideIndex || 0;
      playSlide(di);
    });

    toggle && toggle.addEventListener('click', function() {
      muted = !muted;
      if (muted) {
        player.pause();
        label.textContent = 'Narration Off';
        toggle.textContent = '🔇 ';
        toggle.appendChild(label);
      } else {
        label.textContent = 'Narration On';
        toggle.textContent = '🔊 ';
        toggle.appendChild(label);
      }
    });
  })();
})();
