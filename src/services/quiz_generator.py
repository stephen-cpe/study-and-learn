"""
Quiz generation service for the Study-and-Learn MVP.
"""
import json
import random
import logging
from src.services.ai_client import call_ollama
from src.services.exceptions import AIServiceError

logger = logging.getLogger(__name__)


def _shuffle_options(options, correct_indices, single_index=False):
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


def _shuffle_questions(questions):
    for q in questions:
        qtype = q.get('type', '')
        if qtype == 'mcq':
            options = q.get('options', [])
            idx = q.get('answer_index', 0)
            if isinstance(idx, int) and 0 <= idx < len(options):
                q['options'], q['answer_index'] = _shuffle_options(options, idx, True)
        elif qtype == 'multi_select':
            options = q.get('options', [])
            indices = q.get('answer_indices', [])
            if isinstance(indices, list) and all(isinstance(x, int) and 0 <= x < len(options) for x in indices):
                q['options'], q['answer_indices'] = _shuffle_options(options, indices, False)
    return questions


def _diversify_true_false(questions):
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


def _invert_statement(text):
    t = text.strip()
    if t.lower().startswith('not '):
        return t[4:].strip()
    return 'It is NOT the case that ' + t[0].lower() + t[1:]


def _shuffle_checkpoint(cp):
    if not isinstance(cp, dict):
        return cp
    options = cp.get('options', [])
    idx = cp.get('answer_index', 0)
    if isinstance(idx, int) and 0 <= idx < len(options):
        cp['options'], cp['answer_index'] = _shuffle_options(options, idx, True)
    return cp


def generate_quiz(module_title: str, slides: list, retriever, n_questions: int = 5) -> dict:
    if not module_title or not module_title.strip():
        return _fallback_quiz(n_questions)

    slide_summary = _summarize_slides(slides)

    rag_context = ""
    if retriever:
        try:
            query = f"{module_title}"
            result = retriever(query)
            if result:
                rag_context = result
        except Exception as e:
            logger.warning("RAG retrieval failed for quiz '%s': %s", module_title, str(e))

    question_types = ['mcq', 'true_false', 'multi_select', 'fill_blank']
    type_mix = _build_type_mix(n_questions, question_types)

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

    prompt = f"""You are an expert educator creating a quiz for high-school to early-college learners.

{context_instruction}
Module: {module_title}
Lesson Content: {slide_summary}
Context: {rag_context if rag_context else 'None'}

PEDAGOGICAL REQUIREMENTS:
1. Every distractor (wrong answer) MUST be plausible — a confident but mistaken learner could choose it.
   Avoid absurd, obviously wrong, or silly distractors.
2. Every correct answer MUST be unambiguously correct based on the lesson content or Context.
3. For fill_blank: the answer MUST be a single word only (no spaces, no hyphens, no multi-word phrases).
   The blank MUST replace a key term directly stated in the preceding lesson content.
4. Explanations MUST explain WHY the correct answer is right and briefly why distractors are wrong.
5. Distribute questions across the module's key concepts — do NOT cluster all questions on one detail.
6. VARY the position of the correct answer across questions. No two consecutive mcq/multi_select
   questions should share the same answer index. For true_false, ensure a mix of True and False answers —
   do NOT make all answers the same boolean value.

Create exactly {n_questions} questions with the following type distribution:
{json.dumps(type_mix)}

For each question type:
- mcq: 4 options, exactly 1 correct. Include prompt, options array, answer_index (0-based), explanation.
- true_false: A clear factual statement. Include prompt, answer (boolean), explanation.
- multi_select: 4 options, 2-3 correct. Include prompt, options array, answer_indices array (0-based), explanation.
- fill_blank: A sentence with exactly one ___ placeholder replacing a single key term. Include prompt (with ___), answer string (single word only — no spaces), acceptable_answers array (each a single word), explanation.

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
      "type": "fill_blank",
      "prompt": "The chemical symbol for water is ___. ",
      "answer": "H2O",
      "acceptable_answers": ["H2O", "h2o"],
      "explanation": "Water is composed of two hydrogen atoms and one oxygen atom, giving it the chemical formula H2O."
    }}
  ]
}}

Quiz:"""

    try:
        response = call_ollama(prompt)
    except AIServiceError as e:
        logger.error("Quiz generation failed for module '%s': %s", module_title, str(e))
        return _fallback_quiz(n_questions)

    try:
        start_idx = response.find('{')
        end_idx = response.rfind('}') + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response[start_idx:end_idx]
            result = json.loads(json_str)
            if 'questions' in result and isinstance(result['questions'], list):
                validated = _validate_questions(result['questions'], n_questions)
                if validated:
                    validated = _shuffle_questions(validated)
                    validated = _diversify_true_false(validated)
                    return {'questions': validated}
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        pass

    return _fallback_quiz(n_questions)


def generate_inline_checkpoint(module_title: str, slides_subset: list, retriever) -> dict:
    slide_summary = _summarize_slides(slides_subset)
    rag_context = ""
    if retriever:
        try:
            result = retriever(f"{module_title}")
            if result:
                rag_context = result
        except Exception as e:
            logger.warning("RAG retrieval failed for checkpoint '%s': %s", module_title, str(e))

    prompt = f"""You are an expert educator creating a quick comprehension checkpoint for high-school to early-college learners.

Create 1 multiple-choice question that tests IMMEDIATE RECALL of a key concept from the lesson segment.
The question must be answerable using only the information provided below.

Module: {module_title}
Segment Content: {slide_summary}
Context: {rag_context if rag_context else 'None'}

CHECKPOINT RULES:
1. The question MUST test a core concept directly stated in the segment content — NOT obscure trivia.
2. All 4 options must be plausible — avoid absurd or obviously wrong distractors.
3. The correct answer must be unambiguously correct based on the segment content.
4. The explanation must briefly justify why the answer is correct.
5. Vary the position of the correct answer. Do NOT always place it at index 0.

Respond with ONLY a JSON object — no prose, no markdown.

JSON FORMAT:
{{
  "id": "checkpoint",
  "type": "mcq",
  "prompt": "Question text here?",
  "options": ["Option A", "Option B", "Option C", "Option D"],
  "answer_index": <0-based index of correct option>,
  "explanation": "Brief explanation of the correct answer."
}}

Question:"""

    try:
        response = call_ollama(prompt)
    except AIServiceError as e:
        logger.error("Checkpoint generation failed for module '%s': %s", module_title, str(e))
        return _fallback_checkpoint()

    try:
        start_idx = response.find('{')
        end_idx = response.rfind('}') + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response[start_idx:end_idx]
            result = json.loads(json_str)
            if all(k in result for k in ['type', 'prompt', 'options', 'answer_index']):
                return _shuffle_checkpoint(result)
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        pass

    return _fallback_checkpoint()


def _fallback_checkpoint() -> dict:
    fallback = {
        'id': 'checkpoint',
        'type': 'mcq',
        'prompt': 'Based on the material you just read, what is the most important concept to remember?',
        'options': ['Review key terms', 'Understand core principles', 'Practice with examples', 'Memorize all facts'],
        'answer_index': 1,
        'explanation': 'Understanding core principles helps you apply knowledge in different contexts.'
    }
    return _shuffle_checkpoint(fallback)


def _summarize_slides(slides: list) -> str:
    parts = []
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


def _build_type_mix(n: int, types: list) -> dict:
    counts = {t: 0 for t in types}
    for i in range(n):
        counts[types[i % len(types)]] += 1
    return counts


def _validate_questions(questions: list, expected_count: int) -> list:
    valid = []
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
        elif qtype == 'fill_blank':
            if all(k in q for k in ['prompt', 'answer']):
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


def _fallback_quiz(n_questions: int = 5) -> dict:
    questions = [
        {
            'id': 'q1',
            'type': 'true_false',
            'prompt': 'Understanding core concepts is essential for mastering any subject.',
            'answer': True,
            'explanation': 'Core concepts form the foundation for deeper learning.'
        },
        {
            'id': 'q2',
            'type': 'mcq',
            'prompt': 'What is the most effective way to learn new material?',
            'options': [
                'Passive reading only',
                'Active recall and practice',
                'Skipping difficult sections',
                'Memorizing without understanding'
            ],
            'answer_index': 1,
            'explanation': 'Active recall and practice are proven to be the most effective learning strategies.'
        },
        {
            'id': 'q3',
            'type': 'multi_select',
            'prompt': 'Which of the following are effective study techniques? (Select all that apply)',
            'options': [
                'Spaced repetition',
                'Cramming the night before',
                'Teaching others',
                'Practice testing'
            ],
            'answer_indices': [0, 2, 3],
            'explanation': 'Spaced repetition, teaching others, and practice testing are all evidence-based study techniques.'
        },
        {
            'id': 'q4',
            'type': 'fill_blank',
            'prompt': 'The practice of actively retrieving information from memory is called ___.',
            'answer': 'recall',
            'acceptable_answers': ['recall', 'retrieval'],
            'explanation': 'Active recall is the practice of actively stimulating memory during the learning process.'
        },
        {
            'id': 'q5',
            'type': 'mcq',
            'prompt': 'Why is it important to review material multiple times?',
            'options': [
                'To waste time',
                'To strengthen neural connections',
                'Because teachers say so',
                'It is not important'
            ],
            'answer_index': 1,
            'explanation': 'Reviewing material strengthens neural connections, making recall easier and more durable.'
        }
    ]
    questions = [q for q in questions if q.get('type') != 'true_false' or q.get('answer') is not False]
    questions = [
        {'id': 'q_tf_f', 'type': 'true_false', 'prompt': 'Last-minute cramming is the most effective way to retain information long-term.', 'answer': False, 'explanation': 'Cramming leads to rapid forgetting. Spaced repetition is far more effective for long-term retention.'}
    ] + questions
    sliced = questions[:n_questions]
    sliced = _shuffle_questions(sliced)
    sliced = _diversify_true_false(sliced)
    return {'questions': sliced}
