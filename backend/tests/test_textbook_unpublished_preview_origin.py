"""Unpublished audio provenance must not borrow publication authority."""
from copy import deepcopy
import json
import unittest

from content.textbook_catalog import canonical, digest
from content.textbook_operator_revision import sha_text
from content.textbook_preview_audio_contract import compare_transcript
from content.textbook_unpublished_preview_origin import validate_preview_parent
from core.errors import ApiError
from tests.test_textbook_operator_revision import parent_fixture


def fixture():
    parent = parent_fixture(v2=True, retry=True, authoring={
        'mode': 'openmaic_pro_workbench', 'request': 'Synthetic original draft.',
        'sessionId': 'unpublished-origin-test', 'stageId': 'original-operator'})
    parent.pop('build')
    return parent


class UnpublishedPreviewOriginTests(unittest.TestCase):
    def test_preserves_real_unpublished_identity_and_recorded_retry(self):
        parent = fixture(); before = deepcopy(parent)
        origin = validate_preview_parent(parent)
        self.assertEqual(parent, before)
        self.assertEqual(origin['sourceKind'], 'audited-unpublished-preview')
        self.assertNotIn('releaseSha256', origin)
        self.assertNotIn('contentKey', origin)
        self.assertEqual(origin['sourceIdentitySha256'], digest(parent))
        self.assertEqual(len(origin['segments']), 3)
        self.assertEqual(origin['segments'][1]['attempt'], 2)

    def test_failed_raw_asr_is_retained_but_never_inherited(self):
        parent = fixture(); audit = parent['audit']; entry = audit['segments'][0]
        entry['transcript'] = '完全不同的声音。'
        entry['asr'].update(transcript=entry['transcript'], transcriptSha256=sha_text(entry['transcript']))
        entry['comparison'] = compare_transcript(parent['plan'], entry['text'], entry['transcript'])
        entry['similarityBps'] = entry['comparison']['similarityBps']
        audit['passed'] = False; audit['sha256'] = digest({k: v for k, v in audit.items() if k != 'sha256'})
        origin = validate_preview_parent(parent)
        self.assertFalse(origin['sourceAuditPassed'])
        self.assertEqual(len(origin['segments']), 2)
        self.assertEqual(origin['rejectedSegments'][0]['actionId'], entry['actionId'])
        audit['passed'] = True; audit['sha256'] = digest({k: v for k, v in audit.items() if k != 'sha256'})
        with self.assertRaises(ApiError): validate_preview_parent(parent)

    def test_rejects_cross_lesson_teacher_receipt_and_audit_substitution(self):
        def wrong_teacher(p):
            source = json.loads(p['preview']['classroom_json'])
            source['scenes'][0]['actions'][0]['audioMetadata']['voiceId'] = 'Other'
            p['preview'].update(classroom_json=canonical(source), classroom_sha256=digest(source))
            p['audit']['sourceSha256'] = digest(source)
            p['audit']['sha256'] = digest({k: v for k, v in p['audit'].items() if k != 'sha256'})
        mutations = [lambda p: p['preview'].update(node_id='u1-l4'), wrong_teacher,
            lambda p: p['receipts'][0].update(status='unknown'),
            lambda p: p['audit']['segments'].pop(),
            lambda p: p.update(build={'status': 'published'}),
            lambda p: p['audit']['segments'][0].update(transcript='changed'),
            lambda p: p['preview'].update(status='generating')]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                parent = fixture(); mutation(parent)
                with self.assertRaises(ApiError): validate_preview_parent(parent)

    def test_rejects_foreign_asset_and_forged_frozen_input(self):
        for change in ('asset', 'scope'):
            parent = fixture(); frozen = json.loads(parent['preview']['input_json'])
            if change == 'asset': frozen['originalMedia']['assets'][0]['mediaPath'] = '/api/classroom-media/other/media/a.png'
            else: frozen['nodeId'] = 'u1-l4'
            parent['preview']['input_json'] = canonical(frozen)
            with self.assertRaises(ApiError): validate_preview_parent(parent)


if __name__ == '__main__':
    unittest.main()
