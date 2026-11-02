"""Durable bounded queue for reviewed v4 textbook workbench drafts.

The queue is deliberately a thin coordinator around
``TextbookWorkbenchAuthoring``.  It freezes exact reviewed draft bytes, calls
the existing single-course ``prepare`` implementation, and never creates a
workbench session except from :meth:`start_bounded`.  Per-course authoring
jobs remain the source of truth for dispatch identity and recovery.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
from http.cookiejar import DefaultCookiePolicy, MozillaCookieJar
import json
import os
from pathlib import Path
import re
import stat
from urllib.request import HTTPCookieProcessor, ProxyHandler, build_opener

from content.textbook_catalog import digest, identifier
from integrations.openmaic_workbench_client import (
    OpenMaicWorkbenchClient, WorkbenchError, _NoRedirect, local_origin, private_write,
)
from services.course_file_store import course_bytes, course_exists, course_glob, course_text
from services.textbook_batch_generation_service import atomic_json
from services.textbook_workbench_authoring import sha, timestamp, validate_draft


REQUEST_SCHEMA = "mira.operator.workbench-batch-request.v1"
BATCH_SCHEMA = "mira.operator.workbench-batch.v1"
PREPARED_SCHEMA = "mira.operator.workbench-batch-prepared-entry.v1"
HOLD_SCHEMA = "mira.operator.workbench-batch-hold.v1"
MAX_CONCURRENT_AUTHOR_SESSIONS = 2
MAX_BATCH_ENTRIES = 200
_BATCH_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_TERMINAL_SESSION_STATES = frozenset({"succeeded", "failed", "cancelled", "canceled"})


class _ReadOnlyWorkbenchClient(OpenMaicWorkbenchClient):
    """Use the original owner for GETs without chmod or cookie persistence."""

    def __init__(self, origin, cookie_path, *, timeout=20):
        self.origin = local_origin(origin)
        self.cookie_path = Path(cookie_path)
        self.timeout = timeout
        self.scene_contract_schema = None
        self.material_groups_schema = None
        if self.cookie_path.is_symlink() or not self.cookie_path.is_file():
            raise WorkbenchError("owner_cookie_invalid", "原会话身份文件不可读")
        self.jar = MozillaCookieJar(policy=DefaultCookiePolicy(secure_protocols=("https", "http")))
        self.jar.load(str(self.cookie_path), ignore_discard=True, ignore_expires=True)
        self.opener = build_opener(ProxyHandler({}), _NoRedirect(), HTTPCookieProcessor(self.jar))

    def _save_owner(self):
        self.owner_fingerprint()

    def _open(self, path, payload=None, *, raw=None, headers=None):
        if payload is not None or raw is not None:
            raise WorkbenchError("read_only_client", "只读核验禁止提交请求")
        return super()._open(path, headers=headers)


def _json_object(path: Path) -> dict:
    try:
        value = json.loads(course_text(path))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError("workbench_batch_document_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("workbench_batch_document_invalid")
    return value


def _immutable_bytes(path: Path, raw: bytes) -> None:
    if path.is_symlink():
        raise ValueError("workbench_batch_snapshot_symlink_forbidden")
    if course_exists(path):
        if course_bytes(path) != raw:
            raise ValueError("workbench_batch_snapshot_changed")
        return
    private_write(path, raw)


def _safe_error(exc: Exception) -> dict:
    if isinstance(exc, WorkbenchError):
        return {"error": exc.code, "message": str(exc)}
    return {"error": "workbench_batch_entry_failed", "errorType": type(exc).__name__}


class TextbookWorkbenchBatch:
    """Freeze and operate a bounded set of exact single-course authoring jobs."""

    def __init__(self, directory, authoring=None):
        # Keep the final component unresolved so a caller cannot hide a queue
        # directory symlink behind ``resolve`` before the lock check.
        self.directory = Path(directory).absolute()
        self.authoring = authoring

    @contextmanager
    def _locked(self, *, create=False):
        if self.directory.is_symlink():
            raise ValueError("workbench_batch_directory_symlink_forbidden")
        if create:
            self.directory.mkdir(parents=True, mode=0o700, exist_ok=True)
            os.chmod(self.directory, 0o700)
        if (not self.directory.is_dir()
                or stat.S_IMODE(self.directory.stat().st_mode) != 0o700):
            raise ValueError("workbench_batch_not_initialized")
        lock = self.directory / ".batch.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        except OSError as exc:
            raise ValueError("workbench_batch_lock_invalid") from exc
        with os.fdopen(fd, "a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("workbench_batch_operator_already_running") from exc
            yield

    @contextmanager
    def _dispatch_locked(self):
        """Serialize slot admission across every batch sharing an output root.

        The stable lock file must never be unlinked on release: another process
        may already have opened that inode. Nonblocking admission avoids a lock
        cycle with a different batch or a single-course authoring operation.
        """
        output_root = getattr(self.authoring, "output_root", None)
        if output_root is None:
            raise ValueError("workbench_batch_authoring_output_root_required")
        root = Path(output_root).absolute()
        root_fd = lock_fd = None
        acquired = False
        try:
            root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            root_info = os.fstat(root_fd)
            if not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.getuid():
                raise ValueError("workbench_batch_dispatch_root_invalid")
            name = ".workbench-dispatch.lock"
            lock_fd = os.open(name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                              0o600, dir_fd=root_fd)
            info = os.fstat(lock_fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600):
                raise ValueError("workbench_batch_dispatch_lock_invalid")
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("workbench_batch_dispatch_operator_already_running") from exc
            current = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            if (not stat.S_ISREG(current.st_mode)
                    or (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino)):
                raise ValueError("workbench_batch_dispatch_lock_invalid")
            acquired = True
            yield
        except OSError as exc:
            if acquired:
                raise
            raise ValueError("workbench_batch_dispatch_lock_invalid") from exc
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
            if root_fd is not None:
                os.close(root_fd)

    def _entry_folder(self, entry_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{64}", str(entry_id)):
            raise ValueError("workbench_batch_entry_id_invalid")
        return self.directory / "entries" / entry_id

    def _validate_entry_folder(self, folder: Path) -> None:
        entries = self.directory / "entries"
        if (entries.is_symlink() or not entries.is_dir()
                or stat.S_IMODE(entries.stat().st_mode) != 0o700
                or not entries.resolve().is_relative_to(self.directory.resolve())):
            raise ValueError("workbench_batch_entries_directory_invalid")
        if (folder.is_symlink() or not folder.is_dir()
                or stat.S_IMODE(folder.stat().st_mode) != 0o700
                or not folder.resolve().is_relative_to(entries.resolve())):
            raise ValueError("workbench_batch_entry_directory_invalid")

    @staticmethod
    def _request(path: Path) -> tuple[bytes, dict]:
        try:
            if path.is_symlink():
                raise ValueError()
            raw = path.read_bytes()
            value = json.loads(raw)
        except (OSError, ValueError, UnicodeError) as exc:
            raise ValueError("workbench_batch_request_invalid") from exc
        allowed = {"schemaVersion", "batchId", "scope", "maximumConcurrentAuthorSessions", "entries"}
        if (not isinstance(value, dict) or set(value) != allowed
                or value.get("schemaVersion") != REQUEST_SCHEMA
                or not _BATCH_ID.fullmatch(str(value.get("batchId", "")))
                or not isinstance(value.get("scope"), dict) or not value["scope"]
                or value.get("maximumConcurrentAuthorSessions") != MAX_CONCURRENT_AUTHOR_SESSIONS
                or not isinstance(value.get("entries"), list)
                or not 1 <= len(value["entries"]) <= MAX_BATCH_ENTRIES):
            raise ValueError("workbench_batch_request_invalid")
        return raw, value

    @staticmethod
    def _resolve_draft(request_path: Path, row: dict, scope: dict) -> dict:
        if (not isinstance(row, dict) or set(row) != {"draftPath", "teachingRevision"}
                or not isinstance(row.get("draftPath"), str) or not row["draftPath"].strip()
                or not identifier(str(row.get("teachingRevision", "")))):
            raise ValueError("workbench_batch_entry_invalid")
        source = Path(row["draftPath"])
        if not source.is_absolute():
            source = request_path.parent / source
        if source.is_symlink():
            raise ValueError("workbench_batch_draft_symlink_forbidden")
        source = source.resolve()
        try:
            raw = source.read_bytes()
            draft = json.loads(raw)
        except (OSError, ValueError, UnicodeError) as exc:
            raise ValueError("workbench_batch_draft_invalid") from exc
        binding = validate_draft(draft)
        if not set(scope).issubset(binding):
            raise ValueError("workbench_batch_scope_key_invalid")
        for key, expected in scope.items():
            if binding[key] != expected:
                raise ValueError("workbench_batch_scope_mismatch")
        revision = str(row["teachingRevision"])
        if binding.get("teachingRevision", revision) != revision:
            raise ValueError("workbench_batch_teaching_revision_mismatch")
        identity = {"binding": binding, "teachingRevision": revision}
        return {"entryId": digest(identity), "binding": binding, "teachingRevision": revision,
                "sourceDraftPath": str(source), "draftSha256": sha(raw), "draftBytes": raw}

    def initialize(self, request_path) -> dict:
        request_path = Path(request_path).absolute()
        request_raw, request = self._request(request_path)
        rows = [self._resolve_draft(request_path, row, request["scope"]) for row in request["entries"]]
        if len({row["entryId"] for row in rows}) != len(rows):
            raise ValueError("workbench_batch_duplicate_entry")
        job_keys = [(row["binding"]["editionId"], row["binding"]["nodeId"], row["teachingRevision"])
                    for row in rows]
        if len(set(job_keys)) != len(job_keys):
            raise ValueError("workbench_batch_duplicate_job_path")
        frozen_entries = [{key: row[key] for key in (
            "entryId", "binding", "teachingRevision", "sourceDraftPath", "draftSha256")}
            for row in rows]
        with self._locked(create=True):
            existing_path = self.directory / "batch.json"
            if course_exists(existing_path):
                manifest = self._manifest()
                if (manifest["requestSha256"] != sha(request_raw)
                        or manifest["entries"] != frozen_entries):
                    raise ValueError("workbench_batch_already_initialized_differently")
                return self._status_locked(manifest, poll=False)
            request_snapshot = self.directory / "request.json"
            _immutable_bytes(request_snapshot, request_raw)
            entries_folder = self.directory / "entries"
            if entries_folder.is_symlink() or (entries_folder.exists() and not entries_folder.is_dir()):
                raise ValueError("workbench_batch_entries_directory_invalid")
            entries_folder.mkdir(mode=0o700, exist_ok=True)
            os.chmod(entries_folder, 0o700)
            if not entries_folder.resolve().is_relative_to(self.directory.resolve()):
                raise ValueError("workbench_batch_entries_directory_invalid")
            for row in rows:
                folder = self._entry_folder(row["entryId"])
                if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
                    raise ValueError("workbench_batch_entry_directory_invalid")
                folder.mkdir(mode=0o700, exist_ok=True)
                os.chmod(folder, 0o700)
                self._validate_entry_folder(folder)
                _immutable_bytes(folder / "draft.json", row["draftBytes"])
            manifest = {"schemaVersion": BATCH_SCHEMA, "batchId": request["batchId"],
                        "scope": request["scope"],
                        "maximumConcurrentAuthorSessions": MAX_CONCURRENT_AUTHOR_SESSIONS,
                        "entries": frozen_entries, "requestSha256": sha(request_raw),
                        "createdAt": timestamp(), "publicationAllowed": False,
                        "studentDeliveryAllowed": False}
            manifest["batchSha256"] = digest(manifest)
            atomic_json(existing_path, manifest, immutable=True)
            return self._status_locked(manifest, poll=False)

    def _manifest(self) -> dict:
        if ((self.directory / "batch.json").is_symlink()
                or (self.directory / "request.json").is_symlink()):
            raise ValueError("workbench_batch_snapshot_symlink_forbidden")
        manifest = _json_object(self.directory / "batch.json")
        manifest_fields = {"schemaVersion", "batchId", "scope", "maximumConcurrentAuthorSessions",
                           "entries", "requestSha256", "createdAt", "publicationAllowed",
                           "studentDeliveryAllowed", "batchSha256"}
        expected = digest({key: value for key, value in manifest.items() if key != "batchSha256"})
        if (set(manifest) != manifest_fields or manifest.get("schemaVersion") != BATCH_SCHEMA
                or manifest.get("batchSha256") != expected
                or manifest.get("maximumConcurrentAuthorSessions") != MAX_CONCURRENT_AUTHOR_SESSIONS
                or manifest.get("publicationAllowed") is not False
                or manifest.get("studentDeliveryAllowed") is not False
                or not isinstance(manifest.get("entries"), list)
                or not 1 <= len(manifest["entries"]) <= MAX_BATCH_ENTRIES):
            raise ValueError("workbench_batch_manifest_integrity_failed")
        if sha(course_bytes(self.directory / "request.json")) != manifest.get("requestSha256"):
            raise ValueError("workbench_batch_request_snapshot_changed")
        seen = set()
        for row in manifest["entries"]:
            entry_fields = {"entryId", "binding", "teachingRevision", "sourceDraftPath", "draftSha256"}
            if not isinstance(row, dict) or set(row) != entry_fields:
                raise ValueError("workbench_batch_entry_integrity_failed")
            entry_id = row.get("entryId")
            if entry_id in seen or digest({"binding": row.get("binding"),
                                           "teachingRevision": row.get("teachingRevision")}) != entry_id:
                raise ValueError("workbench_batch_entry_integrity_failed")
            seen.add(entry_id)
            folder = self._entry_folder(entry_id)
            self._validate_entry_folder(folder)
            draft = folder / "draft.json"
            if draft.is_symlink() or sha(course_bytes(draft)) != row.get("draftSha256"):
                raise ValueError("workbench_batch_draft_snapshot_changed")
            try:
                if stat.S_IMODE(draft.stat().st_mode) != 0o600:
                    raise ValueError()
                snapshot = json.loads(course_text(draft))
                binding = validate_draft(snapshot, check_current_teacher=False)
            except (OSError, ValueError, UnicodeError):
                raise ValueError("workbench_batch_draft_snapshot_changed") from None
            if (binding != row.get("binding")
                    or binding.get("teachingRevision", row.get("teachingRevision"))
                    != row.get("teachingRevision")):
                raise ValueError("workbench_batch_draft_binding_changed")
        return manifest

    def _prepared(self, row: dict, manifest: dict) -> dict | None:
        path = self._entry_folder(row["entryId"]) / "prepared.json"
        if not course_exists(path):
            return None
        if path.is_symlink():
            raise ValueError("workbench_batch_prepared_entry_integrity_failed")
        value = _json_object(path)
        fields = {"schemaVersion", "batchSha256", "entryId", "draftSha256", "teachingRevision",
                  "authoringOutputRoot", "jobDirectory", "preparedAt", "sha256"}
        body = {key: field for key, field in value.items() if key != "sha256"}
        if (set(value) != fields or value.get("schemaVersion") != PREPARED_SCHEMA
                or value.get("sha256") != digest(body)
                or value.get("batchSha256") != manifest["batchSha256"]
                or value.get("entryId") != row["entryId"]
                or value.get("draftSha256") != row["draftSha256"]
                or value.get("teachingRevision") != row["teachingRevision"]
                or not isinstance(value.get("jobDirectory"), str)
                or not isinstance(value.get("authoringOutputRoot"), str)):
            raise ValueError("workbench_batch_prepared_entry_integrity_failed")
        root = Path(value["authoringOutputRoot"]).resolve()
        job = Path(value["jobDirectory"]).resolve()
        expected = (root / row["binding"]["editionId"] / row["binding"]["nodeId"]
                    / ("teaching-" + row["teachingRevision"]) / "authoring-job")
        if job != expected or not job.is_relative_to(root):
            raise ValueError("workbench_batch_prepared_entry_path_invalid")
        if self.authoring is not None:
            active_root = Path(getattr(self.authoring, "output_root", "")).resolve()
            if active_root != root:
                raise ValueError("workbench_batch_prepared_entry_path_invalid")
        return value

    def _hold(self, row: dict, manifest: dict) -> dict | None:
        path = self._entry_folder(row["entryId"]) / "hold.json"
        if not course_exists(path):
            return None
        if path.is_symlink():
            raise ValueError("workbench_batch_hold_integrity_failed")
        value = _json_object(path)
        fields = {"schemaVersion", "batchSha256", "entryId", "draftSha256", "reason",
                  "createdAt", "publicationAllowed", "sha256"}
        body = {key: field for key, field in value.items() if key != "sha256"}
        if (set(value) != fields or value.get("schemaVersion") != HOLD_SCHEMA
                or value.get("sha256") != digest(body)
                or value.get("batchSha256") != manifest["batchSha256"]
                or value.get("entryId") != row["entryId"]
                or value.get("draftSha256") != row["draftSha256"]
                or value.get("publicationAllowed") is not False
                or not isinstance(value.get("reason"), str) or not value["reason"].strip()):
            raise ValueError("workbench_batch_hold_integrity_failed")
        return value

    @staticmethod
    def _compact(row: dict, result: dict) -> dict:
        allowed = ("status", "jobDirectory", "sessionId", "sessionStatus", "savedStages", "error",
                   "httpStatus", "message", "existingArtifacts", "materialsStatus", "materialCount",
                   "reviewHold")
        return {"entryId": row["entryId"], "binding": row["binding"],
                "teachingRevision": row["teachingRevision"],
                **{key: result[key] for key in allowed if key in result}}

    @staticmethod
    def _occupies(result: dict) -> bool:
        status = str(result.get("status", ""))
        if status in {"dispatch_unknown", "session_found"}:
            return True
        if status.startswith("session_"):
            return status.removeprefix("session_") not in _TERMINAL_SESSION_STATES
        return False

    @staticmethod
    def _entry_dispatch_blocker(result: dict) -> str | None:
        """Return one safe fail-closed reason for automatic wave dispatch."""
        if result.get("held") or result.get("status") == "held":
            return None
        status = str(result.get("status") or "unknown")
        if result.get("httpStatus") == 402:
            return "provider_payment_required"
        if result.get("reviewHold"):
            return "review_hold_active"
        if result.get("existingArtifacts"):
            return "reuse_review_required"
        if status == "pending":
            return "preparation_required"
        if status == "dispatch_unknown":
            return "dispatch_reconciliation_required"
        if status == "preparation_blocked":
            return "preparation_blocked"
        if status in {"operator_error", "reuse_review_required"}:
            return "operator_reconciliation_required"
        if status in {"session_failed", "session_cancelled", "session_canceled"}:
            return "generation_failed"
        if status == "session_succeeded":
            return "saved_stage_missing"
        if result.get("error"):
            return "operator_reconciliation_required"
        if result.get("materialsStatus") not in {None, "ready"}:
            return "material_preparation_required"
        if status in {"prepared", "prepared_snapshot"} and result.get("sessionId"):
            return "prepared_session_identity_conflict"
        if status == "saved_stage_available":
            stages = result.get("savedStages")
            return None if isinstance(stages, list) and stages else "saved_stage_missing"
        if status not in {"prepared", "prepared_snapshot", "session_queued", "session_running"}:
            return "unexpected_authoring_state"
        return None

    @classmethod
    def _strict_dispatch_blockers(cls, results: list[dict], global_occupied: list[dict]) -> list[dict]:
        blockers = []
        for result in results:
            reason = cls._entry_dispatch_blocker(result)
            if reason:
                blockers.append({"scope": "batch_entry", "entryId": result.get("entryId"),
                                 "status": str(result.get("status") or "unknown"), "reason": reason})
        for row in global_occupied:
            if row.get("source") != "output_root":
                continue
            status = str(row.get("status") or "unknown")
            if row.get("reconciliationRequired") or status not in {"session_queued", "session_running"}:
                blockers.append({"scope": "external_authoring", "status": (
                    status if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", status) else "unknown"),
                    "reason": "external_dispatch_reconciliation_required"})
        return blockers

    @staticmethod
    def _saved_job_occupies(job: Path, state: dict | None) -> bool:
        """Conservatively classify any saved job, including outside this batch."""
        if not isinstance(state, dict):
            return True
        try:
            marker = course_exists(job / "dispatch.json")
        except Exception:
            # Registry unavailability cannot turn an unresolved paid intent
            # into a free author slot, even if the local original is gone.
            return True
        status = str(state.get("status", ""))
        if status in {"saved_stage_available", "session_succeeded", "session_failed",
                      "session_cancelled", "session_canceled"}:
            return False
        if status in {"dispatch_unknown", "session_found"}:
            return True
        if status.startswith("session_"):
            return status.removeprefix("session_") not in _TERMINAL_SESSION_STATES
        # A marker or session identity with an unrecognised/non-terminal state
        # is an unresolved dispatch and must consume capacity.
        if status in {"prepared", "reuse_review_required"}:
            return bool(marker or state.get("sessionId"))
        return True

    def _verified_external_terminal(self, job: Path, observed: dict) -> bool:
        """Prove an old dispatch terminal without changing its archived evidence."""
        try:
            if (observed.get("status") not in {"session_running", "session_queued"}
                    or not observed.get("sessionId") or observed.get("error")
                    or observed.get("httpStatus") or observed.get("existingArtifacts")):
                return False
            frozen, draft, state = self.authoring._load(job)
            if state != observed:
                return False
            _, dispatched = self.authoring._material_payload(job, frozen, draft)
            marker = _json_object(job / "dispatch.json")
            client = _ReadOnlyWorkbenchClient(self.authoring.origin, job / "owner.cookies")
            owner = client.owner_fingerprint()
            if (marker.get("action") not in {"single_post_intent", "reuse_existing_session"}
                    or marker.get("requestSha256") != dispatched["requestSha256"]
                    or marker.get("payloadSha256") != dispatched["payloadSha256"]
                    or marker.get("materialsSha256") != dispatched.get("materialsSha256")
                    or marker.get("ownerFingerprint") != owner
                    or (dispatched.get("materialsOwnerFingerprint") is not None
                        and dispatched["materialsOwnerFingerprint"] != owner)):
                return False
            # _recover checks exact session id, full prompt digest and skill;
            # where present it also checks the live opening material bindings.
            session = self.authoring._recover(client, dispatched, state)
            return session.get("status") in {"succeeded", "failed", "cancelled"}
        except Exception:
            # Missing, changed, unreadable or unreachable evidence is never a
            # reason to free a slot or to issue a replacement request.
            return False

    def _global_occupied_jobs(self, results: list[dict]) -> list[dict]:
        if self.authoring is None or not hasattr(self.authoring, "output_root"):
            # Tests and alternate callers without a declared root cannot prove
            # external capacity.  Their explicit per-batch results remain the
            # conservative source of occupied slots.
            return [{"jobDirectory": result.get("jobDirectory"), "status": result.get("status"),
                     "reconciliationRequired": bool(
                         result.get("error") or result.get("httpStatus") == 402)}
                    for result in results if self._occupies(result)]
        root = Path(self.authoring.output_root).resolve()
        occupied = {}
        current_jobs = {str(Path(result["jobDirectory"]).resolve()) for result in results
                        if result.get("jobDirectory")}
        for result in results:
            if self._occupies(result) and result.get("jobDirectory"):
                occupied[str(Path(result["jobDirectory"]).resolve())] = {
                    "jobDirectory": str(Path(result["jobDirectory"]).resolve()),
                    "status": result.get("status"), "source": "current_batch",
                    "reconciliationRequired": bool(
                        result.get("error") or result.get("httpStatus") == 402)}
        try:
            jobs = ({path.parent for path in course_glob(root, "state.json", recursive=True)}
                    | {path.parent for path in course_glob(root, "dispatch.json", recursive=True)})
        except Exception:
            # An incomplete inventory cannot prove spare capacity. Keep raw
            # storage/database errors out of the operator response.
            raise ValueError("workbench_batch_authoring_inventory_unavailable") from None
        for job in jobs:
            resolved = job.absolute()
            state_path = job / "state.json"
            try:
                resolved = job.resolve()
                if job.name != "authoring-job" or not resolved.is_relative_to(root):
                    continue
                state = (None if state_path.is_symlink() or not course_exists(state_path)
                         else json.loads(course_text(state_path)))
                if not isinstance(state, dict):
                    state = None
            except Exception:
                # An unreadable job with a dispatch marker is unresolved.  Do
                # not leak the raw parser/OS exception into aggregate output.
                state = None
            if self._saved_job_occupies(resolved, state):
                previous = occupied.get(str(resolved), {})
                if (str(resolved) not in current_jobs and isinstance(state, dict)
                        and self._verified_external_terminal(resolved, state)):
                    continue
                occupied[str(resolved)] = {"jobDirectory": str(resolved),
                                           "status": (state or {}).get("status", "unreadable_unknown"),
                                           "reconciliationRequired": bool(
                                               previous.get("reconciliationRequired")
                                               or state is None or state.get("error")
                                               or state.get("httpStatus") == 402
                                               or state.get("existingArtifacts")),
                                           "source": ("current_batch" if previous
                                                      else "output_root")}
        return sorted(occupied.values(), key=lambda row: row["jobDirectory"])

    def _observe(self, row: dict, manifest: dict, *, poll: bool) -> dict:
        hold = self._hold(row, manifest)
        prepared = self._prepared(row, manifest)
        if prepared is None:
            result = {"entryId": row["entryId"], "binding": row["binding"],
                      "teachingRevision": row["teachingRevision"],
                      "status": "held" if hold else "pending"}
        elif not poll:
            result = {"entryId": row["entryId"], "binding": row["binding"],
                      "teachingRevision": row["teachingRevision"],
                      "jobDirectory": prepared["jobDirectory"], "status": "prepared_snapshot"}
        elif self.authoring is None:
            raise ValueError("workbench_batch_authoring_service_required")
        else:
            try:
                result = self._compact(row, self.authoring.run(Path(prepared["jobDirectory"]), start=False))
            except Exception as exc:
                # If the single-course dispatch marker exists, uncertainty must
                # continue to occupy a slot and can only be reconciled by GET.
                dispatched = course_exists(Path(prepared["jobDirectory"]) / "dispatch.json")
                result = {"entryId": row["entryId"], "binding": row["binding"],
                          "teachingRevision": row["teachingRevision"],
                          "jobDirectory": prepared["jobDirectory"],
                          "status": "dispatch_unknown" if dispatched else "operator_error",
                          **_safe_error(exc)}
        if hold is not None:
            result["held"] = True
            result["holdReason"] = hold["reason"]
        return result

    @staticmethod
    def _summary(manifest: dict, results: list[dict], *, global_occupied: list[dict] | None = None) -> dict:
        counts = {}
        for result in results:
            status = result.get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1
        occupied_status_counts = {}
        external_occupied_status_counts = {}
        for row in global_occupied or []:
            status = str(row.get("status") or "unknown")
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", status):
                status = "unknown"
            occupied_status_counts[status] = occupied_status_counts.get(status, 0) + 1
            if row.get("source") == "output_root":
                external_occupied_status_counts[status] = external_occupied_status_counts.get(status, 0) + 1
        occupied = (len(global_occupied) if global_occupied is not None
                    else sum(TextbookWorkbenchBatch._occupies(result) for result in results))
        dispatch_blockers = TextbookWorkbenchBatch._strict_dispatch_blockers(
            results, global_occupied or [])
        return {"schemaVersion": BATCH_SCHEMA, "batchId": manifest["batchId"],
                "batchSha256": manifest["batchSha256"], "scope": manifest["scope"],
                "entryCount": len(results), "statusCounts": counts,
                "occupiedAuthorSessions": occupied,
                "occupiedAuthorSessionStatusCounts": occupied_status_counts,
                "externalOccupiedAuthorSessions": sum(
                    row.get("source") == "output_root" for row in (global_occupied or [])),
                "externalOccupiedAuthorSessionStatusCounts": external_occupied_status_counts,
                "maximumConcurrentAuthorSessions": MAX_CONCURRENT_AUTHOR_SESSIONS,
                "newSessionCreationAllowedOnlyBy": "start-bounded",
                "dispatchBlockerCount": len(dispatch_blockers),
                "dispatchBlockers": dispatch_blockers,
                "generatedDraftsAreReviewed": False,
                "audioCompleted": False,
                "publicationAllowed": False, "studentDeliveryAllowed": False,
                "entries": results, "updatedAt": timestamp()}

    def _status_locked(self, manifest: dict, *, poll: bool = True) -> dict:
        results = [self._observe(row, manifest, poll=poll) for row in manifest["entries"]]
        occupied = self._global_occupied_jobs(results) if poll else None
        summary = self._summary(manifest, results, global_occupied=occupied)
        atomic_json(self.directory / "latest-summary.json", summary)
        return summary

    def prepare(self, *, limit=8) -> dict:
        if not 1 <= limit <= MAX_BATCH_ENTRIES:
            raise ValueError("workbench_batch_prepare_limit_invalid")
        if self.authoring is None:
            raise ValueError("workbench_batch_authoring_service_required")
        with self._locked():
            manifest = self._manifest()
            attempts = []
            for row in manifest["entries"]:
                if len(attempts) >= limit:
                    break
                if self._prepared(row, manifest) is not None or self._hold(row, manifest) is not None:
                    continue
                folder = self._entry_folder(row["entryId"])
                try:
                    result = self.authoring.prepare(folder / "draft.json",
                                                    teaching_revision=row["teachingRevision"])
                    output_root = getattr(self.authoring, "output_root", None)
                    if output_root is None:
                        raise ValueError("workbench_batch_authoring_output_root_required")
                    record = {"schemaVersion": PREPARED_SCHEMA,
                              "batchSha256": manifest["batchSha256"],
                              "entryId": row["entryId"], "draftSha256": row["draftSha256"],
                              "teachingRevision": row["teachingRevision"],
                              "authoringOutputRoot": str(Path(output_root).resolve()),
                              "jobDirectory": result["jobDirectory"], "preparedAt": timestamp()}
                    record["sha256"] = digest(record)
                    atomic_json(folder / "prepared.json", record, immutable=True)
                    attempts.append(self._compact(row, result))
                except Exception as exc:
                    error = {"entryId": row["entryId"], "status": "preparation_blocked",
                             "observedAt": timestamp(), **_safe_error(exc)}
                    atomic_json(folder / "last-prepare-error.json", error)
                    attempts.append({"entryId": row["entryId"], "binding": row["binding"],
                                     "teachingRevision": row["teachingRevision"], **error})
            return {"attempts": attempts, "summary": self._status_locked(manifest, poll=False),
                    "providerCalls": 0, "publicationAllowed": False}

    def status(self) -> dict:
        with self._locked():
            return self._status_locked(self._manifest(), poll=True)

    def start_bounded(self, *, max_starts: int, confirm_batch_sha256: str,
                      stop_on_blockers: bool = False) -> dict:
        """Poll all jobs, then make at most two explicit new-session attempts."""
        if not 0 <= max_starts <= MAX_CONCURRENT_AUTHOR_SESSIONS:
            raise ValueError("workbench_batch_max_starts_invalid")
        if self.authoring is None:
            raise ValueError("workbench_batch_authoring_service_required")
        with self._locked(), self._dispatch_locked():
            manifest = self._manifest()
            if confirm_batch_sha256 != manifest["batchSha256"]:
                raise ValueError("workbench_batch_confirmation_mismatch")
            observed = [self._observe(row, manifest, poll=True) for row in manifest["entries"]]
            by_id = {result["entryId"]: result for result in observed}
            global_occupied = self._global_occupied_jobs(observed)
            occupied = len(global_occupied)
            blockers = self._strict_dispatch_blockers(observed, global_occupied)
            slots = (0 if stop_on_blockers and blockers else
                     min(max_starts, max(0, MAX_CONCURRENT_AUTHOR_SESSIONS - occupied)))
            attempts = []
            for row in manifest["entries"]:
                if len(attempts) >= slots:
                    break
                current = by_id[row["entryId"]]
                prepared = self._prepared(row, manifest)
                if (prepared is None or current.get("held") or current.get("status") != "prepared"
                        or current.get("error") or current.get("existingArtifacts")
                        or current.get("sessionId")):
                    continue
                job = Path(prepared["jobDirectory"])
                state = _json_object(job / "state.json") if course_exists(job / "state.json") else {}
                if (course_exists(job / "dispatch.json") or state.get("sessionId") or state.get("error")
                        or state.get("existingArtifacts") or state.get("status") != "prepared"):
                    continue
                try:
                    result = self._compact(
                        row, self.authoring.run(job, start=True))
                except Exception as exc:
                    dispatched = course_exists(job / "dispatch.json")
                    result = {"entryId": row["entryId"], "binding": row["binding"],
                              "teachingRevision": row["teachingRevision"],
                              "jobDirectory": prepared["jobDirectory"],
                              "status": "dispatch_unknown" if dispatched else "operator_error",
                              **_safe_error(exc)}
                attempts.append(result)
                by_id[row["entryId"]] = result
                if stop_on_blockers and self._entry_dispatch_blocker(result):
                    break
            final_results = [by_id[row["entryId"]] for row in manifest["entries"]]
            summary = self._summary(manifest, final_results,
                                    global_occupied=self._global_occupied_jobs(final_results))
            atomic_json(self.directory / "latest-summary.json", summary)
            return {"startAttempts": attempts, "summary": summary,
                    "maximumNewStartsThisAction": max_starts,
                    "publicationAllowed": False, "studentDeliveryAllowed": False}

    def hold(self, entry_ids: list[str], *, reason: str) -> dict:
        if (not isinstance(entry_ids, list) or not entry_ids or len(entry_ids) > MAX_BATCH_ENTRIES
                or len(set(entry_ids)) != len(entry_ids)
                or not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 240):
            raise ValueError("workbench_batch_hold_invalid")
        with self._locked():
            manifest = self._manifest()
            rows = {row["entryId"]: row for row in manifest["entries"]}
            if any(entry_id not in rows for entry_id in entry_ids):
                raise ValueError("workbench_batch_hold_unknown_entry")
            receipts = []
            for entry_id in entry_ids:
                row = rows[entry_id]
                prepared = self._prepared(row, manifest)
                if prepared is not None:
                    job = Path(prepared["jobDirectory"])
                    if not course_exists(job / "state.json"):
                        raise ValueError("workbench_batch_hold_entry_state_invalid")
                    state = _json_object(job / "state.json")
                    if (course_exists(job / "dispatch.json") or state.get("sessionId")
                            or state.get("status") != "prepared" or state.get("error")
                            or state.get("existingArtifacts")):
                        raise ValueError("workbench_batch_hold_cannot_cancel_dispatched_entry")
                existing = self._hold(row, manifest)
                if existing is not None:
                    if existing["reason"] != reason.strip():
                        raise ValueError("workbench_batch_hold_already_exists_differently")
                    receipts.append(existing)
                    continue
                receipt = {"schemaVersion": HOLD_SCHEMA, "batchSha256": manifest["batchSha256"],
                           "entryId": entry_id, "draftSha256": row["draftSha256"],
                           "reason": reason.strip(), "createdAt": timestamp(),
                           "publicationAllowed": False}
                receipt["sha256"] = digest(receipt)
                atomic_json(self._entry_folder(entry_id) / "hold.json", receipt, immutable=True)
                receipts.append(receipt)
            return {"holds": receipts, "summary": self._status_locked(manifest, poll=False),
                    "providerCalls": 0, "publicationAllowed": False}
