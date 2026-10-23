"""Legacy adoption uses literal v2 evidence; no native receipt or provider calls."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from content.textbook_catalog import canonical, digest, lesson_by_id
from content.textbook_interaction_policy import freeze_interaction_policy
from content.textbook_legacy_complete_scene_revision import (
    PATCH_SCHEMA, body_without_audio, legacy_complete_scene_candidate, validate_legacy_evidence)
from content.textbook_operator_revision import sha_text, validate_parent
from core.errors import ApiError
from services.textbook_legacy_complete_scene_revision import read_legacy_complete_scene_evidence
from tests.test_textbook_operator_revision import parent_fixture


def fixture(folder):
    parent = parent_fixture(v2=True)
    origin = validate_parent(parent)
    room = json.loads(parent['preview']['classroom_json'])
    body = body_without_audio(room)
    body['id'] = body['stage']['id'] = 'reviewed-legacy-body'
    for scene in body['scenes']:
        scene['stageId'] = body['id']
    q = body['scenes'][-1]['content']['questions'][0]
    q.update(points=10, speechActionId='line-quiz')
    old_url = origin['originalMedia']['assets'][0]['mediaPath']
    url = '/review-assets/legacy/picture.png'
    body = json.loads(canonical(body).replace(old_url, url))
    body['scenes'][0]['actions'][0]['text'] = '眼睛帮助我们观察。'
    body['scenes'][0]['actions'].append({'id': 'extra', 'type': 'speech', 'text': '再仔细看一看。'})
    manifest, node = parent['manifest'], parent['build']['node_id']
    unit, lesson = lesson_by_id(manifest, node)
    binding = {k: manifest[k] for k in ('editionId', 'revisionId', 'gradeCode', 'subject', 'volume', 'schoolSystem')}
    binding.update(nodeId=node, unitId=unit['unitId'], unitTitle=unit['title'], lessonTitle=lesson['title'])
    teacher = origin['teacher']
    teacher_contract = {'teacherProfileId': teacher['teacherProfile']['id'],
        'teacherProfileVersion': teacher['teacherProfile']['version'], 'teacherProfileHash': teacher['teacherProfile']['contentHash'],
        'voiceId': teacher['voiceId'], 'languageCode': teacher['languageCode']}
    locked = [{**{k: q[k] for k in ('id', 'type', 'question', 'analysis')}, 'points': 10,
        'answer': q['answer'][0], 'page': 3, 'choices': [{**o, 'asset': 'picture'} for o in q['options']]}]
    source_review = {'binding': binding, 'scopeStatus': 'synthetic'}
    draft = {'binding': binding, 'request': 'synthetic original request', 'sourceReview': source_review,
             'teacherContract': teacher_contract, 'lockedAssessments': locked}
    raw_draft = canonical(draft) + '\n'
    frozen = {'schemaVersion': 'mira.operator.workbench-authoring.v2', 'binding': binding,
        'teacherContract': teacher_contract, 'draftSha256': sha_text(raw_draft),
        'draftCanonicalSha256': digest(draft), 'requestSha256': sha_text(draft['request'])}
    release = json.loads(parent['build']['review_json'])['release']
    def write(name, value, canonical_sha=False):
        path = folder / (name + '.json')
        raw = canonical(value) + '\n'; path.write_text(raw)
        return {'path': str(path), 'fileSha256': sha_text(raw), **({'canonicalSha256': digest(value)} if canonical_sha else {})}
    b = {'schemaVersion': 'mira.textbook.legacy-revision-source-bundle.v1',
        'candidate': write('candidate', body, True), 'replacementBody': write('body', body, True),
        'parent': {'classroom': write('parent-room', release['classroom'], True),
            'preparedRelease': write('prepared', {'release': release}),
            'publicationReceipt': write('publication', {'ok': True, 'status': 'published',
                'classroomId': release['classroomId'], 'contentKey': release['contentKey'], 'releaseSha256': release['sha256']}),
            'classroomId': release['classroomId'], 'contentKey': release['contentKey'], 'releaseSha256': release['sha256']},
        'legacyAuthority': {'frozen': write('frozen', frozen), 'draft': write('draft', draft),
            'sourceReview': write('source-review', source_review), 'lockedAssessments': write('locked', locked),
            'sceneContractPresent': False, 'authoringCandidateLedgerPresent': False,
            'mustNotFabricateLegacyContractOrLedger': True},
        'newPolicy': {'version': 2, 'canonicalSha256': freeze_interaction_policy()['sha256'],
            'source': write('policy', freeze_interaction_policy()['policy'])},
        'audioDelta': write('delta', {'synthetic': True})}
    out = io.BytesIO(); Image.new('RGB', (8, 8), 'green').save(out, format='PNG')
    raw = out.getvalue(); image = folder / 'picture.png'; image.write_bytes(raw)
    asset = {'assetKey': 'picture', 'sourceFilePath': str(image), 'sourceFileSha256': hashlib.sha256(raw).hexdigest(), 'reviewUrl': url}
    receipt = write('asset-receipt', {**asset, 'schemaVersion': 'mira.textbook.review-asset-source-receipt.v1',
                    'kind': 'synthetic', 'role': 'test picture', 'source': 'synthetic fixture'})
    asset.update(sourceReceiptPath=receipt['path'], sourceReceiptFileSha256=receipt['fileSha256'])
    b['assetAdditions'] = [asset]
    bundle_path = folder / 'bundle.json'; bundle_path.write_text(canonical(b) + '\n')
    patch = {'schemaVersion': PATCH_SCHEMA, 'parentContentKey': origin['contentKey'],
        'expectedSourceSha256': origin['classroomSha256'], 'teachingRevision': '4',
        'reviewer': 'synthetic', 'basis': 'legacy body repair', 'sourceBundlePath': str(bundle_path),
        'expectedSourceBundleSha256': sha_text(bundle_path.read_text())}
    return parent, patch, bundle_path


class LegacyCompleteSceneRevisionTests(unittest.TestCase):
    def test_read_only_source_and_exact_shared_audio_inheritance(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp); parent, patch, path = fixture(folder)
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            root = folder / 'runtime-that-must-not-be-created'
            evidence, files = read_legacy_complete_scene_evidence(parent, root, path)
            patch['evidenceSha256'] = digest(evidence)
            candidate = legacy_complete_scene_candidate(parent, patch, evidence)
            self.assertEqual(candidate['modifiedSegments'], [['slide', 'line-slide']])
            self.assertEqual(candidate['addedSegments'], [['slide', 'extra']])
            self.assertEqual(len(candidate['inheritedSegments']), 2)
            self.assertFalse(root.exists())
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
            self.assertEqual(len(files), 1)
            self.assertNotIn('completeSceneReviewFollowup', evidence['summary'])
            self.assertEqual(evidence['summary']['interactionPolicyVersion'], 2)
            self.assertNotIn('/review-assets/', canonical(candidate['classroom']))

    def test_modified_bytes_cannot_be_replaced_by_matching_outer_evidence_hash(self):
        mutations = [lambda e: e['documents'].__setitem__('frozen', '{}'),
            lambda e: e['media']['assets'][0].update(sha256='0' * 64),
            lambda e: e['summary'].update(qualityReviewRequired=False),
            lambda e: e.update(ledgerJson='{}'),
            lambda e: e['authoring'].update(sessionId='fabricated-native-session')]
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                parent, patch, path = fixture(Path(tmp))
                evidence, _ = read_legacy_complete_scene_evidence(parent, Path(tmp), path)
                mutation(evidence); patch['evidenceSha256'] = digest(evidence)
                with self.assertRaises(ApiError):
                    legacy_complete_scene_candidate(parent, patch, evidence)

    def test_resealed_candidate_still_cannot_change_locked_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent, _, path = fixture(Path(tmp))
            bundle = json.loads(path.read_text())
            for name in ('candidate', 'replacementBody'):
                p = Path(bundle[name]['path']); body = json.loads(p.read_text())
                body['scenes'][-1]['content']['questions'][0]['answer'] = ['A']
                p.write_text(canonical(body) + '\n')
                bundle[name].update(fileSha256=sha_text(p.read_text()), canonicalSha256=digest(body))
            path.write_text(canonical(bundle) + '\n')
            with self.assertRaises(ApiError):
                read_legacy_complete_scene_evidence(parent, Path(tmp), path)

    def test_missing_or_changed_asset_bytes_stop_before_runtime_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent, _, path = fixture(Path(tmp))
            image = Path(tmp) / 'picture.png'; image.write_bytes(b'changed')
            with self.assertRaises(ApiError):
                read_legacy_complete_scene_evidence(parent, Path(tmp) / 'runtime', path)


if __name__ == '__main__':
    unittest.main()
