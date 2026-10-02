"""
Shared LLM JSON extraction helper.

Every service that asks the LLM for JSON (quiz_generator, curriculum_generator,
relevance_checker, lesson_generator) previously used the same fragile pattern::

    start = response.find('{')
    end = response.rfind('}') + 1
    json_str = response[start:end]
    result = json.loads(json_str)

This fails on:
  - Markdown code fences (```` ```json ... ``` ````) — the fence characters
    contaminate the substring.
  - Prose before/after the JSON — ``rfind('}')`` may grab a brace from
    trailing remarks.
  - Truncation (timeout mid-generation) — ``json.loads`` raises and the
    ``except`` silently swallows it, leaving no diagnostic log.

``extract_json`` handles these cases:
  1. Strips markdown code fences.
  2. Uses ``json.JSONDecoder().raw_decode`` to parse from the first ``{``
     rather than guessing the endpoint with ``rfind``.
  3. Logs a WARNING with the raw response on failure so the failure is
     never silent.

``call_ollama_json`` wraps the full generate→parse→repair loop used by the
lesson and quiz generators: on a parse/validation failure it re-prompts the
model with a repair instruction before the caller degrades to a placeholder.
This is the highest-impact reliability control for the class of defects the
quality audit found (every degraded module carried ``parse_error`` and no
retry was ever attempted).
"""
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

# Matches ```json ... ``` or ``` ... ``` fences.
_FENCE_RE = re.compile(r'^```(?:json)?\s*\n?(.*?)\n?```\s*$', re.DOTALL)


def extract_json(response: str):
    """Extract and parse the first JSON object from an LLM response.

    Strips markdown code fences, finds the first ``{``, and uses
    ``raw_decode`` to parse exactly as much as constitutes a valid JSON
    object (ignoring trailing prose). Returns ``None`` on failure and
    logs a WARNING with the raw response so the failure is diagnosable.

    Args:
        response: The raw LLM response text.

    Returns:
        The parsed JSON object (dict/list/primitive), or ``None`` if no
        valid JSON could be extracted.
    """
    if not response or not response.strip():
        return None

    text = response.strip()

    # Strip markdown code fences: ```json\n{...}\n```  ->  {...}
    m = _FENCE_RE.match(text)
    if m:
        text = m.group(1).strip()

    # Find the first '{' — the start of the JSON object.
    start = text.find('{')
    if start == -1:
        logger.warning("Failed to extract JSON: no '{' found in response: %r",
                       text[:200])
        return None

    # Use raw_decode to parse from `start` — it consumes exactly one
    # JSON value and ignores trailing content (prose, fences, etc.).
    # This is more robust than rfind('}') which can grab braces from
    # trailing remarks or miss nested-object endpoints.
    try:
        decoder = json.JSONDecoder()
        result, _end = decoder.raw_decode(text[start:])
        return result
    except json.JSONDecodeError as e:
        logger.warning(
            "Failed to extract JSON from LLM response: %s. "
            "Response (first 300 chars): %r",
            e, text[:300]
        )
        return None


def extract_json_array(response: str):
    """Extract and parse the first JSON array from an LLM response.

    Like :func:`extract_json` but looks for ``[`` instead of ``{``.
    Used by the narration-script generators which expect a JSON array
    of ``{"slide_index": int, "text": str}`` objects.

    Args:
        response: The raw LLM response text.

    Returns:
        The parsed JSON array (list), or ``None`` if no valid array
        could be extracted.
    """
    if not response or not response.strip():
        return None

    text = response.strip()

    # Strip markdown code fences.
    m = _FENCE_RE.match(text)
    if m:
        text = m.group(1).strip()

    start = text.find('[')
    if start == -1:
        logger.warning("Failed to extract JSON array: no '[' found in response: %r",
                       text[:200])
        return None

    try:
        decoder = json.JSONDecoder()
        result, _end = decoder.raw_decode(text[start:])
        if isinstance(result, list):
            return result
        return None
    except json.JSONDecodeError as e:
        logger.warning(
            "Failed to extract JSON array from LLM response: %s. "
            "Response (first 300 chars): %r",
            e, text[:300]
        )
        return None


# ── Generate → parse → repair loop ──────────────────────────────────────
#
# The quality audit found that 100% of degraded modules (41.5% of all
# generated modules across a 53-module sample) carried
# ``fallback_reason='parse_error'`` and that no retry was ever attempted:
# ``generate_lesson`` retried once on backend errors only, and a malformed
# or truncated JSON response fell straight through to the placeholder.
#
# These helpers wrap the full loop so a parse failure gets one or more
# repair attempts (re-prompting the model with the invalid output and a
# strict "return ONLY valid JSON matching this schema" instruction) before
# the caller degrades to a placeholder.


def _repair_prompt(original_prompt: str, bad_response: str,
                   schema_hint: str = "") -> str:
    """Build the repair re-prompt sent after an unparseable response."""
    tail = bad_response[-4000:] if bad_response else '<empty response>'
    schema = f"\nRequired shape:\n{schema_hint}\n" if schema_hint else ""
    return (
        "Your previous output was not valid JSON and could not be parsed.\n"
        f"{schema}\n"
        "Rewrite the SAME content as a single valid JSON object. "
        "Return ONLY the JSON object — no prose, no markdown fences, no "
        "commentary. Ensure every string is quoted, every array/object is "
        "closed, and no trailing commas are present.\n\n"
        "Previous invalid output (tail):\n"
        f"{tail}\n\n"
        f"Original task:\n{original_prompt}"
    )


def generate_json(
    prompt: str,
    call_fn,
    parse_fn=None,
    schema_hint: str = "",
    max_attempts: int = None,
    label: str = "llm_json",
):
    """Call the model and parse JSON, retrying with a repair prompt.

    Args:
        prompt: The original generation prompt.
        call_fn: Callable ``(prompt) -> str`` invoking the backend.
        parse_fn: Callable ``(response) -> parsed | None``; defaults to
            :func:`extract_json`.
        schema_hint: Short schema description included in repair prompts.
        max_attempts: Total attempts (initial + repairs). Defaults to
            ``1 + LLM_JSON_REPAIR_ATTEMPTS`` (env-tunable).
        label: Log prefix (e.g. the module title).

    Returns:
        The parsed JSON object, or ``None`` when every attempt failed.
        Never raises for parse failures; backend exceptions propagate so
        the caller keeps its existing error handling.
    """
    if parse_fn is None:
        parse_fn = extract_json
    if max_attempts is None:
        from config_defaults import LLM_JSON_REPAIR_ATTEMPTS_DEFAULT
        # Under AI_MOCK the backend is a deterministic stub: it returns the
        # same non-JSON text every time, so retrying can never succeed and
        # only wastes test time. One attempt in mock mode.
        if os.environ.get('AI_MOCK', '').lower() == 'true':
            max_attempts = 1
        else:
            try:
                extra = int(os.environ.get(
                    'LLM_JSON_REPAIR_ATTEMPTS',
                    LLM_JSON_REPAIR_ATTEMPTS_DEFAULT,
                ))
            except (TypeError, ValueError):
                extra = LLM_JSON_REPAIR_ATTEMPTS_DEFAULT
            max_attempts = 1 + max(0, extra)

    response = None
    for attempt in range(max_attempts):
        if attempt == 0:
            response = call_fn(prompt)
        else:
            response = call_fn(_repair_prompt(prompt, response, schema_hint))
        parsed = parse_fn(response)
        if parsed is not None:
            if attempt > 0:
                logger.info(
                    "%s: JSON repair attempt %d/%d succeeded",
                    label, attempt, max_attempts - 1,
                )
            return parsed
        logger.warning(
            "%s: attempt %d/%d produced unparseable JSON "
            "(response length=%d)",
            label, attempt + 1, max_attempts,
            len(response) if response else 0,
        )
    logger.error(
        "%s: all %d JSON attempts failed; caller must degrade",
        label, max_attempts,
    )
    return None


def log_bad_response(response: str, reason: str = "", limit: int = 2000) -> None:
    """Log head+tail of a failed response for post-mortem diagnosis.

    Truncation is the most common parse-error cause; logging both ends lets
    an operator distinguish it from malformed nesting or prose wrappers.
    """
    if not response:
        logger.error("LLM response was empty (%s)", reason or 'unknown')
        return
    head = response[:limit]
    tail = response[-limit:] if len(response) > limit else ''
    logger.error(
        "LLM response unusable (%s) length=%d. HEAD: %r%s",
        reason or 'unknown', len(response), head,
        f" TAIL: {tail!r}" if tail else '',
    )