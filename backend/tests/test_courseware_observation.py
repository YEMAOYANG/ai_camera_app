"""Completed simulations remain scoped to a single child's exact course release."""

from contextlib import nullcontext
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from content.courseware_observation import (
    SNAPSHOT_SCHEMA, project_snapshot, report_cards, validate_card,
)
from content.courseware_release import build_release, validate_light_release
from core.errors import ApiError
from services.learning_service import LearningService
from tests.test_courseware_release import refresh_receipts, sample_inputs


RELEASE = 'a' * 64
HTML = 'b' * 64
PHOTO = 'c' * 64
OTHER_PHOTO = 'd' * 64
ROOM = 'tbpub_example'
SCENE = 'scene-lab'
SESSION = 'session-a'


def fixture():
    def view(label, sha):
        return {'label': label, 'image': f'/api/classroom-media/{ROOM}/media/{sha}.png'}
    card = validate_card({'title': '看杯子', 'familyTask': '和家人一起看一看杯底。',
        'levels': [{'label': '试一试', 'trials': [{'id': 'before', 'label': '平放',
            'top': {'round': view('圆的杯口', PHOTO), 'other': view('其他结果', OTHER_PHOTO)},
            'side': {'upright': view('杯子是立着的', PHOTO)}}]}]})
    state = {'schemaVersion': SNAPSHOT_SCHEMA, 'kind': 'simulation', 'sceneId': SCENE,
             'levels': [{'level': 1, 'trials': [{'trialId': 'before', 'top': 'round', 'side': 'upright'}]}]}
    course = {'releaseSha256': RELEASE, 'observationClassroomId': ROOM,
              'observationCards': {SCENE: {'card': card, 'contentSha256': HTML}}}
    progress = {'activitySnapshots': {'releases': {RELEASE: {'learningSessionId': SESSION,
        'classroomId': ROOM, 'scenes': {SCENE: {'contentSha256': HTML, 'state': state}}}}}}
    return card, state, course, progress


class CoursewareObservationTests(unittest.TestCase):
    def test_release_freezes_exact_scene_html_and_registered_image_paths(self):
        card, _, _, _ = fixture()
        inputs = sample_inputs()
        inputs['manifest']['subject'] = 'science'
        image = next(name for name in inputs['media'] if name.endswith('.png'))
        for trial in card['levels'][0]['trials']:
            for view in ('top', 'side'):
                for outcome in trial[view].values():
                    outcome['image'] = '/api/classroom-media/authored/media/' + image
        manifest = '<script type="application/json" id="mira-observation-card">' + json.dumps(card) + '</script>'
        inputs['body']['scenes'].append({'id': SCENE, 'stageId': 'authored', 'type': 'interactive',
            'content': {'type': 'interactive', 'html': '<body>' + manifest + '</body>'}, 'actions': []})
        inputs['playReceipt']['pages'] = [{'scene': 3, 'ok': True, 'finished': True, 'errors': [], 'stuck': None}]
        refresh_receipts(inputs)
        prepared = build_release(inputs)
        self.assertEqual(validate_light_release(prepared, inputs['manifest']), [])
        content = prepared['content_json']
        definition = content['observationCards'][SCENE]
        released_scene = prepared['classroom']['scenes'][-1]
        self.assertEqual(definition['contentSha256'],
                         hashlib.sha256(released_scene['content']['html'].encode()).hexdigest())
        self.assertEqual(definition['card']['levels'][0]['trials'][0]['top']['round']['image'],
                         '/api/classroom-media/' + content['observationClassroomId'] + '/media/' + image)

    def test_uses_declared_images_and_accepts_only_a_complete_simulation(self):
        card, state, _, _ = fixture()
        result = project_snapshot(card, SCENE, state)
        self.assertEqual(result['levels'][0]['trials'][0]['top']['label'], '圆的杯口')
        self.assertNotIn('score', result)
        for altered in ({**state, 'levels': []}, {**state, 'kind': 'real'},
                        {**state, 'sceneId': 'foreign'}, {**state, 'score': 100}):
            with self.assertRaises(ValueError):
                project_snapshot(card, SCENE, altered)
        state['levels'][0]['trials'][0]['top'] = 'undeclared'
        with self.assertRaises(ValueError):
            project_snapshot(card, SCENE, state)

    def test_report_has_no_cross_release_or_cross_session_observations(self):
        _, _, course, progress = fixture()
        self.assertEqual(len(report_cards(course, progress, SESSION)), 1)
        self.assertEqual(report_cards(course, progress, 'another-child-session'), [])
        self.assertEqual(report_cards({**course, 'releaseSha256': 'e' * 64}, progress, SESSION), [])
        stale = deepcopy(progress)
        stale['activitySnapshots']['releases'][RELEASE]['scenes'][SCENE]['contentSha256'] = 'e' * 64
        self.assertEqual(report_cards(course, stale, SESSION), [])
        self.assertEqual(report_cards({}, progress, SESSION), [])

    def test_parent_can_read_the_recorded_image_only_for_an_owned_report(self):
        _, _, course, progress = fixture()
        report = {'subject': 'science', 'session_id': SESSION,
                  'observation_course_json': course, 'observation_runtime_json': progress}
        service = object.__new__(LearningService)
        service.auth_service = SimpleNamespace(authenticate=lambda token: {'family': {'id': token}})
        service.repository = SimpleNamespace(transaction=lambda: nullcontext(None),
            parse_json=lambda value, fallback: value or fallback,
            get_report_detail=lambda conn, **key: report if key == {
                'family_id': 'family-a', 'child_id': 'child-a', 'report_id': 'report-a'} else None)
        service._child_or_error = Mock()
        query = {'childId': 'child-a'}
        with patch('services.learning_service.report_payload', return_value={'score': 50}):
            value = service.report_detail('family-a', 'report-a', query)['report']
        self.assertEqual(value['score'], 50)
        self.assertEqual(value['observationCards'][0]['levels'][0]['trials'][0]['top'],
                         {'label': '圆的杯口', 'imageSha256': PHOTO})
        with patch('services.course_file_store.CourseFileStore') as store:
            store.return_value.project_root = Path('/repo')
            store.return_value.read_bytes.return_value = b'png'
            self.assertEqual(service.report_observation_image('family-a', 'report-a', query, PHOTO), b'png')
            self.assertEqual(store.return_value.read_bytes.call_args.kwargs['expected_sha256'], PHOTO)
            with self.assertRaises(ApiError):
                service.report_observation_image('family-a', 'report-a', query, OTHER_PHOTO)
            with self.assertRaises(ApiError):
                service.report_observation_image('family-b', 'report-a', query, PHOTO)
            self.assertEqual(store.return_value.read_bytes.call_count, 1)
