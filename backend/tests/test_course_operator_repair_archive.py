"""Only completed, owned operator revisions join a fixed course archive."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from PIL import Image

from scripts.course_storage_releases import canonical
from services.course_archive_exporter import ArchiveSnapshot, CourseArchiveError, CourseArchiveExporter


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value).encode())


def seal(value):
    return {**value, "sha256": digest(value)}


class OperatorRepairArchiveTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get("MIRA_TASK_TMPDIR"))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.private = self.root / "private"
        self.private.mkdir()
        environment = patch.dict(os.environ, {"MIRA_TASK_TMPDIR": str(self.private)})
        environment.start()
        self.addCleanup(environment.stop)
        self.exporter = CourseArchiveExporter(project_root=self.root, media_store=Mock(),
            native_document_loader=lambda _: None,
            material_inventory_loader=lambda _: {"schemaVersion": "mira.course-material-inventory.v1",
                "materials": [], "dependencySha256": digest([])},
            standard_asset_resolver=lambda *a, **k: {"entries": [], "unresolved": []})
        self.session, self.stage = "session-owned", "stage-owned"
        self.native = self.exporter.native_root / "data"
        self.job = self.root / "output/book/node/teaching-1/authoring-job"
        self.contract = {"schemaVersion": "mira.frozen-textbook-scene-authoring.v1",
            "contract": {"pagePlan": [{"page": 7, "type": "quiz"}]}}
        self.contract["sha256"] = digest(self.contract["contract"])
        self.candidate = seal({"schemaVersion": "mira.textbook.authoring-candidate.v1",
            "sessionId": self.session, "stageId": self.stage, "frozenContract": self.contract,
            "status": "author_candidate", "verification": "static_contract_only_not_play_or_semantic_review",
            "assetBindings": [], "bindingHistory": [], "scenes": []})
        self.candidate_path = self.native / "classrooms" / self.stage / "textbook-authoring-candidate.json"
        self.write(self.candidate_path, self.candidate)
        self.write(self.job / "frozen.json", {"sceneContract": self.contract})
        self.input = {"authoring": {"sessionId": self.session, "stageId": self.stage}}
        self.snapshot = ArchiveSnapshot(identity={"courseId": "course", "courseVersion": "1",
            "classroomId": self.stage, "contentKey": None, "releaseSha256": None},
            metadata={"title": "拼音练习", "subjectName": "语文", "gradeLabel": "一年级"},
            classroom={"stage": {"id": self.stage}, "scenes": [{"id": "one", "content": {}}]},
            status="generated_saved")

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else (canonical(value) + "\n").encode())
        return path

    def finish(self, kind, plan, receipt_extra=None):
        schema = "mira.textbook." + self.exporter._OPERATOR_REPAIRS[kind]
        plan = seal({"schemaVersion": schema + "-plan.v1",
            "verification": "static_only_not_play_audio_or_publication",
            "sessionId": self.session, "stageId": self.stage, "sceneId": "scene-one",
            "contractSha256": self.contract["sha256"], "beforeDocumentSha256": "a" * 64,
            "afterDocumentSha256": "b" * 64, "beforeCandidateSha256": "c" * 64,
            "afterCandidateSha256": "d" * 64, "revisedSceneSha256": "e" * 64, **plan})
        directory = self.native / kind / sha(self.session.encode()) / self.stage / plan["sha256"]
        receipt = seal({"schemaVersion": schema + "-receipt.v1",
            "verification": "static_only_not_play_audio_or_publication", "status": "static_candidate_accepted",
            "sessionId": self.session, "stageId": self.stage, "sceneId": plan["sceneId"],
            "planSha256": plan["sha256"], "sceneSha256": plan.get("sceneSha256", plan["revisedSceneSha256"]),
            "documentSha256": plan["afterDocumentSha256"], "candidateSha256": plan["afterCandidateSha256"],
            "providerCalls": 0, **(receipt_extra or {})})
        self.write(directory / "intent.json", plan)
        self.write(directory / "receipt.json", receipt)
        return directory, plan, receipt

    def missing(self):
        png = BytesIO()
        Image.new("RGB", (3, 2), "orange").save(png, "PNG")
        raw = png.getvalue()
        before = {"stage": {"id": self.stage}, "scenes": []}
        directory, plan, receipt = self.finish("textbook-missing-locked-quiz-repairs", {
            "input": {"jobDir": str(self.job), "stageId": self.stage, "page": 7,
                "expectedCurrentDocumentSha256": digest(before),
                "expectedCurrentCandidateSha256": self.candidate["sha256"],
                "assets": [{"assetKey": "pinyin-qiong", "sha256": sha(raw), "width": 3, "height": 2,
                    "src": f"/api/classroom-media/{self.stage}/media/exact-pinyin.png"}]},
            "beforeDocumentSha256": digest(before), "beforeCandidateSha256": self.candidate["sha256"],
            "sceneSha256": "f" * 64, "assetProvenance": "operator_deterministic_png"},
            {"assetProvenance": "operator_deterministic_png"})
        self.write(directory / "original-document.json", before)
        self.write(directory / "original-candidate.json", self.candidate)
        self.write(directory / (sha(raw) + ".png"), raw)
        return directory, plan, receipt

    def rejected(self):
        old = {"id": "scene-one", "stageId": self.stage, "order": 11, "type": "quiz", "content": {}}
        new = {**old, "content": {"question": "听老师读，点一张图。"}}
        rejection = {"schemaVersion": "mira.textbook.rejected-scene.v1", "sessionId": self.session,
            "stageId": self.stage, "contractSha256": self.contract["sha256"],
            "sceneSha256": digest(old), "sceneCanonicalJson": canonical(old)}
        raw = (canonical(rejection) + "\n").encode()
        archive = self.native / "textbook-rejected-scenes" / sha(self.session.encode()) / self.stage / (sha(raw) + ".json")
        self.write(archive, raw)
        revised = self.write(self.job.parent / "planning/revised-scene.json", new)
        review = seal({"frozenContractSha256": self.contract["sha256"], "originalSceneSha256": digest(old),
            "revisedSceneSha256": digest(new)})
        return self.finish("textbook-rejected-quiz-locked-question-reviews", {
            "input": {"jobDir": str(self.job), "archivePath": str(archive), "archiveSha256": sha(raw),
                "revisedScenePath": str(revised), "revisedSceneSha256": sha(revised.read_bytes())},
            "archiveSceneSha256": digest(old), "revisedSceneSha256": digest(new), "lockedQuestionReview": review},
            {"archiveSha256": sha(raw), "lockedQuestionReviewSha256": review["sha256"]})

    def saved(self):
        old = {"id": "scene-one", "stageId": self.stage, "order": 10, "type": "interactive",
            "content": {"type": "interactive", "html": "<p>original</p>"}}
        path = self.write(self.job.parent / "planning/original-scene.json", old)
        html = self.write(self.job.parent / "planning/revised.html", b"<p>fixed</p>")
        new = {**old, "content": {**old["content"], "html": html.read_text()}}
        directory, plan, receipt = self.finish("textbook-saved-scene-repairs", {
            "input": {"jobDir": str(self.job), "stageId": self.stage, "sceneId": old["id"],
                "originalScenePath": str(path), "originalSceneFileSha256": sha(path.read_bytes()),
                "originalSceneSha256": digest(old), "revisedHtmlPath": str(html), "revisedHtmlSha256": sha(html.read_bytes())},
            "originalSceneSha256": digest(old), "revisedSceneSha256": digest(new)},
            {"originalSceneFileSha256": sha(path.read_bytes()), "originalSceneSha256": digest(old)})
        self.write(directory / "original-scene.json", old)
        return directory, plan, receipt

    def collect(self):
        return self.exporter._operator_repair_inventory(self.session, self.stage)

    def test_all_three_completed_repair_kinds_keep_exact_original_bytes(self):
        directories = [self.missing()[0], self.rejected()[0], self.saved()[0]]
        self.exporter._add_operator_repairs(self.snapshot, self.session, self.stage)
        evidence = self.snapshot.operator_repair_bindings[0]
        self.assertEqual(len(evidence["receipts"]), 3)
        result = self.exporter.export_snapshot(self.snapshot, staging_root=self.private / "export")
        self.assertTrue(result["complete"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            sources = {f.get("sourceIdentity"): f for f in manifest["files"]}
            for source, checksum in evidence["files"].items():
                self.assertEqual(sha(archive.read(sources[source]["archivePath"])), checksum)
                self.assertEqual(archive.read(sources[source]["archivePath"]), (self.root / source).read_bytes())
            for directory in directories:
                self.assertIn((directory / "receipt.json").relative_to(self.root).as_posix(), sources)
            self.assertNotIn(self.candidate_path.relative_to(self.root).as_posix(), sources)

    def test_exact_session_stage_and_only_completed_intents_are_selected(self):
        directory, _, _ = self.missing()
        self.write(directory.parent / ("0" * 64) / "intent.json", {"unfinished": True})
        self.write(directory.parent.parent / "stage-other" / ("1" * 64) / "receipt.json", {"foreign": True})
        foreign = self.native / directory.relative_to(self.native).parts[0] / sha(b"other-session") / self.stage
        self.write(foreign / ("2" * 64) / "receipt.json", {"foreign": True})
        self.write(directory / "owner.cookies", b"must never be read or exported")
        self.write(directory / "unrelated.json", {"unused": True})
        evidence = self.collect()
        self.assertEqual(len(evidence["receipts"]), 1)
        self.assertFalse(any("other" in p or "owner.cookies" in p or "unrelated" in p for p in evidence["files"]))

    def test_invalid_seal_and_receipt_identity_are_rejected(self):
        directory, _, receipt = self.missing()
        for field, value in (("sha256", "0" * 64), ("sessionId", "foreign"), ("documentSha256", "0" * 64)):
            with self.subTest(field=field):
                changed = {**receipt, field: value}
                if field != "sha256":
                    changed = seal({k: v for k, v in changed.items() if k != "sha256"})
                self.write(directory / "receipt.json", changed)
                with self.assertRaises(CourseArchiveError):
                    self.collect()

    def test_original_document_candidate_and_png_tampering_fail_closed(self):
        directory, _, _ = self.missing()
        paths = [directory / "original-document.json", directory / "original-candidate.json", next(directory.glob("*.png"))]
        for path in paths:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(b"{}")
                with self.assertRaises(CourseArchiveError):
                    self.collect()
                path.write_bytes(original)

    def test_rejected_original_and_revised_input_bytes_are_verified(self):
        _, plan, _ = self.rejected()
        for field in ("archivePath", "revisedScenePath"):
            path = Path(plan["input"][field]); original = path.read_bytes()
            path.write_bytes(b"{}")
            with self.assertRaises(CourseArchiveError):
                self.collect()
            path.write_bytes(original)

    def test_saved_original_snapshot_and_html_hash_are_verified(self):
        directory, plan, _ = self.saved()
        for path in (directory / "original-scene.json", Path(plan["input"]["revisedHtmlPath"])):
            original = path.read_bytes(); path.write_bytes(b"{}")
            with self.assertRaises(CourseArchiveError):
                self.collect()
            path.write_bytes(original)

    def test_foreign_revised_input_and_symlink_cannot_expand_owned_scope(self):
        directory, plan, receipt = self.saved()
        outside = self.write(self.root / "output/other/private.html", b"<p>fixed</p>")
        inputs = {**plan["input"], "revisedHtmlPath": str(outside)}
        changed = seal({**{k: v for k, v in plan.items() if k != "sha256"}, "input": inputs})
        # An internally valid seal still does not authorize a sibling course.
        new_dir = directory.with_name(changed["sha256"]); directory.rename(new_dir)
        self.write(new_dir / "intent.json", changed)
        self.write(new_dir / "receipt.json", seal({**{k: v for k, v in receipt.items() if k != "sha256"}, "planSha256": changed["sha256"]}))
        with self.assertRaisesRegex(CourseArchiveError, "original_unbound"):
            self.collect()
        outside.unlink(); outside.symlink_to(Path(plan["input"]["revisedHtmlPath"]))
        with self.assertRaisesRegex(CourseArchiveError, "linked"):
            self.collect()

    def test_remote_only_evidence_is_collectable_without_restoring_local_files(self):
        self.missing(); self.rejected(); self.saved()
        expected = self.collect()
        paths = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        stats = {p: p.stat() for p in paths}
        for path in paths:
            path.unlink()
        def glob(root, pattern, recursive=False):
            import fnmatch
            return [p for p in paths if p.is_relative_to(root) and fnmatch.fnmatchcase(p.relative_to(root).as_posix(), pattern)]
        with patch("services.course_archive_exporter.course_bytes", side_effect=lambda p: paths[Path(p)]), \
             patch("services.course_archive_exporter.course_exists", side_effect=lambda p: Path(p) in paths), \
             patch("services.course_archive_exporter.course_stat", side_effect=lambda p: stats[Path(p)]), \
             patch("services.course_archive_exporter.course_glob", side_effect=glob):
            self.assertEqual(self.collect(), expected)
        self.assertFalse(any(p.exists() for p in paths))

    def test_new_completed_proof_or_changed_bytes_prevent_complete_archive(self):
        self.missing()
        self.exporter._add_operator_repairs(self.snapshot, self.session, self.stage)
        self.saved()
        with self.assertRaisesRegex(CourseArchiveError, "dependencies_changed"):
            self.exporter.export_snapshot(self.snapshot, staging_root=self.private / "export")

    def test_png_dimensions_are_verified_even_with_consistent_updated_byte_hash(self):
        directory, plan, receipt = self.missing()
        changed = deepcopy(plan)
        changed["input"]["assets"][0]["width"] = 99
        changed = seal({k: v for k, v in changed.items() if k != "sha256"})
        new_dir = directory.with_name(changed["sha256"]); directory.rename(new_dir)
        self.write(new_dir / "intent.json", changed)
        self.write(new_dir / "receipt.json", seal({**{k: v for k, v in receipt.items() if k != "sha256"}, "planSha256": changed["sha256"]}))
        with self.assertRaisesRegex(CourseArchiveError, "dimensions_invalid"):
            self.collect()

    def test_large_unicode_and_numeric_keys_use_producer_canonical_order(self):
        self.candidate = seal({**{k: v for k, v in self.candidate.items() if k != "sha256"},
            "unicode": "中国" * 50000, "keys": {"10": 1, "2": 2, "\ue000": "private-use", "😀": "astral"}})
        self.write(self.candidate_path, self.candidate)
        self.missing()
        self.assertEqual(len(self.collect()["receipts"]), 1)

    def test_native_snapshot_canonical_stream_preserves_large_chinese_across_chunks(self):
        document = {"stage": {"id": self.stage, "name": "中国课件" * 50000},
            "scenes": [{"id": "one", "content": {"html": "<p>听老师讲，再点图片。</p>" * 10000}}]}
        expected = canonical(document)
        self.assertGreater(len(expected.encode()), 512 * 1024)
        self.assertEqual(self.exporter._native_canonical(document), expected)
        self.assertEqual(self.exporter._native_digest(document), sha(expected.encode()))

    def test_only_new_missing_quiz_schema_changes_existing_catalog_revision(self):
        self.assertIsNone(self.exporter._operator_repair_revision(self.input))
        self.saved()
        self.assertIsNone(self.exporter._operator_repair_revision(self.input))
        self.missing()
        first = self.exporter._operator_repair_revision(self.input)
        self.assertEqual(first, self.exporter._operator_repair_revision(self.input))
        self.rejected()
        self.assertNotEqual(first, self.exporter._operator_repair_revision(self.input))
        self.assertIsNone(self.exporter._operator_repair_revision({"authoring": {"sessionId": "foreign", "stageId": self.stage}}))

    def test_catalog_keeps_unaffected_revision_byte_for_byte_and_invalidates_only_owned_new_proof(self):
        row = {"preview_key": "1" * 64, "classroom_id": self.stage, "classroom_sha256": "2" * 64,
            "status": "preview_ready", "input_json": canonical(self.input), "result_json": "{}", "updated_at": 10}
        sibling = {**row, "preview_key": "3" * 64, "input_json": canonical({"authoring": {"sessionId": "other", "stageId": self.stage}})}
        conn = Mock(); conn.execute.return_value.fetchall.return_value = [row, sibling]
        with patch("services.course_archive_exporter.releases._current_keys", return_value=[]), \
             patch("services.course_archive_exporter.releases._other_published_courses", return_value=[]):
            before = self.exporter.list_courses(conn, include_saved=True)
            self.saved()
            self.assertEqual(before, self.exporter.list_courses(conn, include_saved=True))
            self.missing()
            after = self.exporter.list_courses(conn, include_saved=True)
        # The old algorithm includes its canonical newline.
        expected = sha((canonical({"classroomSha256": row["classroom_sha256"], "status": row["status"],
            "updatedAt": row["updated_at"], "input": row["input_json"], "result": row["result_json"]}) + "\n").encode())
        self.assertEqual(before[0]["archiveSourceRevision"], expected)
        self.assertNotEqual(before[0]["archiveSourceRevision"], after[0]["archiveSourceRevision"])
        self.assertEqual(before[1], after[1])

    def test_textbook_and_native_source_adapters_collect_precisely_bound_repairs(self):
        self.missing()
        self.exporter._textbook_sources(self.snapshot, self.input,
            {"textbookBinding": {"editionId": "book", "nodeId": "node"}})
        self.assertEqual(len(self.snapshot.operator_repair_bindings), 1)
        other = deepcopy(self.snapshot); other.operator_repair_bindings.clear()
        with patch.object(self.exporter, "_workbench_jobs", return_value=[]):
            self.exporter._native_authoring_sources(other, {"sessionId": self.session}, source_digest="a" * 64)
        self.assertEqual(len(other.operator_repair_bindings), 1)


if __name__ == "__main__":
    unittest.main()
