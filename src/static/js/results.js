/**
 * Results page — markdown rendering and lesson generation button.
 */
(function () {
  'use strict';

  function parseMarkdown(elementId) {
    var el = document.getElementById(elementId);
    if (!el || typeof marked === 'undefined') return;
    el.innerHTML = marked.parse(el.innerText.trim());
    el.classList.remove('raw-md');
  }

  window.initResultsPage = function () {
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
        window.startGenerateLessons(generateBtn.dataset.generateUrl);
      });
    }
  };

  document.addEventListener('DOMContentLoaded', function () {
    if (document.getElementById('summary-content')) {
      window.initResultsPage();
    }
  });
})();
