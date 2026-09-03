"""
RAG retriever orchestrator service.
"""
import logging
import uuid
from typing import Any, Dict, List

from config_defaults import RAG_TOP_K_DEFAULT, env_int
from src.services.chunker import chunk_text
from src.services.rag_budget import (
    estimate_coverage_ratio,
    estimate_total_chars,
    get_context_budget_chars,
)
from src.services.vector_store import (
    get_collection_name,
    retrieve_context,
    retrieve_from_multiple_collections,
    retrieve_from_multiple_collections_with_sources,
    retrieve_with_scores,
    store_chunks,
)

logger = logging.getLogger(__name__)


def build_rag_context(goal: str, files_data: List[str]) -> str:
    """Orchestrate RAG pipeline: chunk, store, and retrieve context.
    
    Args:
        goal (str): The learning goal (used as query)
        files_data (List[str]): List of extracted text from uploaded files
        
    Returns:
        str: Retrieved context from RAG pipeline
    """
    if not files_data:
        return ""
    
    all_chunks = []
    
    for text in files_data:
        if text and text.strip():
            chunks = chunk_text(text)
            all_chunks.extend(chunks)
    
    if not all_chunks:
        return ""
    
    collection_name = f"study_{uuid.uuid4().hex[:8]}"
    
    try:
        store_chunks(all_chunks, collection_name)
        top_k = env_int('RAG_TOP_K', RAG_TOP_K_DEFAULT)
        context = retrieve_context(goal, collection_name, top_k=top_k)
        return context
    except Exception as e:
        logger.warning("RAG pipeline failed, falling back to concatenated text: %s", str(e))
        return ""


def _resolve_valid_collections(goal: str, file_hashes: List[str]) -> List[str]:
    """Discover, validate, and if needed rebuild the ChromaDB collections
    for the given file hashes.

    For each hash: if a ChromaDB collection exists, accept it; if not but
    ContentRegistry has cached text, chunk and embed it on-the-fly. Each
    discovered collection is then probed with a tiny retrieval — a
    collection whose index is corrupted (e.g. HNSW "Nothing found on
    disk") is deleted and rebuilt from ContentRegistry text before being
    accepted.

    Note: the ``ContentRegistry`` and ``get_chroma_client`` imports are
    deliberately function-level (call-time) so tests can patch them at
    their source modules.

    Args:
        goal: The learning goal (used as the probe query).
        file_hashes: List of SHA-256 hashes for uploaded files.

    Returns:
        List of valid collection names; empty when nothing could be
        discovered or rebuilt.
    """
    from src.models import ContentRegistry

    collection_names = []

    for h in file_hashes:
        coll_name = get_collection_name(h)
        try:
            from src.services.vector_store import get_chroma_client
            client = get_chroma_client()
            try:
                client.get_collection(name=coll_name)
                collection_names.append(coll_name)
                continue
            except Exception as e:
                logger.debug("Collection '%s' not found, will rebuild from registry: %s", coll_name, str(e))

            entry = ContentRegistry.query.filter_by(file_hash=h).first()
            if entry and entry.extracted_text:
                chunks = chunk_text(entry.extracted_text)
                if chunks:
                    chunk_metadata = [{"source_hash": h, "content_type": "text"} for _ in chunks]
                    store_chunks(chunks, coll_name, metadata=chunk_metadata)
                    collection_names.append(coll_name)
        except Exception as e:
            logger.warning("Skipping hash %s: %s", h[:8], str(e))

    if not collection_names:
        logger.warning("No ChromaDB collections found for any file hash, falling back")
        return []

    from src.services.vector_store import get_chroma_client as _get_client
    clean_client = _get_client()
    valid_names = []
    for coll_name in collection_names:
        try:
            retrieve_with_scores(goal, coll_name, top_k=1)
            valid_names.append(coll_name)
        except Exception as e:
            logger.warning(
                "Collection '%s' is corrupted (query failed), attempting rebuild: %s",
                coll_name[:40], str(e)
            )
            try:
                clean_client.delete_collection(name=coll_name)
            except Exception:
                pass
            for h in file_hashes:
                test_name = get_collection_name(h)
                if test_name == coll_name:
                    entry = ContentRegistry.query.filter_by(file_hash=h).first()
                    if entry and entry.extracted_text:
                        chunks = chunk_text(entry.extracted_text)
                        if chunks:
                            chunk_metadata = [{"source_hash": h, "content_type": "text"} for _ in chunks]
                            try:
                                store_chunks(chunks, coll_name, metadata=chunk_metadata)
                                valid_names.append(coll_name)
                            except Exception as rebuild_err:
                                logger.warning(
                                    "Failed to rebuild corrupted collection '%s': %s",
                                    coll_name[:40], str(rebuild_err)
                                )
                    break

    if not valid_names:
        logger.warning("No valid ChromaDB collections found for any file hash")
        return []

    return valid_names


def build_rag_context_from_hashes(goal: str, file_hashes: List[str], top_k: int = None) -> str:
    """Build RAG context by querying content-keyed ChromaDB collections.

    Collection discovery, corruption detection, and rebuilds are handled
    by :func:`_resolve_valid_collections`; this function then queries all
    valid collections and merges the results.

    Args:
        goal: The learning goal (used as retrieval query)
        file_hashes: List of SHA-256 hashes for uploaded files

    Returns:
        Merged RAG context from all relevant document collections.
    """
    if not file_hashes:
        return ""

    valid_names = _resolve_valid_collections(goal, file_hashes)
    if not valid_names:
        return ""

    try:
        context = retrieve_from_multiple_collections(goal, valid_names, top_k=top_k)
        return context
    except Exception as e:
        logger.warning("Multi-collection retrieval failed: %s", str(e))
        return ""


def build_rag_context_from_hashes_with_sources(
    goal: str, file_hashes: List[str], file_names: List[str] = None,
    top_k: int = None, exclude_chunks: set = None, max_chars: int = None,
) -> Dict[str, Any]:
    """Build RAG context with source provenance metadata.

    Like ``build_rag_context_from_hashes`` but returns a dict with both the
    joined context text and per-chunk source metadata including resolved
    filenames.  The retrieved context is sized so it actually fits inside
    the model's context window (see :mod:`rag_budget`).

    Args:
        goal: The learning goal (used as retrieval query).
        file_hashes: SHA-256 hashes for uploaded files.
        file_names: Parallel list of original filenames, one per hash.
            Used to resolve human-readable names in source entries.
        top_k: Total number of top chunks across all collections.  When
            None, the context-aware per-collection depth is used so the
            retrieval scales with ``OLLAMA_NUM_CTX``.
        exclude_chunks: Optional set of chunk IDs to omit (cross-module
            dedup).
        max_chars: Hard cap on the joined context length in characters.
            When None, derived from the context budget.

    Returns:
        Dict with ``context_text`` (str) and ``sources`` (list of dicts
        each containing chunk_id, source_hash, score, text, filename).
    """
    if not file_hashes:
        return {"context_text": "", "sources": []}

    hash_to_name: Dict[str, str] = {}
    if file_names:
        for h, name in zip(file_hashes, file_names):
            if h and name:
                hash_to_name[h] = name

    valid_names = _resolve_valid_collections(goal, file_hashes)
    if not valid_names:
        return {"context_text": "", "sources": []}

    try:
        result = retrieve_from_multiple_collections_with_sources(
            goal, valid_names, top_k=top_k, max_chars=max_chars
        )
        if exclude_chunks:
            filtered_sources = []
            filtered_docs = []
            for source in result.get("sources", []):
                chunk_id = source.get("chunk_id", "")
                if chunk_id and chunk_id in exclude_chunks:
                    continue
                filtered_sources.append(source)
                filtered_docs.append(source.get("text", ""))
            result["sources"] = filtered_sources
            result["context_text"] = "\n\n".join(filtered_docs)
        for source in result.get("sources", []):
            sh = source.get("source_hash", "")
            source["filename"] = hash_to_name.get(sh, sh[:12] + "...")
        return result
    except Exception as e:
        logger.warning("Multi-collection retrieval with sources failed: %s", str(e))
        return {"context_text": "", "sources": []}


# ── Full-coverage map-reduce context ─────────────────────────────────────
#
# Relevance-filtered retrieval only ever surfaces the ``top_k`` most similar
# chunks, which means arbitrary sections of the document never reach the LLM
# (the model never "reads" most of the file).  The map step fixes this by
# summarizing *every* extracted chunk in reading order, concatenating the
# per-chunk summaries into a "document digest", and prepending that digest
# to the (budget-sized) retrieved context.  The LLM is therefore grounded in
# the *entire* document regardless of which chunks similarity search picked.


def _split_into_sections(text: str, max_section_chars: int) -> List[str]:
    """Split *text* into ordered sections no larger than ``max_section_chars``.

    Splits on blank lines first, then hard-splits overly long segments so no
    single map call exceeds the section budget.  Guarantees every returned
    section is non-empty and within budget.
    """
    if not text or max_section_chars <= 0:
        return []

    def _hard_split(s: str) -> List[str]:
        out = []
        while len(s) > max_section_chars:
            head = s[:max_section_chars]
            cut = head.rfind('. ')
            if cut <= 0 or cut + 2 > max_section_chars:
                cut = max_section_chars
            out.append(s[:cut].strip())
            s = s[cut:]
        s = s.strip()
        if s:
            out.append(s)
        return [seg for seg in out if seg]

    sections: List[str] = []
    current = ''
    for para in [p.strip() for p in text.split('\n\n') if p.strip()]:
        if len(para) > max_section_chars:
            # Flush any accumulated section, then hard-split the long para.
            if current:
                sections.append(current)
                current = ''
            sections.extend(_hard_split(para))
            continue
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= max_section_chars:
            current = candidate
        else:
            if current:
                sections.append(current)
            current = para
    if current:
        sections.append(current)
    # Defensive: nothing leaves here longer than the budget.
    return [s for s in sections if s]


def _map_summaries(
    file_hashes: List[str],
    file_names: List[str],
    goal: str,
    summary_max_chars: int,
    progress_callback=None,
) -> str:
    """Run the map step: summarize every chunk of every file.

    Returns a concatenated digest of per-chunk summaries in reading order.
    Any LLM failure on a section is replaced with a truncated plain-text
    version of that section so coverage is preserved even when the model
    cannot summarize it.
    """
    from src.models import ContentRegistry
    from src.services import rag_budget

    parts: List[str] = []
    total_sections = 0
    max_sections = rag_budget.map_max_sections()
    section_budget = rag_budget.map_max_section_chars()

    for file_idx, file_hash in enumerate(file_hashes):
        if not file_hash:
            continue
        entry = ContentRegistry.query.filter_by(file_hash=file_hash).first()
        if not entry or not entry.extracted_text:
            continue

        file_name = (
            file_names[file_idx]
            if file_names and file_idx < len(file_names)
            else (file_hash[:12] + '...')
        )
        sections = _split_into_sections(entry.extracted_text, section_budget)
        if not sections:
            continue

        for sec_idx, section in enumerate(sections):
            if total_sections >= max_sections:
                break
            total_sections += 1
            if progress_callback:
                progress_callback(total_sections, max_sections)

            prompt = (
                "You are preparing a reading digest so another AI can answer questions "
                "about the entire document without reading it fully. Read the section "
                f"below, extracted from '{file_name}' (section {sec_idx + 1} of "
                f"{len(sections)} in this file), and write a concise, faithful summary "
                "of every important fact, definition, step, number, and concept it "
                "contains. Preserve concrete details — they are the only record the "
                "downstream AI will have of this section.\n\n"
                f"Learning Goal: {goal}\n\n"
                f"Section:\n{section}\n\n"
                f"Digest entry (under {summary_max_chars} characters):"
            )
            try:
                from src.services.ai_client import call_ollama
                digest = call_ollama(prompt)
            except Exception as e:
                logger.warning(
                    "Map summary failed for %s section %d: %s",
                    file_name, sec_idx + 1, str(e),
                )
                digest = section[:summary_max_chars]

            header = f"[{file_name} — section {sec_idx + 1}/{len(sections)}]"
            parts.append(f"{header}\n{digest.strip()}")

        if total_sections >= max_sections:
            break

    return "\n\n".join(parts)


def build_full_coverage_context(
    goal: str,
    file_hashes: List[str],
    file_names: List[str] = None,
    *,
    top_k: int = None,
    exclude_chunks: set = None,
    progress_callback=None,
) -> Dict[str, Any]:
    """Build a context string grounded in the **entire** document.

    Pipeline:

    1.  Map step — summarize every extracted chunk in reading order
        (full coverage, independent of similarity to the query).
    2.  Budget-sized reduce step — retrieve the most relevant chunks within
        the context window's character budget.
    3.  Return ``digest + retrieved`` as ``context_text`` with the same
        ``sources`` provenance as the regular retrieval path.

    The result is attached as ``content_digest`` on the payload so callers
    (summarizer, curriculum generator, relevance checker) can ground their
    prompts in the digest even when the retrieved chunk list is relevance-
    restricted.

    Falls back to plain retrieval when the map step is disabled
    (``RAG_SUMMARY_MAP=false``) or produces nothing.
    """
    from src.services import rag_budget

    # Default character budget for the retrieved half: half of the usable
    # context window.  The digest gets the other half.  Both halves are
    # computed with the SAME fraction so the digest budget is genuinely the
    # complement of the retrieved budget (not a second, full-size budget that
    # would overfill the context window).
    retrieved_budget = get_context_budget_chars(fraction=0.5)

    retrieved = build_rag_context_from_hashes_with_sources(
        goal, file_hashes, file_names,
        top_k=top_k, exclude_chunks=exclude_chunks, max_chars=retrieved_budget,
    )

    if not rag_budget.map_reduce_enabled():
        retrieved['content_digest'] = ''
        retrieved['coverage_ratio'] = None
        return retrieved

    digest_budget = get_context_budget_chars(fraction=0.5)
    digest = _map_summaries(
        file_hashes, file_names or [], goal,
        summary_max_chars=rag_budget.map_max_section_chars() // 2,
        progress_callback=progress_callback,
    )

    if digest and len(digest) > digest_budget:
        marker = '\n[... digest truncated to fit context window ...]'
        keep = max(0, digest_budget - len(marker))
        digest = digest[:keep] + marker if keep > 0 else digest[:digest_budget]

    parts = []
    if digest:
        parts.append(
            "# Complete Document Digest\n"
            "(full-coverage summary of every section, in reading order)\n\n"
            + digest
        )
    if retrieved.get('context_text'):
        parts.append("# Retrieved Context\n" + retrieved['context_text'])

    retrieved['content_digest'] = digest
    retrieved['context_text'] = "\n\n".join(parts)

    total_chars = estimate_total_chars(file_hashes)
    retrieved_chars = len(retrieved['context_text'])
    retrieved['coverage_ratio'] = estimate_coverage_ratio(
        retrieved_chars, total_chars
    )
    return retrieved