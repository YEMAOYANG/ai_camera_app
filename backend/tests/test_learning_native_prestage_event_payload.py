import unittest

from content.learning_budget_policy import digest
from repositories.learning_curriculum_preparation_repository import LearningCurriculumPreparationRepository
from services.learning_native_prestage_recovery import (
    _admitted_preview_from_archive,
    _public_recovery_event,
)


class NativePrestageEventPayloadTest(unittest.TestCase):
    def test_pending_and_applied_events_use_the_real_public_validator(self):
        archive = {
            'native': {'historySha256': 'b' * 64, 'jobId': 'omformal_test',
                       'remainingSearchAttempts': 1},
            'originalRuntime': {'id': 'runtime_test', 'error_code': 'original_failure'},
            'originalOwner': {'id': 'owner_test', 'error_code': None},
            'contentDispatchesSha256': 'c' * 64,
        }
        history_sha = digest(archive)
        preview = _admitted_preview_from_archive(archive, history_sha)
        validate = LearningCurriculumPreparationRepository._validate_event_payload
        # Regression: the rich private preview must remain forbidden publicly.
        with self.assertRaisesRegex(ValueError, 'non-public field'):
            validate(preview)
        for status in ('pending', 'applied'):
            with self.subTest(status=status):
                event = _public_recovery_event({**preview, 'applied': status == 'applied'}, status=status)
                self.assertEqual(validate(event), event)
                self.assertEqual(event['recoveryReceiptId'], history_sha)
                self.assertEqual(event['nativeRecoveryReceiptId'], 'b' * 64)
                self.assertEqual(event['contentDispatchCount'], 13)
                self.assertEqual(event['remainingSearchAttemptCount'], 1)
                self.assertFalse(any(isinstance(value, (bool, list, dict)) or value is None
                                     for value in event.values()))
        self.assertEqual(digest(archive), history_sha)

    def test_replay_reconstructs_from_private_archive_and_rejects_tampering(self):
        archive = {'native': {'historySha256': 'a' * 64, 'jobId': 'omformal_original',
                              'remainingSearchAttempts': 1},
                   'originalRuntime': {'id': 'runtime_original'},
                   'originalOwner': {'id': 'owner_original'}}
        history_sha = digest(archive)
        preview = _admitted_preview_from_archive(archive, history_sha)
        self.assertEqual((preview['runtimeId'], preview['ownerId']),
                         ('runtime_original', 'owner_original'))
        self.assertEqual(preview['nativeHistorySha256'], 'a' * 64)
        archive['native']['remainingSearchAttempts'] = 4
        with self.assertRaisesRegex(ValueError, 'fingerprint mismatch'):
            _admitted_preview_from_archive(archive, history_sha)


if __name__ == '__main__':
    unittest.main()
