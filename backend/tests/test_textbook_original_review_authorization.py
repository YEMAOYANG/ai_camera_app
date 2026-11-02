"""Synthetic pre-dispatch consent; no real conversation or provider calls."""
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import patch

from content.textbook_catalog import digest
from content.textbook_official_followup import validate_followup, validate_frozen_followup
from content.textbook_original_review_authorization import SCHEMA
from tests.test_textbook_official_followup import FollowupEvidenceTest


class OriginalAuthorizationTest(unittest.TestCase):
    def setUp(self):
        fixture = FollowupEvidenceTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.f = fixture
        fixture.dispatch['createdAt'] = '2026-10-29T00:00:00+08:00'
        exception = fixture.original['reviewExceptions'][0]
        exception.update(authorizedAt='2026-10-28T16:20:00+08:00',
                         userInstruction=fixture.auth['answer'])
        self.auth = {**fixture.auth, 'binding': deepcopy(fixture.frozen['binding']),
                     'teachingRevision': '1', 'classHourIds': ['lesson_1']}
        self._record()

    def _meta(self, path):
        data = path.read_bytes()
        return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'byteSize': len(data)}

    def _record(self):
        f = self.f
        source = f.course / 'source-input'
        review_file = source / 'sources/original-review.json'
        review_file.write_text(json.dumps(f.original))
        f.draft['scopeReview']['postClassPractice']['officialResourceReviewSha256'] = digest(f.original)
        for name, value in [('draft', f.draft), ('frozen', f.frozen), ('dispatch', f.dispatch)]:
            (f.job / f'{name}.json').write_text(json.dumps(value))
        (source / 'request-draft.json').write_bytes((f.job / 'draft.json').read_bytes())
        self.record = {'schemaVersion': SCHEMA,
            'status': 'original_authorization_verified_for_current_candidate',
            'verification': 'authorization_record_only_not_play_audio_or_publication',
            'binding': deepcopy(f.frozen['binding']), 'teachingRevision': '1',
            'classHourIds': ['lesson_1'], 'authorization': deepcopy(self.auth),
            'originals': {**{k: self._meta(f.job / f'{k}.json') for k in ('draft', 'frozen', 'dispatch')},
                'sourceDraft': self._meta(source / 'request-draft.json'),
                'dispatchCreatedAt': f.dispatch['createdAt']},
            'currentNative': deepcopy(f.record['currentNative']), 'originalReview': deepcopy(f.original),
            'unchangedEvidence': {'originalReviewSha256': digest(f.original),
                'originalReviewFile': self._meta(review_file),
                'postClassPracticeSource': self._meta(source / 'sources/post.json')},
            'evidenceBoundaries': ['Only original consent; no source-viewing or publication claim.']}
        self._seal()

    def _seal(self):
        self.record.pop('sha256', None)
        self.record['sha256'] = digest(self.record)
        self.path = self.f.course / 'review-followups/official-video-exception' / self.record['sha256'] / 'review-followup.json'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.record))

    def check(self, operator=None):
        f = self.f
        with patch('content.textbook_official_resource_review.validate_new_course_post_class_practice'):
            return validate_followup(self.path, self.record['sha256'], f.operator if operator is None else operator,
                job=f.job, frozen=f.frozen, draft=f.draft, dispatch=f.dispatch,
                native_proof=f.proof, followup=f.chain)

    def test_original_consent_remains_pre_dispatch_and_bound_through_freeze(self):
        result = self.check()
        self.assertIs(result['authorizationIsPostDispatch'], False)
        self.assertIs(result['newDispatchAllowed'], False)
        native = {**self.f.proof, 'followupSha256': self.f.chain['sha256']}
        validate_frozen_followup(result, native)
        for field in ('effectiveReviewSha256', 'followupSha256'):
            with self.assertRaises(ValueError):
                validate_frozen_followup({**result, field: '0'*64}, native)
        with self.assertRaises(ValueError):
            validate_frozen_followup(result, {**native, 'candidateSha256': '0'*64})

    def test_cannot_relabel_a_new_or_unverified_authorization(self):
        for operator in ({}, {**self.f.operator, 'answer': 'different'}):
            with self.assertRaises(ValueError): self.check(operator)
        self.record['authorization']['teachingRevision'] = '2'; self._seal()
        with self.assertRaises(ValueError): self.check()
        self.record['authorization']['teachingRevision'] = '1'
        self.record['originals']['dispatchCreatedAt'] = '2026-10-27T00:00:00+08:00'; self._seal()
        with self.assertRaises(ValueError): self.check()

    def test_new_scope_or_changed_source_is_rejected_even_when_resealed(self):
        self.record['originalReview']['classHours'][0]['resources']['courseware']['findings'] = ['fabricated']
        self.record['unchangedEvidence']['originalReviewSha256'] = digest(self.record['originalReview'])
        self._seal()
        with self.assertRaises(ValueError): self.check()
        self._record()
        (self.f.job / 'draft.json').write_text('{}')
        with self.assertRaises(ValueError): self.check()

    def test_official_absence_uses_existing_review_validator_without_inventing_review(self):
        hour = self.f.original['classHours'][0]
        resource = hour['resources']['learningTaskSheet']
        resource.update(status='not_provided', sourceUrl=hour['courseUrl'],
                        locations=['官方资源清单未提供学习任务单'], findings=['官方未提供学习任务单。'])
        self.f.draft['scopeReview']['postClassPractice'].pop('sourcePath')
        self.f.draft['scopeReview']['postClassPractice']['sourceKind'] = 'official-inventory-absence'
        self._record()
        self.check()
        resource['findings'] = ['需要登录，无法访问']
        self._record()
        with self.assertRaises(ValueError): self.check()


if __name__ == '__main__':
    unittest.main()
