"""
Shared prompt building blocks for the AI generators.

Holds constants that must stay identical across services (lessons,
quizzes, checkpoints) so pedagogical tone is defined in exactly one
place.
"""

DIFFICULTY_INSTRUCTIONS = {
    'Easy': (
        "AUDIENCE — Easy (age 10–11):\n"
        "Use short sentences and simple vocabulary. Introduce every concept with a "
        "concrete everyday analogy before stating the formal definition. Avoid jargon "
        "entirely — if a technical term is unavoidable, define it immediately in plain "
        "language. Use encouraging language. Never condescend; treat the learner as "
        "curious and fully capable.\n"
    ),
    'Normal': (
        "AUDIENCE — Normal (age 12–13):\n"
        "Use clear, moderately detailed language. Some subject-specific terms are "
        "appropriate — define each on first use before continuing. Assume the learner "
        "has basic school-level knowledge. Balance depth with accessibility.\n"
    ),
    'Hard': (
        "AUDIENCE — Hard (age 14–15):\n"
        "Use full subject vocabulary without simplifying. Do not filter or dumb down "
        "material. Assume a motivated learner who can handle nuance, multi-step "
        "reasoning, and precise terminology. Keep examples concise and sophisticated.\n"
    ),
}

DEFAULT_DIFFICULTY_INSTRUCTION = DIFFICULTY_INSTRUCTIONS['Normal']