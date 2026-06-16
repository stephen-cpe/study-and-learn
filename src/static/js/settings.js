/* ===== Settings page interactions ===== */

(function () {
  'use strict';

  const DIFFICULTY_LABELS = ['Easy', 'Normal', 'Hard'];

  // ── Avatar modal ─────────────────────────────────────────────────
  const modal = document.getElementById('avatar-modal');
  const openBtn = document.getElementById('open-avatar-modal');
  const closeBtn = document.getElementById('close-avatar-modal');
  const confirmBtn = document.getElementById('confirm-avatar');
  const grid = document.getElementById('avatar-grid');
  const avatarInput = document.getElementById('avatar-input');
  const currentImg = document.getElementById('current-avatar-img');
  const form = document.getElementById('settings-form');
  const difficultyInput = document.getElementById('difficulty-input');

  let pendingAvatar = null;

  if (openBtn && modal) {
    openBtn.addEventListener('click', () => {
      modal.hidden = false;
      pendingAvatar = avatarInput.value;
    });

    closeBtn.addEventListener('click', () => {
      modal.hidden = true;
    });

    modal.addEventListener('click', (event) => {
      if (event.target === modal) modal.hidden = true;
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !modal.hidden) modal.hidden = true;
    });

    if (grid) {
      grid.addEventListener('click', (event) => {
        const cell = event.target.closest('.avatar-cell');
        if (!cell) return;
        grid.querySelectorAll('.avatar-cell').forEach((c) => c.classList.remove('is-selected'));
        cell.classList.add('is-selected');
        pendingAvatar = cell.dataset.avatar;
      });
    }

    if (confirmBtn) {
      confirmBtn.addEventListener('click', () => {
        if (pendingAvatar && pendingAvatar !== avatarInput.value) {
          avatarInput.value = pendingAvatar;
          if (currentImg) {
            currentImg.src = currentImg.src.replace(/[^/]*$/, pendingAvatar);
          }
        }
        modal.hidden = true;
        if (form) form.submit();
      });
    }
  }

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
