from __future__ import annotations

from pathlib import Path
import unittest

from core.database import _split_sql_script


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "061_learning_openmaic_runtime_events.sql"
ASR_MIGRATION = ROOT / "migrations" / "062_learning_openmaic_asr_transcription_events.sql"
ADAPTIVE_MIGRATION = ROOT / "migrations" / "069_learning_adaptive_formal_runtime.sql"


class LearningOpenMaicRuntimeEventsMigrationTest(unittest.TestCase):
    def test_event_stream_and_ledger_freeze_identity_and_exactly_once_keys(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        statements = _split_sql_script(sql)
        normalized = " ".join(sql.split()).lower()

        self.assertGreaterEqual(len(statements), 2)
        self.assertIn("create table if not exists learning_openmaic_runtime_event_streams", normalized)
        self.assertIn("create table if not exists learning_openmaic_runtime_events", normalized)
        for column in (
            "runtime_session_id",
            "learning_session_id",
            "runtime_classroom_id",
            "upstream_classroom_id",
            "family_id",
            "child_id",
            "release_id",
            "target_fingerprint",
            "expected_scene_count",
            "last_sequence",
            "report_id",
        ):
            self.assertIn(column, normalized)
        self.assertIn("unique key uq_openmaic_runtime_event_sequence", normalized)
        self.assertIn("unique key uq_openmaic_runtime_event_idempotency", normalized)
        self.assertIn("attempt_number = 1", normalized)
        self.assertIn("foreign key (runtime_session_id)", normalized)
        self.assertIn("references student_openmaic_runtime_sessions(id)", normalized)
        self.assertIn("foreign key (runtime_classroom_id)", normalized)
        self.assertIn("references learning_openmaic_runtime_classrooms(id)", normalized)
        self.assertIn("foreign key (release_id)", normalized)
        self.assertIn("references learning_catalog_releases(id)", normalized)

    def test_asr_extension_adds_only_a_non_assessment_event_shape(self):
        self.assertTrue(ASR_MIGRATION.exists())
        sql = ASR_MIGRATION.read_text(encoding="utf-8")
        statements = _split_sql_script(sql)
        normalized = " ".join(sql.split()).lower()
        self.assertEqual(len(statements), 1)
        self.assertIn(
            "alter table learning_openmaic_runtime_events drop check chk_openmaic_runtime_event_identity",
            normalized,
        )
        self.assertIn("'asr_transcribed'", normalized)
        self.assertIn(
            "event_type = 'asr_transcribed' and action_id is null and question_id is null and attempt_number is null",
            normalized,
        )
        self.assertNotIn("update learning_openmaic_runtime_events", normalized)

    def test_interaction_extension_keeps_non_assessment_shape_and_adaptive_bounds(self):
        sql = (ROOT / "migrations/075_learning_openmaic_interaction_events.sql").read_text(encoding="utf-8")
        normalized = " ".join(sql.split()).lower()
        self.assertEqual(len(_split_sql_script(sql)), 1)
        self.assertIn("'interaction_completed'", normalized)
        self.assertIn("event_type = 'interaction_completed' and action_id is null and question_id is null and attempt_number is null", normalized)
        self.assertIn("scene_index >= 0 and scene_index < 60", normalized)
        self.assertNotIn("update learning_openmaic_runtime_events", normalized)

    def test_adaptive_extension_bounds_counts_and_uses_per_job_audio_authority(self):
        sql = ADAPTIVE_MIGRATION.read_text(encoding="utf-8")
        normalized = " ".join(sql.split()).lower()

        self.assertIn("expected_segment_count between 1 and 240", normalized)
        self.assertIn(
            "tts_attempted_count = expected_segment_count", normalized
        )
        self.assertIn("asr_passed_count = expected_segment_count", normalized)
        self.assertIn("expected_scene_count between 1 and 60", normalized)
        self.assertIn(
            "drop index uq_formal_qwen_audio_segment_scene", normalized
        )
        self.assertIn(
            "add index idx_formal_qwen_audio_segment_scene(build_item_id, scene_id)",
            normalized,
        )
        self.assertIn("scene_order between 0 and 239", normalized)
        self.assertIn("validation_scene_order between 0 and 239", normalized)
        self.assertIn("scene_index >= 0 and scene_index < 60", normalized)
        self.assertNotIn("expected_scene_count = 10", normalized)
        self.assertNotIn("scene_order between 0 and 9", normalized)
        self.assertNotIn("validation_scene_order between 0 and 9", normalized)
        self.assertNotIn("scene_index < 10", normalized)


if __name__ == "__main__":
    unittest.main()
