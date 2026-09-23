"""Honest prerequisite placement from unused, formally released questions.

No generation occurs here. Every source is revalidated at issue, resume and
answer. All reserved questions count as exposed, including abandoned attempts.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
import re
import secrets

from content.progressive_curriculum import CURRICULUM_VERSION, lesson_by_id, prerequisite_closure
from core.errors import ApiError
from core.security import now_ms
from repositories.progressive_formal_course_repository import progressive_formal_authority
from repositories.progressive_learning_repository import ProgressiveLearningRepository
from schemas.learning import decode_question_response, question_payload
from services.formal_student_learning_access import assert_formal_student_workspace_open
from services.learning_question_evaluator import LearningQuestionEvaluator
from services.progressive_course_generation import validate_progressive_course_for_release
from services.progressive_learning_service import ProgressiveLearningService, _canonical, _content, _grade_number, _question_fingerprint, _sha, lesson_mastery_policy


SCHEMA = 'mira.learning.placement.v1'


def _decoded(value):
    return json.loads(value) if isinstance(value, str) else value


class LearningPlacementService:
    def __init__(self, *, repository, student_auth_service, clock=now_ms):
        self.repository, self.auth, self.clock = repository, student_auth_service, clock
        self.progression = ProgressiveLearningService(ProgressiveLearningRepository(repository.database))
        self.evaluator = LearningQuestionEvaluator()

    def _child(self, conn, principal):
        child = self.repository.lock_child(conn, principal)
        if child is None:
            raise ApiError('placement_identity_changed', '学习身份已变化，请重新进入', 409)
        assert_formal_student_workspace_open(child)
        return child

    @staticmethod
    def _scope(child):
        return {'family_id': child['family_id'], 'child_id': child['id'], 'curriculum_version': CURRICULUM_VERSION}

    def _next_lesson(self, conn, child, subject):
        if subject not in {'chinese', 'math', 'english'}:
            raise ApiError('placement_subject_invalid', '请选择语文、数学或英语', 400)
        # There is no explicit remediation scope in the current product.
        # Enrollment starts at that grade's own introduction; an empty history
        # never authorizes a diagnostic across all of the earlier grades.
        return None

    def _envelope(self, subject, status, lesson=None, *, attempt=None, message=None):
        messages = {
            'available': '先独立完成基础摸底，已经掌握的这一课可以直接通过。',
            'preparing': '未见过的基础题正在准备，可以先回学习路线学习。',
            'observation_required': '这部分需要实际朗读或操作，请先学习，再请家长确认独立表现。',
            'not_required': '请从当前年级的入门课程开始，按顺序继续学习。',
            'needs_learning': '这部分先从基础课学起，学会后再继续下一课。',
            'in_progress': '继续上次的基础摸底，已提交的作答会保留。',
            'completed': '基础摸底已完成。',
        }
        return {'ok': True, 'schemaVersion': SCHEMA, 'subject': subject, 'status': status,
                'message': message or messages[status], 'canStart': status == 'available',
                'lesson': {key: lesson[key] for key in ('lessonId', 'title', 'gradeCode', 'subject', 'assessmentMode')} if lesson else None,
                'attempt': attempt, 'fallbackPath': '/learning/path?subject=' + subject}

    def status(self, token, query):
        if not isinstance(query, Mapping) or set(query) - {'subject'}:
            raise ApiError('placement_request_invalid', '摸底请求格式不正确', 400)
        principal = self.auth.authenticate(token)['principal']
        with self.repository.transaction() as conn:
            child = self._child(conn, principal)
            return self._status(conn, child, query.get('subject'))

    def _status(self, conn, child, subject):
        lesson = self._next_lesson(conn, child, subject)
        if lesson is None:
            return self._envelope(subject, 'not_required')
        if lesson['assessmentMode'] == 'observed':
            return self._envelope(subject, 'observation_required', lesson)
        prior = self.repository.existing_attempt(conn, **self._scope(child), lesson_id=lesson['lessonId'])
        if prior is not None:
            if (prior['status'] == 'invalidated' or prior['grade_code'] != child['grade_code']
                    or int(prior['grade_revision']) != int(child['grade_selection_revision'])):
                return self._envelope(subject, 'needs_learning', lesson)
            if prior['status'] == 'completed':
                # A failed attempt never offers a second opportunity using known answers.
                return self._view(conn, prior, status='needs_learning')
            try:
                self._validate_attempt(conn, child, prior)
            except ApiError:
                self.repository.invalidate_attempt(conn, attempt_id=prior['id'], now=int(self.clock()))
                return self._envelope(subject, 'needs_learning', lesson)
            return self._view(conn, prior)
        questions, known_exposure = self._available_questions(conn, child, lesson)
        if not known_exposure:
            return self._envelope(subject, 'needs_learning', lesson)
        chosen = self._choose(questions, lesson_mastery_policy(lesson)['independentQuestionCount'])
        return self._envelope(subject, 'available' if chosen else 'preparing', lesson)

    def start(self, token, data):
        if not isinstance(data, Mapping) or set(data) != {'lessonId'} or not isinstance(data.get('lessonId'), str):
            raise ApiError('placement_request_invalid', '请选择需要摸底的基础课次', 400)
        self.auth.authenticate(token)
        raise ApiError('placement_explicit_scope_required', '请先按当前年级的学习路线学习，当前无需基础摸底', 409)

    def _start_scoped_attempt(self, token, data):
        """Retained internal implementation; no route grants remediation scope."""
        try:
            requested = lesson_by_id(data['lessonId'])
        except (KeyError, ValueError):
            raise ApiError('placement_lesson_invalid', '课次不存在，请重新打开学习路线', 400)
        principal, timestamp = self.auth.authenticate(token)['principal'], int(self.clock())
        with self.repository.transaction() as conn:
            child = self._child(conn, principal)
            lesson = self._next_lesson(conn, child, requested['subject'])
            if lesson is None or lesson['lessonId'] != requested['lessonId']:
                raise ApiError('placement_lesson_not_next', '请从当前需要补齐的基础课次开始', 409)
            state = self._status(conn, child, requested['subject'])
            if state['status'] != 'available':
                return state
            # Reuse only the verified pool inside this locked transaction. No
            # request body can supply a question, expected answer or score.
            questions, known_exposure = self._available_questions(conn, child, lesson)
            policy = lesson_mastery_policy(lesson)
            chosen = self._choose(questions, policy['independentQuestionCount']) if known_exposure else []
            if not chosen:
                return self._envelope(lesson['subject'], 'preparing', lesson)
            attempt = {'id': 'placement_' + secrets.token_hex(16), **self._scope(child),
                       'grade_code': child['grade_code'], 'grade_revision': int(child['grade_selection_revision']),
                       'subject': lesson['subject'], 'lesson_id': lesson['lessonId'], 'policy_json': _canonical(policy),
                       'status': 'in_progress', 'total_questions': len(chosen), 'current_index': 0,
                       'correct_count': 0, 'passed': None, 'created_at': timestamp, 'updated_at': timestamp, 'completed_at': None}
            self.repository.create_attempt(conn, attempt=attempt, questions=chosen)
            return self._view(conn, attempt)

    def get(self, token, attempt_id):
        principal = self.auth.authenticate(token)['principal']
        with self.repository.transaction() as conn:
            child = self._child(conn, principal)
            attempt = self._load(conn, child, attempt_id)
            self._validate_attempt(conn, child, attempt)
            return self._view(conn, attempt)

    def answer(self, token, attempt_id, data):
        if (not isinstance(data, Mapping) or set(data) != {'questionId', 'answer'}
                or not isinstance(data.get('questionId'), str)):
            raise ApiError('placement_answer_invalid', '请提交当前题目的作答', 400)
        try:
            answer_json = json.dumps(data['answer'], ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        except (TypeError, ValueError):
            raise ApiError('placement_answer_invalid', '作答格式不正确', 400)
        if len(answer_json) > 8192:
            raise ApiError('placement_answer_invalid', '作答内容过长', 400)
        principal, timestamp = self.auth.authenticate(token)['principal'], int(self.clock())
        with self.repository.transaction() as conn:
            child = self._child(conn, principal)
            attempt = self._load(conn, child, attempt_id)
            items = self._validate_attempt(conn, child, attempt)
            item = next((value for value in items if value['question_id'] == data['questionId']), None)
            if item is None:
                raise ApiError('placement_question_invalid', '题目不属于这次摸底', 409)
            response_hash = _sha(data['answer'])
            if item['response_sha256'] is not None:
                if response_hash != item['response_sha256']:
                    raise ApiError('placement_answer_immutable', '这道题已经提交，首次作答不能更改', 409)
                return self._view(conn, attempt)
            if attempt['status'] != 'in_progress' or int(item['ordinal']) != int(attempt['current_index']):
                raise ApiError('placement_question_out_of_order', '请先完成当前题目', 409)
            question = {**_decoded(item['snapshot_json']), 'id': item['question_id']}
            public = question_payload(question, index=int(item['ordinal']), attempt_number=1, choice_seed=attempt['id'])
            submitted = data['answer']
            if question['type'] == 'single_choice':
                if not isinstance(submitted, str) or submitted not in {choice['id'] for choice in public['choices']}:
                    raise ApiError('placement_answer_invalid', '请从当前题目的选项中作答', 400)
            elif question['type'] in {'sequence', 'tap_objects'}:
                options = public['choices'] if question['type'] == 'sequence' else public['objects']
                if (not isinstance(submitted, list) or not submitted or len(submitted) > 20
                        or any(not isinstance(value, str) or value not in {option['id'] for option in options} for value in submitted)):
                    raise ApiError('placement_answer_invalid', '请使用当前题目的选项或物体作答', 400)
            elif not isinstance(submitted, str) or not submitted.strip():
                raise ApiError('placement_answer_invalid', '请先填写作答内容', 400)
            response = decode_question_response(question, data['answer'], choice_seed=attempt['id'] + ':' + item['question_id'])
            evaluation = self.evaluator.evaluate(question, response)
            if evaluation['correct'] is None:
                raise ApiError('placement_question_unavailable', '这道题暂不可用，请返回学习路线', 409)
            policy = _decoded(attempt['policy_json'])
            correct = int(evaluation['correct'])
            passed = (int(attempt['correct_count']) + correct) / int(attempt['total_questions']) >= policy['minimumAccuracy']
            self.repository.answer_item(conn, attempt=attempt, item=item, response_sha256=response_hash,
                                        correct=correct, passed=passed, now=timestamp)
            attempt = self._load(conn, child, attempt_id)
            if attempt['status'] == 'completed':
                self.progression.record_placement_evidence(conn, child=child, attempt=attempt, now=timestamp)
            return self._view(conn, attempt)

    def _load(self, conn, child, attempt_id):
        if not isinstance(attempt_id, str) or not re.fullmatch(r'placement_[0-9a-f]{32}', attempt_id):
            raise ApiError('placement_not_found', '未找到这次基础摸底', 404)
        attempt = self.repository.get_attempt(conn, family_id=child['family_id'], child_id=child['id'], attempt_id=attempt_id)
        if attempt is None:
            raise ApiError('placement_not_found', '未找到这次基础摸底', 404)
        return dict(attempt)

    def _validate_source(self, conn, child, source, lesson):
        binding = self.progression.binding_for_course(conn, course=source)
        if binding is None or binding['lesson_id'] != lesson['lessonId']:
            raise ValueError('placement lesson binding mismatch')
        self.progression.assert_course_progression(conn, child=child, course=source)
        authority = progressive_formal_authority(conn, database=self.repository.database, child=child, course=source)
        if authority is None:
            raise ValueError('placement source is not formally available')
        validate_progressive_course_for_release(conn, course=source, expected_lesson_id=lesson['lessonId'])
        return binding, dict(authority)

    def _available_questions(self, conn, child, lesson):
        seen, known = self._seen_questions(conn, child)
        if not known:
            return [], False
        pool = {}
        for source in self.progression.course_candidates(conn, lesson_id=lesson['lessonId']):
            try:
                binding, authority = self._validate_source(conn, child, source, lesson)
                content = _content(source)
                if content.get('assessmentMode') != 'objective' or content.get('difficultyCode') != 'basic':
                    continue
                allowed = {step.get('questionId') for step in content['progressiveFlow'] if step['phase'] == 'independent'}
                for question in content['questions']:
                    fingerprint = _question_fingerprint(question)
                    if (question['id'] not in allowed or fingerprint in seen
                            or not self.evaluator.is_scored_deterministic(question['type'])):
                        continue
                    pool.setdefault(fingerprint, {
                        'question_id': 'placementq_' + secrets.token_hex(16), 'course_id': source['id'],
                        'course_version': source['version'], 'source_question_id': question['id'],
                        'assessment_set_id': binding['assessment_set_id'], 'question_fingerprint': fingerprint,
                        'source_content_sha256': binding['content_sha256'], 'authority_sha256': _sha(authority),
                        'snapshot_sha256': _sha(question), 'snapshot_json': _canonical(question),
                        'response_sha256': None, 'correct': None, 'answered_at': None})
            except (ApiError, KeyError, ValueError, TypeError):
                continue
        return list(pool.values()), True

    def inventory_status(self, conn, *, child, lesson):
        """Read-only supply boundary; raw course counts cannot prove a fresh set."""
        questions, known = self._available_questions(conn, child, lesson)
        policy = lesson_mastery_policy(lesson)
        sets = {question['assessment_set_id'] for question in questions}
        return {'exposureKnown': known, 'availableQuestionCount': len(questions),
                'assessmentSetIds': sorted(sets),
                'ready': known and len(questions) >= policy['independentQuestionCount']
                         and len(sets) >= policy['distinctAssessmentSets']}

    def _seen_questions(self, conn, child, *, exclude_attempt_id=None):
        courses, practice, fingerprints = self.repository.exposure_sources(
            conn, family_id=child['family_id'], child_id=child['id'], exclude_attempt_id=exclude_attempt_id)
        seen = {row['question_fingerprint'] for row in fingerprints}
        try:
            for row in courses:
                content = _decoded(row['content_json'])
                if not isinstance(content, Mapping) or not isinstance(content.get('questions'), list):
                    return seen, False
                for question in content['questions']:
                    if not isinstance(question, Mapping) or not question.get('prompt'):
                        return seen, False
                    seen.add(_question_fingerprint(question))
            for row in practice:
                question = _decoded(row['question_json'])
                if not isinstance(question, Mapping) or not question.get('prompt'):
                    return seen, False
                seen.add(_question_fingerprint(question))
        except (KeyError, TypeError, ValueError):
            return seen, False
        return seen, True

    @staticmethod
    def _choose(questions, count):
        groups = {}
        for question in questions:
            groups.setdefault(question['assessment_set_id'], []).append(question)
        if len(groups) < 2 or len(questions) < count:
            return []
        groups = list(groups.values())
        secrets.SystemRandom().shuffle(groups)
        for group in groups:
            secrets.SystemRandom().shuffle(group)
        chosen = []
        while len(chosen) < count:
            for group in groups:
                if group and len(chosen) < count:
                    chosen.append(group.pop())
        return chosen

    def _validate_attempt(self, conn, child, attempt):
        lesson = lesson_by_id(attempt['lesson_id'])
        policy = lesson_mastery_policy(lesson)
        if (attempt['status'] == 'invalidated' or attempt['curriculum_version'] != CURRICULUM_VERSION or attempt['grade_code'] != child['grade_code']
                or int(attempt['grade_revision']) != int(child['grade_selection_revision'])
                or _grade_number(lesson['gradeCode']) >= _grade_number(child['grade_code'])
                or lesson['assessmentMode'] != 'objective'
                or _decoded(attempt['policy_json']) != policy
                or int(attempt['total_questions']) != policy['independentQuestionCount']):
            raise ApiError('placement_scope_changed', '学习资料或摸底规则已变化，请回学习路线继续学习', 409)
        progress = self.progression.repository.list_progress(conn, **self._scope(child))
        if (any(not self.progression._mastered(progress, identifier) for identifier in prerequisite_closure(lesson['lessonId']))
                or attempt['status'] == 'in_progress' and self.progression._mastered(progress, lesson['lessonId'])):
            raise ApiError('placement_progress_changed', '学习进度已变化，请回学习路线继续学习', 409)
        items = self.repository.items(conn, attempt['id'])
        if (len(items) != int(attempt['total_questions']) or {int(item['ordinal']) for item in items} != set(range(len(items)))
                or len({item['assessment_set_id'] for item in items}) < policy['distinctAssessmentSets']
                or len({item['question_fingerprint'] for item in items}) != len(items)):
            raise ApiError('placement_contract_changed', '摸底题目记录不完整，请回学习路线', 409)
        if attempt['status'] == 'in_progress':
            seen, known = self._seen_questions(conn, child, exclude_attempt_id=attempt['id'])
            if not known or any(item['question_fingerprint'] in seen for item in items):
                raise ApiError('placement_question_exposed', '这部分已经进入学习，请回学习路线继续练习', 409)
        sources = {}
        try:
            for item in items:
                key = (item['course_id'], item['course_version'])
                if key not in sources:
                    source = self.repository.source_course(conn, course_id=key[0], course_version=key[1])
                    if source is None:
                        raise ValueError('placement source removed')
                    binding, authority = self._validate_source(conn, child, source, lesson)
                    sources[key] = (_content(source), binding, authority)
                content, binding, authority = sources[key]
                question = _decoded(item['snapshot_json'])
                original = next((value for value in content['questions'] if value['id'] == item['source_question_id']), None)
                if (original != question or _sha(question) != item['snapshot_sha256']
                        or _question_fingerprint(question) != item['question_fingerprint']
                        or binding['assessment_set_id'] != item['assessment_set_id']
                        or binding['content_sha256'] != item['source_content_sha256']
                        or _sha(authority) != item['authority_sha256']
                        or not any(step.get('questionId') == item['source_question_id'] and step['phase'] == 'independent'
                                   for step in content['progressiveFlow'])):
                    raise ValueError('placement frozen source changed')
        except (ApiError, ValueError, TypeError, KeyError) as exc:
            raise ApiError('placement_source_unavailable', '这组摸底题的课程已更新或暂不可用，请回学习路线', 409) from exc
        return items

    def _view(self, conn, attempt, *, status=None):
        completed = attempt['status'] == 'completed'
        items = self.repository.items(conn, attempt['id'])
        index = int(attempt['current_index'])
        current = None
        if not completed:
            item = items[index]
            current = question_payload({**_decoded(item['snapshot_json']), 'id': item['question_id']},
                index=index, attempt_number=1, choice_seed=attempt['id'])
        payload = {'id': attempt['id'], 'status': attempt['status'], 'currentQuestionIndex': index,
                   'totalQuestions': int(attempt['total_questions']), 'answeredCount': index, 'currentQuestion': current,
                   'result': {'passed': bool(attempt['passed']), 'correctCount': int(attempt['correct_count']),
                              'totalQuestions': int(attempt['total_questions']),
                              'accuracy': int(attempt['correct_count']) / int(attempt['total_questions']),
                              'masteryStatus': 'mastered' if attempt['passed'] else 'needs_practice'} if completed else None}
        return self._envelope(attempt['subject'], status or attempt['status'], lesson_by_id(attempt['lesson_id']), attempt=payload)
