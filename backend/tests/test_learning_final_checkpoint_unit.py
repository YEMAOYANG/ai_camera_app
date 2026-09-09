from __future__ import annotations

import hashlib
import json
import unittest

from services.learning_catalog_release_service import LearningCatalogReleaseService


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _dispatch(
    phase: str,
    ordinal: int,
    checkpoint: dict[str, object],
    *,
    status: str = "succeeded",
    output_sha256: str | None = None,
) -> dict[str, object]:
    encoded = _canonical_json(checkpoint)
    return {
        "phase": phase,
        "phase_ordinal": ordinal,
        "status": status,
        "checkpoint_json": encoded,
        "output_sha256": output_sha256
        or hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }


def _final(ordinal: int, fingerprint: str) -> dict[str, object]:
    key = "candidateCourse" if ordinal == 11 else "repairedCandidateCourse"
    return {
        key: {"id": f"course-{ordinal}", "version": "v1", "content": {}},
        "questionFingerprints": [{"fingerprint": fingerprint}],
        "validation": {"passed": True},
        "independentSolution": {"teachingReview": {"passed": ordinal == 11}},
    }


class LearningFinalCheckpointUnitTest(unittest.TestCase):
    def setUp(self):
        self.service = object.__new__(LearningCatalogReleaseService)

    def test_repaired_terminal_chain_selects_phase_14_fingerprints(self):
        phase_11 = _final(11, "phase-11-fingerprint")
        phase_12 = {"repair": {"accepted": True}}
        phase_14 = _final(14, "phase-14-fingerprint")

        checkpoint = self.service._final_checkpoint_from_dispatches(
            [
                _dispatch("independent_verification", 11, phase_11),
                _dispatch("consistency_repair", 12, phase_12),
                _dispatch("verification_after_repair", 14, phase_14),
            ]
        )

        self.assertEqual(
            checkpoint["questionFingerprints"],
            [{"fingerprint": "phase-14-fingerprint"}],
        )

    def test_phase_11_only_selects_its_terminal_fingerprints(self):
        phase_11 = _final(11, "phase-11-fingerprint")

        checkpoint = self.service._final_checkpoint_from_dispatches(
            [_dispatch("independent_verification", 11, phase_11)]
        )

        self.assertEqual(
            checkpoint["questionFingerprints"],
            [{"fingerprint": "phase-11-fingerprint"}],
        )

    def test_nonterminal_tail_after_final_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service._final_checkpoint_from_dispatches(
                [
                    _dispatch(
                        "independent_verification",
                        11,
                        _final(11, "phase-11-fingerprint"),
                    ),
                    _dispatch(
                        "consistency_repair",
                        12,
                        {"repair": {"accepted": True}},
                    ),
                ]
            )

    def test_chain_without_a_final_checkpoint_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service._final_checkpoint_from_dispatches(
                [
                    _dispatch(
                        "consistency_repair",
                        12,
                        {"repair": {"accepted": True}},
                    )
                ]
            )

    def test_terminal_final_hash_drift_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "hash drift"):
            self.service._final_checkpoint_from_dispatches(
                [
                    _dispatch(
                        "independent_verification",
                        11,
                        _final(11, "phase-11-fingerprint"),
                        output_sha256="0" * 64,
                    )
                ]
            )


if __name__ == "__main__":
    unittest.main()
