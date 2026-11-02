"""Translate classroom quiz results into learning evidence."""
from content.textbook_release import questions
from services.learning_evidence_service import record_course_answers


def record_quiz_evidence(conn, session, course, classroom, results, now):
    if not results:
        return 0
    items = [{'id': q['id'], 'skill': q.get('skill'), 'type': q.get('type'),
              'prompt': q.get('question'), 'options': q.get('options'),
              'answer': q.get('answer'), 'explanation': q.get('analysis')}
             for q in questions(classroom)]
    records = [{'questionId': r['questionId'], 'answer': r['response'], 'correct': r['correct'],
                'attemptNumber': 1, 'hintUsed': False} for r in results]
    record_course_answers(conn, session, course, items, records, now)
    return len(records)
