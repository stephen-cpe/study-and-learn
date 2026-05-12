# STATUS.md
Last Updated: 2026-05-12
Sprint: 4
Last Task Completed: Completed interactive lesson generation with quizzes, checkpoints, and gated progression (Sprint 3)
Commit Message Suggestion: feat: complete interactive lessons module with quiz grading and module gating
Known Issues:
  - Loading UX: Full-screen overlay blocks interaction; needs background progress indicator
  - Session stability: Large lesson JSON occasionally exceeds cookie limits despite server-side storage
  - AI output consistency: Lesson/quiz quality varies with qwen3:1.7b; needs prompt refinement or model evaluation
  - Responsive layout: Slide deck needs mobile breakpoint adjustments for smaller screens
  - Mascot integration: Placeholder image present; animation frames and state logic pending
Pending Decisions:
  - Model selection: Evaluate gemma3:4b vs granite4.1:3b vs qwen3:1.7b for lesson quality/speed tradeoff on 6GB VRAM
  - Deployment target: Confirm Render vs Railway free tier for final submission
  - Difficulty toggle scope: Decide if Easy/Moderate/Hard selector is Sprint 4 or deferred to post-MVP
Next 3 Tasks:
  1. Replace full-screen loading overlay with background progress bar showing generation stage
  2. Conduct model quality research: test lesson/quiz outputs across candidate Ollama models on target hardware
  3. Integrate retro mascot (`mascot-robot.png`) with idle/waiting/done visual states
