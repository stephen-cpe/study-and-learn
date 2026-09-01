/**
 * CSRF token injection for AJAX/JSON requests.
 *
 * Reads the token from <meta name="csrf-token"> and attaches it as the
 * X-CSRFToken header on every fetch() POST/PUT/PATCH/DELETE. GET/HEAD/
 * OPTIONS are exempt. Wrapped once at page load so every existing
 * callsite (upload.js, deck-engine.js, deck-page.js, progress.js,
 * mascot.js) inherits the header without per-file edits.
 *
 * This file is included by base.html AND lesson_deck.html (which is a
 * standalone document that does not extend base.html).
 */
(function () {
  'use strict';

  var meta = document.querySelector('meta[name="csrf-token"]');
  if (!meta) return;
  var token = meta.getAttribute('content');
  if (!token) return;

  if (window.__csrfFetchWrapped) return;
  window.__csrfFetchWrapped = true;

  var originalFetch = window.fetch;
  window.fetch = function (input, init) {
    init = init || {};
    var method = (init.method || 'GET').toUpperCase();
    if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') {
      return originalFetch(input, init);
    }
    var headers = init.headers || {};
    var merged = {};
    if (headers instanceof Headers) {
      headers.forEach(function (v, k) { merged[k] = v; });
    } else {
      for (var k in headers) {
        if (Object.prototype.hasOwnProperty.call(headers, k)) merged[k] = headers[k];
      }
    }
    if (!merged['X-CSRFToken'] && !merged['x-csrftoken']) {
      merged['X-CSRFToken'] = token;
    }
    init.headers = merged;
    return originalFetch(input, init);
  };
})();