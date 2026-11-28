/**
 * Mascot — data-driven sprite player and behaviour engine.
 *
 * The mascot is a <div class="mascot-sprite"> whose background-image is
 * a 1-row sprite sheet. Frames are stepped in JS so each frame can hold
 * its own duration from the manifest — CSS step timing cannot express
 * variable per-frame timing. Every timing, pool and per-mascot variant
 * comes from the inline #mascot-config JSON rendered by _mascot.html
 * from src/services/mascot_registry.py; this file holds no mascot ids
 * and no tuning constants of its own. Behaviour follows
 * docs/MASCOTS.md sections 3, 5 and 6.
 *
 * Idle chatter and click-to-talk lines are fetched from the backend
 * endpoint ``GET /mascot/line?context=<event>`` which calls the LLM
 * with the learner's memories + current study context.  On any fetch
 * error, the mascot falls back to a short static array so it always
 * has something to say.
 *
 * Speech bubble is styled as a 4:3 CRT monitor (see retro.css). Text is
 * rendered with a fast per-character "typewriter" effect using the
 * PressStart2P pixel font, with a blinking underscore caret at the end.
 */
(function () {
  'use strict';

  // ── Priorities (docs/MASCOTS.md section 6), highest first ─────────
  // Six distinct levels, kept in the spec's order: a higher priority
  // interrupts a lower one; an equal or lower one waits (at most one
  // event is held pending) or is dropped.
  var PRIO_ERROR = 1;  // error and warning events
  var PRIO_EVENT = 2;  // app events and work loops
  var PRIO_CLICK = 3;  // click reactions
  var PRIO_HOVER = 4;  // hover and glances
  var PRIO_IDLE = 5;   // idle variety
  var PRIO_BASE = 6;   // the base idle loop

  // Shared animation names (docs/MASCOTS.md section 9; same for all three).
  var BASE = 'idle-blink';
  var SLEEPY = 'sleepy';
  var POWER_DOWN = 'power-down';
  var WAKE_UP = 'wake-up';
  var HELLO = 'hello';

  // sessionStorage keys: the greeting flag makes `hello` play once per
  // browser session; the last-line timestamp carries Raster's chatter
  // gap across pages so navigating neither resets nor triggers it.
  var GREETED_KEY = 'mascot_greeted';
  var LAST_LINE_KEY = 'mascot_last_line_at';

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

  var _engine = null;
  var _mascotCfg = null;
  var _legacyState = null;

  // ── Small helpers ─────────────────────────────────────────────────

  function _loadConfig() {
    var el = document.getElementById('mascot-config');
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return null;
    }
  }

  function _prefersReducedMotion() {
    return !!(window.matchMedia
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  // The floor is the footer's top border, where the feet stand. Its
  // height varies by page and viewport, so measure it and hand it to CSS
  // as --mascot-floor; the :root fallback covers pages without a footer.
  function _measureFloor() {
    var footer = document.querySelector('.az-footer');
    if (!footer) return;
    var h = Math.round(footer.getBoundingClientRect().height);
    if (h > 0) {
      document.documentElement.style.setProperty('--mascot-floor', h + 'px');
    }
  }

  function _storageGet(key) {
    try { return window.sessionStorage.getItem(key); } catch (e) { return null; }
  }

  function _storageSet(key, value) {
    try { window.sessionStorage.setItem(key, value); } catch (e) { /* private mode */ }
  }

  function _storageGetInt(key) {
    var raw = _storageGet(key);
    if (raw === null) return null;
    var n = parseInt(raw, 10);
    return isNaN(n) ? null : n;
  }

  function _storageSetInt(key, value) {
    _storageSet(key, String(value));
  }

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
        return text;
      })
      .catch(function () {
        // Fallback: pick a random static line
        return FALLBACK_MESSAGES[
          Math.floor(Math.random() * FALLBACK_MESSAGES.length)
        ];
      });
  }

  // ── Sprite player ─────────────────────────────────────────────────
  // Steps background-position across a 1-row sheet, holding each frame
  // for its own manifest duration. Loops repeat; one-shots call back
  // once the final frame has had its full duration (or hold it, for
  // power-down and the error pose). Sheets load eagerly for the base
  // loop and friends, lazily elsewhere; a missing sheet falls back to
  // still.png so there is never a broken box.
  function createSpritePlayer(el, cfg) {
    var fw = cfg.frame_width;
    var fh = cfg.frame_height;
    var stillUrl = cfg.asset_base + cfg.still;
    var sheetState = {};   // url -> 'loading' | 'ok' | 'fail'
    var waiters = {};
    var frames = null;
    var idx = 0;
    var timer = null;
    var onDone = null;
    var holdLast = false;
    var looping = false;
    var currentName = null;
    var paused = false;

    function sheetUrl(name) {
      return cfg.asset_base + cfg.animations[name].sheet;
    }

    function flushWaiters(url, ok) {
      var list = waiters[url] || [];
      waiters[url] = [];
      for (var i = 0; i < list.length; i++) list[i](ok);
    }

    function ensureLoaded(name, cb) {
      var url = sheetUrl(name);
      var st = sheetState[url];
      if (st === 'ok') { cb(true); return; }
      if (st === 'fail') { cb(false); return; }
      if (st === 'loading') { waiters[url].push(cb); return; }
      sheetState[url] = 'loading';
      waiters[url] = [cb];
      var img = new Image();
      img.onload = function () {
        sheetState[url] = 'ok';
        flushWaiters(url, true);
      };
      img.onerror = function () {
        sheetState[url] = 'fail';
        flushWaiters(url, false);
      };
      img.src = url;
    }

    function showStill() {
      el.style.backgroundImage = 'url("' + stillUrl + '")';
      el.style.backgroundSize = fw + 'px ' + fh + 'px';
      el.style.backgroundPosition = '0 0';
    }

    function drawFrame(i) {
      el.style.backgroundPosition = (-i * fw) + 'px 0';
    }

    function finish() {
      var done = onDone;
      onDone = null;
      if (done) done();
    }

    function schedule() {
      if (paused) return;
      timer = setTimeout(advance, frames[idx]);
    }

    function advance() {
      if (idx < frames.length - 1) {
        idx += 1;
        drawFrame(idx);
        schedule();
      } else if (looping) {
        idx = 0;
        drawFrame(idx);
        schedule();
      } else {
        // One-shot over: the final frame already got its full duration.
        if (holdLast) return;
        finish();
      }
    }

    function play(name, opts) {
      opts = opts || {};
      stop();
      el.setAttribute('data-anim', name);
      onDone = opts.onDone || null;
      holdLast = !!opts.holdLast;
      var anim = cfg.animations[name];
      if (!anim || _prefersReducedMotion()) {
        // Unknown animation or reduced motion: still frame, never animate.
        showStill();
        if (!holdLast) setTimeout(finish, 0);
        return;
      }
      frames = anim.frames;
      looping = !!anim.loop;
      currentName = name;
      idx = 0;
      ensureLoaded(name, function (ok) {
        if (currentName !== name) return;
        if (!ok) {
          // Missing sheet: fall back to the still frame, keep the flow.
          showStill();
          if (!holdLast) finish();
          return;
        }
        el.style.backgroundImage = 'url("' + sheetUrl(name) + '")';
        el.style.backgroundSize = (frames.length * fw) + 'px ' + fh + 'px';
        drawFrame(idx);
        schedule();
      });
    }

    function stop() {
      clearTimeout(timer);
      timer = null;
      frames = null;
      onDone = null;
      currentName = null;
    }

    function preload(names) {
      // still.png backs every fallback, so it goes first.
      var still = new Image();
      still.src = stillUrl;
      for (var i = 0; i < names.length; i++) {
        if (cfg.animations[names[i]]) {
          ensureLoaded(names[i], function () {});
        }
      }
    }

    // Hidden tab: pause mid-frame and resume from it without catch-up.
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) {
        paused = true;
        clearTimeout(timer);
      } else {
        paused = false;
        if (frames) schedule();
      }
    });

    return { play: play, stop: stop, preload: preload };
  }

  // ── Behaviour engine ──────────────────────────────────────────────
  // docs/MASCOTS.md section 6: priorities, idle variety, hover, sleep,
  // session greeting, the click shuffle bag and chatter.
  function createBehaviourEngine(cfg, player, el, sayLine) {
    var beh = cfg.behaviour;
    var state = {
      currentAnim: null,
      kind: null,          // 'loop' | 'oneshot' | 'hold' | 'done'
      prio: PRIO_BASE,
      workLoop: null,
      talking: false,
      pending: null,       // at most one held event (section 6)
      errorHolding: false,
      sleep: 'awake',      // 'awake' | 'sleepy' | 'powered-down'
      sleepAccum: 0
    };
    var _errorHoldTimer = null;
    var _varietyTimer = null;
    var _chatterTimer = null;
    var _hoverTimer = null;
    var _sleepTimer = null;
    var _hoverFired = false;
    var _wakeAt = 0;
    var _clickBag = [];
    var _sleepLastTick = Date.now();
    var _pointer = {
      x: (window.innerWidth || 800) / 2,
      y: (window.innerHeight || 600) / 2
    };

    function playNow(anim, opts) {
      opts = opts || {};
      state.currentAnim = anim;
      state.kind = opts.holdLast ? 'hold' : (opts.loop ? 'loop' : 'oneshot');
      state.prio = opts.prio;
      player.play(anim, {
        holdLast: opts.holdLast,
        onDone: opts.holdLast ? null : function () {
          if (state.currentAnim !== anim) return;
          state.kind = 'done';
          if (opts.onDone) opts.onDone();
          firePendingOrBase();
        }
      });
    }

    // Queue one waiting event, or drop it. Only app events are worth
    // holding: a transient reaction (click, hover, glance) is stale by
    // the time the slot frees up, so those are dropped instead.
    function holdPending(anim, prio, onDone) {
      if (prio > PRIO_EVENT) return;
      if (!state.pending) {
        state.pending = { anim: anim, prio: prio, onDone: onDone };
      }
    }

    function firePendingOrBase() {
      if (state.pending) {
        var p = state.pending;
        state.pending = null;
        requestOneShot(p.anim, p.prio, p.onDone);
      } else {
        returnToBase();
      }
    }

    function requestOneShot(anim, prio, onDone) {
      if (state.errorHolding && prio > PRIO_ERROR) {
        holdPending(anim, prio, onDone);
        return;
      }
      if (state.sleep === 'powered-down') {
        // Parked: only an app event or error breaks through (the app's
        // message always gets through); that quietly ends the sleep.
        if (prio > PRIO_EVENT) return;
        state.sleep = 'awake';
      }
      if (state.kind === 'oneshot' && state.prio <= prio) {
        holdPending(anim, prio, onDone);
        return;
      }
      playNow(anim, { loop: false, prio: prio, onDone: onDone });
    }

    function requestLoop(anim, prio) {
      if (state.errorHolding && prio > PRIO_ERROR) return;
      if (state.sleep === 'powered-down') {
        if (prio > PRIO_EVENT) return;
        state.sleep = 'awake';
      }
      if (state.kind === 'oneshot' && state.prio < prio) return;
      if (state.currentAnim === anim && state.kind === 'loop') return;
      playNow(anim, { loop: true, prio: prio });
    }

    // After a one-shot: the loop for the current situation — the work
    // loop while a job runs, sleepy/doze while asleep, else idle-blink.
    function returnToBase() {
      if (state.errorHolding) return;
      if (state.talking) {
        requestLoop(beh.talk_anim, PRIO_EVENT);
        return;
      }
      if (state.sleep === 'sleepy') {
        requestLoop(SLEEPY, PRIO_EVENT);
        return;
      }
      if (state.sleep === 'powered-down') return;
      if (window._progressActive && state.workLoop) {
        requestLoop(state.workLoop, PRIO_EVENT);
        return;
      }
      requestLoop(BASE, PRIO_BASE);
    }

    // Errors and warnings hold their final frame with the error glow
    // until progress.js's sticky-error window clears. Repeats extend the
    // hold instead of replaying (the sticky window extends the same way).
    function errorEvent(anim) {
      state.errorHolding = true;
      if (state.kind !== 'hold' || state.prio !== PRIO_ERROR) {
        playNow(anim, { loop: false, prio: PRIO_ERROR, holdLast: true });
      }
      clearTimeout(_errorHoldTimer);
      _errorHoldTimer = setTimeout(function () {
        state.errorHolding = false;
        firePendingOrBase();
      }, beh.error_hold_ms);
    }

    function setWorkLoop(anim) {
      state.workLoop = anim;
      if (anim) {
        requestLoop(anim, PRIO_EVENT);
      } else {
        requestLoop(BASE, PRIO_BASE);
      }
    }

    function startTalking() {
      state.talking = true;
      requestLoop(beh.talk_anim, PRIO_EVENT);
    }

    function stopTalking() {
      state.talking = false;
      returnToBase();
    }

    // ── Idle life (docs/MASCOTS.md section 6) ────────────────────────

    function weightedPick(pool) {
      var total = 0;
      var i;
      for (i = 0; i < pool.length; i++) total += pool[i].weight;
      var r = Math.random() * total;
      for (i = 0; i < pool.length; i++) {
        r -= pool[i].weight;
        if (r < 0) return pool[i].anim;
      }
      return pool[pool.length - 1].anim;
    }

    // The cursor glance plays the look-* pointing from the mascot's
    // corner toward the pointer (mostly look-left / look-up, since the
    // mascot sits bottom-right).
    function glanceAnim() {
      var rect = el.getBoundingClientRect();
      var dx = _pointer.x - (rect.left + rect.width / 2);
      var dy = _pointer.y - (rect.top + rect.height / 2);
      if (Math.abs(dx) > Math.abs(dy)) {
        return dx < 0 ? 'look-left' : 'look-right';
      }
      return dy < 0 ? 'look-up' : 'look-down';
    }

    function scheduleVariety() {
      clearTimeout(_varietyTimer);
      var gap = beh.idle_gap_ms;
      var delay = gap[0] + Math.floor(Math.random() * (gap[1] - gap[0] + 1));
      _varietyTimer = setTimeout(varietyAttempt, delay);
    }

    function varietyAttempt() {
      if (state.sleep === 'awake' && !window._progressActive
          && !document.hidden && state.kind === 'loop'
          && state.currentAnim === BASE) {
        var pick = weightedPick(beh.idle_pool);
        if (pick === 'cursor-glance') pick = glanceAnim();
        requestOneShot(pick, PRIO_IDLE);
      }
      scheduleVariety();
    }

    // ── Hover and clicks (docs/MASCOTS.md sections 6-7) ──────────────

    function onHoverStart() {
      _hoverFired = false;
      clearTimeout(_hoverTimer);
      _hoverTimer = setTimeout(function () {
        if (_hoverFired || state.sleep !== 'awake') return;
        _hoverFired = true;
        var pool = beh.hover_anims;
        requestOneShot(pool[Math.floor(Math.random() * pool.length)],
                       PRIO_HOVER);
      }, beh.hover_delay_ms);
    }

    function onHoverEnd() {
      clearTimeout(_hoverTimer);
      _hoverFired = false;
    }

    // Shuffle bag: every group of N clicks holds exactly one "talk" at a
    // random slot. Clicks landing while a reaction plays are ignored.
    function drawClickBag() {
      if (_clickBag.length === 0) {
        var n = beh.click_talk_every;
        var talkSlot = Math.floor(Math.random() * n);
        for (var i = 0; i < n; i++) {
          _clickBag.push(i === talkSlot ? 'talk' : 'reaction');
        }
      }
      return _clickBag.pop();
    }

    function onMascotClick() {
      // A click that lands with the wake-up is the wake-up, not a draw.
      if (Date.now() - _wakeAt < 700) return;
      if (state.errorHolding) return;
      if (state.sleep !== 'awake') return;
      if (state.kind === 'oneshot' && state.prio === PRIO_CLICK) return;
      var draw = drawClickBag();
      if (draw === 'talk' && !window._progressActive) {
        sayLine(null);
        return;
      }
      // Click-talk is suppressed during a long job, but clicks still get
      // a reaction (docs/MASCOTS.md section 5).
      var pool = beh.click_reactions;
      requestOneShot(pool[Math.floor(Math.random() * pool.length)],
                     PRIO_CLICK);
    }

    function onKeyDown(e) {
      var key = e.key || e.keyCode;
      if (key === 'Enter' || key === ' ' || key === 'Spacebar'
          || key === 13 || key === 32) {
        if (e.preventDefault) e.preventDefault();
        onMascotClick();
      }
    }

    // ── Sleep (docs/MASCOTS.md section 6) ────────────────────────────

    function onInput() {
      state.sleepAccum = 0;
      if (state.sleep === 'sleepy') {
        // Leaving sleepy without a power-down: idle, with no line.
        state.sleep = 'awake';
        returnToBase();
      } else if (state.sleep === 'powered-down') {
        state.sleep = 'awake';
        _wakeAt = Date.now();
        requestOneShot(WAKE_UP, PRIO_EVENT, function () {
          sayLine(null);   // the wake-up line
        });
      }
    }

    function onPointerMove(e) {
      _pointer.x = e.clientX;
      _pointer.y = e.clientY;
    }

    function sleepTick() {
      var now = Date.now();
      // The sleep timers pause while a long job runs: the mascot is
      // working, not being ignored.
      if (!window._progressActive) state.sleepAccum += now - _sleepLastTick;
      _sleepLastTick = now;
      if (state.sleep === 'awake'
          && state.sleepAccum >= beh.sleepy_after_ms) {
        state.sleep = 'sleepy';
        requestLoop(SLEEPY, PRIO_EVENT);
      } else if (state.sleep === 'sleepy'
                 && state.sleepAccum >= beh.power_down_after_ms) {
        state.sleep = 'powered-down';
        // One-shot held on its final pose: no variety, no chatter.
        playNow(POWER_DOWN, { loop: false, prio: PRIO_EVENT, holdLast: true });
      }
      _sleepTimer = setTimeout(sleepTick, 1000);
    }

    // ── Chatter (docs/MASCOTS.md section 5) ──────────────────────────
    // One attempt a configured gap after the last line of any kind plus
    // a small random delay, at most. The timestamp lives in
    // sessionStorage so navigating neither resets nor triggers it.

    function freshGap() {
      return beh.chatter_gap_ms
        + Math.floor(Math.random() * (beh.chatter_jitter_ms + 1));
    }

    function delayUntilChatter() {
      var last = _storageGetInt(LAST_LINE_KEY);
      if (last === null) last = Date.now();
      return Math.max(0, last + beh.chatter_gap_ms - Date.now())
        + Math.floor(Math.random() * (beh.chatter_jitter_ms + 1));
    }

    function scheduleChatter(delay) {
      clearTimeout(_chatterTimer);
      if (!beh.chatter_enabled) return;
      _chatterTimer = setTimeout(chatterAttempt,
        delay === undefined ? delayUntilChatter() : delay);
    }

    function chatterAttempt() {
      // Suppressed during a long job, while asleep, while a line is
      // already up or while the tab is hidden: skip and re-arm a fresh
      // gap rather than firing the moment the suppression ends.
      if (window._progressActive || state.sleep !== 'awake'
          || state.talking || document.hidden) {
        scheduleChatter(freshGap());
        return;
      }
      if (!sayLine(null)) scheduleChatter(freshGap());
    }

    // Any line of any kind resets the chatter clock.
    function noteLineShown() {
      _storageSetInt(LAST_LINE_KEY, Date.now());
      scheduleChatter();
    }

    // ── Session greeting (docs/MASCOTS.md section 6) ────────────────

    function greet() {
      if (!_storageGet(GREETED_KEY)) {
        _storageSet(GREETED_KEY, '1');
        requestOneShot(HELLO, PRIO_EVENT, function () {
          if (beh.greeting_line) sayLine(null);
        });
      } else {
        // Later pages in the session: one quick glance, silent.
        var pool = beh.page_glance_anims;
        requestOneShot(pool[Math.floor(Math.random() * pool.length)],
                       PRIO_HOVER);
      }
    }

    function start() {
      sleepTick();
      scheduleChatter();
      scheduleVariety();
    }

    return {
      start: start,
      greet: greet,
      requestOneShot: requestOneShot,
      requestLoop: requestLoop,
      setWorkLoop: setWorkLoop,
      errorEvent: errorEvent,
      startTalking: startTalking,
      stopTalking: stopTalking,
      noteLineShown: noteLineShown,
      returnToBase: returnToBase,
      onMascotClick: onMascotClick,
      onKeyDown: onKeyDown,
      onHoverStart: onHoverStart,
      onHoverEnd: onHoverEnd,
      onInput: onInput,
      onPointerMove: onPointerMove
    };
  }

  // ── CRT bubble + typewriter ────────────────────────────────────────

  function typewriteInto(el, text) {
    if (!el) return Promise.resolve();
    if (!text) {
      el.textContent = '';
      return Promise.resolve();
    }
    el.textContent = '';
    el.setAttribute('data-bubble-text', text);
    // Reduced motion: the whole line appears at once (docs/MASCOTS.md
    // section 3).
    if (_prefersReducedMotion()) {
      el.textContent = text;
      return Promise.resolve();
    }
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

  // ── Legacy state adapter ──────────────────────────────────────────
  // Exposed always so callers on pages without a mascot stay harmless.
  window.setMascotState = function (state) {
    if (!_engine || !_mascotCfg) return;

    // LEGACY: removed in Task 5
    // The old state names that progress.js, upload.js and the inline
    // script in lessons.html still send, mapped to the new animation
    // names (docs/MASCOTS.md section 8). busyC and talk come from the
    // config because they differ per mascot (Trace "writes" where
    // Raster and Pip "speak") — no mascot id appears in this file.
    var LEGACY_STATE_MAP = {
      'idle': 'idle-blink',
      'busy': 'processing',
      'busyB': 'searching',
      'busyC': _mascotCfg.behaviour.work_typing_anim,
      'happy': 'success',
      'error': 'error',
      'talk': _mascotCfg.behaviour.talk_anim,
      'wave': 'hello'
    };

    var raw = String(state || 'idle');
    var key = null;
    for (var k in LEGACY_STATE_MAP) {
      if (k.toLowerCase() === raw.toLowerCase()) { key = k; break; }
    }
    if (key === null) key = 'idle';

    if (key === 'error') {
      // Error repeats extend the hold (progress.js's sticky window
      // extends the same way) instead of replaying the animation.
      _engine.errorEvent(LEGACY_STATE_MAP[key]);
      _legacyState = key;
      return;
    }
    if (_legacyState === key) return;   // polls repeat states every 2 s
    _legacyState = key;

    if (key === 'busy' || key === 'busyB' || key === 'busyC') {
      _engine.setWorkLoop(LEGACY_STATE_MAP[key]);
    } else if (key === 'idle') {
      _engine.setWorkLoop(null);
    } else if (key === 'talk') {
      _engine.requestLoop(LEGACY_STATE_MAP[key], PRIO_EVENT);
    } else {
      // happy / wave: one-shots, then back to the current loop.
      _engine.requestOneShot(LEGACY_STATE_MAP[key], PRIO_EVENT);
    }
  };

  // ── Init ──────────────────────────────────────────────────────────

  window.initMascot = function () {
    var el = document.getElementById('mascot');
    var cfg = _loadConfig();
    // lesson_deck.html loads this file without the mascot markup: no
    // config, no mascot element, nothing to do.
    if (!el || !cfg) return;

    var _typewriterToken = 0;
    var _pageContext = _detectContext();
    var bubbleText = document.getElementById('bubble-text');

    function talkLine(customMsg) {
      if (window._progressActive) return false;
      var els = getBubbleEls();
      if (!els.bubble || !els.text) return false;
      var token = ++_typewriterToken;
      els.bubble.classList.add('active');
      // Talking animation (docs/MASCOTS.md section 6): "speaking", or
      // "writing" for a mascot without it — configured server-side.
      _engine.startTalking();
      _engine.noteLineShown();

      function hideAfterLine() {
        if (token !== _typewriterToken) return;
        setTimeout(function () {
          if (token !== _typewriterToken) return;
          if (window._progressActive) return;
          els.bubble.classList.remove('active');
          _engine.stopTalking();
        }, 4000);
      }

      // A custom message (e.g. from upload.js) is shown directly — no
      // fetch needed.
      if (customMsg) {
        typewriteInto(els.text, customMsg).then(hideAfterLine);
        return true;
      }
      _fetchMascotLine(_pageContext).then(function (line) {
        if (token !== _typewriterToken) return;  // a newer call superseded us
        typewriteInto(els.text, line).then(hideAfterLine);
      });
      return true;
    }

    var player = createSpritePlayer(el, cfg);
    _engine = createBehaviourEngine(cfg, player, el, talkLine);
    _mascotCfg = cfg;

    // Keep the floor at the measured footer height, at load and on
    // resize (docs/MASCOTS.md section 3: the feet share one baseline).
    _measureFloor();
    window.addEventListener('load', _measureFloor);
    window.addEventListener('resize', _measureFloor);

    // Eager sheets: the base loop, hello, the idle pool and the sheets
    // this page is likely to use (work loops + talking). The rest lazy
    // load the first time they are needed.
    var eager = [BASE, HELLO, cfg.behaviour.talk_anim,
                 cfg.behaviour.work_typing_anim,
                 'processing', 'searching', 'reading', 'thinking'];
    var pools = [cfg.behaviour.idle_pool,
                 cfg.behaviour.click_reactions,
                 cfg.behaviour.hover_anims];
    for (var p = 0; p < pools.length; p++) {
      for (var a = 0; a < pools[p].length; a++) {
        var entry = pools[p][a];
        eager.push(typeof entry === 'string' ? entry : entry.anim);
      }
    }
    player.preload(eager);

    window._mascotTalk = talkLine;
    // Expose the typewriter so progress.js can reuse it.
    window._bubbleTypewrite = function (text) {
      return typewriteInto(bubbleText, text);
    };
    window._BUBBLE_TYPEWRITER_CHAR_DELAY_MS = TYPEWRITER_CHAR_DELAY_MS;

    el.addEventListener('click', _engine.onMascotClick);
    el.addEventListener('keydown', _engine.onKeyDown);
    el.addEventListener('mouseenter', _engine.onHoverStart);
    el.addEventListener('mouseleave', _engine.onHoverEnd);
    document.addEventListener('mousemove', _engine.onPointerMove);
    // Input that resets the sleep timers (docs/MASCOTS.md section 6):
    // mouse movement, key press, pointer down, scroll or touch.
    var inputEvents = ['mousemove', 'keydown', 'pointerdown', 'scroll',
                       'touchstart'];
    for (var i = 0; i < inputEvents.length; i++) {
      document.addEventListener(inputEvents[i], _engine.onInput);
    }

    _engine.start();
    _engine.greet();
  };

  document.addEventListener('DOMContentLoaded', function () {
    window.initMascot();
  });
})();
