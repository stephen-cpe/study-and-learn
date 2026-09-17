"""
External (web) suggestions — fired only when internal doc topics are
exhausted AND the topic is public.

* Proprietary (HR, company-internal, salaries, memos, confidential) →
  NEVER call web_search. There is nothing to suggest on the web.
* Public (Physics, Engineering, Mathematics, CS, Bio/Chem, generic
  textbooks) → web_search + web_fetch + LLM synthesis with verbatim URLs.

Privacy: only the sanitized topic query (goal + module titles) ever
leaves the server. Raw doc text / digest / summary are NEVER sent to
web_search. Queries are stripped of org names. All functions never
raise — failure yields {"suggestions": [], "source": ...}.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from src.services.ai_client import call_ollama
from src.services.llm_json import extract_json

logger = logging.getLogger(__name__)

MAX_EXTERNAL = 3

# Blocklist wins over allowlist. Hit => proprietary, no web.
_BLOCK_MARKERS = (
    'salary', 'salaries', 'payroll', 'compensation', 'disciplinary',
    'performance review', 'performance improvement', 'employee id',
    'employee handbook', 'hr policy', 'hr handbook', 'internal memo',
    'internal only', 'confidential', 'proprietary', 'non-public',
    'company policy', 'layoff', 'termination', 'benefits enrollment',
)

# Public subjects where web follow-ups make sense.
_PUBLIC_MARKERS = (
    'physics', 'engineering', 'mathematics', 'maths', 'computer science',
    'algorithms', 'data structures', 'machine learning', 'biology',
    'chemistry', 'textbook', 'tutorial', 'calculus', 'linear algebra',
    'thermodynamics', 'mechanics', 'electromagnetism',
)

_ORG_HINT = re.compile(
    r'\b[A-Z][A-Za-z0-9&.\-]*\s+(inc\.?|llc|ltd|corp\.?|gmbh|pty|co\.,?|company|corporation)\b'
    r'|\b(inc\.?|llc|ltd|corp\.?|gmbh|pty|co\.,?|company|corporation)\b',
    re.IGNORECASE,
)


def _clean(text: str, limit: int) -> str:
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    return text if len(text) <= limit else text[:limit] + '…'


def sanitize_query(text: str) -> str:
    """Strip org/company hints + emails/IDs from a web query."""
    t = re.sub(r'\S+@\S+', ' ', str(text or ''))
    t = _ORG_HINT.sub(' ', t)
    # Drop CamelCase internal project codes like ABC-1234.
    t = re.sub(r'\b[A-Z]{2,}-?\d{3,}\b', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()[:200]


def classify_topic_source(
    learning_goal: str = '',
    summary: str = '',
    file_names: List[str] | None = None,
) -> Dict[str, Any]:
    """Classify as public|proprietary. Fail-closed → proprietary.

    Pure heuristic + optional LLM confirm is intentionally NOT used
    here (no extra LLM cost on every suggestions click). Heuristic
    only; returns {source, confidence, reason}.
    """
    try:
        blob = ' '.join([
            str(learning_goal or ''),
            str(summary or '')[:800],
            ' '.join(file_names or []),
        ]).lower()
        for marker in _BLOCK_MARKERS:
            if marker in blob:
                return {
                    'source': 'proprietary',
                    'confidence': 'high',
                    'reason': f"matched blocklist '{marker}'",
                }
        for marker in _PUBLIC_MARKERS:
            if marker in blob:
                return {
                    'source': 'public',
                    'confidence': 'medium',
                    'reason': f"matched allowlist '{marker}'",
                }
        # Filenames like HR_Handbook_* are proprietary even without body hit.
        for name in (file_names or []):
            n = str(name or '').lower()
            if n.startswith(('hr_', 'hr-', 'internal_', 'confidential')):
                return {
                    'source': 'proprietary',
                    'confidence': 'medium',
                    'reason': f"proprietary filename '{name}'",
                }
        return {
            'source': 'proprietary',
            'confidence': 'low',
            'reason': 'no public-subject signal — fail closed',
        }
    except Exception:
        return {'source': 'proprietary', 'confidence': 'low', 'reason': 'error'}


def build_external_query(learning_goal: str, modules: List[Dict[str, Any]]) -> str:
    """Build a short sanitized web query from goal + recent titles."""
    titles = [str((m or {}).get('title', '') or '').strip()
              for m in (modules or []) if (m or {}).get('title')]
    recent = ' '.join(titles[-2:]) if titles else ''
    raw = f"{learning_goal or ''} {recent} next topics to learn".strip()
    return sanitize_query(raw) or sanitize_query(str(learning_goal or '')) or 'general study topics'


def build_external_synthesis_prompt(
    learning_goal: str,
    modules: List[Dict[str, Any]],
    snippets: List[Dict[str, Any]],
) -> str:
    lines = []
    for m in modules or []:
        lines.append(f"- {m.get('title', 'Untitled')}")
    taught = '\n'.join(lines) if lines else '(none)'
    snip_lines = []
    for i, s in enumerate(snippets or []):
        snip_lines.append(
            f"[{i}] Title: {(s.get('title') or '')[:120]}\n"
            f"URL: {s.get('url') or ''}\n"
            f"Snippet: {(s.get('content') or '')[:800]}"
        )
    snippets_text = '\n\n'.join(snip_lines) if snip_lines else '(no snippets)'
    return f"""You are an expert tutor suggesting what to study NEXT after the learner exhausted their documents.

Learning Goal: {_clean(learning_goal, 300)}

Already taught (NEVER suggest these again):
{taught}

Web results (URLs are verbatim — copy them exactly, never invent links):
{snippets_text}

STRICT RULES:
- Propose up to {MAX_EXTERNAL} follow-up topics NOT in the taught list.
- Each reason is ONE sentence grounded in the snippets above.
- source_urls MUST be copied verbatim from the Web results URLs (subset). Empty array if unsure — never invent a URL.
- NEVER include company, employee, or person names from learner docs. Topics must be generic/public.
- Respond with ONLY a JSON object — no prose, no markdown.
JSON FORMAT:
{{
  "suggestions": [
    {{"title": "...", "reason": "...", "source_refs": "...", "source_urls": ["https://..."]}}
  ]
}}
"""


def compute_external_suggestions(
    learning_goal: str,
    modules: List[Dict[str, Any]] | None = None,
    summary: str = '',
    file_names: List[str] | None = None,
    search_fn=None,
    fetch_fn=None,
) -> Dict[str, Any]:
    """Compute web suggestions. Never raises; [] when blocked/failing."""
    import os

    from config_defaults import env_default, env_int

    modules = modules or []
    if os.environ.get('AI_MOCK', '').lower() == 'true':
        return {'suggestions': [], 'source': 'web-disabled-mock'}
    if env_default('WEB_SEARCH_ENABLED', 'false').lower() != 'true':
        return {'suggestions': [], 'source': 'web-disabled'}
    verdict = classify_topic_source(learning_goal, summary, file_names)
    if verdict.get('source') != 'public':
        return {'suggestions': [], 'source': 'proprietary',
                'reason': verdict.get('reason', '')}

    if search_fn is None or fetch_fn is None:
        from src.services.web_search_service import web_fetch as _fetch
        from src.services.web_search_service import web_search as _search
        search_fn = search_fn or _search
        fetch_fn = fetch_fn or _fetch

    try:
        max_results = env_int('WEB_SEARCH_MAX_RESULTS', 5)
        query = build_external_query(learning_goal, modules)
        results = search_fn(query, max_results=max_results) or []
        if not results:
            return {'suggestions': [], 'source': 'web-empty'}

        # Fetch top 2 pages to ground synthesis (cap tokens).
        allowed_urls = {r.get('url') for r in results if r.get('url')}
        enriched = []
        for r in results[:3]:
            body = ''
            try:
                if r.get('url'):
                    body = fetch_fn(r['url']) or ''
            except Exception:
                body = ''
            enriched.append({
                'title': r.get('title', ''),
                'url': r.get('url', ''),
                'content': body[:2000] if body else r.get('content', ''),
            })

        prompt = build_external_synthesis_prompt(learning_goal, modules, enriched)
        model = env_default('WEB_SEARCH_SYNTH_MODEL', 'gpt-oss:20b-cloud')
        try:
            response = call_ollama(prompt, model=model)
        except TypeError:
            response = call_ollama(prompt)
        result = extract_json(response)
        raw = (result or {}).get('suggestions', []) if isinstance(result, dict) else []

        from src.services.suggest_next import _is_duplicate_title as _dup
        from src.services.suggest_next import _normalize_title as _norm
        planned = {_norm((m or {}).get('title', '')) for m in modules}
        suggestions, seen = [], set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            title = str(item.get('title', '')).strip()
            if not title or _norm(title) in seen or _dup(title, planned):
                continue
            # Verbatim-URL enforcement: drop invented links.
            urls = item.get('source_urls', []) or []
            if isinstance(urls, str):
                urls = [urls]
            clean_urls = [u.strip() for u in urls
                          if isinstance(u, str) and u.strip() in allowed_urls][:3]
            seen.add(_norm(title))
            suggestions.append({
                'title': title[:200],
                'reason': str(item.get('reason', '')).strip()[:1000],
                'source_refs': str(item.get('source_refs', '')).strip()[:500],
                'source_urls': clean_urls,
            })
            if len(suggestions) >= MAX_EXTERNAL:
                break
        return {'suggestions': suggestions, 'source': 'web'}
    except Exception as e:
        logger.warning("compute_external_suggestions failed: %s", str(e))
        return {'suggestions': [], 'source': 'web-error'}
