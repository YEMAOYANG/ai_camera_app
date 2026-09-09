from __future__ import annotations

import unittest
from unittest.mock import Mock

from core.database import Database
from repositories.openmaic_runtime_repository import OpenMaicRuntimeRepository
from services.openmaic_full_runtime_service import OpenMaicFullRuntimeService
from tests.support import fresh_test_config


class CourseSupplyProviderBootstrapTest(unittest.TestCase):
    def setUp(self):
        self.repository = OpenMaicRuntimeRepository(
            Database(fresh_test_config()['DATABASE_URL'])
        )
        self.service = OpenMaicFullRuntimeService.__new__(OpenMaicFullRuntimeService)
        self.service.repository = self.repository
        self.service._require_generation = Mock()
        self.service.client = Mock()

    def test_fresh_install_probes_once_and_reuses_durable_readiness(self):
        self.service.client.formal_generation_provider_canary.return_value = {'ready': True}
        first = self.service.ensure_initial_formal_provider_probe()
        second = self.service.ensure_initial_formal_provider_probe()
        self.assertTrue(first['dispatchAllowed'])
        self.assertTrue(second['dispatchAllowed'])
        self.service.client.formal_generation_provider_canary.assert_called_once()

    def test_uncertain_probe_is_not_repeated_after_restart(self):
        self.service.client.formal_generation_provider_canary.side_effect = TimeoutError()
        self.assertFalse(self.service.ensure_initial_formal_provider_probe()['dispatchAllowed'])
        self.service.client = Mock()
        result = self.service.ensure_initial_formal_provider_probe()
        self.assertFalse(result['dispatchAllowed'])
        self.assertEqual(result['reasonCode'], 'initial_probe_pending')
        self.service.client.formal_generation_provider_canary.assert_not_called()

    def test_existing_failure_is_not_automatically_overridden(self):
        with self.repository.transaction() as conn:
            self.repository.open_formal_provider_circuit(
                conn, reason_code='quota_exhausted', runtime_id=None, now=1000
            )
        self.assertFalse(self.service.ensure_initial_formal_provider_probe()['dispatchAllowed'])
        self.service.client.formal_generation_provider_canary.assert_not_called()

    def test_duplicate_reservation_and_stale_completion_cannot_open_gate(self):
        with self.repository.transaction() as conn:
            self.assertTrue(self.repository.claim_initial_formal_provider_probe(conn, now=1000))
        with self.repository.transaction() as conn:
            self.assertFalse(self.repository.claim_initial_formal_provider_probe(conn, now=1001))
            self.repository.open_formal_provider_circuit(
                conn, reason_code='newer_failure', runtime_id=None, now=1002
            )
            self.assertFalse(self.repository.complete_initial_formal_provider_probe(
                conn, claimed_at=1000, ready=True, now=1003
            ))
        self.assertFalse(self.service.formal_provider_circuit_status()['dispatchAllowed'])


class FreeQuotaClassificationTest(unittest.TestCase):
    def test_bailian_exhaustion_is_a_global_billing_stop(self):
        from integrations.openmaic_full_runtime_client import _generation_failure_code
        for message in ('AllocationQuota.FreeTierOnly', 'FORMAL_PROFESSIONAL_SESSION_FAILED:Free quota exhausted.'):
            self.assertEqual(_generation_failure_code('failed', message), 'openmaic_formal_provider_free_quota_exhausted')
        self.assertIsNone(_generation_failure_code('generating', 'Free quota exhausted'))


if __name__ == '__main__':
    unittest.main()
