"""Local, resumable private drafts: durable claim before a single paid POST."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile
import time

from content.textbook_catalog import canonical, digest
from content.textbook_batch_generation import HASH, INPUT_SCHEMA, inspect_draft
from services.course_file_store import (course_bytes, course_text, course_exists,
    course_is_dir, course_write_bytes)


def atomic_json(path, value, *, immutable=False):
    path = Path(path)
    content = canonical(value) + "\n"
    if course_exists(path) and immutable:
        if course_text(path) != content:
            raise ValueError("Existing immutable draft artifact differs")
        return
    if not immutable and course_write_bytes(path, content.encode('utf-8')):
        return
    handle, temporary = tempfile.mkstemp(prefix=".batch-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class TextbookBatchGenerationService:
    def __init__(self, directory, runtime=None):
        self.directory = Path(directory).resolve()
        self.runtime = runtime

    def _folder(self, task_id):
        if HASH.fullmatch(str(task_id)) is None:
            raise ValueError("Invalid task ID")
        return self.directory / task_id

    @contextmanager
    def _lock(self, task_id, *, create=False):
        folder = self._folder(task_id)
        if create:
            folder.mkdir(parents=True, exist_ok=True)
        if not course_is_dir(folder):
            raise ValueError("Prepare this exact task before starting it")
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "operator.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("This task is already being operated; read its saved status") from exc
            yield folder

    @staticmethod
    def _read(folder, name):
        return json.loads(course_text(folder / name))

    def _input(self, folder):
        frozen = self._read(folder, "input.json")
        if (frozen.get("schemaVersion") != INPUT_SCHEMA or frozen.get("taskId") != folder.name
                or frozen.get("inputSha256") != digest({k: v for k, v in frozen.items() if k != "inputSha256"})):
            raise ValueError("Frozen draft input integrity failed")
        return frozen

    @staticmethod
    def _validate_state(state, frozen):
        if (state.get("taskId") != frozen["taskId"] or state.get("inputSha256") != frozen["inputSha256"]
                or state.get("publicationAllowed") is not False):
            raise ValueError("Saved task state differs from frozen input")

    def prepare(self, frozen):
        with self._lock(frozen["taskId"], create=True) as folder:
            atomic_json(folder / "input.json", frozen, immutable=True)
            verified = self._input(folder)
            if not course_exists(folder / "state.json"):
                atomic_json(folder / "state.json", {"schemaVersion": "mira.textbook.private-batch-generation-state.v1",
                    "taskId": frozen["taskId"], "inputSha256": frozen["inputSha256"], "status": "prepared",
                    "runtimeOrigin": None, "runtimeJobId": None, "providerDispatched": False,
                    "createdAt": int(time.time() * 1000), "publicationAllowed": False, "studentDeliveryAllowed": False})
            state = self._read(folder, "state.json")
            self._validate_state(state, verified)
            return self.summary(state)

    def get(self, task_id):
        folder = self._folder(task_id)
        frozen = self._input(folder)
        state = self._read(folder, "state.json")
        self._validate_state(state, frozen)
        return self.summary(state)

    def has_exact_reservation(self, frozen):
        """Read-only queue admission; changed frozen input is never skipped."""
        folder = self._folder(frozen["taskId"])
        if not course_exists(folder / "input.json"):
            return False
        existing = self._input(folder)
        if existing != frozen:
            raise ValueError("Existing immutable draft input differs; reconcile original reservation")
        # Recover a prepare interrupted between input and state on the next
        # prepare. No dispatch is possible until the state exists.
        if not course_exists(folder / "state.json"):
            return False
        state = self._read(folder, "state.json")
        self._validate_state(state, existing)
        return True

    def _runtime_matches(self, state):
        if self.runtime is None:
            raise ValueError("Runtime is required for start/poll")
        if state.get("runtimeOrigin") not in (None, self.runtime.base_url):
            raise ValueError("Task belongs to a different runtime; original outcome needs reconciliation")

    def start(self, task_id):
        with self._lock(task_id) as folder:
            frozen = self._input(folder)
            state = self._read(folder, "state.json")
            self._validate_state(state, frozen)
            self._runtime_matches(state)
            if state["status"] != "prepared":
                return self.summary(state)
            from content.textbook_provided_media import validate_frozen_provided_media
            validate_frozen_provided_media(frozen)
            state.update(status="dispatching", runtimeOrigin=self.runtime.base_url,
                         providerDispatched=True, dispatchStartedAt=int(time.time() * 1000))
            atomic_json(folder / "state.json", state)
            try:
                job = self.runtime.start_generation(requirement=frozen["requirement"], **frozen["generationOptions"])
                if not isinstance(job.job_id, str) or not job.job_id:
                    raise ValueError("Missing upstream generation identity")
            except Exception:
                state.update(status="dispatch_unknown", safeErrorCode="openmaic_dispatch_outcome_unknown")
                atomic_json(folder / "state.json", state)
                return self.summary(state)
            state.update(status="generating", runtimeJobId=job.job_id, upstreamStatus=job.status,
                         dispatchReturnedAt=int(time.time() * 1000))
            atomic_json(folder / "state.json", state)
            return self.summary(state)

    def poll(self, task_id):
        with self._lock(task_id) as folder:
            frozen = self._input(folder)
            state = self._read(folder, "state.json")
            self._validate_state(state, frozen)
            self._runtime_matches(state)
            if state["status"] != "generating":
                return self.summary(state)
            job = self.runtime.get_generation_job(state["runtimeJobId"])
            if job.job_id != state["runtimeJobId"]:
                raise ValueError("Upstream generation identity changed")
            state.update(upstreamStatus=job.status, progress=job.progress, polledAt=int(time.time() * 1000))
            if job.status in {"failed", "ambiguous"}:
                state.update(status="failed_needs_reconciliation", safeErrorCode="openmaic_generation_failed_or_ambiguous")
            elif job.status == "succeeded":
                if not job.classroom_id:
                    raise ValueError("Successful job has no saved classroom")
                classroom = self.runtime.get_classroom(job.classroom_id)
                if classroom.get("id") != job.classroom_id or classroom.get("stage", {}).get("id") != job.classroom_id:
                    raise ValueError("Saved classroom identity differs from upstream job")
                report = inspect_draft(classroom, frozen)
                atomic_json(folder / "classroom.json", classroom, immutable=True)
                atomic_json(folder / "quality-report.json", report, immutable=True)
                state.update(status="generated_needs_review", classroomId=job.classroom_id,
                    classroomSha256=digest(classroom), qualityIssues=report["issues"], qualityPassed=False,
                    previewUrl=f"{self.runtime.base_url}/classroom/{job.classroom_id}")
            atomic_json(folder / "state.json", state)
            return self.summary(state)

    def summary(self, state):
        return {**state, "artifactDirectory": str(self._folder(state["taskId"])),
                "publicationAllowed": False, "studentDeliveryAllowed": False}
