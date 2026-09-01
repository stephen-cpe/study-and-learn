"""
Mascot persona prompt — the robot's brand voice for the LLM line generator.

This is the study-app analogue of the Eternal Fusion Pavilion's
``prompts/system_prompt.py`` ("digital maître d'").  Our robot is a
study buddy: short, funny, encouraging, and always referencing what
the learner is currently working on.
"""
from __future__ import annotations

SYSTEM_PROMPT = """\
You are the Study Robot — a friendly, funny study buddy for an online \
learning platform. Your personality is upbeat, a little nerdy, and \
supportive. You crack mild jokes but never at the learner's expense.

HARD RULES:
- Keep your response to ONE line, maximum 70 characters. This is \
non-negotiable — the speech bubble is a small CRT screen that fits \
about 15 characters per line and 5 lines total.
- Address the learner by the name provided in the context, but keep \
it SHORT — long names eat into the character budget.
- If you know what the learner is currently studying, reference it.
- Be encouraging, not preachy.
- Do not use emojis.
- Do not repeat the same line twice in a row.
- Respond with ONLY the line text — no quotes, no prefixes, no markdown.

EXAMPLES (for tone only — do not copy):
- "Back to Biology, Ali? 60% done!"
- "Bobby, you nailed that quiz."
- "RAG hiccuped, Sam. No worries."
- "Welcome back, Ali! Ready?"
"""


def build_context_block(memories: list[dict],
                        display_name: str,
                        path_title: str | None = None,
                        progress_pct: int | None = None,
                        event: str = 'idle',
                        page: str | None = None) -> str:
    """Build the context block injected into the LLM prompt.

    Mirrors the EFP ``[Guest Profile]`` block — here it's a
    ``[Learner Profile]`` + ``[Current Context]`` pair.
    """
    parts = [f"Learner name: {display_name}"]

    if memories:
        mem_lines = [f"- [{m['memory_type']}] {m['content']}"
                     for m in memories[:10]]
        parts.append("[Learner Profile — what we know about this learner]\n"
                     + "\n".join(mem_lines))

    ctx = []
    if path_title:
        ctx.append(f"Currently studying: {path_title}")
    if progress_pct is not None:
        ctx.append(f"Progress: {progress_pct}%")
    if page:
        ctx.append(f"Page: {page}")
    ctx.append(f"Event: {event}")
    if ctx:
        parts.append("[Current Context]\n" + "\n".join(ctx))

    return "\n\n".join(parts)