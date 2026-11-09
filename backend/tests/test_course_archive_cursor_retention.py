import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from services.course_archive_queue import CourseArchiveWorker


class _Queue:
    def __init__(self, root: Path):
        self.root = root
        self.directory = root / "archive-queue"
        self.items = self.directory / "items"
        self.directory.mkdir(parents=True)
        self.items.mkdir()
        (self.root / "archive-events").mkdir()

    def due(self, _limit, max_priority=None):
        del max_priority
        return []


class _Client:
    def events(self, *, after_id, limit):
        self.events_call = (after_id, limit)
        return []

    def saved_stages(self, *, after_stage_id, limit):
        self.saved_stages_call = (after_stage_id, limit)
        return []


class CourseArchiveCursorRetentionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("MIRA_TASK_TMPDIR"))
        self.root = Path(self.temporary.name).resolve()
        self.queue = _Queue(self.root)
        self.client = _Client()
        self.native_root = self.root / "native"
        (self.native_root / "data/classrooms").mkdir(parents=True)
        self.processor = SimpleNamespace(
            client=self.client,
            exporter=SimpleNamespace(native_root=self.native_root),
        )
        self.worker = CourseArchiveWorker(
            self.queue,
            self.processor,
            database=None,
            scan_catalog=False,
            scan_history=False,
        )

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def _write(path: Path, value: dict):
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def _read(path: Path):
        return json.loads(path.read_text(encoding="utf-8"))

    def test_empty_outbox_page_keeps_postgres_cursor(self):
        path = self.queue.directory / "postgres-cursor.json"
        self._write(path, {"afterId": 73})

        result = self.worker.run_once()

        self.assertEqual(result, {
            "discovered": 0,
            "completed": 0,
            "failed": 0,
            "discoveryErrors": 0,
        })
        self.assertEqual(self.client.events_call, (73, 100))
        self.assertEqual(self._read(path), {"afterId": 73})

    def test_empty_saved_stage_page_keeps_stage_cursor(self):
        path = self.queue.directory / "stages-cursor.json"
        self._write(path, {"after": "stage-z"})

        self.assertEqual(self.worker._reconcile_postgres(), 0)

        self.assertEqual(self.client.saved_stages_call, ("stage-z", 100))
        self.assertEqual(self._read(path), {"after": "stage-z"})

    def test_empty_legacy_page_keeps_file_cursor(self):
        path = self.queue.directory / "legacy-cursor.json"
        self._write(path, {"after": "stage-z.json", "files": {}})

        self.assertEqual(self.worker._reconcile_legacy(), 0)

        self.assertEqual(self._read(path), {"after": "stage-z.json", "files": {}})


if __name__ == "__main__":
    unittest.main()
