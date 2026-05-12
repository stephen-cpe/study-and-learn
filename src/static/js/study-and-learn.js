(function() {
    'use strict';

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
            this.goToSlide(0);
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
            if (!option) return;

            const slide = option.closest('.checkpoint-slide');
            if (!slide || slide.dataset.answered === 'true') return;

            slide.querySelectorAll('.checkpoint-option').forEach(o => o.classList.remove('selected'));
            option.classList.add('selected');

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

            if (this.options.onSlideChange) {
                this.options.onSlideChange({
                    index: this.currentSlide,
                    slide: this.slides[this.currentSlide],
                    total: this.totalSlides
                });
            }
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
            if (!slide || slide.dataset.answered === 'true') return;

            const selected = slide.querySelector('.checkpoint-option.selected');
            if (!selected) return;

            const userValue = parseInt(selected.dataset.value);
            const slideIndex = slide.dataset.checkpoint;
            const fb = slide.querySelector('.checkpoint-feedback');

            if (typeof window.gradeCheckpoint === 'function') {
                window.gradeCheckpoint(slideIndex, userValue, fb, () => {
                    this.checkpointAnswers[slideIndex] = userValue;
                    slide.dataset.answered = 'true';
                    this.updateControls();
                    setTimeout(() => this.next(), 3000);
                });
            } else {
                this.checkpointAnswers[slideIndex] = userValue;
                slide.dataset.answered = 'true';
                this.updateControls();
                setTimeout(() => this.next(), 3000);
            }
        }

        submitFinalQuiz() {
            const answers = [];
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
                    const input = qq.querySelector('.q-input');
                    if (input && input.value.trim()) {
                        answers.push(input.value.trim());
                    } else {
                        allAnswered = false;
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
                window.gradeQuiz(answers);
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