from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from courseware.tools import post_publish


class PostPublishDeliveryResumeTest(unittest.TestCase):
    def setUp(self):
        self.expected = {'contentKey': 'a' * 64, 'classroomId': 'tbpub_' + 'a' * 24, 'releaseSha256': 'b' * 64}
        self.identity = {'editionId': 'edition', 'revisionId': 'revision', 'nodeId': 'node'}
        self.scope = {'scopeKey': 'c' * 64}
        self.audio = {'path': f"/api/classroom-media/{self.expected['classroomId']}/audio/example.wav",
                      'sha256': 'd' * 64, 'byteSize': 120, 'mimeType': 'audio/wav'}
        self.inventory = [self.audio, {'path': 'image', 'sha256': 'e' * 64, 'byteSize': 5, 'mimeType': 'image/png'}]
        self.proof = {
            'archiveReadback': {'scopeKey': self.scope['scopeKey'], 'registryOnly': True,
                                'mediaVerifiedCount': 2, 'mediaVerifiedBytes': 125},
            'studentPlayback': {'ok': True, 'mode': 'student-launch', 'openedFromDirectory': True,
                                'recordedAudioPlayed': True, 'classroomId': self.expected['classroomId'],
                                'directoryIdentity': {**self.identity, 'selected': True},
                                'audioPath': self.audio['path'], 'audioSha256': self.audio['sha256'],
                                'audioBytes': self.audio['byteSize']},
            'timingsSeconds': {'archiveRegistration': 3, 'studentPlayback': 5},
        }

    def test_resume_preserves_receipt_and_does_not_repeat_student_launch(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'delivery.json'
            collect = Mock(return_value=self.proof)
            first = post_publish.delivery_checkpoint(path, self.expected, self.scope, self.inventory, collect,
                                                     directory_identity=self.identity)
            original = path.read_bytes()
            resumed = post_publish.delivery_checkpoint(path, self.expected, self.scope, self.inventory, collect,
                                                       directory_identity=self.identity)
            self.assertEqual(first, resumed)
            self.assertEqual(original, path.read_bytes())
            collect.assert_called_once()
            with self.assertRaisesRegex(ValueError, 'registered archive'):
                post_publish.delivery_checkpoint(path, self.expected, {'scopeKey': 'other'}, self.inventory, collect,
                                                 directory_identity=self.identity)
            with self.assertRaisesRegex(ValueError, 'different publication'):
                post_publish.delivery_checkpoint(path, {**self.expected, 'releaseSha256': 'other'}, self.scope,
                                                 self.inventory, collect, directory_identity=self.identity)
            self.assertEqual(original, path.read_bytes())
            collect.assert_called_once()

    def test_preview_or_unbound_audio_cannot_be_saved_as_student_acceptance(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'delivery.json'
            for changes in ({'mode': 'student-chrome-preview'}, {'audioSha256': 'other'}, {'audioBytes': 121}):
                proof = {**self.proof, 'studentPlayback': {**self.proof['studentPlayback'], **changes}}
                with self.assertRaisesRegex(ValueError, 'recorded clip'):
                    post_publish.delivery_checkpoint(path, self.expected, self.scope, self.inventory, lambda: proof,
                                                     directory_identity=self.identity)
                self.assertFalse(path.exists())

    def test_explicit_resume_requires_a_real_existing_receipt(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'delivery.json'
            with self.assertRaisesRegex(ValueError, 'Explicit delivery receipt does not exist'):
                post_publish.delivery_checkpoint(path, self.expected, self.scope, self.inventory, collect=None,
                                                 directory_identity=self.identity)
            first = post_publish.delivery_checkpoint(path, self.expected, self.scope, self.inventory,
                                                      lambda: self.proof, directory_identity=self.identity)
            self.assertEqual(first, post_publish.delivery_checkpoint(path, self.expected, self.scope,
                                                                      self.inventory, collect=None,
                                                                      directory_identity=self.identity))

    def test_selected_directory_and_lesson_must_match(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'delivery.json'
            for observed in (None, {**self.identity, 'selected': False},
                             {**self.identity, 'selected': True, 'revisionId': 'other'},
                             {**self.identity, 'selected': True, 'nodeId': 'other'}):
                student = {**self.proof['studentPlayback'], 'directoryIdentity': observed}
                proof = {**self.proof, 'studentPlayback': student}
                with self.assertRaisesRegex(ValueError, 'exact selected textbook directory lesson'):
                    post_publish.delivery_checkpoint(path, self.expected, self.scope, self.inventory, lambda: proof,
                                                     directory_identity=self.identity)
                self.assertFalse(path.exists())

    def test_completion_retry_preserves_cleanup_already_verified_for_that_release(self):
        identity = {'editionId': 'edition', 'revisionId': 'revision', 'nodeId': 'node'}
        assignment = {**identity, 'owner': '/root/author', 'slug': 'lesson',
                      'localCleanup': 'verified_duplicate_media_removed', 'contentKey': self.expected['contentKey']}
        ledger = {'currentGoalBatch': {'active': {'author': assignment}}}
        receipt = {**self.expected, 'verifiedAt': 'time', 'receiptPath': 'receipt.json',
                   'timingsSeconds': {'studentPlayback': 5}}
        post_publish.record_completion(ledger, 'author', identity, 'lesson', receipt)
        self.assertEqual(assignment['localCleanup'], 'verified_duplicate_media_removed')

    def test_confirmation_is_an_exact_current_or_historical_pair(self):
        batch = {'ownerQuote': 'new', 'confirmedAt': 'later',
                 'ownerConfirmationHistory': [{'ownerQuote': 'old', 'confirmedAt': 'earlier'}]}
        def confirmed(quote, at, by='owner'):
            return post_publish.matches_owner_confirmation(
                batch, {'userQuote': quote, 'confirmedAt': at, 'confirmedBy': by})
        self.assertTrue(confirmed('new', 'later'))
        self.assertTrue(confirmed('old', 'earlier'))
        self.assertFalse(confirmed('old', 'later'))
        self.assertFalse(confirmed('old', 'earlier', 'different'))
