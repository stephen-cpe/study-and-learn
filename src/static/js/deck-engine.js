(function() {
    'use strict';

    var _savePositionTimer = null;

    function _debouncedSavePosition(container, idx) {
        clearTimeout(_savePositionTimer);
        _savePositionTimer = setTimeout(function() {
            _savePosition(container, idx);
        }, 500);
    }

    function _savePosition(container, idx) {
        var moduleIndex = parseInt(container.dataset.moduleIndex);
        var pathId = container.dataset.pathId || '';
        fetch('/lessons/' + moduleIndex + '/save-position?path_id=' + encodeURIComponent(pathId), {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({slide_index: idx})
        }).catch(function() {});
    }

    class StudyAndLearnDeck {
        constructor(options) {
            this.currentSlide = 0;
            this.slides = [];
            this.checkpointAnswers = {};
            this.quizSubmitted = false;
            this.finalGrade = null;
            this.options = options || {};
            this.init();
        }

        init() {
            this.container = document.querySelector('.deck-container');
            this.wrapper = document.querySelector('.slides-wrapper');
            this.progressBar = document.querySelector('.deck-progress-bar');
            this.prevBtn = document.getElementById('prev-slide');
            this.nextBtn = document.getElementById('next-slide');

            if (!this.container || !this.wrapper) {
                console.error('Deck container or wrapper not found');
                return;
            }

            this.slides = Array.from(this.container.querySelectorAll('.slide'));
            this.totalSlides = this.slides.length;
            this.wheelCooldown = false;

            this.bindEvents();

            var resumeSlide = parseInt(this.container.dataset.resumeSlide) || 0;
            if (resumeSlide > 0 && resumeSlide < this.totalSlides) {
                this.goToSlide(resumeSlide);
            } else {
                this.goToSlide(0);
            }
        }

        bindEvents() {
            document.addEventListener('keydown', (e) => this.handleKeydown(e));

            if (this.prevBtn) {
                this.prevBtn.addEventListener('click', () => this.prev());
            }
            if (this.nextBtn) {
                this.nextBtn.addEventListener('click', () => this.next());
            }

            this.container.addEventListener('wheel', (e) => this.handleWheel(e), { passive: false });
            this.container.addEventListener('click', (e) => this.handleClick(e));
            this.container.addEventListener('change', (e) => this.handleCheckpointSelectChange(e));

            this.container.addEventListener('touchstart', (e) => {
                this.touchStartY = e.touches[0].clientY;
            }, { passive: true });

            this.container.addEventListener('touchend', (e) => {
                if (this.touchStartY === undefined) return;
                const deltaY = e.changedTouches[0].clientY - this.touchStartY;
                if (Math.abs(deltaY) > 50) {
                    if (deltaY < 0) this.next();
                    else this.prev();
                }
                this.touchStartY = undefined;
            }, { passive: true });
        }

        handleKeydown(e) {
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                e.preventDefault();
                this.next();
            } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                e.preventDefault();
                this.prev();
            }
        }

        handleWheel(e) {
            const currentSlideEl = this.slides[this.currentSlide];
            const container = currentSlideEl?.querySelector('.scroll-container');

            if (container) {
                const isScrollable = container.scrollHeight > container.clientHeight + 1;
                if (isScrollable) {
                    const atTop = container.scrollTop <= 0;
                    const atBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 1;
                    const scrollingDown = e.deltaY > 0;
                    const scrollingUp = e.deltaY < 0;

                    if ((scrollingDown && !atBottom) || (scrollingUp && !atTop)) {
                        container.scrollTop += e.deltaY;
                        e.preventDefault();
                    }
                }
            }
        }

        handleClick(e) {
            const option = e.target.closest('.checkpoint-option');
            if (option) {
                const slide = option.closest('.checkpoint-slide');
                if (!slide || slide.dataset.answered === 'true') return;

                slide.querySelectorAll('.checkpoint-option').forEach(o => o.classList.remove('selected'));
                option.classList.add('selected');

                const btn = slide.querySelector('.btn-submit-quiz');
                if (btn) btn.style.display = 'inline-block';
                return;
            }
        }

        handleCheckpointSelectChange(e) {
            const select = e.target.closest('.checkpoint-select');
            if (!select) return;

            const slide = select.closest('.checkpoint-slide');
            if (!slide || slide.dataset.answered === 'true') return;
            if (select.value === '') return;

            const btn = slide.querySelector('.btn-submit-quiz');
            if (btn) btn.style.display = 'inline-block';
        }

        goToSlide(index) {
            if (index < 0) index = 0;
            if (index >= this.totalSlides) index = this.totalSlides - 1;

            this.slides.forEach((slide, i) => {
                slide.classList.remove('active');
            });

            this.slides[index].classList.add('active');
            this.currentSlide = index;
            this.updateControls();
            this.updateProgressBar();

            // Use the slide element's own data-deck-index (Task 4) as the
            // canonical deck index. This is the single source of truth
            // shared with the template and the TTS narration manifest.
            // If the attribute is missing (legacy data-index), fall back
            // to the array index.
            var activeEl = this.slides[index];
            var deckIndex = parseInt(activeEl.dataset.deckIndex);
            if (isNaN(deckIndex)) {
                deckIndex = parseInt(activeEl.dataset.index) || index;
            }

            if (this.options.onSlideChange) {
                this.options.onSlideChange({
                    index: this.currentSlide,
                    slide: this.slides[this.currentSlide],
                    total: this.totalSlides,
                    deckIndex: deckIndex,
                });
            }

            document.dispatchEvent(new CustomEvent('deckSlideChanged', {
                detail: { slideIndex: this.currentSlide, deckIndex: deckIndex }
            }));
            _debouncedSavePosition(this.container, this.currentSlide);
        }

        next() {
            if (this.currentSlide >= this.totalSlides - 1) return;

            const currentSlideEl = this.slides[this.currentSlide];
            const state = currentSlideEl?.dataset?.state;

            if (state === 'checkpoint-blocked' && currentSlideEl.dataset.answered !== 'true') return;
            if (state === 'quiz-blocked' && !this.quizSubmitted) return;

            this.goToSlide(this.currentSlide + 1);
        }

        prev() {
            this.goToSlide(this.currentSlide - 1);
        }

        updateControls() {
            if (this.prevBtn) {
                this.prevBtn.disabled = this.currentSlide === 0;
            }
            if (this.nextBtn) {
                const currentSlideEl = this.slides[this.currentSlide];
                const state = currentSlideEl?.dataset?.state;
                const isBlocked = (state === 'checkpoint-blocked' && currentSlideEl.dataset.answered !== 'true') ||
                                  (state === 'quiz-blocked' && !this.quizSubmitted);
                this.nextBtn.disabled = this.currentSlide === this.totalSlides - 1 || isBlocked;
            }
        }

        updateProgressBar() {
            if (this.progressBar) {
                const progress = ((this.currentSlide + 1) / this.totalSlides) * 100;
                this.progressBar.style.width = progress + '%';
            }
        }

        advanceFromCheckpoint(btn) {
            const slide = btn.closest('.checkpoint-slide');
            if (!slide) return;

            // Two-click progression for Quick Checks:
            //
            //   First click:  validate the answer, request per-question
            //                 feedback from the server (if a grading
            //                 endpoint is available), and mark the slide
            //                 as answered. The slide's feedback element
            //                 shows the correct/incorrect result. The
            //                 Continue button stays visible so the
            //                 learner can read the feedback at their own
            //                 pace.
            //
            //   Second click: advance to the next slide.
            //
            // There is NO automatic timer — the user is always in
            // control. The user can also press the right-arrow key to
            // advance (deck-engine.js:next() unblocks once
            // data-answered is true).
            if (slide.dataset.answered === 'true') {
                this.next();
                return;
            }

            const cpType = slide.dataset.cpType || 'mcq';
            let userValue;

            if (cpType === 'cloze_dropdown') {
                const select = slide.querySelector('.checkpoint-select');
                if (!select || select.value === '') return;
                userValue = parseInt(select.value);
            } else {
                const selected = slide.querySelector('.checkpoint-option.selected');
                if (!selected) return;
                const raw = selected.dataset.value;
                if (cpType === 'true_false') {
                    userValue = raw === 'true';
                } else {
                    userValue = parseInt(raw);
                }
            }

            const slideIndex = slide.dataset.checkpoint;
            const fb = slide.querySelector('.checkpoint-feedback');

            const markAnswered = () => {
                this.checkpointAnswers[slideIndex] = userValue;
                slide.dataset.answered = 'true';
                const select = slide.querySelector('.checkpoint-select');
                if (select) select.disabled = true;
                this.updateControls();
            };

            if (typeof window.gradeCheckpoint === 'function') {
                window.gradeCheckpoint(slideIndex, userValue, fb, () => {
                    markAnswered();
                });
            } else {
                markAnswered();
            }
        }

        submitFinalQuiz() {
            const answers = [];
            const fillBlankAnswers = {};
            const quizQuestions = document.querySelectorAll('.quiz-question');
            let allAnswered = true;

            quizQuestions.forEach(qq => {
                const qtype = qq.dataset.qtype;
                const qid = qq.dataset.qid;
                if (qtype === 'mcq') {
                    const selected = qq.querySelector('input[type="radio"]:checked');
                    if (selected) {
                        answers.push(parseInt(selected.value));
                    } else {
                        allAnswered = false;
                    }
                } else if (qtype === 'cloze_dropdown') {
                    const select = qq.querySelector('.cloze-select');
                    if (select && select.value !== '') {
                        answers.push(parseInt(select.value));
                    } else {
                        allAnswered = false;
                    }
                } else if (qtype === 'true_false') {
                    const selected = qq.querySelector('input[type="radio"]:checked');
                    if (selected) {
                        answers.push(selected.value === 'true');
                    } else {
                        allAnswered = false;
                    }
                } else if (qtype === 'multi_select') {
                    const selected = qq.querySelectorAll('input[type="checkbox"]:checked');
                    if (selected.length > 0) {
                        answers.push(Array.from(selected).map(cb => parseInt(cb.value)));
                    } else {
                        allAnswered = false;
                    }
                } else if (qtype === 'fill_blank') {
                    const select = qq.querySelector('.cloze-select');
                    if (select) {
                        if (select.value !== '') {
                            answers.push(parseInt(select.value));
                        } else {
                            allAnswered = false;
                        }
                    } else {
                        const input = qq.querySelector('.q-input');
                        if (input && input.value.trim()) {
                            const val = input.value.trim();
                            fillBlankAnswers[qid] = val;
                            answers.push(null);
                        } else {
                            allAnswered = false;
                        }
                    }
                }
            });

            if (!allAnswered) {
                const errorEl = document.getElementById('quiz-error');
                if (errorEl) errorEl.style.display = 'block';
                return;
            }

            const errorEl = document.getElementById('quiz-error');
            if (errorEl) errorEl.style.display = 'none';

            if (typeof window.gradeQuiz === 'function') {
                window.gradeQuiz(answers, fillBlankAnswers);
            }
        }

        showResults(data) {
            this.quizSubmitted = true;
            this.finalGrade = data;
            this.updateControls();

            const scoreCircle = document.getElementById('score-circle');
            const verdictText = document.getElementById('verdict-text');
            const resultsDetail = document.getElementById('results-detail');
            const btnRetake = document.getElementById('btn-retake');

            if (scoreCircle) {
                scoreCircle.textContent = data.score + '%';
                scoreCircle.className = 'score-circle ' + (data.passed ? 'passed' : 'failed');
            }

            if (verdictText) {
                verdictText.textContent = data.passed ?
                    'Module Passed!' :
                    'Keep Trying — You need ' + data.threshold + '% to pass';
                verdictText.className = 'verdict ' + (data.passed ? 'passed' : 'failed');
            }

            if (resultsDetail && data.quiz_results) {
                let detailHtml = '';
                data.quiz_results.forEach(r => {
                    const icon = r.correct ? '✓' : '✗';
                    const color = r.correct ? 'var(--deck-success)' : 'var(--deck-danger)';
                    detailHtml += '<p style="color: ' + color + '; margin-bottom:0.5rem;">' + icon + ' ' + r.prompt + '<br><small>' + (r.explanation || '') + '</small></p>';
                });
                resultsDetail.innerHTML = detailHtml;
                resultsDetail.style.display = 'block';
            }

            if (btnRetake) {
                btnRetake.style.display = data.passed ? 'none' : 'inline-block';
            }

            this.goToSlide(this.totalSlides - 1);
        }

        getCurrentSlide() {
            return this.currentSlide;
        }

        getTotalSlides() {
            return this.totalSlides;
        }
    }

    window.StudyAndLearnDeck = StudyAndLearnDeck;
})();