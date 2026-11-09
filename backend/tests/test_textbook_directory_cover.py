import hashlib
import io
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from services.courseware_asset_store import CoursewareAssetNotFound
from services.textbook_directory_cover import read_directory_cover


class TextbookDirectoryCoverTests(unittest.TestCase):
    def setUp(self):
        self.repo = MagicMock()
        self.repo.get_build.return_value = {
            "status": "published", "part_index": 1, "edition_id": "edition", "revision_id": "revision",
        }
        self.repo.get_revision.return_value = {"grade_code": "primary_1"}
        self.store = MagicMock()
        self.store.project_root = Path("/project")
        source = io.BytesIO()
        Image.new("RGB", (64, 48), (20, 90, 190)).save(source, "PNG")
        self.body = source.getvalue()
        self.sha = hashlib.sha256(self.body).hexdigest()
        self.path = f"/api/classroom-media/tbpub_course/media/{self.sha}.png"
        self.release = {
            "classroomId": "tbpub_course",
            "media": [{"path": self.path, "sha256": self.sha, "byteSize": len(self.body), "mimeType": "image/png"}],
            "classroom": {"scenes": [{"type": "slide", "content": {"canvas": {"elements": [
                {"type": "image", "src": "/api/classroom-media/other/media/wrong.png"},
                {"type": "image", "src": self.path},
            ]}}}]},
        }
        verifier = patch("services.textbook_directory_cover.published_release",
                         return_value=({}, self.release, {}, {}))
        self.verify = verifier.start()
        self.addCleanup(verifier.stop)

    def test_cover_uses_the_exact_archived_opening_image(self):
        self.store.read_bytes.return_value = self.body
        entry, cover = read_directory_cover(self.repo, "a" * 64, store=self.store)
        with Image.open(io.BytesIO(cover)) as image:
            self.assertEqual((image.format, image.size), ("WEBP", (960, 540)))
        self.assertEqual(entry["sha256"], hashlib.sha256(cover).hexdigest())
        self.store.read_bytes.assert_called_once_with(
            Path(f"/project/openmaic-runtime/.runtime/OpenMAIC/data/classrooms/tbpub_course/media/{self.sha}.png"),
            expected_sha256=self.sha, expected_bytes=len(self.body), max_bytes=8 * 1024 * 1024)

    def test_missing_archive_or_retired_release_cannot_supply_a_cover(self):
        self.store.read_bytes.return_value = None
        with self.assertRaises(CoursewareAssetNotFound):
            read_directory_cover(self.repo, "a" * 64, store=self.store)
        self.repo.get_build.return_value["status"] = "retired"
        self.store.reset_mock()
        self.verify.reset_mock()
        with self.assertRaises(CoursewareAssetNotFound):
            read_directory_cover(self.repo, "a" * 64, store=self.store)
        self.verify.assert_not_called()
        self.store.read_bytes.assert_not_called()
