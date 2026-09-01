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
"""
import json
import logging
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