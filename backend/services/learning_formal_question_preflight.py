"""Pure live-work admission; historical dispatch decoding remains unchanged."""
from __future__ import annotations
from collections.abc import Mapping
from content.formal_objective_rules import validate_objective_question


class FormalQuestionPreflightError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__('; '.join(f"q{x['question']}: {x['reason']}" for x in self.issues))


def validate_formal_phase_question_checkpoint(command) -> None:
    # Invalid raw questions are the input to bounded repair, not a terminal
    # preparation failure. The Sidecar checks repaired output with this same
    # Host solver; only accepted questions may reach paid lesson generation.
    if command.grade_code == 'primary_1' or command.phase in {'outline', 'raw_candidate', 'candidate_repair', 'candidate_repair_retry'}:
        return
    key = ('rawCandidate' if command.phase in {'candidate_repair','candidate_repair_retry'} else
           'candidate' if command.phase in {'lesson_text','reconciliation','reconciliation_retry'} else
           'reconciliation' if command.phase in {'independent_verification','practice_leak_repair_1','practice_leak_repair_2','choice_prompt_repair'} else
           'candidateCourse')
    candidate = command.checkpoint.get(key)
    if key == 'candidateCourse' and isinstance(candidate, Mapping): candidate = candidate.get('content')
    questions = candidate.get('questions') if isinstance(candidate, Mapping) else None
    if not isinstance(questions, list) or len(questions) != 5:
        raise FormalQuestionPreflightError([{'question':0,'reason':'five frozen question objects are required'}])
    issues=[]
    for index, question in enumerate(questions,1):
        try:
            if not isinstance(question, Mapping): raise ValueError('question must be an object')
            validate_objective_question(command.grade_code, command.subject, command.boundary['skillId'], question, command.difficulty_code)
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            issues.append({'question':index,'reason':' '.join(str(exc).split())[:240]})
    if issues: raise FormalQuestionPreflightError(issues)
