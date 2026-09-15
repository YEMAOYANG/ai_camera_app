"""Bounded, pure stdin bridge to the authoritative objective solver. No DB/AI."""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content.formal_objective_rules import objective_question_policy, validate_objective_question


def main():
    raw = sys.stdin.buffer.read(262145)
    if len(raw) > 262144:
        raise ValueError('preflight input too large')
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != {'gradeCode', 'subject', 'skillId', 'objectivePolicy', 'questions'}:
        raise ValueError('preflight input fields mismatch')
    policy = data['objectivePolicy']
    if not isinstance(policy, dict) or data['gradeCode'] not in {f'primary_{i}' for i in range(2, 7)}:
        raise ValueError('preflight authority invalid')
    band = policy.get('difficultyCode')
    expected = objective_question_policy(data['gradeCode'], data['subject'], data['skillId'], band)
    # The adapter sends JSON through Node before returning here. Registered
    # inventories can contain Python tuples (for example English verb forms),
    # which become JSON arrays. Compare the exact JSON authority so that this
    # lossless transport cannot be mistaken for drift. Canonical JSON still
    # distinguishes booleans from numbers and rejects any changed field.
    canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True,
                                          separators=(',', ':'), allow_nan=False)
    if canonical(policy) != canonical(expected):
        raise ValueError('preflight objective authority mismatch')
    questions = data['questions']
    if not isinstance(questions, list) or len(questions) != 5:
        raise ValueError('preflight requires five question objects')
    issues = []
    for index, question in enumerate(questions, 1):
        try:
            if not isinstance(question, dict):
                raise ValueError('question must be an object')
            validate_objective_question(data['gradeCode'], data['subject'], data['skillId'], question, band)
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            issues.append({'question': index, 'reason': ' '.join(str(exc).split())[:240]})
    print(json.dumps({'schemaVersion': 'mira.formal-objective-preflight.v1', 'issues': issues}, ensure_ascii=False))


if __name__ == '__main__':
    main()
