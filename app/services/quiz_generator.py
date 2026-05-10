"""
Quiz generation service for the Study-and-Learn MVP.
"""
import json
import random
from app.services.ai_client import call_ollama


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
        except Exception:
            pass

    question_types = ['mcq', 'true_false', 'multi_select', 'fill_blank']
    type_mix = _build_type_mix(n_questions, question_types)

    prompt = f"""You are an AI assistant that creates educational quizzes.
Generate a quiz for the following lesson module.

Module: {module_title}
Lesson Content: {slide_summary}
Additional Context: {rag_context if rag_context else 'None'}

Create exactly {n_questions} questions with the following type distribution:
{json.dumps(type_mix)}

For each question type:
- mcq: Single correct answer from options A-D. Include prompt, options array, answer_index (0-based), explanation.
- true_false: True or false statement. Include prompt, answer (boolean), explanation.
- multi_select: Multiple correct answers from options A-D. Include prompt, options array, answer_indices array (0-based), explanation.
- fill_blank: Sentence with ___ placeholder. Include prompt (with ___), answer string, acceptable_answers array, explanation.

Provide your response in this JSON format:
{{
  "questions": [
    {{
      "id": "q1",
      "type": "mcq",
      "prompt": "What is the capital of France?",
      "options": ["London", "Paris", "Berlin", "Madrid"],
      "answer_index": 1,
      "explanation": "Paris is the capital of France."
    }}
  ]
}}

Quiz:"""

    response = call_ollama(prompt)

    try:
        start_idx = response.find('{')
        end_idx = response.rfind('}') + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response[start_idx:end_idx]
            result = json.loads(json_str)
            if 'questions' in result and isinstance(result['questions'], list):
                validated = _validate_questions(result['questions'], n_questions)
                if validated:
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
        except Exception:
            pass

    prompt = f"""You are an AI assistant that creates quick comprehension checkpoints.
Based on the following lesson segment, create 1 multiple-choice question.

Module: {module_title}
Segment Content: {slide_summary}
Additional Context: {rag_context if rag_context else 'None'}

Provide your response in this JSON format:
{{
  "id": "checkpoint",
  "type": "mcq",
  "prompt": "Question text here?",
  "options": ["A", "B", "C", "D"],
  "answer_index": 0,
  "explanation": "Explanation of the correct answer."
}}

Question:"""

    response = call_ollama(prompt)

    try:
        start_idx = response.find('{')
        end_idx = response.rfind('}') + 1
        if start_idx != -1 and end_idx != 0:
            json_str = response[start_idx:end_idx]
            result = json.loads(json_str)
            if all(k in result for k in ['type', 'prompt', 'options', 'answer_index']):
                return result
    except (json.JSONDecodeError, ValueError, KeyError, TypeError):
        pass

    return {
        'id': 'checkpoint',
        'type': 'mcq',
        'prompt': 'Based on the material you just read, what is the most important concept to remember?',
        'options': ['Review key terms', 'Understand core principles', 'Practice with examples', 'Memorize all facts'],
        'answer_index': 1,
        'explanation': 'Understanding core principles helps you apply knowledge in different contexts.'
    }


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
                valid.append({
                    'id': q.get('id', f'q{len(valid)+1}'),
                    'type': 'fill_blank',
                    'prompt': q['prompt'],
                    'answer': q['answer'],
                    'acceptable_answers': q.get('acceptable_answers', [q['answer']]),
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
            'prompt': 'The process of actively retrieving information from memory is called ___.',
            'answer': 'active recall',
            'acceptable_answers': ['active recall', 'recall', 'retrieval practice'],
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
    return {'questions': questions[:n_questions]}
