"""Shared, versioned revision questions from completed published classrooms.

Production and grading are deterministic projections of Host-approved contracts.
No request here creates a course, asks a model, or mutates classroom questions.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import logging
import re
import secrets
from typing import Any, Mapping

from core.errors import ApiError
from core.security import now_ms
from repositories.dynamic_learning_course_repository import DynamicLearningCourseRepository
from schemas.learning import question_payload
from services.formal_student_learning_access import assert_formal_student_workspace_open
from services.learning_catalog_validator import PrimaryOneCourseTarget
from services.learning_generated_course_validator import AcceptedPrimaryOneHostReceipt, LearningGeneratedCourseValidator
from services.learning_question_evaluator import LearningQuestionEvaluator
from services.learning_difficulty import available_skill_order, course_difficulty, preferred_difficulty
from content.primary_skill_boundaries import boundaries_for

logger = logging.getLogger(__name__)
SCHEMA = 'mira.learning.practice.v1'
_IDENTIFIER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$')


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def decoded(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


class LearningPracticeService:
    def __init__(self, *, repository, student_auth_service, clock=now_ms, host_validator=None):
        self.repository, self.auth, self.clock = repository, student_auth_service, clock
        self.host_validator = host_validator or LearningGeneratedCourseValidator()
        self.evaluator = LearningQuestionEvaluator()

    def _identity(self, token):
        return self.auth.authenticate(token)['principal']

    def _child(self, conn, principal):
        child = self.repository.lock_child(conn, principal)
        if child is None:
            raise ApiError('student_practice_identity_changed', '学习身份已变化，请重新进入', 409)
        grade = assert_formal_student_workspace_open(child)
        return child, grade, int(child['grade_selection_revision'])

    def start(self, token: str, data: Mapping[str, Any]) -> dict:
        if not isinstance(data, Mapping) or set(data) - {'requestId', 'subject', 'skillId', 'count'}:
            raise ApiError('invalid_practice_request', '练习请求格式不正确')
        request_id, subject, skill = data.get('requestId'), data.get('subject'), data.get('skillId')
        count = data.get('count', 5)
        if (not isinstance(request_id, str) or not _IDENTIFIER.fullmatch(request_id)
                or subject not in ('chinese', 'math', 'english') or type(count) is not int or not 1 <= count <= 5
                or (skill is not None and (not isinstance(skill, str) or not _IDENTIFIER.fullmatch(skill)))):
            raise ApiError('invalid_practice_request', '请选择学科，每次最多练习五题')
        principal, timestamp = self._identity(token), self.clock()
        scope = {'family_id': principal['family_id'], 'child_id': principal['child_id']}
        request_key = digest({**scope, 'requestId': request_id})
        request_hash = digest({'subject': subject, 'skillId': skill, 'count': count})
        with self.repository.transaction() as conn:
            _, grade, revision = self._child(conn, principal)
            prior = self.repository.existing(conn, **scope, request_key=request_key)
            if prior is not None:
                if prior['request_sha256'] != request_hash:
                    raise ApiError('practice_request_conflict', '这次练习请求已使用，请重新开始', 409)
                self._assert_session_grade(prior, grade, revision)
                return self._view(conn, prior)
            active = self.repository.active(conn, **scope, grade_code=grade, grade_revision=revision, subject=subject, skill_id=skill)
            if active is not None:
                return self._view(conn, active)
            sources = self.repository.eligible_sources(conn, **scope, grade_code=grade, subject=subject, skill_id=skill)
            mastery_by_node = None
            if grade != 'primary_1':
                mastery_by_node = self.repository.difficulty_mastery(conn, **scope, grade_code=grade, subject=subject)
                eligible = set(available_skill_order(boundaries_for(grade, subject), mastery_by_node))
                sources = [row for row in sources if row['node_code'] in eligible]
            pool = {}
            for source in sources:
                try:
                    if (mastery_by_node is not None and course_difficulty(source)
                            != preferred_difficulty(mastery_by_node.get(source['node_code']))):
                        continue
                    rows = self._project_source(source, grade=grade, subject=subject, skill=skill, timestamp=timestamp)
                    for row in rows:
                        item = self.repository.project(conn, row)
                        pool[item['dedupe_sha256']] = item
                except (ValueError, KeyError, TypeError, ApiError):
                    logger.warning('Practice source failed immutable Host recheck: %s', source.get('id'))
            seen = self.repository.seen(conn, **scope)
            available = [row for fingerprint, row in pool.items() if fingerprint not in seen]
            secrets.SystemRandom().shuffle(available)
            chosen = available[:count]
            if not chosen:
                return {'ok': True, 'schemaVersion': SCHEMA, 'session': None, 'availableCount': 0,
                        'fallbackPath': '/learning', 'message': ('当前难度还没有新的复习题，先回学习书架复习学过的课程吧。'
                            if grade != 'primary_1' else '暂时没有新的复习题，先回学习书架复习学过的课程吧。')}
            session = { 'id': 'practice_' + secrets.token_hex(16), **scope, 'grade_code': grade,
                'grade_revision': revision, 'subject': subject, 'skill_id': skill,
                'request_key_sha256': request_key, 'request_sha256': request_hash,
                'status': 'in_progress', 'total_questions': len(chosen), 'current_index': 0, 'correct_count': 0,
                'created_at': timestamp, 'updated_at': timestamp, 'completed_at': None }
            exposures = [{ 'id': digest({**scope, 'dedupe': row['dedupe_sha256']}), **scope,
                'dedupe_sha256': row['dedupe_sha256'], 'session_id': session['id'], 'question_id': row['id'],
                'created_at': timestamp } for row in chosen]
            self.repository.create(conn, session=session, questions=chosen, exposures=exposures)
            return {**self._view(conn, session), 'availableCount': len(available)}

    def _project_source(self, source, *, grade, subject, skill, timestamp):
        if (source['grade_code'] != grade or source['subject'] != subject
                or (skill is not None and source['node_code'] != skill)
                or source['status'] != 'published' or source['quality_status'] != 'released' or source.get('retired_at') is not None):
            raise ValueError('practice source scope mismatch')
        content, manifest, envelope = decoded(source['content_json']), decoded(source['feature_manifest_json']), decoded(source['validation_json'])
        if not isinstance(content, dict) or not isinstance(manifest, dict) or not isinstance(envelope, dict):
            raise ValueError('practice source contract missing')
        content_hash = digest(content)
        if (manifest.get('sourceCourseContentSha256') != content_hash
                or envelope.get('hostGateReceiptHash') != source['content_receipt_hash']
                or digest(envelope.get('hostGateReceipt')) != source['content_receipt_hash']):
            raise ValueError('practice source Host identity mismatch')
        target = PrimaryOneCourseTarget(grade_code=grade, subject=subject, subject_ordinal=int(source['subject_ordinal']),
            skill_id=source['node_code'], boundary_ordinal=int(source['boundary_ordinal']), boundary_version=source['boundary_version'],
            variant_ordinal=int(source['variant_ordinal']), instruction_language_code='zh-CN', target_language_code='en-US' if subject == 'english' else 'zh-CN')
        immutable = { 'id': source['id'], 'version': source['version'], 'gradeCode': grade, 'subject': subject,
            'nodeCode': source['node_code'], 'title': source['title'], 'objective': source['objective'], 'status': 'published', 'content': content }
        self.host_validator.validate_primary_one_accepted_receipt(AcceptedPrimaryOneHostReceipt(target=target,
            immutable_course=immutable, receipt=envelope['hostGateReceipt'], receipt_hash=source['content_receipt_hash']))
        questions = content.get('questions')
        flow = content.get('teachingFlow')
        if not isinstance(questions, list) or not isinstance(flow, Mapping):
            raise ValueError('practice source assessment phase is missing')
        allowed = set(flow.get('independentQuestionIds') or [])
        rows = []
        for question in questions:
            if not isinstance(question, dict) or question.get('id') not in allowed:
                continue  # Worked examples and guided/revealed answers are not a revision pool.
            if not self.evaluator.is_scored_deterministic(question.get('type')):
                raise ValueError('practice source cannot be scored deterministically')
            identity = {'gradeCode': grade, 'subject': subject, 'skillId': source['node_code'], 'releaseId': source['release_id'],
                        'courseId': source['id'], 'courseVersion': source['version'], 'questionId': question['id']}
            source_key, contract = digest(identity), digest(question)
            rows.append({'id': digest({**identity, 'contractSha256': contract}), 'source_key_sha256': source_key,
                'grade_code': grade, 'subject': subject, 'skill_id': source['node_code'], 'release_id': source['release_id'],
                'course_id': source['id'], 'course_version': source['version'], 'source_question_id': question['id'],
                'source_content_sha256': content_hash, 'contract_sha256': contract,
                'dedupe_sha256': DynamicLearningCourseRepository.question_fingerprint(grade_code=grade, subject=subject, node_code=source['node_code'], question=question),
                'question_json': canonical(question), 'created_at': timestamp})
        return rows

    def get(self, token, session_id):
        principal = self._identity(token)
        with self.repository.transaction() as conn:
            _, grade, revision = self._child(conn, principal)
            session = self._session(conn, principal, session_id, grade, revision)
            return self._view(conn, session)

    def answer(self, token, session_id, data):
        if (not isinstance(data, Mapping) or set(data) != {'questionId', 'response'} or not isinstance(data['questionId'], str)
                or not re.fullmatch('[a-f0-9]{64}', data['questionId']) or not isinstance(data['response'], (str, list))
                or (isinstance(data['response'], list) and any(not isinstance(item, str) for item in data['response']))
                or len(canonical(data['response']).encode()) > 4096):
            raise ApiError('invalid_practice_answer', '请填写这道题的答案')
        principal = self._identity(token)
        with self.repository.transaction() as conn:
            _, grade, revision = self._child(conn, principal)
            session = self._session(conn, principal, session_id, grade, revision)
            items = self.repository.items(conn, session_id)
            item = next((item for item in items if item['question_id'] == data['questionId']), None)
            if item is None:
                raise ApiError('practice_question_mismatch', '这道题不在本次练习中', 409)
            response_hash = digest(data['response'])
            if item.get('response_sha256') is not None:
                if item['response_sha256'] != response_hash:
                    raise ApiError('practice_answer_conflict', '这道题已经提交过了', 409)
                return {**self._view(conn, session), 'evaluation': decoded(item['feedback_json'])}
            if item['ordinal'] != session['current_index'] or session['status'] != 'in_progress':
                raise ApiError('practice_question_order', '请先完成当前这道题', 409)
            question = decoded(item['snapshot_json'])
            if digest(question) != item['contract_sha256']:
                raise ApiError('practice_contract_changed', '练习题版本校验没有通过，请返回学习书架', 409)
            evaluated = self.evaluator.evaluate(question, data['response'])
            if evaluated.get('status') not in ('correct', 'incorrect'):
                raise ApiError('practice_answer_unscorable', '这道题暂时无法判定，请返回学习书架', 409)
            correct = evaluated['status'] == 'correct'
            feedback = {'questionId': item['question_id'], 'correct': correct, 'status': evaluated['status'],
                'message': '答对啦！' if correct else '这次还差一点，回想一下老师的示范。',
                'explanation': str(question.get('explanation') or ''), 'evaluatorVersion': self.evaluator.version}
            self.repository.answer(conn, session=session, item=item, response_sha256=response_hash, feedback=feedback, now=self.clock())
            current = self._session(conn, principal, session_id, grade, revision)
            return {**self._view(conn, current), 'evaluation': feedback}

    def _session(self, conn, principal, session_id, grade, revision):
        if not isinstance(session_id, str) or not _IDENTIFIER.fullmatch(session_id):
            raise ApiError('practice_session_not_found', '没有找到这次练习', 404)
        session = self.repository.get_session(conn, family_id=principal['family_id'], child_id=principal['child_id'], session_id=session_id)
        if session is None:
            raise ApiError('practice_session_not_found', '没有找到这次练习', 404)
        self._assert_session_grade(session, grade, revision)
        return session

    @staticmethod
    def _assert_session_grade(session, grade, revision):
        if session['grade_code'] != grade or int(session['grade_revision']) != revision:
            raise ApiError('practice_grade_changed', '年级已更新，请返回学习书架开始新的练习', 409)

    def _view(self, conn, session):
        index = int(session['current_index'])
        items = self.repository.items(conn, session['id'])
        current = next((item for item in items if item['ordinal'] == index), None) if session['status'] == 'in_progress' else None
        public = None
        if current:
            question = deepcopy(decoded(current['snapshot_json']))
            if digest(question) != current['contract_sha256']:
                raise ApiError('practice_contract_changed', '练习题版本校验没有通过', 409)
            question['id'] = current['question_id']
            public = question_payload(question, index=index, attempt_number=1, choice_seed=session['id'])
        return {'ok': True, 'schemaVersion': SCHEMA, 'fallbackPath': '/learning',
            'session': {'id': session['id'], 'gradeCode': session['grade_code'], 'subject': session['subject'],
                'skillId': session['skill_id'], 'status': session['status'], 'currentQuestionIndex': index,
                'totalQuestions': int(session['total_questions']), 'correctCount': int(session['correct_count']),
                'currentQuestion': public, 'completedAt': session.get('completed_at')}}
