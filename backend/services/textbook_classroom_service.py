"""Student access, playback progress and deterministic grading for fixed releases."""
from datetime import datetime
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from threading import Lock
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from itsdangerous import BadSignature, URLSafeTimedSerializer

from content.textbook_catalog import canonical, digest, lesson_by_id
from content import textbook_journey as textbook_activity
from services.textbook_journey_service import sync_journey
from content.textbook_classroom import classroom_roster, discussion_request, INTERACTION_PATHS
from content.textbook_release import KEY, INPUT_SCHEMA, fail, grade_answers, public_classroom, validate_release, questions
from core.errors import ApiError
from core.security import now_ms
from repositories.learning_repository import LearningRepository
from repositories.textbook_repository import TextbookRepository
from repositories.course_storage_repository import CourseStorageRepository
from services.course_file_store import CourseFileStore, CourseFileStorageError
from services import textbook_activity_state as activity_state


RECEIPT_SCHEMA = 'mira.openmaic.student-runtime-event-receipt.v1'
_CLASSROOM_SOURCE = Path('openmaic-runtime/.runtime/OpenMAIC/data/classrooms')
_CLASSROOM_CACHE_BYTES = 64 * 1024 * 1024
_CLASSROOM_CACHE_ENTRIES = 64


class TextbookClassroomService:
    def __init__(self, repository, *, student_auth, signing_key, public_url, budget_service=None,
                 course_file_store=None):
        self.repository = repository
        self.learning = LearningRepository(repository.database)
        self.auth = student_auth
        self.budget_service = budget_service
        self.signer = URLSafeTimedSerializer(signing_key, salt='mira-fixed-textbook-runtime-v1',
                                             signer_kwargs={'digest_method': hashlib.sha256})
        self.public_url = public_url.rstrip('/')
        self.course_files = course_file_store or CourseFileStore(
            repository=CourseStorageRepository(repository.database))
        self._classroom_cache = OrderedDict()
        self._classroom_cache_lock = Lock()

    def _playback_release(self, release):
        """Supply only verified MinIO bytes; the DB release is a frozen comparator.

        Current published aliases retain the complete Native document, including
        id/createdAt. Never trim an arbitrary document into a matching shape.
        The bounded cache holds only remotely verified immutable versions.
        """
        try:
            cid = release['classroomId']
            expected = release['classroomSha256']
            if (not isinstance(cid, str) or re.fullmatch(r'tbpub_[a-f0-9]{24}', cid) is None
                    or not isinstance(expected, str) or KEY.fullmatch(expected) is None
                    or self.course_files.config.mode != 'registry'):
                raise ValueError('published classroom registry identity missing')
            source = self.course_files.project_root / _CLASSROOM_SOURCE / (cid + '.json')
            entry = self.course_files.resolve(source)
            if entry is None or entry['mimeType'] != 'application/json':
                raise ValueError('published classroom is not registered')
            key = (str(source), entry['sha256'], entry['byteSize'], canonical(entry['locator']), expected)
            with self._classroom_cache_lock:
                cached = self._classroom_cache.get(key)
                if cached is not None:
                    self._classroom_cache.move_to_end(key)
                    return {**release, 'classroom': deepcopy(cached['classroom'])}
            raw = self.course_files.read_bytes(source, expected_sha256=entry['sha256'],
                                               expected_bytes=entry['byteSize'])
            if not isinstance(raw, bytes) or len(raw) != entry['byteSize']:
                raise ValueError('published classroom bytes unavailable')

            def unique_pairs(pairs):
                value = {}
                for name, item in pairs:
                    if name in value:
                        raise ValueError('duplicate published classroom JSON member')
                    value[name] = item
                return value

            classroom = json.loads(raw, object_pairs_hook=unique_pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError('invalid JSON number')))
            if (not isinstance(classroom, dict) or set(classroom) != {'id', 'stage', 'scenes', 'createdAt'}
                    or classroom['id'] != cid or not isinstance(classroom['stage'], dict)
                    or classroom['stage'].get('id') != cid or not isinstance(classroom['scenes'], list)
                    or not classroom['scenes'] or type(classroom['createdAt']) not in {str, int}
                    or digest(classroom) != expected or classroom != release['classroom']):
                raise ValueError('published classroom differs from frozen release')
            # CourseFileStore proves the raw SHA. Keep this explicit assertion
            # at the student delivery boundary as well as its canonical seal.
            if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                raise ValueError('published classroom raw hash differs')
            if len(raw) <= _CLASSROOM_CACHE_BYTES:
                with self._classroom_cache_lock:
                    self._classroom_cache[key] = {'classroom': deepcopy(classroom), 'size': len(raw)}
                    self._classroom_cache.move_to_end(key)
                    while (len(self._classroom_cache) > _CLASSROOM_CACHE_ENTRIES
                           or sum(value['size'] for value in self._classroom_cache.values()) > _CLASSROOM_CACHE_BYTES):
                        self._classroom_cache.popitem(last=False)
            return {**release, 'classroom': classroom}
        except (CourseFileStorageError, ValueError, TypeError, KeyError, OSError):
            raise ApiError('textbook_content_unavailable', '课堂内容暂时不可用，请稍后重新进入', 503) from None

    def _release(self, conn, key, child, *, access_scope='selected_textbook'):
        if access_scope == 'published_directory':
            from services.textbook_runtime_release_cache import published_runtime_release
            build, release, course, _ = published_runtime_release(self.repository, conn, key, child)
            return build, release, course
        if access_scope != 'selected_textbook':
            fail()
        if not isinstance(key, str) or KEY.fullmatch(key) is None:
            fail()
        build = self.repository.get_build(conn, key)
        if build is None or build['status'] != 'published':
            fail()
        directory = self.repository.get_revision(conn, build['edition_id'], build['revision_id'])
        if directory is None:
            fail()
        manifest = self.repository.manifest(directory)
        if digest(manifest) != directory['manifest_sha256'] or manifest['gradeCode'] != child['grade_code']:
            fail()
        from services.textbook_learning_service import textbook_context
        context = textbook_context(self.repository, conn, child)
        choices = self.repository.selections(conn, child, context['schoolYearStartYear'], context['semester'])
        if not any(r['edition_id'] == build['edition_id'] and r['revision_id'] == build['revision_id'] for r in choices):
            raise ApiError('textbook_selection_changed', '学校教材已变化，请返回书包重新选课', 409)
        course = conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=?',
                              (build['course_id'], build['course_version'])).fetchone()
        if course is None:
            fail()
        release = validate_release(build, manifest, course)
        if release is None:
            fail()
        return build, release, course

    def launch(self, token, key, *, access_scope='published_directory'):
        context = self.auth.authenticate(token)
        principal = context['principal']
        with self.repository.transaction() as conn:
            child = self.repository.child(conn, principal['family_id'], principal['child_id'], lock=True)
            if child is None:
                fail()
            build, release, course = self._release(conn, key, child, access_scope=access_scope)
            task, _ = self.learning.assign_catalog_task(conn, family_id=child['family_id'], child_id=child['id'],
                course=course, created_by=principal['id'], now=now_ms())
            session, _ = self.learning.create_or_get_session(conn, family_id=child['family_id'], child_id=child['id'],
                task_id=task['id'], course_id=course['id'], course_version=course['version'], now=now_ms())
            self.learning.mark_task_in_progress(conn, family_id=child['family_id'], task_id=task['id'], now=now_ms())
            authority = {'purpose': 'ticket', 'key': key, 'release': release['sha256'],
                'studentSession': context['session']['id'], 'learningSession': session['id'],
                'gradeRevision': int(child['grade_selection_revision']), 'accessScope': access_scope}
            directory = self.repository.get_revision(conn, build['edition_id'], build['revision_id'])
            if release.get('assessmentMode') == 'ungraded':
                from content.textbook_batch_release import activity_unit
                unit = activity_unit(self.repository.manifest(directory), self.repository.parse(build['input_json']))
            else:
                unit, _ = lesson_by_id(self.repository.manifest(directory), build['node_id'])
        ticket = 'tbpt_' + self.signer.dumps(authority)
        return {'ok': True, 'launchUrl': self.public_url + '/mira/textbook-launch?' + urlencode({'ticket': ticket}),
            'title': course['title'], 'editionId': build['edition_id'], 'revisionId': build['revision_id'],
            'unitId': unit['unitId'] if unit else None, 'contentKey': key, 'learningSessionId': session['id']}

    def _authority(self, token, *, purpose='runtime'):
        prefix, age = ('tbpt_', 90) if purpose == 'ticket' else ('tbpr_', 14400)
        if not isinstance(token, str) or not token.startswith(prefix) or len(token) > 3000:
            raise ApiError('textbook_session_invalid', '请从教材目录重新进入课堂', 401)
        try:
            data = self.signer.loads(token[len(prefix):], max_age=age)
        except BadSignature:
            raise ApiError('textbook_session_invalid', '请从教材目录重新进入课堂', 401)
        if not isinstance(data, dict) or data.get('purpose') != purpose:
            raise ApiError('textbook_session_invalid', '课堂票据无效', 401)
        with self.repository.transaction() as conn:
            login = self.auth.repository.get_session(conn, session_id=data.get('studentSession'))
            if login is None or login.get('revoked_at') is not None or int(login['refresh_expires_at']) <= now_ms():
                raise ApiError('textbook_session_invalid', '学习登录已结束，请重新解锁', 401)
            principal, _ = self.auth._active_principal_and_device(conn, session=login, now=now_ms())
            child = self.repository.child(conn, principal['family_id'], principal['child_id'])
            if child is None or data.get('gradeRevision') != int(child['grade_selection_revision']):
                fail('年级已变化，请返回书包')
            build, release, course = self._release(conn, data.get('key'), child,
                access_scope=data.get('accessScope', 'selected_textbook'))
            session = self.learning.get_session(conn, family_id=child['family_id'], session_id=data.get('learningSession'))
            if (session is None or session['child_id'] != child['id'] or session['course_id'] != course['id']
                    or session['course_version'] != course['version'] or data.get('release') != release['sha256']):
                fail('课堂身份与课程不一致')
        return data, child, build, release, course, session

    def exchange(self, ticket):
        data, _, _, release, _, session = self._authority(ticket, purpose='ticket')
        authority = {**data, 'purpose': 'runtime', 'expiresAt': now_ms() + 14400_000}
        return {'ok': True, 'runtimeToken': 'tbpr_' + self.signer.dumps(authority),
            'classroomId': release['classroomId'], 'expiresAt': authority['expiresAt'], 'learningSessionId': session['id']}

    def validate(self, token):
        data, _, _, release, _, session = self._authority(token)
        if int(data.get('expiresAt', 0)) <= now_ms():
            raise ApiError('textbook_session_invalid', '请重新进入课堂', 401)
        return {'ok': True, 'purpose': 'fixed_textbook', 'classroomId': release['classroomId'],
            'runtimeSessionId': session['id'], 'learningSessionId': session['id'], 'expiresAt': data['expiresAt'],
            'media': release['media'], 'releaseSha256': release['sha256'],
            'activityPersistence': activity_state.descriptors(release)}

    def classroom(self, token):
        _, child, build, release, _, _ = self._authority(token)
        release = self._playback_release(release)
        content = public_classroom(release)
        textbook_activity.attach(content, release)
        # Bind the published subject, never the operator's default roster.
        # This is session presentation metadata; the signed release is unchanged.
        ids, agents = classroom_roster(self.repository.parse(build['input_json']), release)
        content['stage'].update(agentIds=ids, generatedAgentConfigs=agents)
        # Children do not yet have a custom avatar field. Use the existing
        # student portrait, with the authenticated child's display name.
        content['stage']['miraStudent'] = {
            'name': child.get('nickname') or child['name'], 'avatar': '/avatars/user.png',
        }
        return {'success': True, 'classroom': content}

    def admit_interaction(self, token, data):
        """Attach ordinary classroom teaching to the existing dispatch ledger.

        Fixed textbook means shared authored content, not a read-only player.
        The native discussion, voice, and whiteboard engines stay unchanged.
        """
        _, child, build, release, course, session = self._authority(token)
        if (not isinstance(data, dict) or set(data) != {'path', 'request'}
                or data['path'] not in INTERACTION_PATHS or not isinstance(data['request'], dict)):
            raise ApiError('textbook_interaction_invalid', '课堂互动请求无效', 400)
        frozen = self.repository.parse(build['input_json'])
        canonical_request = None
        if data['path'] in {'/api/chat', '/api/chat/pi'}:
            release = self._playback_release(release)
            canonical_request = discussion_request(frozen, release, data['request'])
        from services.learning_paid_authority import scope_digest
        scope = {'purpose': 'required_teaching', 'gradeCode': frozen['gradeCode'], 'subject': frozen['subject'],
            'courseId': course['id'], 'courseVersion': course['version'], 'userId': child['id'],
            'sessionId': session['id'], 'productionJobId': None, 'approvalReference': release['sha256']}
        binding = self.budget_service.issue_course_authorization(
            authorization_id=scope_digest(scope), scope=scope) if self.budget_service else None
        if binding is None:
            raise ApiError('learning_budget_unavailable', '课堂互动暂不可用，请稍后再试', 503)
        result = {'ok': True, 'paidBudget': binding, 'purpose': 'required_teaching'}
        if canonical_request is not None:
            if textbook_activity.supported(release):
                # Asking a teacher/peer is assistance even if the hint button
                # was not pressed. Keep the new question context answer-blind.
                with self.repository.transaction() as conn:
                    locked = self.learning.get_session(conn, family_id=child['family_id'], session_id=session['id'], for_update=True)
                    progress = self._state(locked)
                    state = textbook_activity.initial(progress, release)
                    scene = canonical_request['storeState']['currentSceneId']
                    section_name = next((name for name, scene_id in textbook_activity.definition(release=release).plan['sceneIds'].items() if scene_id == scene), None)
                    if section_name:
                        section = state[section_name]
                        current = textbook_activity.item(section, release, state)
                        if current and not section.get('feedback', {}).get('canNext'):
                            section['hintLevel'] = max(1, section.get('hintLevel', 0))
                            state['version'] += 1
                            progress['textbookPlay'] = state
                            conn.execute('UPDATE learning_sessions SET runtime_state_json=?,updated_at=? WHERE id=?',
                                (canonical(progress), now_ms(), session['id']))
                            target = next(s for s in canonical_request['storeState']['scenes'] if s['id'] == scene)
                            view = textbook_activity.public_view(state, release)[section_name]
                            target['type'] = 'quiz'
                            target['content'] = {'type': 'quiz', 'questions': [{
                                'id': current['id'], 'type': 'single',
                                'question': view['prompt'] + '\n' + textbook_activity.definition(release=release).flow['teachingGuidance'],
                                'options': current.get('options', []), 'points': 0}]}
                            target['actions'] = []
            result['request'] = canonical_request
        return result

    @staticmethod
    def _state(session):
        value = TextbookRepository.parse(session.get('runtime_state_json'))
        if value is None:
            return {'schemaVersion': 'mira.textbook.progress.v1', 'lastSequence': 0, 'visited': [], 'actions': [], 'quiz': None}
        if value.get('schemaVersion') != 'mira.textbook.progress.v1':
            fail('学习进度身份无效')
        return value

    @staticmethod
    def _status(session, release):
        state = TextbookClassroomService._state(session)
        scenes = textbook_activity.ordered_scenes(release)
        visited = set(state['visited'])
        resume = max((i for i, s in enumerate(scenes) if s['id'] in visited), default=-1)
        play = state.get('textbookPlay')
        if textbook_activity.supported(release) and play is None:
            play = textbook_activity.initial(state, release)
        if textbook_activity.supported(release) and play:
            # Returning children resume their unfinished activity, even when
            # they previously opened the final slide. Preserve historical grades.
            pending = next((section for section in ('games', 'challenge')
                            if play[section]['phase'] != 'done'), 'challenge')
            if pending:
                resume = next(i for i, s in enumerate(scenes)
                              if s['id'] == textbook_activity.definition(release=release).plan['sceneIds'][pending])
        complete = session['status'] == 'completed'
        # OpenMAIC records the final action after the page's narration finishes.
        completed_scenes = [s['id'] for s in scenes if not s.get('actions')
                            or s['actions'][-1]['id'] in state['actions']]
        # Native activity completion is separate evidence from lecture audio.
        # Its own cues can pause the lecture without making a finished game
        # depend on replaying the legacy HTML introduction to the final action.
        required_audio = [s['id'] for s in scenes if not textbook_activity.supported(release)
                          or s['id'] not in textbook_activity.definition(release=release).plan['sceneIds'].values()]
        # Ungraded content records viewing only. Visiting a page is never an
        # independent game result, a quiz grade, or evidence of subject mastery.
        ungraded_ready = (release.get('assessmentMode') == 'ungraded' and len(visited) == len(scenes)
                          and all(scene_id in completed_scenes for scene_id in required_audio))
        return {'ok': True, 'schemaVersion': RECEIPT_SCHEMA, 'runtimeSessionId': session['id'],
            'learningSessionId': session['id'], 'classroomId': release['classroomId'], 'releaseId': release['sha256'],
            'lastSequence': state['lastSequence'], 'nextSequence': state['lastSequence'] + 1, 'completed': complete,
            'completionReady': ungraded_ready if release.get('assessmentMode') == 'ungraded' else textbook_activity.complete(state) if (play or {}).get('flowVersion') == 2 else bool(state['quiz'] and len(visited) == len(scenes)
                                    and all(scene_id in completed_scenes for scene_id in required_audio)
                                    and (complete or not textbook_activity.supported(release)
                                         or textbook_activity.complete(state))),
            'answeredQuestionIds': [r['questionId'] for r in (state['quiz'] or state.get('quizPartial') or {}).get('results', [])],
            'completedInteractionObjectiveIndexes': [], 'completedActionSceneIds': completed_scenes,
            'resumeScene': {'sceneIndex': resume, 'sceneId': scenes[resume]['id']} if resume >= 0 else None}

    def events(self, token, event=None):
        _, child, _, release, course, initial_session = self._authority(token)
        with self.repository.transaction() as conn:
            session = self.learning.get_session(conn, family_id=child['family_id'], session_id=initial_session['id'], for_update=True)
            if event is None:
                return self._status(session, release)
            if (not isinstance(event, dict) or set(event) != {'schemaVersion', 'sequence', 'type', 'payload'}
                    or event['schemaVersion'] != 'mira.openmaic.student-runtime-event.v1'
                    or type(event['sequence']) is not int or event['sequence'] < 1):
                raise ApiError('textbook_event_invalid', '学习记录格式无效', 400)
            previous = conn.execute('SELECT * FROM learning_session_runtime_records WHERE session_id=? AND seq=?',
                                    (session['id'], event['sequence'])).fetchone()
            if previous:
                if self.repository.parse(previous['payload_json']) != event:
                    raise ApiError('textbook_event_conflict', '学习记录顺序冲突，请重新进入课堂', 409)
                return self.repository.parse(previous['response_json'])
            state = self._state(session)
            if event['sequence'] != state['lastSequence'] + 1:
                raise ApiError('textbook_event_conflict', '请刷新课堂后继续', 409)
            scenes = textbook_activity.ordered_scenes(release)
            payload = event['payload']
            index = payload.get('sceneIndex') if isinstance(payload, dict) else None
            if type(index) is not int or not 0 <= index < len(scenes) or payload.get('sceneId') != scenes[index]['id']:
                raise ApiError('textbook_event_invalid', '课件页面身份无效', 400)
            scene = scenes[index]
            if event['type'] == 'scene_entered' and set(payload) == {'sceneIndex', 'sceneId'}:
                if scene['id'] not in state['visited']:
                    state['visited'].append(scene['id'])
            elif event['type'] == 'action_completed' and set(payload) == {'sceneIndex', 'sceneId', 'actionId'}:
                if payload['actionId'] not in {a['id'] for a in scene.get('actions', [])}:
                    raise ApiError('textbook_event_invalid', '讲解片段不存在', 400)
                if payload['actionId'] not in state['actions']:
                    state['actions'].append(payload['actionId'])
            elif event['type'] == 'asr_transcribed':
                # The existing recorder persists the turn before forwarding it
                # to discussion. Keep its contract; speech is not quiz credit.
                from services.openmaic_runtime_event_service import OpenMaicRuntimeEventService
                OpenMaicRuntimeEventService._event({**event, 'idempotencyKey': digest(event)})
            elif event['type'] == 'classroom_completed' and set(payload) == {'sceneIndex', 'sceneId'}:
                if not self._status(session, release)['completionReady']:
                    raise ApiError('textbook_learning_incomplete', '请先完成学习和练习', 409)
                self._complete(conn, session, child, course, state['quiz'])
            else:
                raise ApiError('textbook_event_invalid', '本节固定课程不接受这个操作', 400)
            state['lastSequence'] = event['sequence']
            conn.execute('UPDATE learning_sessions SET runtime_state_json=?,updated_at=? WHERE id=?',
                          (canonical(state), now_ms(), session['id']))
            completed = event['type'] == 'classroom_completed' or session['status'] == 'completed'
            receipt = {'ok': True, 'sequence': event['sequence'], 'completed': completed,
                'receiptSha256': digest({'session': session['id'], 'event': event})}
            conn.execute('INSERT INTO learning_session_runtime_records (id,session_id,seq,idempotency_key,scene_id,action_id,record_type,payload_json,response_json,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                ('tbev_' + digest({'session': session['id'], 'seq': event['sequence']})[:40], session['id'], event['sequence'],
                 'textbook:' + str(event['sequence']), scene['id'], payload.get('actionId'), event['type'], canonical(event), canonical(receipt), now_ms()))
            return receipt

    def activity_state(self, token, data=None):
        """Persist only the bound iframe's UI continuity, independently of grades."""
        _, child, _, release, course, initial_session = self._authority(token)
        if data is not None:
            data = activity_state.parse_post(data)
        definitions = activity_state.descriptors(release)
        identity = {'ok': True, 'schemaVersion': activity_state.SCHEMA,
            'classroomId': release['classroomId'], 'learningSessionId': initial_session['id'],
            'releaseSha256': release['sha256']}
        with self.repository.transaction() as conn:
            session = self.learning.get_session(conn, family_id=child['family_id'],
                session_id=initial_session['id'], for_update=True)
            if (session is None or session['id'] != initial_session['id'] or session['child_id'] != child['id']
                    or session['course_id'] != course['id'] or session['course_version'] != course['version']
                    or (data is not None and data['learningSessionId'] != session['id'])):
                raise ApiError('textbook_activity_state_identity', '课堂进度身份已变化，请重新进入', 409)
            progress = self._state(session)
            saved_scope = activity_state.scope(progress, session_id=session['id'], release=release)
            if data is None:
                return activity_state.response_within_budget({**identity, 'activities': [activity_state.activity(item,
                    saved_scope['scenes'].get(item['sceneId'])) for item in definitions]})
            definition = next((item for item in definitions if item['sceneId'] == data['sceneId']), None)
            if (definition is None or data['sceneIndex'] != definition['sceneIndex']
                    or data['releaseSha256'] != release['sha256']
                    or data['contentSha256'] != definition['contentSha256']):
                raise ApiError('textbook_activity_state_identity', '小游戏版本已变化，请重新进入', 409)
            stored = saved_scope['scenes'].get(definition['sceneId'])
            current = activity_state.activity(definition, stored)
            request_sha = activity_state.request_sha(data)
            mutations = dict((stored or {}).get('mutations', {}))
            if data['mutationId'] in mutations:
                if mutations[data['mutationId']] != request_sha:
                    raise ApiError('textbook_activity_mutation_conflict', '小游戏保存标识已用于另一份进度', 409)
                return {**identity, 'activity': current}
            if data['expectedRevision'] != current['revision']:
                raise ApiError('textbook_activity_revision_conflict', '小游戏已在其他页面更新，请重新进入', 409)
            mutations[data['mutationId']] = request_sha
            mutations = dict(list(mutations.items())[-activity_state.MAX_MUTATIONS:])
            updated = {key: deepcopy(data[key]) for key in ('sceneIndex', 'contentSha256', 'mutationId', 'state')}
            updated.update(revision=current['revision'] + 1, mutations=mutations)
            saved_scope = activity_state.scope(progress, session_id=session['id'], release=release, create=True)
            saved_scope['scenes'][definition['sceneId']] = updated
            activity_state.validate_storage_budget(progress)
            conn.execute('UPDATE learning_sessions SET runtime_state_json=?,updated_at=? WHERE id=?',
                (canonical(progress), now_ms(), session['id']))
            return {**identity, 'activity': activity_state.activity(definition, updated)}

    def quiz(self, token, answers=None):
        _, child, _, release, course, initial_session = self._authority(token)
        with self.repository.transaction() as conn:
            session = self.learning.get_session(conn, family_id=child['family_id'], session_id=initial_session['id'], for_update=True)
            state = self._state(session)
            # A lesson may spread its questions over several in-class checks.
            # Each check is graded when it is handed in; the lesson result and
            # the parent report exist only once every question is answered.
            saved = {r['questionId']: r for r in (state['quiz'] or state.get('quizPartial') or {}).get('results', [])}
            if answers is None:
                return {'ok': True, 'result': state['quiz'], 'partial': state.get('quizPartial')}
            if release.get('assessmentMode') == 'ungraded':
                raise ApiError('textbook_activity_ungraded', '这份探索不提供评分或掌握度测评', 409)
            if textbook_activity.supported(release):
                raise ApiError('textbook_play_required', '请刷新课堂，逐题完成互动练习', 409)
            graded = grade_answers(release, answers, partial=True)
            if any(q in saved and saved[q]['response'] != answer for q, answer in answers.items()):
                raise ApiError('textbook_answers_already_submitted', '这次练习已经提交，请查看已保存的结果', 409)
            if state['quiz']:
                return {'ok': True, 'result': state['quiz'], 'partial': None}
            merged = {**saved, **{r['questionId']: r for r in graded['results']}}
            if len(merged) < len(questions(release['classroom'])):
                state['quizPartial'] = {'results': list(merged.values())}
                conn.execute('UPDATE learning_sessions SET runtime_state_json=?,updated_at=? WHERE id=?',
                              (canonical(state), now_ms(), session['id']))
                return {'ok': True, 'result': None, 'partial': state['quizPartial']}
            result = grade_answers(release, {q: r['response'] for q, r in merged.items()})
            state['quiz'] = result
            state.pop('quizPartial', None)
            conn.execute('UPDATE learning_sessions SET runtime_state_json=?,answers_json=?,attempted_count=?,correct_count=?,current_question_index=?,updated_at=? WHERE id=?',
                (canonical(state), canonical([{'questionId': r['questionId'], 'answer': r['response'], 'correct': r['correct'],
                    'attemptNumber': 1, 'hintUsed': False} for r in result['results']]), result['totalQuestions'],
                 result['correctCount'], result['totalQuestions'], now_ms(), session['id']))
            # The report describes the exercise; it does not claim oral-reading mastery.
            self._report(conn, session, child, course, result)
            return {'ok': True, 'result': result, 'partial': None}

    def play(self, token, data=None):
        _, child, _, release, course, initial_session = self._authority(token)
        release = self._playback_release(release)
        if not textbook_activity.supported(release):
            raise ApiError('textbook_play_unavailable', '这节课没有配置该互动', 404)
        with self.repository.transaction() as conn:
            session = self.learning.get_session(conn, family_id=child['family_id'],
                session_id=initial_session['id'], for_update=True)
            progress = self._state(session)
            state = textbook_activity.initial(progress, release)
            previous = deepcopy(state)
            if data is not None:
                textbook_activity.advance(state, data.get('section') if isinstance(data, dict) else None, data, release)
                progress['textbookPlay'] = state
                result = textbook_activity.quiz_result(state, release)
                if result and progress['quiz'] is None:
                    progress['quiz'] = result
                    conn.execute('UPDATE learning_sessions SET answers_json=?,attempted_count=?,correct_count=?,current_question_index=?,updated_at=? WHERE id=?',
                        (canonical([{'questionId': r['questionId'], 'answer': r['response'], 'correct': r['correct'],
                            'attemptNumber': 1, 'hintUsed': r['hintUsed'], 'adultHelp': r['adultHelp']} for r in result['results']]),
                         result['totalQuestions'], result['correctCount'], result['totalQuestions'], now_ms(), session['id']))
                    self._report(conn, session, child, course, result)
                from services.learning_evidence_service import record_textbook_changes
                record_textbook_changes(conn, session, course, state, previous, release)
                sync_journey(conn, self.learning, session, child, course, state, previous)
                if textbook_activity.complete(progress) and result:
                    self._complete(conn, session, child, course, result)
                conn.execute('UPDATE learning_sessions SET runtime_state_json=?,updated_at=? WHERE id=?',
                    (canonical(progress), now_ms(), session['id']))
            return textbook_activity.public_view(state, release)

    def activity_audio(self, token, asset):
        _, _, _, release, _, _ = self._authority(token)
        if not textbook_activity.supported(release):
            fail()
        return textbook_activity.audio_file(asset, release=release)

    def _report(self, conn, session, child, course, result):
        wrong = [r for r in result['results'] if not r['correct']]
        total, correct = result['totalQuestions'], result['correctCount']
        independent = result.get('independentCorrectCount', correct)
        hints, adult = result.get('hintCount', 0), result.get('adultHelpCount', 0)
        summary = f'《{course["title"]}》图文选择练习完成 {total} 题，首次独立答对 {independent} 题；使用提示 {hints} 题，请大人帮助 {adult} 题。'
        next_step = ('可在课堂继续完成针对性再练和换种玩法，孩子可按语音提示继续。'
                     '本次未评价口头朗读或书写能力。') if 'independentCorrectCount' in result else (
                     ('再听一听：' + '；'.join(r['explanation'] for r in wrong)) if wrong
                     else '可以与家人指图说一说；本次未评价口头朗读或书写能力。')
        self.learning.create_or_get_report(conn, family_id=child['family_id'], child_id=child['id'], task_id=session['task_id'],
            session_id=session['id'], course_id=course['id'], course_version=course['version'],
            learning_date=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(), grade_code=course['grade_code'], subject=course['subject'],
            score=round(100 * result['score'] / result['maxScore']), correct_count=correct, independent_correct_count=independent,
            hint_count=hints, total_questions=total, mastery_level='developing', summary=summary,
            strengths=[r['explanation'] for r in result['results'] if r['correct']],
            next_step=next_step, now=now_ms())

    def _complete(self, conn, session, child, course, result):
        if session['status'] == 'completed':
            return
        conn.execute("UPDATE learning_sessions SET status='completed',completed_at=?,classroom_completed_at=?,updated_at=? WHERE id=?",
                     (now_ms(), now_ms(), now_ms(), session['id']))
        self.learning.mark_task_completed(conn, family_id=child['family_id'], task_id=session['task_id'],
            summary=(f'教材课练习答对 {result["correctCount"]}/{result["totalQuestions"]} 题。' if result is not None
                     else '已浏览本次教学活动；未进行独立能力测评。'), now=now_ms())
