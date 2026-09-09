import json
from pathlib import Path
import subprocess
import unittest

from services.learning_question_phase_contract import (
    PROVIDER_PHASES,
    QUESTION_CONTRACT_VERSION,
    provider_phase,
    validate_provider_phase_graph,
)


EXPECTED_PROVIDER_PHASES = (
    ("outline", 1),
    ("raw_candidate", 2),
    ("candidate_repair", 3),
    ("candidate_repair_retry", 4),
    ("lesson_text", 5),
    ("reconciliation", 6),
    ("reconciliation_retry", 7),
    ("practice_leak_repair_1", 8),
    ("practice_leak_repair_2", 9),
    ("choice_prompt_repair", 10),
    ("independent_verification", 11),
    ("consistency_repair", 12),
    ("consistency_repair_retry", 13),
    ("verification_after_repair", 14),
)


class LearningQuestionPhaseContractTest(unittest.TestCase):
    def test_contract_freezes_exact_fourteen_named_phases(self):
        self.assertEqual(
            QUESTION_CONTRACT_VERSION,
            "mira.learning.question-contract.v2",
        )
        self.assertEqual(PROVIDER_PHASES, EXPECTED_PROVIDER_PHASES)
        self.assertEqual(
            [
                (
                    provider_phase(name, ordinal).phase,
                    provider_phase(name, ordinal).phase_ordinal,
                )
                for name, ordinal in EXPECTED_PROVIDER_PHASES
            ],
            list(EXPECTED_PROVIDER_PHASES),
        )

    def test_caller_cannot_choose_a_different_ordinal(self):
        with self.assertRaisesRegex(ValueError, "phase ordinal mismatch"):
            provider_phase("outline", 2)

    def test_phase_ordinals_reject_bool_float_string_and_null(self):
        invalid_ordinals = (True, 1.0, "1", None)
        for invalid in invalid_ordinals:
            with self.subTest(api="provider_phase", invalid=repr(invalid)):
                with self.assertRaisesRegex(ValueError, "phase ordinal"):
                    provider_phase("outline", invalid)
            graph = list(EXPECTED_PROVIDER_PHASES)
            graph[0] = ("outline", invalid)
            with self.subTest(api="validate_graph", invalid=repr(invalid)):
                with self.assertRaisesRegex(ValueError, "phase ordinal"):
                    validate_provider_phase_graph(tuple(graph))

    def test_python_and_node_exports_match_shared_phase_authority(self):
        backend_root = Path(__file__).resolve().parents[1]
        authority_path = (
            backend_root
            / "openmaic-sidecar"
            / "contracts"
            / "learning_question_phase_contract.v2.json"
        )
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
        node_script = """
          import {
            PROVIDER_PHASES,
            QUESTION_CONTRACT_VERSION,
          } from './src/question-contract.mjs';
          process.stdout.write(JSON.stringify({
            questionContractVersion: QUESTION_CONTRACT_VERSION,
            providerPhases: PROVIDER_PHASES,
          }));
        """
        completed = subprocess.run(
            ["node", "--input-type=module", "--eval", node_script],
            cwd=backend_root / "openmaic-sidecar",
            check=True,
            capture_output=True,
            text=True,
        )
        node_contract = json.loads(completed.stdout)
        expected_phases = [
            [item["phase"], item["phaseOrdinal"]]
            for item in authority["providerPhases"]
        ]
        self.assertEqual(
            authority["questionContractVersion"], QUESTION_CONTRACT_VERSION
        )
        self.assertEqual(expected_phases, [list(item) for item in PROVIDER_PHASES])
        self.assertEqual(
            node_contract,
            {
                "questionContractVersion": QUESTION_CONTRACT_VERSION,
                "providerPhases": expected_phases,
            },
        )

    def test_fifteenth_phase_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "at most 14"):
            validate_provider_phase_graph(
                (*EXPECTED_PROVIDER_PHASES, ("uncontracted_phase", 15))
            )

    def test_duplicate_phase_and_duplicate_ordinal_are_rejected(self):
        invalid_graphs = (
            (*EXPECTED_PROVIDER_PHASES[:-1], ("outline", 14)),
            (*EXPECTED_PROVIDER_PHASES[:-1], ("other_phase", 13)),
        )
        expected_messages = ("duplicate provider phase", "duplicate phase ordinal")
        for graph, message in zip(invalid_graphs, expected_messages):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    validate_provider_phase_graph(graph)


if __name__ == "__main__":
    unittest.main()
