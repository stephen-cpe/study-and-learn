/* ===== Settings page interactions ===== */

(function () {
  'use strict';

  const DIFFICULTY_LABELS = ['Easy', 'Normal', 'Hard'];

  // ── Shared grid picker (avatar and mascot) ───────────────────────
  // Both modals use the same overlay, header, grid and footer markup.
  // They differ only in the selected value, the image to update, and
  // (for mascots) a hello preview before the form submits.
  function setupPicker(config) {
    const modal = document.getElementById(config.modalId);
    const openBtn = document.getElementById(config.openId);
    const closeBtn = document.getElementById(config.closeId);
    const confirmBtn = document.getElementById(config.confirmId);
    const grid = document.getElementById(config.gridId);
    const input = document.getElementById(config.inputId);
    const form = document.getElementById('settings-form');

    if (!openBtn || !modal || !input) return;

    let pending = null;
    let busy = false;

    const close = () => {
      if (!busy) modal.hidden = true;
    };

    openBtn.addEventListener('click', () => {
      modal.hidden = false;
      pending = input.value;
    });

    if (closeBtn) closeBtn.addEventListener('click', close);

    modal.addEventListener('click', (event) => {
      if (event.target === modal) close();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !modal.hidden) close();
    });

    if (grid) {
      grid.addEventListener('click', (event) => {
        if (busy) return;
        const cell = event.target.closest(config.cellSelector);
        if (!cell) return;
        grid.querySelectorAll(config.cellSelector).forEach((item) => {
          item.classList.remove('is-selected');
        });
        cell.classList.add('is-selected');
        pending = cell.dataset[config.dataKey];
      });
    }

    if (confirmBtn) {
      confirmBtn.addEventListener('click', () => {
        if (busy) return;

        const changed = pending && pending !== input.value;
        if (changed) {
          input.value = pending;
          if (config.onChange) config.onChange(pending);
        }

        const selectedCell = grid
          ? grid.querySelector(config.cellSelector + '.is-selected')
          : null;
        const waitMs = changed && config.beforeSubmit
          ? config.beforeSubmit(pending, selectedCell) || 0
          : 0;

        if (waitMs > 0) {
          // Keep the modal open for the preview. Ignore close attempts so
          // a stray click cannot cancel halfway or submit twice.
          busy = true;
          confirmBtn.disabled = true;
          modal.setAttribute('aria-busy', 'true');
          setTimeout(() => {
            modal.hidden = true;
            if (form) form.submit();
          }, waitMs);
          return;
        }

        modal.hidden = true;
        if (form) form.submit();
      });
    }
  }

  const currentAvatar = document.getElementById('current-avatar-img');
  setupPicker({
    modalId: 'avatar-modal',
    openId: 'open-avatar-modal',
    closeId: 'close-avatar-modal',
    confirmId: 'confirm-avatar',
    gridId: 'avatar-grid',
    inputId: 'avatar-input',
    cellSelector: '.avatar-cell',
    dataKey: 'avatar',
    onChange: (avatar) => {
      if (currentAvatar) {
        currentAvatar.src = currentAvatar.src.replace(/[^/]*$/, avatar);
      }
    },
  });

  setupPicker({
    modalId: 'mascot-modal',
    openId: 'open-mascot-modal',
    closeId: 'close-mascot-modal',
    confirmId: 'confirm-mascot',
    gridId: 'mascot-grid',
    inputId: 'mascot-input',
    cellSelector: '.mascot-cell',
    dataKey: 'mascot',
    beforeSubmit: (mascotId, cell) => {
      if (!cell) return 0;
      const preview = cell.querySelector('img');
      if (preview) {
        // Cache-bust so an already-loaded GIF replays instead of showing
        // its final frame.
        preview.src = preview.src.replace(
          /preview-idle\.gif.*$/,
          'preview-hello.gif?t=' + Date.now()
        );
      }
      const totalMs = parseInt(cell.dataset.helloMs, 10) || 0;
      return Math.min(totalMs, 3500);
    },
  });

  // ── TTS toggle → enable/disable speaker dropdown ─────────────────
  const ttsToggle = document.getElementById('tts-toggle');
  const ttsSelect = document.getElementById('tts_speaker');
  const speakerRow = document.querySelector('.tts-speaker-row');

  if (ttsToggle && ttsSelect && speakerRow) {
    ttsToggle.addEventListener('change', () => {
      const enabled = ttsToggle.checked;
      ttsSelect.disabled = !enabled;
      speakerRow.classList.toggle('is-disabled', !enabled);
    });
  }

  // ── Difficulty slider → update label, current value display, and hidden input ───
  const difficultySlider = document.getElementById('difficulty-slider');
  const difficultyValue = document.getElementById('difficulty-current-value');
  const difficultyInput = document.getElementById('difficulty-input');

  if (difficultySlider && difficultyValue && difficultyInput) {
    const sync = () => {
      const idx = parseInt(difficultySlider.value, 10) || 0;
      const label = DIFFICULTY_LABELS[idx] || 'Normal';
      difficultyValue.textContent = label;
      difficultyInput.value = label;
    };
    difficultySlider.addEventListener('input', sync);
    sync();
  }
})();
