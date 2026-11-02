from copy import deepcopy
import unittest

from content.textbook_catalog import digest
from content.textbook_user_audio_reconciliation import build_confirmation, validate_reconciliation
from core.errors import ApiError
from core.security import now_ms
from services.textbook_publication_service import TextbookPublicationService
from tests import test_textbook_preview_audio_v2 as fixtures


class UserAudioConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.helper = fixtures.PreviewAudioV2Tests()
        self.addCleanup(self.helper.doCleanups)
        self.f = self.helper.fixture(first_text='姨。')
        self.f.transcript_override = '咦。'
        self.audit = self.helper.audit(self.f, ('--collect-only',))
        failed = [e for e in self.audit['segments'] if not e['comparison']['passed']]
        self.presented = [{k: e[k] for k in ('sceneId', 'actionId', 'textSha256', 'audioSha256')}
                          for e in failed]
        self.record = build_confirmation(plan=self.f.plan, classroom=self.f.classroom,
            audit=self.audit, expected_source_sha256=self.f.source_sha,
            statement='正确，赶紧发布', conversation_id='isolated-test-conversation',
            recorded_at=now_ms(), presented_segments=self.presented)

    def validate(self, record=None, audit=None, classroom=None):
        return validate_reconciliation(record or self.record, plan=self.f.plan,
            classroom=classroom or self.f.classroom, audit=audit or self.audit,
            expected_source_sha256=self.f.source_sha, now_ms=now_ms())

    def test_exact_record_preserves_failed_asr_and_only_confirms_presented_segment(self):
        before = deepcopy(self.audit)
        self.assertEqual(len(self.validate()), 1)
        self.assertEqual(self.audit, before)
        self.assertFalse(self.audit['passed'])
        self.assertEqual(self.record['segments'][0]['similarityBps'], 0)

    def test_resealed_tampering_cannot_accept_other_audio_or_unheard_segments(self):
        for field, value in [('audioSha256', 'a' * 64), ('textSha256', 'b' * 64),
                             ('actionId', 'different'), ('similarityBps', 10000)]:
            with self.subTest(field=field):
                record = deepcopy(self.record)
                record['segments'][0][field] = value
                record['sha256'] = digest({k: v for k, v in record.items() if k != 'sha256'})
                with self.assertRaises(ApiError): self.validate(record)
        record = deepcopy(self.record)
        record['presentedSegments'] = []
        with self.assertRaises(ApiError): self.validate(record)

    def test_failed_provider_missing_coverage_and_changed_source_are_rejected(self):
        for mode in ('provider', 'coverage', 'source'):
            audit = deepcopy(self.audit)
            if mode == 'provider': audit['segments'][0]['asr']['status'] = 'failed'
            if mode == 'coverage': audit['segments'].pop()
            if mode == 'source': audit['sourceSha256'] = 'c' * 64
            audit['sha256'] = digest({k: v for k, v in audit.items() if k != 'sha256'})
            with self.subTest(mode=mode), self.assertRaises(ApiError): self.validate(audit=audit)

    def test_publication_and_portable_release_keep_original_failed_audit(self):
        f = self.f
        row = f.service.get(f.key)
        review = {'alignmentConfirmed': True, 'originalExpressionConfirmed': True,
            'sourceUsageConfirmed': True, 'publicationAuthorized': True, 'reviewer': 'test',
            'basis': 'isolated review', 'sourceSha256': f.source_sha, 'reviewedAt': now_ms()}
        release = TextbookPublicationService(f.service).prepare(key=f.key,
            edition=row['edition_id'], revision=row['revision_id'], node=row['node_id'],
            teaching_revision='user-review-test', review=review, audio_audit=self.audit,
            asr_reconciliation=self.record, classroom_directory=f.root)
        release = release['release']
        self.assertEqual(release['audioAudit']['literalAudit'], self.audit)
        self.assertEqual(release['audioAudit']['acceptanceMethod'], 'user-confirmed-presented-audio')
        self.assertFalse(release['audioAudit']['literalPassed'])
        self.assertFalse(release['audioAudit']['literalAudit']['passed'])


if __name__ == '__main__': unittest.main()
