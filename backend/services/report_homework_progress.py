"""Read current, owned same-question correction progress without dispatch or writes.

This is a current snapshot for homework associated with the selected period,
not a historical reconstruction or evidence of independent mastery.
"""
import json

from services.homework_answer_quality import (
    attach_reference_answer_layout, reference_for_correction, reviewed_result,
)
from services.homework_correction import correction_view


SCHEMA = 'mira.report.homework-progress.v1'
COUNTS = ('total', 'corrected', 'selfReportedCompleted', 'inProgress', 'notStarted', 'needsReview', 'assisted')


def _timestamp(value):
    return value if type(value) is int and value > 0 else 0


def homework_progress_for_period(conn, *, family_id, start, end):
    """Select by upload/latest correction activity; expose today's source gate."""
    rows = conn.execute('''SELECT s.*,ch.nickname AS child_name
        FROM homework_submissions s
        JOIN children ch ON ch.id=s.child_id AND ch.family_id=s.family_id
        WHERE s.family_id=? AND s.deleted_at IS NULL AND s.created_at<?
          AND s.source NOT IN (?,?) ORDER BY s.created_at DESC,s.id''',
        (family_id, end, 'synthetic_fixture', 'paid_validation')).fetchall()
    entries = []
    for raw_row in rows:
        row = dict(raw_row)
        items = conn.execute('SELECT * FROM homework_items WHERE submission_id=?',
                             (row['id'],)).fetchall()
        counts = dict.fromkeys(COUNTS, 0)
        latest_answer_at = 0
        question_count = 0
        for raw_item in items:
            item = dict(raw_item)
            raw_page = conn.execute('SELECT * FROM homework_pages WHERE id=? AND submission_id=?',
                                    (item['page_id'], row['id'])).fetchone()
            if raw_page is None:
                continue
            result = reviewed_result(row, item, dict(raw_page))
            if result.get('method') == 'tencent_essay.v1':
                continue
            question_count += 1
            result = attach_reference_answer_layout(conn, row, item, result)
            reference = reference_for_correction(result)
            correction = item['correction_json']
            correction = json.loads(correction) if isinstance(correction, str) else correction
            view = correction_view(result, correction if isinstance(correction, dict) else {}, item_revision=item['revision'])
            latest_answer_at = max(latest_answer_at, _timestamp(view['updatedAt']),
                                  _timestamp(view['selfReportedCompletedAt']))
            if reference is None:
                if result.get('answerState') != 'blank':
                    counts['needsReview'] += 1
                continue
            if reference['originalStatus'] != 'incorrect':
                continue
            counts['total'] += 1
            assisted = any(view[key] for key in ('hintViewed', 'explanationViewed', 'tutorViewed'))
            counts['assisted'] += int(assisted)
            key = ('corrected' if view['correct'] is True else 'selfReportedCompleted'
                   if view['selfReportedCompleted'] else 'inProgress'
                   if view['attempts'] > 0 or assisted else 'notStarted')
            counts[key] += 1
        created_at = _timestamp(row['created_at'])
        if not question_count or not (start <= created_at < end or start <= latest_answer_at < end):
            continue
        entries.append({**counts, 'submissionId': row['id'], 'childId': row['child_id'],
            'childName': row['child_name'], 'title': row['title'],
            'lastActivityAt': max(created_at, latest_answer_at)})
    entries.sort(key=lambda entry: (-entry['lastActivityAt'], entry['submissionId']))
    return {'schemaVersion': SCHEMA, 'scope': 'current_same_question_correction',
        'periodSelection': 'uploaded_or_latest_correction_activity_in_period',
        'submissionCount': len(entries), **{key: sum(entry[key] for entry in entries) for key in COUNTS},
        'independent': None, 'countsForAbility': False, 'entries': entries}
