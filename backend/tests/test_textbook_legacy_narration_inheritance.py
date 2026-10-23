"""Published legacy narration amendments survive only as exact visual ancestry."""
from copy import deepcopy
import json
import shutil
import unittest

from content.textbook_catalog import canonical, digest
from content.textbook_operator_revision import VISUAL_PATCH_SCHEMA, validate_parent
from content.textbook_release import validate_release
from core.errors import ApiError
from core.security import now_ms
from services.learning_media_materialization_service import asr_similarity_bps
from services.textbook_operator_revision_service import prepare_revision, register_revision, load_prepared
from services.textbook_preview_audio import narrate_preview
from services.textbook_preview_narration_revision import SCHEMA, revise_preview_narration
from services.textbook_preview_visual_revision import sha_bytes
from services.textbook_publication_service import TextbookPublicationService
from tests import test_textbook_operator_revision_service as service_fixtures


class LegacyNarrationInheritanceTests(unittest.TestCase):
    def setUp(self):
        f = service_fixtures.OperatorRevisionServiceTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.f = f
        # Synthetic source begins before its publication. No real DB is used.
        f.db.execute("UPDATE learning_textbook_course_builds SET status='retired' WHERE content_key=?", (f.parent_key,))
        f.db.raw.commit()
        f.configure_paid_mocks()
        row = f.service.get(f.source_key)
        source = json.loads(row['classroom_json'])
        audit = json.loads(f.source_audit.read_text())
        entry = audit['segments'][0]
        entry['transcript'] = '完全不同。'
        entry['similarityBps'] = asr_similarity_bps(entry['text'], entry['transcript'])
        entry['asr'].update(transcript=entry['transcript'], transcriptSha256=sha_bytes(entry['transcript'].encode()))
        audit['passed'] = False
        audit['sha256'] = digest({k: v for k, v in audit.items() if k != 'sha256'})
        failed = f.base / 'failed.json'; failed.write_text(canonical(audit))
        action = source['scenes'][0]['actions'][0]
        patch = {'schemaVersion': SCHEMA, 'expectedSourceSha256': row['classroom_sha256'],
            'reviewer': 'test', 'basis': 'Repair only the measured failed sentence',
            'changes': [{'sceneId': source['scenes'][0]['id'], 'actionId': action['id'],
                         'beforeTextSha256': sha_bytes(action['text'].encode()), 'text': '目表示眼睛。请观察图片。'}]}
        self.amendment = revise_preview_narration(f.service, f.source_key, f.root, patch, failed, execute=True)
        audit = f.audit(f.source_key)
        self.source_audit_dir = f.base / 'revised-source-audit'
        shutil.copytree(f.base / 'target-audit', self.source_audit_dir)
        publisher = TextbookPublicationService(f.service)
        row = f.service.get(f.source_key)
        released = publisher.prepare(key=f.source_key, edition=row['edition_id'], revision=row['revision_id'], node=row['node_id'],
            teaching_revision='4', review=self.review(row), audio_audit=audit, classroom_directory=f.root)
        self.parent_key = publisher.publish(released)['contentKey']
        current = json.loads(row['classroom_json'])
        old_html = current['scenes'][1]['content']['html']
        self.visual = {'schemaVersion': 'mira.textbook.preview-visual-patch.v1',
            'expectedSourceSha256': row['classroom_sha256'], 'reviewer': 'test', 'basis': 'pure visual', 'changes': [
            {'sceneId': 'interactive', 'beforeHtmlSha256': sha_bytes(old_html.encode()), 'html': old_html + '<button>观察</button>'}]}
        self.patch = {'schemaVersion': VISUAL_PATCH_SCHEMA, 'parentContentKey': self.parent_key,
            'expectedSourceSha256': row['classroom_sha256'], 'teachingRevision': '5', 'reviewer': 'test',
            'basis': 'Only revise game HTML after an already approved legacy narration repair', 'changes': []}
        f.runtime.reset_mock()

    @staticmethod
    def review(row):
        return {'alignmentConfirmed': True, 'originalExpressionConfirmed': True, 'sourceUsageConfirmed': True,
                'publicationAuthorized': True, 'reviewer': 'test', 'basis': 'isolated exact evidence review',
                'sourceSha256': row['classroom_sha256'], 'reviewedAt': now_ms() - 1}

    def prepare(self):
        f = self.f
        return prepare_revision(f.service, self.parent_key, f.root, self.patch,
            self.source_audit_dir / 'audit.json', f.output, visual_patch=self.visual)

    def test_prepare_register_reuse_audit_publish_preserves_old_narration(self):
        f = self.f
        prepared = self.prepare()
        self.assertEqual((prepared['changedSpeechCount'], prepared['inheritedSpeechCount']), (0, 3))
        parent, _, _, _ = load_prepared(f.output, verify_assets=True)
        with self.assertRaises(ApiError):
            validate_parent(parent)  # Legacy published v1 contract stays closed.
        register_revision(f.service, f.output, f.root, budget_reference='test pure visual')
        narrate_preview(f.service, prepared['previewKey'], f.root)
        audit = f.audit(prepared['previewKey'])
        self.assertTrue(audit['passed'])
        self.assertEqual(sum('operatorParent' in e for e in audit['segments']), 3)
        row = f.service.get(prepared['previewKey'])
        publisher = TextbookPublicationService(f.service)
        released = publisher.prepare(key=row['preview_key'], edition=row['edition_id'], revision=row['revision_id'], node=row['node_id'],
            teaching_revision='5', review=self.review(row), audio_audit=audit, classroom_directory=f.root)
        receipt = publisher.publish(released)
        self.assertEqual(validate_release(f.repo.get_build(f.db, receipt['contentKey']), released['manifest']), released['release'])
        f.runtime.start_formal_audio_tts.assert_not_called()
        f.runtime.start_formal_audio_asr.assert_not_called()

    def test_tampered_original_plan_archive_and_false_passing_audit_are_rejected(self):
        f = self.f
        self.prepare()
        parent, _, _, _ = load_prepared(f.output)
        for name in ('plan.json', 'failed-audit.json', 'amendment.json', 'target.json', 'saved.json'):
            changed = deepcopy(parent)
            changed['sourceNarrationRevisions'][0]['files'][name] = '{}'
            with self.subTest(name=name), self.assertRaises(ApiError):
                validate_parent(changed, allow_saved_preview=True, allow_visual_ancestry=True)
        changed = deepcopy(parent)
        entry = changed['audit']['segments'][0]
        entry['transcript'] = '错误。'
        entry['asr'].update(transcript=entry['transcript'], transcriptSha256=sha_bytes(entry['transcript'].encode()))
        changed['audit']['sha256'] = digest({k: v for k, v in changed['audit'].items() if k != 'sha256'})
        with self.assertRaises(ApiError):
            validate_parent(changed, allow_saved_preview=True, allow_visual_ancestry=True)
        original = f.source_folder / 'narration-revisions' / self.amendment['revisionId'] / 'plan.json'
        original.write_text('{}')
        with self.assertRaises(ApiError):
            register_revision(f.service, f.output, f.root, budget_reference='test tamper')


if __name__ == '__main__':
    unittest.main()
