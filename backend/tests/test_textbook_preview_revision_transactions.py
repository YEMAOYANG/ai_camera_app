"""Revision entry points must release SQL locks before cross-process writes."""
from contextlib import contextmanager
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from content.textbook_catalog import canonical, digest
from core.errors import ApiError
from services.textbook_preview_revision_transaction import PreviewRevisionTransaction
from tests import test_textbook_preview_visual_revision as visual
from tests import test_textbook_preview_narration_revision as narration
from tests import test_textbook_preview_pronunciation_revision as pronunciation


class PreviewRevisionTransactionTests(unittest.TestCase):
    def setUp(self):
        mode = patch('services.textbook_preview_revision_transaction._registered_source', return_value=True)
        mode.start()
        self.addCleanup(mode.stop)

    def fixture(self, cls):
        fixture = cls()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def track(self, repository):
        original = repository.transaction
        state = {"depth": 0, "opened": 0}
        @contextmanager
        def transaction():
            state["depth"] += 1
            state["opened"] += 1
            try:
                with original() as conn:
                    yield conn
            finally:
                state["depth"] -= 1
        replacement = patch.object(repository, "transaction", transaction)
        replacement.start()
        self.addCleanup(replacement.stop)
        return state

    def unlocked(self, state, original):
        def call(*args, **kwargs):
            self.assertEqual(state["depth"], 0, "HTTP/registered write holds the preview SQL lock")
            return original(*args, **kwargs)
        return call

    def test_visual_save_runs_between_two_short_transactions(self):
        f = self.fixture(visual.VisualRevisionTests)
        state = self.track(f.service.repository)
        f.runtime.save_preview_classroom.side_effect = self.unlocked(state, f.save)
        f.apply()
        self.assertEqual(state, {"depth": 0, "opened": 3})
        self.assertEqual(f.service.get(f.key)["classroom_sha256"], digest(f.classroom))

    def test_unregistered_local_source_keeps_original_row_lock_protocol(self):
        f = self.fixture(visual.VisualRevisionTests)
        state = self.track(f.service.repository)
        def save(value):
            self.assertEqual(state['depth'], 1)
            return f.save(value)
        f.runtime.save_preview_classroom.side_effect = save
        with patch('services.textbook_preview_revision_transaction._registered_source', return_value=False):
            f.apply()
        self.assertEqual(state, {'depth': 0, 'opened': 2})  # get + original transaction

    def test_narration_paid_fence_save_and_aggregate_write_are_outside_sql(self):
        f = self.fixture(narration.NarrationRevisionTests)
        state = self.track(f.service.repository)
        f.runtime.start_formal_audio_tts.side_effect = self.unlocked(state, f.start_tts)
        f.runtime.save_preview_classroom.side_effect = self.unlocked(state, f.fixture.save)
        from services import textbook_preview_narration_revision as module
        with patch.object(module, 'atomic_json', self.unlocked(state, module.atomic_json)):
            f.run_revision()
        self.assertEqual(state, {"depth": 0, "opened": 3})

    def test_pronunciation_save_and_three_pointer_rotations_are_outside_sql(self):
        case = self.fixture(pronunciation.PronunciationRevisionTests)
        f = case.f
        state = self.track(f.service.repository)
        original = f.runtime.save_preview_classroom.side_effect
        f.runtime.save_preview_classroom.side_effect = self.unlocked(state, original)
        from services import textbook_preview_pronunciation_revision as module
        writes = []
        def atomic(path, value):
            writes.append(path.name)
            return self.unlocked(state, original_atomic)(path, value)
        original_atomic = module.atomic_json
        with patch.object(module, 'atomic_json', atomic):
            case.run_revision()
        self.assertEqual(set(writes), {'plan.json', 'receipts.json', 'checkpoint.json'})
        self.assertEqual(state, {"depth": 0, "opened": 3})
        case.assert_no_provider()

    def test_changed_result_without_classroom_sha_change_is_not_overwritten(self):
        f = self.fixture(visual.VisualRevisionTests)
        old = f.service.get(f.key)
        def save(value):
            f.save(value)
            f.db.execute('UPDATE learning_textbook_course_previews SET result_json=? WHERE preview_key=?',
                         (canonical({'concurrent': True}), f.key))
            f.db.raw.commit()
        f.runtime.save_preview_classroom.side_effect = save
        with self.assertRaises(ApiError):
            f.apply()
        row = f.service.get(f.key)
        self.assertEqual(row['classroom_sha256'], old['classroom_sha256'])
        self.assertEqual(json.loads(row['result_json']), {'concurrent': True})
        self.assertNotEqual(digest(f.classroom), old['classroom_sha256'])
        self.assertTrue((f.archive() / 'saved.json').is_file())
        # The valid remote target remains evidence; no compensating overwrite.
        self.assertEqual(f.runtime.save_preview_classroom.call_count, 1)

    def test_another_runtime_head_after_readback_rejects_final_sql_commit(self):
        f = self.fixture(visual.VisualRevisionTests)
        old = f.service.get(f.key)
        original = PreviewRevisionTransaction.commit_phase
        def race(transaction):
            f.classroom = {**deepcopy(f.classroom), 'createdAt': 'concurrent-native-version'}
            (f.root / (f.cid + '.json')).write_text(canonical(f.classroom))
            original(transaction)
        with patch.object(PreviewRevisionTransaction, 'commit_phase', race), self.assertRaises(ApiError):
            f.apply()
        self.assertEqual(f.service.get(f.key)['classroom_sha256'], old['classroom_sha256'])
        self.assertEqual(f.classroom['createdAt'], 'concurrent-native-version')
        self.assertEqual(f.runtime.save_preview_classroom.call_count, 1)

    def test_release_uses_detached_snapshot_and_final_publication_is_rechecked(self):
        f = self.fixture(visual.VisualRevisionTests)
        original = f.service.repository.transaction
        @contextmanager
        def published_transaction():
            with original() as conn:
                class Proxy:
                    def execute(self, sql, params=()):
                        result = conn.execute(sql, params)
                        if "FROM learning_textbook_course_builds" in sql:
                            class Builds:
                                def fetchall(self):
                                    return [{'input_json': canonical({'previewKey': f.key})}]
                            return Builds()
                        return result
                yield Proxy()
        with PreviewRevisionTransaction(f.service.repository, f.key, lambda msg: (_ for _ in ()).throw(ValueError(msg)), f.root / (f.cid + ".json")) as tx:
            row = tx.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE', (f.key,)).fetchone()
            tx.release(row)
            # Callers cannot change the detached transaction comparison baseline.
            row['status'] = 'published'
            with patch.object(f.service.repository, 'transaction', published_transaction), self.assertRaisesRegex(ValueError, '已发布'):
                tx.commit_phase()
