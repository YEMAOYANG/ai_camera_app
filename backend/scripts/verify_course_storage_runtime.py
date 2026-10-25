"""Recheck signed releases and fork private, unpublished remote-source candidates.

Run through tools/task_tmp.py. This command never publishes, saves a classroom,
or calls a provider. Select at most three explicit current content keys; newer
publication contracts are refused instead of being adapted to an older gate.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from content.textbook_catalog import canonical, digest, identifier
from content.textbook_operator_revision import VISUAL_PATCH_SCHEMA, sha_text
from content.textbook_release import MEDIA, validate_release
from core.config import AppConfig
from core.course_storage_config import CourseStorageConfig
from core.database import Database
from core.errors import ApiError
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
from repositories.course_storage_repository import CourseStorageRepository, storage_id_for
from repositories.textbook_repository import TextbookRepository
from services import course_file_store
from services.textbook_operator_revision_service import load_prepared, prepare_revision, read_parent
from services.textbook_preview_service import TextbookPreviewService
from services.textbook_publication_service import TextbookPublicationService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLASSROOMS = PROJECT_ROOT / "openmaic-runtime/.runtime/OpenMAIC/data/classrooms"
SHA = re.compile(r"[a-f0-9]{64}\Z")


class VerificationError(ValueError):
    pass


class ReadOnlyConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=()):
        if (not re.match(r"\s*SELECT\b", sql, re.I) or ";" in sql
                or re.search(r"\b(?:INTO\s+(?:OUTFILE|DUMPFILE)|FOR\s+(?:UPDATE|SHARE|NO\s+KEY\s+UPDATE|KEY\s+SHARE)"
                             r"|GET_LOCK|RELEASE_LOCK|pg_(?:try_)?advisory\w*|pg_sleep\w*)\b", sql, re.I)):
            raise VerificationError("course_verification_database_write_forbidden")
        return self.connection.execute(sql, params)

    def executescript(self, script):
        raise VerificationError("course_verification_database_write_forbidden")


class ReadOnlyDatabase:
    def __init__(self, database):
        self.database = database

    @contextmanager
    def transaction(self):
        with self.database.transaction() as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            yield ReadOnlyConnection(connection)


class ReadOnlyRuntime:
    def __init__(self, client, *, canonical_origin=None):
        self._client = client
        self.base_url = canonical_origin.rstrip("/") if canonical_origin else client.base_url
        self.read_url = client.base_url
        self.get_count = 0

    def get_classroom(self, classroom_id):
        self.get_count += 1
        return self._client.get_classroom(classroom_id)

    def __getattr__(self, name):
        raise VerificationError("course_verification_runtime_write_forbidden")


def runtime_read_url(value):
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            and not parsed.username and not parsed.password and parsed.path in {"", "/"}
            and not parsed.query and not parsed.fragment)
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise VerificationError("course_verification_runtime_read_url_invalid")
    return value.rstrip("/")


class TrackedRemoteStore:
    def __init__(self, store, project_root, temporary_root):
        self.store, self.config, self.repository = store, store.config, store.repository
        self.project_root, self.temporary_root = Path(project_root).resolve(), Path(temporary_root).resolve()
        self.remote_reads, self.remote_bytes, self.sources = 0, 0, set()
        self.unregistered_sources = set()
        self.failed_sources = set()

    def resolve(self, path, **kwargs):
        return self.store.resolve(path, **kwargs)

    def read_bytes(self, path, **kwargs):
        try:
            raw = self.store.read_bytes(path, **kwargs)
        except course_file_store.CourseFileStorageError:
            source = Path(path).resolve()
            if source.is_relative_to(self.project_root):
                self.failed_sources.add(source.relative_to(self.project_root).as_posix())
            raise
        if raw is None:
            if not Path(path).resolve().is_relative_to(self.temporary_root):
                source = Path(path).resolve()
                if source.is_relative_to(self.project_root):
                    self.unregistered_sources.add(source.relative_to(self.project_root).as_posix())
                raise VerificationError("course_verification_source_unregistered")
            return None  # Only the newly prepared private candidate may be local.
        self.remote_reads += 1
        self.remote_bytes += len(raw)
        self.sources.add(str(Path(path).resolve()))
        return raw


class ExistingMediaOnly:
    def __init__(self, store):
        self.store = store

    def read(self, path, **kwargs):
        raw = self.store.read_bytes(path, **kwargs)
        if raw is None:
            raise VerificationError("course_verification_new_delivery_forbidden")
        return raw


class ExistingDeliveryCopies:
    """Reuse the signed original encoder result, never synthesize a new copy."""
    def __init__(self, release, store):
        self.media, self.store = release["media"], store

    def __call__(self, suffix, raw):
        source_sha = hashlib.sha256(raw).hexdigest()
        matches = [item for item in self.media if item.get("sourceSha256", item["sha256"]) == source_sha]
        identities = {(item["sha256"], item["byteSize"], Path(item["path"]).suffix) for item in matches}
        if len(identities) != 1:
            raise VerificationError("course_verification_original_delivery_ambiguous")
        item = matches[0]
        media = MEDIA.fullmatch(item["path"])
        if media is None:
            raise VerificationError("course_verification_original_delivery_invalid")
        delivered = self.store.read_bytes(CLASSROOMS / media[1] / media[2], expected_sha256=item["sha256"],
            expected_bytes=item["byteSize"])
        if delivered is None:
            raise VerificationError("course_verification_original_delivery_unregistered")
        return Path(item["path"]).suffix, delivered


@contextmanager
def configured_store(store):
    """Inject the real, instrumented registry reader in this standalone process."""
    original = course_file_store.CourseFileStore
    course_file_store.CourseFileStore = lambda: store
    try:
        yield
    finally:
        course_file_store.CourseFileStore = original


def private_output(path, temporary_root):
    root = Path(temporary_root)
    if root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o077:
        raise VerificationError("course_verification_private_task_required")
    target = Path(path)
    if not target.resolve().is_relative_to(root.resolve()):
        raise VerificationError("course_verification_output_outside_task")
    for parent in (target, *target.parents):
        if parent.is_symlink():
            raise VerificationError("course_verification_output_symlink")
        if parent == root:
            break
    return target.resolve()


class WriteGuard:
    """Allow candidate artifacts and local serialization locks, never originals."""
    def __init__(self, output, classroom_root):
        self.output, self.classroom_root = Path(output).resolve(), Path(classroom_root).resolve()

    def check(self, event, args):
        if event == "urllib.Request" and args[3] not in {"GET", "HEAD"}:
            raise VerificationError("course_verification_http_write_forbidden")
        if event == "subprocess.Popen":
            raise VerificationError("course_verification_subprocess_forbidden")
        if event == "open":
            path, mode, flags = args
            if isinstance(path, int) or not ((flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
                return
            target = Path(path).resolve()
            lock = (target.name == "operator.lock" and target.parent.name == "textbook-preview-audio"
                    and target.is_relative_to(self.classroom_root) and mode == "a")
            if not target.is_relative_to(self.output) and not lock:
                raise VerificationError("course_verification_original_write_forbidden")
        if event in {"os.mkdir", "os.remove", "os.rmdir", "os.rename"}:
            paths = args[:2] if event == "os.rename" else args[:1]
            for path in paths:
                target = Path(path).resolve()
                source_lock_parent = (event == "os.mkdir" and target.is_relative_to(self.classroom_root)
                    and (target == self.classroom_root or len(target.relative_to(self.classroom_root).parts) <= 2))
                if not target.is_relative_to(self.output) and not source_lock_parent:
                    raise VerificationError("course_verification_original_write_forbidden")


def source_audit(registry, store, build, release, storage_id):
    scopes = registry.find_scopes(storage_id=storage_id, course_id=build["course_id"], course_version=build["course_version"])
    candidates = sorted({(f["sourcePath"], f["sha256"]) for scope in scopes for f in scope["bindings"]
        if Path(f["sourcePath"]).name in {"audit.json", "audio-audit.json"}})
    if not candidates or len(candidates) > 64:
        raise VerificationError("course_verification_audit_scope_missing_or_ambiguous")
    matches = []
    expected = release["audioAudit"]["sha256"]
    for path, checksum in candidates:
        head = store.resolve(PROJECT_ROOT / path)
        if head is None or head["sha256"] != checksum:
            continue  # Older immutable scope versions are not the current reader.
        raw = store.read_bytes(PROJECT_ROOT / path, expected_sha256=checksum, max_bytes=16 * 1024 * 1024)
        document = json.loads(raw)
        if document.get("sha256") == expected:
            matches.append((path, document))
    if not matches or len({digest(document) for _, document in matches}) != 1:
        raise VerificationError("course_verification_original_audit_not_found")
    return PROJECT_ROOT / matches[0][0], matches[0][1]


def visual_fork(parent, label):
    source = json.loads(parent["preview"]["classroom_json"])
    scene = next((s for s in source["scenes"] if s.get("type") == "interactive"
        and isinstance(s.get("content", {}).get("html"), str)), None)
    if scene is None:
        raise VerificationError("course_verification_interactive_source_required")
    if not identifier(label) or label == parent["build"]["teaching_revision"]:
        raise VerificationError("course_verification_revision_label_invalid")
    # A traceable, non-rendering candidate change; no new teaching claim/audio.
    html = scene["content"]["html"]
    patch = {"schemaVersion": VISUAL_PATCH_SCHEMA, "parentContentKey": parent["build"]["content_key"],
        "expectedSourceSha256": digest(source), "teachingRevision": label,
        "reviewer": "automated remote storage verification",
        "basis": "Private storage verification candidate only; no teaching approval or publication.", "changes": []}
    visual = {"schemaVersion": "mira.textbook.preview-visual-patch.v1", "expectedSourceSha256": digest(source),
        "reviewer": patch["reviewer"], "basis": patch["basis"], "changes": [{"sceneId": scene["id"],
            "beforeHtmlSha256": sha_text(html), "html": html + "\n<!-- mira storage verification candidate: " + label + " -->"}]}
    return patch, visual


def _snapshot(conn, build):
    frozen = json.loads(build["input_json"])
    result = {"build": conn.execute("SELECT * FROM learning_textbook_course_builds WHERE content_key=?",
        (build["content_key"],)).fetchone(), "preview": conn.execute(
        "SELECT * FROM learning_textbook_course_previews WHERE preview_key=?", (frozen["previewKey"],)).fetchone(),
        "course": conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=?",
        (build["course_id"], build["course_version"])).fetchone()}
    return hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def verify_one(service, registry, store, key, output, label, storage_id, *, progress=lambda phase: None, verify_revision=True):
    progress("current_release")
    with service.repository.transaction() as conn:
        build = service.repository.get_build(conn, key)
        if not build or build["status"] != "published":
            raise VerificationError("course_verification_current_release_required")
        directory = service.repository.get_revision(conn, build["edition_id"], build["revision_id"])
        course = conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=?",
            (build["course_id"], build["course_version"])).fetchone()
        if directory is None or course is None:
            raise VerificationError("course_verification_current_release_required")
        validate_release(build, service.repository.manifest(directory), course)
        before = _snapshot(conn, build)
    original_review = json.loads(build["review_json"])
    if original_review.get("schemaVersion") is not None:
        raise VerificationError("course_verification_publication_contract_unsupported")
    review = deepcopy(original_review)
    release = review["release"]
    progress("original_audit")
    audit_path, audit = source_audit(registry, store, build, release, storage_id)
    frozen = json.loads(build["input_json"])
    preview = service.get(frozen["previewKey"])
    source = json.loads(preview["classroom_json"])
    progress("native_snapshot")
    if service.runtime.get_classroom(source["id"]) != source:
        raise VerificationError("course_verification_native_snapshot_mismatch")
    start_reads, start_bytes = store.remote_reads, store.remote_bytes
    progress("publication_prepare")
    prepared = TextbookPublicationService(service, delivery_copy=ExistingDeliveryCopies(release, store),
        course_media_store=ExistingMediaOnly(store)).prepare(
        key=preview["preview_key"], edition=build["edition_id"], revision=build["revision_id"], node=build["node_id"],
        teaching_revision=build["teaching_revision"], review=review, audio_audit=audit, classroom_directory=CLASSROOMS,
        pronunciation_review=release["audioAudit"].get("pronunciationReview"),
        asr_reconciliation=release["audioAudit"].get("reconciliation"))
    if (prepared["frozen"] != frozen or prepared["release"] != release or review != original_review
            or prepared["course"]["id"] != build["course_id"]):
        raise VerificationError("course_verification_original_release_not_reproduced")
    if not verify_revision:
        with service.repository.transaction() as conn:
            if _snapshot(conn, build) != before:
                raise VerificationError('course_verification_business_records_changed')
        return {'ok': True, 'contentKey': key, 'title': release['classroom']['stage']['name'],
            'releaseSha256': release['sha256'], 'originalReviewSha256': digest(original_review),
            'publicationReproduced': True, 'revisionPrepared': False,
            'remoteReads': store.remote_reads - start_reads, 'remoteReadBytes': store.remote_bytes - start_bytes,
            'runtimeReadUrl': service.runtime.read_url, 'businessRecordsUnchanged': True,
            'providerCalls': 0, 'savedOrPublished': False}
    progress("read_parent")
    with service.repository.transaction() as conn:
        parent, files = read_parent(service, key, audit_path, CLASSROOMS, conn,
            allow_saved_preview=True, allow_visual_ancestry=True)
    patch, visual = visual_fork(parent, label + "-" + key[:8])
    candidate_directory = output / key[:16]
    progress("revision_prepare")
    intent = prepare_revision(service, key, CLASSROOMS, patch, audit_path, candidate_directory, visual_patch=visual)
    progress("candidate_assets")
    _, candidate, _, loaded = load_prepared(candidate_directory, verify_assets=True)
    if loaded["sha256"] != intent["sha256"] or candidate["changedSegments"]:
        raise VerificationError("course_verification_unexpected_candidate_audio_change")
    with service.repository.transaction() as conn:
        if _snapshot(conn, build) != before:
            raise VerificationError("course_verification_business_records_changed")
    return {"ok": True, "contentKey": key, "title": release["classroom"]["stage"]["name"],
        "releaseSha256": release["sha256"], "originalReviewSha256": digest(original_review),
        "sourceAuditPath": str(audit_path.relative_to(PROJECT_ROOT)), "sourceAuditSha256": audit["sha256"],
        "candidateDirectory": str(candidate_directory), "candidateProofSha256": intent["sha256"],
        "parentEvidenceFiles": len(files), "inheritedSpeechCount": intent["inheritedSpeechCount"],
        "remoteReads": store.remote_reads - start_reads, "remoteReadBytes": store.remote_bytes - start_bytes,
        "runtimeReadUrl": service.runtime.read_url, "canonicalRuntimeOrigin": service.runtime.base_url,
        "businessRecordsUnchanged": True, "providerCalls": 0, "savedOrPublished": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content-key", action="append", required=True, help="Explicit published key; repeat at most three times")
    parser.add_argument("--output", type=Path, help="Candidate directory within MIRA_TASK_TMPDIR")
    parser.add_argument("--revision-label", default="storage-proof")
    parser.add_argument("--runtime-read-url",
        help="Loopback HTTP read replica, retaining the original frozen runtime identity")
    parser.add_argument('--publication-only', action='store_true',
        help='Verify exact original review/publication without invoking a separate revision contract')
    args = parser.parse_args()
    try:
        if not 1 <= len(args.content_key) <= 3 or len(set(args.content_key)) != len(args.content_key) or any(not SHA.fullmatch(k) for k in args.content_key):
            raise VerificationError("course_verification_selection_invalid")
        if not identifier(args.revision_label) or len(args.revision_label) > 60:
            raise VerificationError("course_verification_revision_label_invalid")
        task = os.environ.get("MIRA_TASK_TMPDIR")
        if not task:
            raise VerificationError("course_verification_private_task_required")
        output = private_output(args.output or Path(task) / "candidates", task)
        config, storage = AppConfig.from_env(), CourseStorageConfig.from_env()
        if storage.mode != "registry":
            raise VerificationError("course_verification_registry_mode_required")
        read_url = runtime_read_url(args.runtime_read_url) if args.runtime_read_url else config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL
        database = ReadOnlyDatabase(Database(config.DATABASE_URL))
        registry = CourseStorageRepository(database)
        store = TrackedRemoteStore(course_file_store.CourseFileStore(config=storage, project_root=PROJECT_ROOT,
            repository=registry), PROJECT_ROOT, Path(task).resolve())
        runtime = ReadOnlyRuntime(OpenMaicFullRuntimeClient(read_url,
            formal_audio_internal_token=config.INTERNAL_API_TOKEN), canonical_origin=config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL)
        service = TextbookPreviewService(TextbookRepository(database), runtime)
        output.mkdir(mode=0o700, parents=True, exist_ok=True)
        sys.addaudithook(WriteGuard(output, CLASSROOMS).check)
        results = []
        with configured_store(store):
            for key in args.content_key:
                phase = {"name": "setup"}
                missing_before = set(store.unregistered_sources)
                failed_before = set(store.failed_sources)
                try:
                    result = verify_one(service, registry, store, key, output, args.revision_label,
                        storage_id_for(storage.endpoint, storage.bucket, storage.region),
                        progress=lambda name: phase.update(name=name), verify_revision=not args.publication_only)
                except Exception as error:
                    code = str(error) if isinstance(error, VerificationError) else getattr(error, "code", "")
                    result = {"ok": False, "contentKey": key, "errorType": type(error).__name__,
                        "phase": phase["name"],
                        "errorCode": code if re.fullmatch(r"[a-z0-9_]+", code or "") else "course_verification_failed"}
                    if isinstance(error, ApiError):
                        result["message"] = error.message
                    missing = sorted(store.unregistered_sources - missing_before)
                    if missing:
                        result["unregisteredSources"] = missing[:8]
                    failed = sorted(store.failed_sources - failed_before)
                    if failed:
                        result["remoteFailureSources"] = failed[:8]
                results.append(result)
                print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0 if all(r["ok"] for r in results) else 1
    except Exception as error:
        code = str(error) if isinstance(error, VerificationError) else "course_verification_setup_failed"
        print(json.dumps({"ok": False, "errorType": type(error).__name__, "errorCode": code}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
