"""
Quiz generation service for the Study-and-Learn MVP.

Generates mixed-type quizzes (mcq, true_false, multi_select, cloze_dropdown,
ordering, matching) and inline comprehension checkpoints grounded in RAG context. Applies
pedagogical safeguards: plausible distractors, diversified true/false
answers, shuffled option ordering, and cloze dropdown with plausible choices.
"""
import json
import logging
import random
from typing import Any, Callable, Dict, List, Optional

from src.services.ai_client import call_ollama
from src.services.exceptions import AIServiceError
from src.services.llm_json import extract_json
from src.services.prompts import DEFAULT_DIFFICULTY_INSTRUCTION, DIFFICULTY_INSTRUCTIONS

logger = logging.getLogger(__name__)


HUMOR_INSTRUCTIONS = (
    "HUMOR REQUIREMENT:\n"
    "For every mcq and multi_select question, at least ONE distractor (wrong answer) "
    "must be obviously ridiculous — something a knowledgeable person would immediately "
    "dismiss, but which is funny rather than mean or offensive. The humor must stay "
    "within the topic domain. A biology question about cell division might have "
    "'The cell sends a politely worded letter requesting division' as a distractor. "
    "A history question might include an absurd anachronism. "
    "Keep it classroom-appropriate. The other distractors must still be genuinely "
    "plausible per PEDAGOGICAL REQUIREMENTS — only one per question should be ridiculous.\n"
)


def _shuffle_options(
    options: List[str],
    correct_indices: Any,
    single_index: bool = False,
) -> Any:
    """Randomly shuffle MCQ/multi-select options while tracking correct positions.

    Args:
        options: The original ordered list of answer options.
        correct_indices: Index (mcq) or list of indices (multi_select).
        single_index: If True, return a single new index; otherwise a sorted list.

    Returns:
        Tuple of (shuffled_options, new_correct_index_or_indices).
    """
    if not options:
        return options, correct_indices
    indexed = list(enumerate(options))
    random.shuffle(indexed)
    old_to_new = {old: new for new, (old, _) in enumerate(indexed)}
    shuffled = [text for _, text in indexed]
    if single_index:
        return shuffled, old_to_new[correct_indices]
    new_indices = sorted(old_to_new[i] for i in correct_indices)
    return shuffled, new_indices


def _shuffle_questions(
    questions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Randomize option ordering within each question.

    Args:
        questions: List of question dicts from AI output.

    Returns:
        The same questions with shuffled options and updated answer indices.
    """
    for q in questions:
        qtype = q.get('type', '')
        if qtype in ('mcq', 'cloze_dropdown'):
            options = q.get('options', [])
            idx = q.get('answer_index', 0)
            if isinstance(idx, int) and 0 <= idx < len(options):
                q['options'], q['answer_index'] = _shuffle_options(options, idx, True)
        elif qtype == 'multi_select':
            options = q.get('options', [])
            indices = q.get('answer_indices', [])
            if isinstance(indices, list) and all(isinstance(x, int) and 0 <= x < len(options) for x in indices):
                q['options'], q['answer_indices'] = _shuffle_options(options, indices, False)
        elif qtype == 'ordering':
            items = q.get('items', [])
            order = q.get('answer_order', [])
            shuffled = _shuffle_sequence(items, order)
            if shuffled is not None:
                q['items'], q['answer_order'] = shuffled
        elif qtype == 'matching':
            rights = q.get('rights', [])
            indices = q.get('answer_indices', [])
            shuffled = _shuffle_sequence(rights, indices)
            if shuffled is not None:
                q['rights'], q['answer_indices'] = shuffled
    return questions


def _shuffle_sequence(
    display: List[str],
    correct: List[int],
) -> Any:
    """Shuffle a display list while remapping a correct-index sequence.

    Used by ordering (display ``items`` + ``answer_order``) and matching
    (display ``rights`` + per-left ``answer_indices``): the correct values
    are resolved before shuffling, then re-indexed into the new order.

    Returns (shuffled_display, new_correct) or None when the input is not
    a clean permutation (duplicates, out-of-range) — callers keep the
    original ordering in that case.
    """
    if not isinstance(display, list) or not isinstance(correct, list):
        return None
    if len(display) < 2 or len(correct) != len(display):
        return None
    if sorted(correct) != list(range(len(display))):
        # matching answer_indices need not be a permutation (several lefts
        # may share a right in theory) — fall back to value mapping only
        # when every correct entry is in range; duplicates keep positions.
        if not all(isinstance(x, int) and 0 <= x < len(display) for x in correct):
            return None
    try:
        # Validate indexability without keeping the values.
        [display[i] for i in correct]
    except (IndexError, TypeError):
        return None
    if len(set(map(str, display))) != len(display):
        return None
    indexed = list(enumerate(display))
    random.shuffle(indexed)
    old_to_new = {old: new for new, (old, _) in enumerate(indexed)}
    shuffled = [text for _, text in indexed]
    new_correct = [old_to_new[i] for i in correct]
    return shuffled, new_correct


def _diversify_true_false(
    questions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Ensure true/false questions have a mix of True and False answers.

    If all T/F questions share the same answer, inverts every other one
    to prevent learners from guessing the pattern.

    Args:
        questions: List of question dicts.

    Returns:
        The questions with diversified true/false answers.
    """
    tf_indices = [(i, q) for i, q in enumerate(questions) if q.get('type') == 'true_false']
    if len(tf_indices) < 2:
        return questions
    answers = [bool(q.get('answer', False)) for _i, q in tf_indices]
    if all(a == answers[0] for a in answers):
        for idx, (_i, q) in enumerate(tf_indices):
            if idx % 2 == 1:
                q['answer'] = not q['answer']
                q['prompt'] = _invert_statement(q['prompt'])
    return questions


def _invert_statement(text: str) -> str:
    """Invert a true/false statement for answer diversification.

    Args:
        text: The original true/false prompt statement.

    Returns:
        A negated version of the statement.
    """
    t = text.strip()
    if t.lower().startswith('not '):
        return t[4:].strip()
    return 'It is NOT the case that ' + t[0].lower() + t[1:]


def _shuffle_checkpoint(cp: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Shuffle the options in an inline checkpoint question (mcq/cloze_dropdown only).

    Args:
        cp: A checkpoint question dict, or None.

    Returns:
        The checkpoint with shuffled options and updated answer_index,
        or unchanged if not a valid dict or not a shuffleable type.
    """
    if not isinstance(cp, dict):
        return cp
    cptype = cp.get('type', 'mcq')
    if cptype not in ('mcq', 'cloze_dropdown'):
        return cp
    options = cp.get('options', [])
    idx = cp.get('answer_index', 0)
    if isinstance(idx, int) and 0 <= idx < len(options):
        cp['options'], cp['answer_index'] = _shuffle_options(options, idx, True)
    return cp


def _build_quiz_prompt(
    module_title: str,
    slide_summary: str,
    rag_context: str,
    type_mix: Dict[str, int],
    n_questions: int,
    difficulty: str,
) -> str:
    """Assemble the final-quiz generation prompt.

    Pure string assembly — no I/O, no retrieval — so it can be unit
    tested and tuned independently of ``generate_quiz``'s control flow.
    """
    context_instruction = ""
    if rag_context and rag_context.strip():
        context_instruction = (
            "You MUST base every question on facts from the provided Context. "
            "Do NOT ask about information not present in the Context or lesson content. "
            "If the Context lacks sufficient detail for a question, write a question "
            "about a concept from the lesson content instead — never fabricate details.\n\n"
        )
    else:
        context_instruction = (
            "No additional context is available. Base questions only on the lesson content provided. "
            "Use widely known facts only — do NOT invent specific data.\n\n"
        )

    diff_instruction = DIFFICULTY_INSTRUCTIONS.get(difficulty, DEFAULT_DIFFICULTY_INSTRUCTION)

    prompt = f"""You are an expert educator creating a quiz for high-school to early-college learners.

{context_instruction}
{diff_instruction}
Module: {module_title}
Lesson Content: {slide_summary}
Context: {rag_context if rag_context else 'None'}

PEDAGOGICAL REQUIREMENTS:
1. Every distractor (wrong answer) MUST be plausible — a confident but mistaken learner could choose it.
   Avoid absurd, obviously wrong, or silly distractors.
2. Every correct answer MUST be unambiguously correct based on the lesson content or Context.
3. For cloze_dropdown: the blank MUST replace a key term directly stated in the preceding lesson content.
    Provide 3-4 short, plausible options. One must be the correct answer at 'answer_index'.
    The wrong options must be plausible enough that a learner who hasn't read carefully might choose them.
    Do NOT use obviously wrong options. The correct answer should not always be at the same index — vary the position.
4. Explanations MUST explain WHY the correct answer is right and briefly why distractors are wrong.
5. Distribute questions across the module's key concepts — do NOT cluster all questions on one detail.
6. VARY the position of the correct answer across questions. No two consecutive mcq/multi_select
   questions should share the same answer index. For true_false, ensure a mix of True and False answers —
   do NOT make all answers the same boolean value.
7. CRITICAL: Each question MUST test a UNIQUE concept from this module. Do NOT repeat or rephrase
   questions from other modules. If this module covers the same topic as a previous module, test a
   DIFFERENT aspect or detail — never the same question with slightly different wording.

{HUMOR_INSTRUCTIONS}
Create exactly {n_questions} questions with the following type distribution:
{json.dumps(type_mix)}

For each question type:
- mcq: 4 options, exactly 1 correct. Include prompt, options array, answer_index (0-based), explanation.
- true_false: A clear factual statement. Include prompt, answer (boolean), explanation.
- multi_select: 4 options, 2-3 correct. Include prompt, options array, answer_indices array (0-based), explanation.
- cloze_dropdown: A sentence with a key concept replaced by '___'. Provide 3-4 short, plausible options in an 'options' array. One must be the correct answer at 'answer_index'. The wrong options must be plausible enough that a learner who hasn't read carefully might choose them. Do NOT use obviously wrong options. The correct answer should not always be at the same index — vary the position. Include prompt (with ___), options array, answer_index (0-based), explanation.
- ordering: A process, sequence, or timeline with 4 steps in SCRAMBLED display order. Include prompt (e.g. "Put these steps in the correct order, 1 = first"), items array (4 distinct steps, scrambled — never already sorted), answer_order array (the display indices in correct sequence: e.g. items ["Boil","Chop","Serve","Cook"] are correctly ordered Chop, Boil, Cook, Serve, so answer_order is [1,0,3,2]), explanation.
- matching: 4 term/definition pairs. Include prompt (e.g. "Match each term to its definition"), lefts array (4 terms, fixed), rights array (4 definitions, SCRAMBLED — never in matching order), answer_indices array (for each left, the 0-based index into rights of its correct match), explanation.

Respond with ONLY a JSON object — no prose, no markdown, no commentary.

JSON FORMAT:
{{
  "questions": [
    {{
      "id": "q1",
      "type": "mcq",
      "prompt": "What is the capital of France?",
      "options": ["Madrid", "Berlin", "Paris", "London"],
      "answer_index": 2,
      "explanation": "Paris is the capital of France. The other cities are capitals of other European countries."
    }},
    {{
      "id": "q2",
      "type": "true_false",
      "prompt": "The Earth orbits around the Sun.",
      "answer": true,
      "explanation": "The Earth follows an elliptical orbit around the Sun, completing one revolution in approximately 365 days."
    }},
    {{
      "id": "q3",
      "type": "true_false",
      "prompt": "Water boils at 50 degrees Celsius at sea level.",
      "answer": false,
      "explanation": "At standard atmospheric pressure (sea level), water boils at 100 degrees Celsius, not 50."
    }},
    {{
      "id": "q4",
      "type": "multi_select",
      "prompt": "Which of the following are primary colors of light? (Select all that apply)",
      "options": ["Red", "Yellow", "Green", "Blue"],
      "answer_indices": [0, 2, 3],
      "explanation": "Red, green, and blue are the primary colors of light (additive color model)."
    }},
    {{
      "id": "q5",
      "type": "cloze_dropdown",
      "prompt": "The chemical symbol for water is ___. ",
      "options": ["H2O", "CO2", "NaCl", "O2"],
      "answer_index": 0,
      "explanation": "Water is composed of two hydrogen atoms and one oxygen atom, giving it the chemical formula H2O."
    }},
    {{
      "id": "q6",
      "type": "ordering",
      "prompt": "Put these steps of a science experiment in the correct order (1 = first).",
      "items": ["Analyze the results", "Form a hypothesis", "Write the conclusion", "Run the experiment"],
      "answer_order": [1, 3, 0, 2],
      "explanation": "The scientific method runs: hypothesis, experiment, analysis, conclusion."
    }},
    {{
      "id": "q7",
      "type": "matching",
      "prompt": "Match each term to its correct definition.",
      "lefts": ["Hypothesis", "Experiment", "Analysis", "Conclusion"],
      "rights": ["A summary of what was learned", "An educated guess", "Interpreting the data", "A controlled test"],
      "answer_indices": [1, 3, 2, 0],
      "explanation": "Each term pairs with its definition: a hypothesis is an educated guess, an experiment is a controlled test, analysis interprets data, and the conclusion summarizes learning."
    }}
  ]
}}

Quiz:"""
    return prompt


def generate_quiz(
    module_title: str,
    slides: List[Dict[str, Any]],
    retriever: Optional[Callable[[str], Dict[str, Any]]],
    n_questions: int = 6,
    difficulty: str = 'Normal',
) -> Dict[str, Any]:
    """Generate a mixed-type quiz for a module grounded in RAG context.

    Args:
        module_title: The module title.
        slides: The lesson slides to base quiz questions on.
        retriever: A callable that returns RAG context for a query string,
            or None if unavailable.
        n_questions: Number of questions to generate (default 6 — one per
            type: mcq, true_false, multi_select, cloze_dropdown, ordering,
            matching).
        difficulty: One of 'Easy', 'Normal', 'Hard'. Controls vocabulary
            and question complexity. Defaults to 'Normal'.

    Returns:
        A dict with key ``questions`` containing a list of validated,
        shuffled, and diversified question dicts.
    """
    if not module_title or not module_title.strip():
        result = _fallback_quiz(n_questions)
        result['fallback'] = True
        return result

    slide_summary = _summarize_slides(slides)

    rag_context = ""
    if retriever:
        try:
            query = f"{module_title}"
            result = retriever(query)
            if isinstance(result, dict):
                rag_context = result.get("context_text", str(result))
            elif result:
                rag_context = str(result)
        except Exception as e:
            logger.warning("RAG retrieval failed for quiz '%s': %s", module_title, str(e))

    question_types = ['mcq', 'true_false', 'multi_select', 'cloze_dropdown',
                      'ordering', 'matching']
    type_mix = _build_type_mix(n_questions, question_types)

    prompt = _build_quiz_prompt(
        module_title=module_title,
        slide_summary=slide_summary,
        rag_context=rag_context,
        type_mix=type_mix,
        n_questions=n_questions,
        difficulty=difficulty,
    )

    try:
        response = call_ollama(prompt)
    except AIServiceError as e:
        logger.error("Quiz generation failed for module '%s': %s", module_title, str(e))
        result = _fallback_quiz(n_questions, module_title=module_title, slides=slides)
        result['fallback'] = True
        return result

    result = extract_json(response)
    if result and 'questions' in result and isinstance(result['questions'], list):
        validated = _validate_questions(result['questions'], n_questions)
        if validated:
            validated = _shuffle_questions(validated)
            validated = _diversify_true_false(validated)
            return {'questions': validated}

    logger.warning(
        "Quiz JSON parsing/validation failed for module '%s', using fallback. "
        "Response (first 300 chars): %r",
        module_title, response[:300] if response else '<empty>'
    )
    fallback = _fallback_quiz(n_questions, module_title=module_title, slides=slides)
    fallback['fallback'] = True
    return fallback


def generate_inline_checkpoint(
    module_title: str,
    slides_subset: List[Dict[str, Any]],
    retriever: Optional[Callable[[str], Dict[str, Any]]],
    cp_type: Optional[str] = None,
    difficulty: str = 'Normal',
) -> Dict[str, Any]:
    """Generate a single inline comprehension checkpoint.

    Tests immediate recall of a key concept from a segment of slides.
    Supports mcq, true_false, and cloze_dropdown types.

    Args:
        module_title: The module title.
        slides_subset: A subset of slides to base the checkpoint on.
        retriever: A callable that returns RAG context, or None.
        cp_type: Optional checkpoint type. If None, randomly selects from
            ['mcq', 'true_false', 'cloze_dropdown'] with weights [0.5, 0.3, 0.2].
        difficulty: One of 'Easy', 'Normal', 'Hard'. Controls vocabulary
            and question complexity. Defaults to 'Normal'.

    Returns:
        A shuffled checkpoint question dict with keys: id, type, prompt,
        and type-specific answer fields.
    """
    if cp_type is None:
        cp_type = random.choices(
            ['mcq', 'true_false', 'cloze_dropdown'],
            weights=[0.5, 0.3, 0.2],
            k=1
        )[0]

    slide_summary = _summarize_slides(slides_subset)
    rag_context = ""
    if retriever:
        try:
            result = retriever(f"{module_title}")
            if isinstance(result, dict):
                rag_context = result.get("context_text", "")
            elif result:
                rag_context = str(result)
        except Exception as e:
            logger.warning("RAG retrieval failed for checkpoint '%s': %s", module_title, str(e))

    type_instruction = ""
    json_format = ""
    if cp_type == 'mcq':
        type_instruction = (
            "Create 1 multiple-choice question that tests IMMEDIATE RECALL of a key concept "
            "from the lesson segment. Provide 4 plausible options with exactly 1 correct answer."
        )
        json_format = """{{
  "id": "checkpoint",
  "type": "mcq",
  "prompt": "Question text here?",
  "options": ["Option A", "Option B", "Option C", "Option D"],
  "answer_index": <0-based index of correct option>,
  "explanation": "Brief explanation of the correct answer."
}}"""
    elif cp_type == 'true_false':
        type_instruction = (
            "Create 1 true/false question that tests IMMEDIATE RECALL of a key concept "
            "from the lesson segment. The statement must be a clear factual claim."
        )
        json_format = """{{
  "id": "checkpoint",
  "type": "true_false",
  "prompt": "A clear factual statement that is either true or false.",
  "answer": <true or false>,
  "explanation": "Brief explanation of why the statement is true or false."
}}"""
    elif cp_type == 'cloze_dropdown':
        type_instruction = (
            "Create 1 cloze dropdown question that tests IMMEDIATE RECALL of a key concept "
            "from the lesson segment. Replace a key term with '___'. Provide 3-4 short, "
            "plausible options. One must be the correct answer at 'answer_index'. "
            "Wrong options must be plausible enough that a learner who hasn't read "
            "carefully might choose them. Do NOT use obviously wrong options."
        )
        json_format = """{{
  "id": "checkpoint",
  "type": "cloze_dropdown",
  "prompt": "A sentence with a key concept replaced by '___'.",
  "options": ["Correct term", "Plausible wrong A", "Plausible wrong B", "Plausible wrong C"],
  "answer_index": <0-based index of correct option>,
  "explanation": "Brief explanation of the correct answer."
}}"""

    diff_instruction = DIFFICULTY_INSTRUCTIONS.get(difficulty, DEFAULT_DIFFICULTY_INSTRUCTION)

    prompt = f"""You are an expert educator creating a quick comprehension checkpoint for high-school to early-college learners.

{diff_instruction}
{type_instruction}
The question must be answerable using only the information provided below.

Module: {module_title}
Segment Content: {slide_summary}
Context: {rag_context if rag_context else 'None'}

CHECKPOINT RULES:
1. The question MUST test a core concept directly stated in the segment content — NOT obscure trivia.
2. For mcq and cloze_dropdown: all options must be plausible — avoid absurd or obviously wrong distractors.
3. The correct answer must be unambiguously correct based on the segment content.
4. The explanation must briefly justify why the answer is correct.
5. Vary the position of the correct answer. Do NOT always place it at index 0.

Respond with ONLY a JSON object — no prose, no markdown.

JSON FORMAT:
{json_format}

Question:"""

    try:
        response = call_ollama(prompt)
    except AIServiceError as e:
        logger.error("Checkpoint generation failed for module '%s': %s", module_title, str(e))
        return _fallback_checkpoint()

    result = extract_json(response)
    if result:
        if cp_type == 'true_false':
            if all(k in result for k in ['type', 'prompt', 'answer']):
                result['id'] = result.get('id', 'checkpoint')
                result['answer'] = bool(result['answer'])
                return result
        elif cp_type in ('mcq', 'cloze_dropdown'):
            if all(k in result for k in ['type', 'prompt', 'options', 'answer_index']):
                return _shuffle_checkpoint(result)

    logger.warning(
        "Checkpoint JSON parsing failed for module '%s', using fallback. "
        "Response (first 300 chars): %r",
        module_title, response[:300] if response else '<empty>'
    )
    return _fallback_checkpoint()


def _fallback_checkpoint() -> Dict[str, Any]:
    """Return a generic placeholder checkpoint when AI generation fails.

    Returns:
        A shuffled checkpoint dict with a generic comprehension question.
    """
    fallback = {
        'id': 'checkpoint',
        'type': 'mcq',
        'prompt': 'Based on the material you just read, what is the most important concept to remember?',
        'options': ['Review key terms', 'Understand core principles', 'Practice with examples', 'Memorize all facts'],
        'answer_index': 1,
        'explanation': 'Understanding core principles helps you apply knowledge in different contexts.'
    }
    return _shuffle_checkpoint(fallback)


def _summarize_slides(slides: List[Dict[str, Any]]) -> str:
    """Build a text summary from slide content for quiz prompt construction.

    Args:
        slides: List of slide dicts from the lesson generator.

    Returns:
        A space-joined string summarizing all slide content.
    """
    parts: List[str] = []
    for slide in slides:
        stype = slide.get('type', '')
        if stype == 'title':
            parts.append(f"Title: {slide.get('title', '')}")
        elif stype == 'content':
            parts.append(f"Heading: {slide.get('heading', '')}")
            bullets = slide.get('bullets', [])
            parts.extend(bullets)
        elif stype == 'example':
            parts.append(f"Example: {slide.get('body', '')}")
        elif stype == 'summary':
            bullets = slide.get('bullets', [])
            parts.extend(bullets)
    return ' '.join(parts)


def _build_type_mix(n: int, types: List[str]) -> Dict[str, int]:
    """Distribute `n` questions across available question types.

    Args:
        n: Number of questions to generate.
        types: Available question type strings.

    Returns:
        A dict mapping each type to its allocated question count.
    """
    counts: Dict[str, int] = {t: 0 for t in types}
    for i in range(n):
        counts[types[i % len(types)]] += 1
    return counts


def _validate_questions(
    questions: List[Dict[str, Any]],
    expected_count: int,
) -> List[Dict[str, Any]]:
    """Validate and normalize AI-generated quiz questions.

    Filters malformed questions and normalizes structure. Stops early
    once enough valid questions are collected.

    Args:
        questions: Raw question list from AI JSON output.
        expected_count: Minimum number of valid questions needed.

    Returns:
        A list of validated question dicts (up to expected_count items).
    """
    valid: List[Dict[str, Any]] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        qtype = q.get('type', '')
        if qtype == 'mcq':
            if all(k in q for k in ['prompt', 'options', 'answer_index']):
                valid.append({
                    'id': q.get('id', f'q{len(valid)+1}'),
                    'type': 'mcq',
                    'prompt': q['prompt'],
                    'options': q['options'],
                    'answer_index': q['answer_index'],
                    'explanation': q.get('explanation', '')
                })
        elif qtype == 'true_false':
            if all(k in q for k in ['prompt', 'answer']):
                valid.append({
                    'id': q.get('id', f'q{len(valid)+1}'),
                    'type': 'true_false',
                    'prompt': q['prompt'],
                    'answer': bool(q['answer']),
                    'explanation': q.get('explanation', '')
                })
        elif qtype == 'multi_select':
            if all(k in q for k in ['prompt', 'options', 'answer_indices']):
                valid.append({
                    'id': q.get('id', f'q{len(valid)+1}'),
                    'type': 'multi_select',
                    'prompt': q['prompt'],
                    'options': q['options'],
                    'answer_indices': q['answer_indices'],
                    'explanation': q.get('explanation', '')
                })
        elif qtype == 'cloze_dropdown':
            if all(k in q for k in ['prompt', 'options', 'answer_index']):
                valid.append({
                    'id': q.get('id', f'q{len(valid)+1}'),
                    'type': 'cloze_dropdown',
                    'prompt': q['prompt'],
                    'options': q['options'],
                    'answer_index': q['answer_index'],
                    'explanation': q.get('explanation', '')
                })
        elif qtype == 'ordering':
            items = q.get('items', [])
            order = q.get('answer_order', [])
            if (all(k in q for k in ['prompt', 'items', 'answer_order'])
                    and isinstance(items, list) and 3 <= len(items) <= 5
                    and isinstance(order, list)
                    and sorted(order) == list(range(len(items)))
                    and len(set(map(str, items))) == len(items)):
                valid.append({
                    'id': q.get('id', f'q{len(valid)+1}'),
                    'type': 'ordering',
                    'prompt': q['prompt'],
                    'items': items,
                    'answer_order': list(order),
                    'explanation': q.get('explanation', '')
                })
        elif qtype == 'matching':
            lefts = q.get('lefts', [])
            rights = q.get('rights', [])
            indices = q.get('answer_indices', [])
            if (all(k in q for k in ['prompt', 'lefts', 'rights', 'answer_indices'])
                    and isinstance(lefts, list) and isinstance(rights, list)
                    and isinstance(indices, list)
                    and 3 <= len(lefts) <= 5 and len(rights) == len(lefts)
                    and len(indices) == len(lefts)
                    and all(isinstance(x, int) and 0 <= x < len(rights) for x in indices)
                    and len(set(map(str, lefts))) == len(lefts)
                    and len(set(map(str, rights))) == len(rights)):
                valid.append({
                    'id': q.get('id', f'q{len(valid)+1}'),
                    'type': 'matching',
                    'prompt': q['prompt'],
                    'lefts': lefts,
                    'rights': rights,
                    'answer_indices': list(indices),
                    'explanation': q.get('explanation', '')
                })
        elif qtype == 'fill_blank':
            if all(k in q for k in ['prompt', 'options', 'answer_index']):
                valid.append({
                    'id': q.get('id', f'q{len(valid)+1}'),
                    'type': 'cloze_dropdown',
                    'prompt': q['prompt'],
                    'options': q['options'],
                    'answer_index': q['answer_index'],
                    'explanation': q.get('explanation', '')
                })
            elif all(k in q for k in ['prompt', 'answer']):
                answer = q['answer']
                if not isinstance(answer, str):
                    continue
                acceptable = q.get('acceptable_answers', [answer])
                single_word = [a for a in acceptable if isinstance(a, str) and ' ' not in a.strip()]
                if not single_word:
                    single_word = [answer] if ' ' not in answer.strip() else acceptable[:1]
                valid.append({
                    'id': q.get('id', f'q{len(valid)+1}'),
                    'type': 'fill_blank',
                    'prompt': q['prompt'],
                    'answer': answer,
                    'acceptable_answers': single_word,
                    'explanation': q.get('explanation', '')
                })
        if len(valid) >= expected_count:
            break
    return valid


def _fallback_quiz(n_questions: int = 6, module_title: str = '',
                   slides: list = None) -> dict:
    """Return a topic-aware fallback quiz when AI generation fails.

    Unlike the old hardcoded study-skills quiz, this builds questions
    that reference the module title and slide content so the learner
    at least sees something related to their lesson. The questions are
    simple (true/false + mcq) and clearly marked as fallback content.

    Args:
        n_questions: Number of questions to return.
        module_title: The module title (used in question prompts).
        slides: The lesson slides (used to extract key terms/concepts).

    Returns:
        Dict with ``questions`` list.
    """
    title = module_title.strip() if module_title else 'this module'
    slide_summary = _summarize_slides(slides) if slides else ''
    # Extract a few key terms from the slide content for question prompts.
    key_terms = []
    if slide_summary:
        for slide in (slides or []):
            if slide.get('type') == 'content':
                heading = slide.get('heading', '')
                if heading:
                    key_terms.append(heading)
                for b in slide.get('bullets', [])[:2]:
                    # Take the first few words of each bullet as a "concept".
                    words = b.strip().split()
                    if len(words) >= 2:
                        key_terms.append(' '.join(words[:4]))
            elif slide.get('type') == 'title':
                t = slide.get('title', '')
                if t and t.lower() not in title.lower():
                    key_terms.append(t)
    # Deduplicate, keep at most 4.
    seen = set()
    unique_terms = []
    for t in key_terms:
        tl = t.lower()
        if tl not in seen and len(tl) > 2:
            seen.add(tl)
            unique_terms.append(t)
    unique_terms = unique_terms[:4]

    questions = []

    # 1. A true/false about the module title.
    questions.append({
        'id': 'q1',
        'type': 'true_false',
        'prompt': f'The main topic of this module is {title}.',
        'answer': True,
        'explanation': f'This module covers {title}.'
    })

    # 2. An mcq about a key concept from the slides.
    if unique_terms:
        correct = unique_terms[0]
        distractors = unique_terms[1:4] if len(unique_terms) > 1 else [
            'a topic not covered here', 'an unrelated concept',
            'a minor detail'
        ]
        # Pad distractors to 3.
        while len(distractors) < 3:
            distractors.append(f'distractor {len(distractors) + 1}')
        options = [correct] + distractors[:3]
        questions.append({
            'id': 'q2',
            'type': 'mcq',
            'prompt': f'Which of the following is a key concept from {title}?',
            'options': options,
            'answer_index': 0,
            'explanation': f'{correct} is a key concept covered in this module.'
        })
    else:
        questions.append({
            'id': 'q2',
            'type': 'mcq',
            'prompt': f'What is the primary focus of {title}?',
            'options': [
                'The main subject of this module',
                'An unrelated topic',
                'A minor detail',
                'Something not covered here'
            ],
            'answer_index': 0,
            'explanation': f'This question tests your understanding of {title}.'
        })

    # 3. A true/false about a slide detail.
    if unique_terms and len(unique_terms) >= 2:
        questions.append({
            'id': 'q3',
            'type': 'true_false',
            'prompt': f'{unique_terms[1]} is related to {title}.',
            'answer': True,
            'explanation': f'{unique_terms[1]} is discussed in this module.'
        })
    else:
        questions.append({
            'id': 'q3',
            'type': 'true_false',
            'prompt': f'Reviewing the material from {title} is important.',
            'answer': True,
            'explanation': f'Reviewing {title} helps reinforce learning.'
        })

    # 4. A cloze_dropdown with a key term.
    if unique_terms:
        term = unique_terms[0]
        questions.append({
            'id': 'q4',
            'type': 'cloze_dropdown',
            'prompt': f'A key concept in {title} is ___.',
            'options': [term, 'unrelated term A', 'unrelated term B', 'unrelated term C'],
            'answer_index': 0,
            'explanation': f'{term} is a key concept in {title}.'
        })
    else:
        questions.append({
            'id': 'q4',
            'type': 'cloze_dropdown',
            'prompt': 'The subject of this module is ___.',
            'options': [title, 'something else', 'not applicable', 'unknown'],
            'answer_index': 0,
            'explanation': f'This module covers {title}.'
        })

    # 5. A multi_select about key concepts.
    if len(unique_terms) >= 3:
        questions.append({
            'id': 'q5',
            'type': 'multi_select',
            'prompt': f'Which of the following are key concepts from {title}? (Select all that apply)',
            'options': unique_terms[:3] + ['an unrelated concept'] if len(unique_terms) >= 3 else unique_terms + ['extra'],
            'answer_indices': list(range(min(3, len(unique_terms)))),
            'explanation': f'These are key concepts from {title}.'
        })
    else:
        questions.append({
            'id': 'q5',
            'type': 'multi_select',
            'prompt': f'Which of the following help you understand {title}? (Select all that apply)',
            'options': [
                f'Reviewing the slides on {title}',
                'Ignoring the material',
                f'Thinking about {title}',
                'Skipping the lesson'
            ],
            'answer_indices': [0, 2],
            'explanation': f'Reviewing and thinking about {title} helps you learn.'
        })

    # 6. An ordering fallback about the study process itself.
    questions.append({
        'id': 'q6',
        'type': 'ordering',
        'prompt': f'Put these study steps for {title} in a sensible order (1 = first).',
        'items': [
            'Practice with examples',
            'Review the key terms',
            'Check your answers',
            'Understand the core principles',
        ],
        'answer_order': [1, 3, 0, 2],
        'explanation': f'A sensible order is: review key terms, understand principles, practice, then check answers for {title}.'
    })

    sliced = questions[:n_questions]
    sliced = _shuffle_questions(sliced)
    sliced = _diversify_true_false(sliced)
    return {'questions': sliced}
