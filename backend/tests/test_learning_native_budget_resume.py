import unittest

from content.learning_budget_policy import digest
from repositories.learning_curriculum_preparation_repository import LearningCurriculumPreparationRepository
from services.learning_native_budget_resume import (
    _settled_ledger_sha256, _admitted_preview_from_archive, _public_recovery_event,
)


class NativeBudgetResumeTest(unittest.TestCase):
    def test_pending_dispatches_are_never_replayed(self):
        settled = [{'id': str(n), 'state': 'settled'} for n in range(31)]
        self.assertEqual(_settled_ledger_sha256(settled), digest(sorted(settled,key=lambda row:row['id'])))
        for state in ('reserved','dispatched','unknown','unsupported'):
            with self.subTest(state=state), self.assertRaises(ValueError):
                _settled_ledger_sha256(settled + [{'id':'pending','state':state}])

    def test_private_resume_preserves_zero_remaining_search_and_safe_events(self):
        archive = {'native': {'historySha256':'a'*64,'jobId':'original_job','remainingSearchAttempts':0},
                   'originalRuntime':{'id':'original_runtime'},'originalOwner':{'id':'original_owner'}}
        sha=digest(archive)
        preview=_admitted_preview_from_archive(archive,sha)
        self.assertEqual(preview['remainingSearchAttempts'],0)
        for state in ('pending','applied'):
            event=_public_recovery_event(preview,status=state)
            self.assertEqual(LearningCurriculumPreparationRepository._validate_event_payload(event),event)
            self.assertEqual(event['remainingSearchAttemptCount'],0)
            self.assertEqual(event['recoveryReceiptId'],sha)


if __name__ == '__main__': unittest.main()
