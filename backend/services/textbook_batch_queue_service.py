"""Durable private authoring queue over the existing frozen-input operator.

This is a local operator, not a publication domain. Two slots bound generation
jobs in this queue; model/media calls inside a job remain native-runtime policy.
No failed or uncertain POST is automatically resent.
"""
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import time

from content.textbook_batch_generation import HASH, KINDS, PROMPT_PATH, QUALITY_PATH, freeze_input
from content.textbook_catalog import canonical, digest
from services.textbook_batch_generation_service import TextbookBatchGenerationService, atomic_json

SCHEMA = "mira.textbook.private-authoring-queue.v1"
INDEX_SCHEMA = "mira.textbook.batch-authoring-index.v1"
HOLD_SCHEMA = "mira.textbook.queue-operator-hold.v1"
UNCERTAIN = {"dispatching", "dispatch_unknown"}


def file_sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def document(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("queue_document_object_required")
    return value


class _ReceiptRuntime:
    """Keep real returned job receipts even if the following state write fails."""
    def __init__(self, runtime, folder, frozen):
        self.runtime, self.folder, self.frozen = runtime, folder, frozen
        self.base_url = runtime.base_url

    def _save(self, name, job, immutable=False):
        payload = asdict(job) if is_dataclass(job) else vars(job)
        value = {"schemaVersion": "mira.textbook.queue-upstream-receipt.v1",
                 "taskId": self.frozen["taskId"], "inputSha256": self.frozen["inputSha256"],
                 "runtimeOrigin": self.base_url, "job": payload}
        value["receiptSha256"] = digest(value)
        atomic_json(self.folder / name, value, immutable=immutable)

    def start_generation(self, **kwargs):
        job = self.runtime.start_generation(**kwargs)
        self._save("upstream-dispatch-response.json", job, immutable=True)
        return job

    def get_generation_job(self, identity):
        job = self.runtime.get_generation_job(identity)
        self._save("upstream-latest-response.json", job)
        if job.status in {"failed", "ambiguous", "succeeded"}:
            payload = asdict(job) if is_dataclass(job) else vars(job)
            self._save("upstream-terminal-response-" + digest(payload) + ".json", job, immutable=True)
            if not (self.folder / "upstream-terminal-response.json").exists():
                self._save("upstream-terminal-response.json", job, immutable=True)
        return job

    def get_classroom(self, identity):
        return self.runtime.get_classroom(identity)


class TextbookBatchQueueService:
    def __init__(self, directory, runtime=None, *, minimum_free_bytes=512 * 1024 * 1024):
        self.directory = Path(directory).resolve()
        self.runtime, self.minimum_free_bytes = runtime, minimum_free_bytes
        self.drafts = self.directory / "drafts"

    @contextmanager
    def _lock(self, create=False):
        if create:
            self.directory.mkdir(parents=True, exist_ok=True)
        if not self.directory.is_dir():
            raise ValueError("queue_init_required")
        with (self.directory / "queue.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("queue_operator_already_running") from exc
            yield

    def _space(self):
        if shutil.disk_usage(self.directory).free < self.minimum_free_bytes:
            raise ValueError("queue_insufficient_free_space_no_new_request")

    def _manifest(self):
        value = document(self.directory / "queue.json")
        if (value.get("schemaVersion") != SCHEMA
                or value.get("queueSha256") != digest({k: v for k, v in value.items() if k != "queueSha256"})
                or value.get("maximumConcurrentJobs") != 2
                or value.get("publicationAllowed") is not False):
            raise ValueError("queue_manifest_integrity_failed")
        for entry in value["frozenFiles"]:
            if file_sha(entry["path"]) != entry["byteSha256"]:
                raise ValueError("queue_frozen_source_or_policy_changed")
        if file_sha(self.directory / "inventory.jsonl") != value["inventoryByteSha256"]:
            raise ValueError("queue_inventory_changed")
        return value

    def _inventory(self):
        with (self.directory / "inventory.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                yield json.loads(line)

    def _task(self, row, manifest):
        with Path(manifest["tasksPath"]).open("rb") as stream:
            stream.seek(row["offset"])
            task = json.loads(stream.readline())
        if task.get("taskId") != row["taskId"] or digest(task) != row["taskSha256"]:
            raise ValueError("queue_exact_task_changed")
        return task

    def initialize(self, tasks_path, *, enrich_existing=False, navigation_drafts=False):
        tasks_path = Path(tasks_path).resolve()
        with self._lock(create=True):
            if (self.directory / "queue.json").exists():
                manifest = self._manifest()
                if (manifest["tasksPath"] != str(tasks_path)
                        or manifest["enrichExisting"] != enrich_existing
                        or manifest["navigationDrafts"] != navigation_drafts):
                    raise ValueError("queue_existing_initialization_differs")
                summary = self._status(manifest)
                atomic_json(self.directory / "latest-summary.json", summary)
                return summary
            rows, seen = [], set()
            with tasks_path.open("rb") as stream:
                while True:
                    offset, line = stream.tell(), stream.readline()
                    if not line:
                        break
                    if not line.strip():
                        continue
                    task = json.loads(line)
                    identity = task.get("taskId")
                    if HASH.fullmatch(str(identity)) is None or identity in seen or task.get("kind") not in KINDS:
                        raise ValueError("queue_invalid_or_duplicate_task")
                    seen.add(identity)
                    blockers = []
                    if task["directoryCoverage"]["status"] == "index_only" or not task.get("directoryScope"):
                        blockers.append("official_directory_missing")
                    if task.get("originalContent") is not None and not enrich_existing:
                        blockers.append("existing_content_requires_explicit_enrichment")
                    if task["kind"] == "lesson_courseware":
                        blockers.append("reviewed_lesson_scope_required")
                    if not navigation_drafts:
                        blockers.append("specific_activity_design_pending")
                    rows.append({"taskId": identity, "offset": offset, "taskSha256": digest(task),
                        "kind": task["kind"], "scope": task["scope"], "title": task["title"],
                        "directoryCoverage": task["directoryCoverage"]["status"],
                        "hasDirectory": bool(task.get("directoryScope")),
                        "hasOriginalContent": task.get("originalContent") is not None,
                        "initialStatus": "source_blocked" if blockers else "pending",
                        "initialBlockers": blockers, "publicationAllowed": False})
            if not rows:
                raise ValueError("queue_empty_inventory")
            content = "".join(canonical(row) + "\n" for row in rows)
            inventory = self.directory / "inventory.jsonl"
            if inventory.exists() and inventory.read_text(encoding="utf-8") != content:
                raise ValueError("queue_interrupted_inventory_differs")
            if not inventory.exists():
                # File is never replaced once admitted, including interrupted init.
                with inventory.open("x", encoding="utf-8") as output:
                    output.write(content)
                    output.flush()
                    import os
                    os.fsync(output.fileno())
            manifest = {"schemaVersion": SCHEMA, "tasksPath": str(tasks_path), "taskCount": len(rows),
                "inventoryByteSha256": file_sha(inventory), "maximumConcurrentJobs": 2,
                "enrichExisting": enrich_existing, "navigationDrafts": navigation_drafts,
                "createdAt": int(time.time() * 1000), "publicationAllowed": False,
                "studentDeliveryAllowed": False, "concurrencyUnit": "native_generation_job",
                "frozenFiles": [{"path": str(path), "byteSha256": file_sha(path)}
                    for path in (tasks_path, PROMPT_PATH, QUALITY_PATH)]}
            manifest["queueSha256"] = digest(manifest)
            atomic_json(self.directory / "queue.json", manifest, immutable=True)
            summary = self._status(manifest)
            atomic_json(self.directory / "latest-summary.json", summary)
            return summary

    def _admission(self, identity):
        path = self.directory / "authoring" / identity / "admission.json"
        if not path.exists():
            return None
        value = document(path)
        if (value.get("taskId") != identity
                or value.get("admissionSha256") != digest({k: v for k, v in value.items() if k != "admissionSha256"})):
            raise ValueError("queue_authoring_admission_changed")
        for entry in value["files"].values():
            if file_sha(entry["path"]) != entry["byteSha256"]:
                raise ValueError("queue_authoring_source_changed")
        return value

    def admit_index(self, path):
        with self._lock():
            manifest = self._manifest()
            index = document(path)
            if set(index) != {"schemaVersion", "entries"} or index["schemaVersion"] != INDEX_SCHEMA:
                raise ValueError("queue_authoring_index_schema_invalid")
            if not isinstance(index["entries"], list) or not index["entries"]:
                raise ValueError("queue_authoring_entries_required")
            inventory = {row["taskId"]: row for row in self._inventory()}
            prepared, seen = [], set()
            for entry in index["entries"]:
                if (not isinstance(entry, dict) or set(entry) - {"taskId", "designPlanPath", "reviewedScopePath"}
                        or entry.get("taskId") not in inventory or entry["taskId"] in seen
                        or not entry.get("designPlanPath")):
                    raise ValueError("queue_authoring_entry_invalid_or_duplicate")
                seen.add(entry["taskId"])
                files = {key: {"path": str(Path(entry[key]).resolve()), "byteSha256": file_sha(entry[key])}
                         for key in ("designPlanPath", "reviewedScopePath") if entry.get(key)}
                task = self._task(inventory[entry["taskId"]], manifest)
                freeze_input(task, design_plan_path=files["designPlanPath"]["path"],
                    reviewed_scope_path=files.get("reviewedScopePath", {}).get("path"),
                    enrich_existing=manifest["enrichExisting"])
                existing = self._admission(entry["taskId"])
                if existing and existing["files"] != files:
                    raise ValueError("queue_existing_authoring_admission_differs")
                value = {"taskId": entry["taskId"], "files": files,
                    "sourceIndexPath": str(Path(path).resolve()), "sourceIndexByteSha256": file_sha(path)}
                value["admissionSha256"] = digest(value)
                prepared.append(existing or value)
            # Entire index validated before writing any admission.
            for value in prepared:
                folder = self.directory / "authoring" / value["taskId"]
                folder.mkdir(parents=True, exist_ok=True)
                atomic_json(folder / "admission.json", value, immutable=True)
            atomic_json(self.directory / "latest-summary.json", self._status(manifest))
            return {"admittedTaskCount": len(prepared), "publicationAllowed": False}

    def _eligibility(self, row, manifest):
        admission = self._admission(row["taskId"])
        reasons = []
        if row["directoryCoverage"] == "index_only" or not row["hasDirectory"]:
            reasons.append("official_directory_missing")
        if row["hasOriginalContent"] and not manifest["enrichExisting"]:
            reasons.append("existing_content_requires_explicit_enrichment")
        if row["kind"] == "lesson_courseware" and not (admission and "reviewedScopePath" in admission["files"]):
            reasons.append("reviewed_lesson_scope_required")
        if not admission and not manifest["navigationDrafts"]:
            reasons.append("specific_activity_design_pending")
        return reasons

    def _frozen(self, row, manifest):
        reasons = self._eligibility(row, manifest)
        if reasons:
            raise ValueError("queue_task_not_authorable:" + ",".join(reasons))
        task = self._task(row, manifest)
        admission = self._admission(row["taskId"])
        if admission:
            files = admission["files"]
            return freeze_input(task, design_plan_path=files["designPlanPath"]["path"],
                reviewed_scope_path=files.get("reviewedScopePath", {}).get("path"),
                enrich_existing=manifest["enrichExisting"])
        # Explicit opt-in is a navigation draft, never an invented knowledge lesson.
        design = {"schemaVersion": "mira.textbook.activity-design.v1", "kind": task["kind"],
            "binding": task["scope"], "manifestSha256": task["manifestSha256"],
            "status": "draft", "publicationAllowed": False, "qualityStatus": "pending_quality",
            "designInstructions": "仅创作真实单元与课题的原创图画路线探索和学习方法邀请。"
                "不把目录节点推测成课时，不从课题名编知识目标、答案或测验。"
                "使用可区分且承担含义的原创SVG生活对象、多图选择/配对/观察；"
                "3D须真实可旋转观察并提供图像替代，不做假视频播放器。"
                "按冻结年级教学profile，设计单一操作的游戏、有限字面量预录cue和显式状态。"
                "无浏览器TTS、emoji、积分或掌握声明；全部仍待教学、媒体、配音与浏览器审核。"}
        folder = self.directory / "authoring" / row["taskId"]
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "navigation-draft-design.json"
        atomic_json(path, design, immutable=True)
        return freeze_input(task, design_plan_path=path, enrich_existing=manifest["enrichExisting"])

    def _state(self, row, manifest):
        folder = self.drafts / row["taskId"]
        if (folder / "state.json").exists():
            return TextbookBatchGenerationService(self.drafts).get(row["taskId"])
        path = self.directory / "task-states" / (row["taskId"] + ".json")
        if path.exists():
            return document(path)
        reasons = self._eligibility(row, manifest)
        status = ("design_pending" if reasons == ["specific_activity_design_pending"] else
                  "source_blocked" if reasons else "pending")
        return {"taskId": row["taskId"], "status": status,
                "blockers": reasons, "publicationAllowed": False, "qualityPassed": False}

    @staticmethod
    def _matches(row, filters):
        return all(not value or (row.get(key) if key in {"taskId", "kind"} else row["scope"].get(key)) in value
                   for key, value in (filters or {}).items())

    def _operator_hold(self, row, manifest):
        path = self.directory / "operator-holds" / (row["taskId"] + ".json")
        if not path.exists():
            return None
        value = document(path)
        expected = {"schemaVersion", "queueSha256", "taskId", "taskSha256", "admissionSha256",
                    "inputSha256", "reason", "publicationAllowed", "createdAt", "holdSha256"}
        admission = self._admission(row["taskId"])
        if (set(value) != expected or value.get("schemaVersion") != HOLD_SCHEMA
                or value.get("holdSha256") != digest({k: v for k, v in value.items() if k != "holdSha256"})
                or value.get("queueSha256") != manifest["queueSha256"]
                or value.get("taskId") != row["taskId"] or value.get("taskSha256") != row["taskSha256"]
                or value.get("admissionSha256") != (admission or {}).get("admissionSha256")
                or value.get("inputSha256") != self._frozen(row, manifest)["inputSha256"]
                or not isinstance(value.get("reason"), str) or not value["reason"].strip()
                or value.get("publicationAllowed") is not False):
            raise ValueError("queue_operator_hold_integrity_failed")
        path = self.drafts / row["taskId"] / "input.json"
        if path.exists() and document(path).get("inputSha256") != value["inputSha256"]:
            raise ValueError("queue_operator_hold_prepared_input_changed")
        return value

    def hold_tasks(self, identities, *, reason):
        """Freeze an additive no-dispatch fence without changing task/admission state.

        Even before prepare, the exact deterministic input is computed locally and
        bound to this receipt. A hold permits explicit provider-free preparation.
        """
        if (not isinstance(identities, list) or not identities or len(identities) > 200
                or len(set(identities)) != len(identities) or not isinstance(reason, str)
                or not reason.strip() or len(reason) > 240):
            raise ValueError("queue_operator_hold_explicit_tasks_and_reason_required")
        with self._lock():
            manifest = self._manifest()
            inventory = {row["taskId"]: row for row in self._inventory()}
            receipts = []
            for identity in identities:
                if identity not in inventory:
                    raise ValueError("queue_operator_hold_unknown_task")
                row = inventory[identity]
                if self._occupies(self._state(row, manifest)):
                    raise ValueError("queue_operator_hold_cannot_cancel_dispatched_job")
                frozen = self._frozen(row, manifest)
                admission = self._admission(identity)
                existing = self._operator_hold(row, manifest)
                if existing:
                    if existing["reason"] != reason.strip():
                        raise ValueError("queue_operator_hold_existing_receipt_differs")
                    receipts.append(existing)
                    continue
                value = {"schemaVersion": HOLD_SCHEMA, "queueSha256": manifest["queueSha256"],
                    "taskId": identity, "taskSha256": row["taskSha256"],
                    "admissionSha256": (admission or {}).get("admissionSha256"),
                    "inputSha256": frozen["inputSha256"], "reason": reason.strip(),
                    "publicationAllowed": False, "createdAt": int(time.time() * 1000)}
                value["holdSha256"] = digest(value)
                receipts.append(value)
            # Complete validation precedes every receipt write.
            folder = self.directory / "operator-holds"
            folder.mkdir(exist_ok=True)
            for value in receipts:
                atomic_json(folder / (value["taskId"] + ".json"), value, immutable=True)
            atomic_json(self.directory / "latest-summary.json", self._status(manifest))
            return {"heldTasks": receipts, "providerCalls": 0, "publicationAllowed": False}

    def _prepare(self, manifest, limit, filters, *, include_held=False):
        prepared = []
        for row in self._inventory():
            if not self._matches(row, filters) or self._state(row, manifest)["status"] != "pending":
                continue
            hold = self._operator_hold(row, manifest)
            if hold and not include_held:
                continue
            self._space()
            try:
                frozen = self._frozen(row, manifest)
                state = TextbookBatchGenerationService(self.drafts).prepare(frozen)
            except ValueError as exc:
                # Save a safe type; private source contents never go to operator logs.
                state = {"taskId": row["taskId"], "status": "preparation_blocked",
                         "safeErrorCode": type(exc).__name__, "publicationAllowed": False, "qualityPassed": False}
                folder = self.directory / "task-states"
                folder.mkdir(exist_ok=True)
                atomic_json(folder / (row["taskId"] + ".json"), state)
            prepared.append(state)
            if len(prepared) >= limit:
                break
        return prepared

    def prepare(self, *, limit=2, filters=None):
        if not 1 <= limit <= 200:
            raise ValueError("queue_prepare_limit_out_of_range")
        with self._lock():
            manifest = self._manifest()
            result = self._prepare(manifest, limit, filters, include_held=True)
            atomic_json(self.directory / "latest-summary.json", self._status(manifest))
            return result

    def _service(self, row, manifest):
        frozen = self._frozen(row, manifest)
        service = TextbookBatchGenerationService(self.drafts)
        if not service.has_exact_reservation(frozen):
            raise ValueError("queue_exact_prepared_reservation_required")
        return TextbookBatchGenerationService(self.drafts,
            _ReceiptRuntime(self.runtime, self.drafts / row["taskId"], frozen))

    def _recover_returned_identity(self, row, manifest, state):
        """Only GET an identity actually returned before a local state crash."""
        folder = self.drafts / row["taskId"]
        path = folder / "upstream-dispatch-response.json"
        if not path.exists():
            return state
        frozen, receipt = document(folder / "input.json"), document(path)
        if (receipt.get("schemaVersion") != "mira.textbook.queue-upstream-receipt.v1"
                or receipt.get("receiptSha256") != digest({k: v for k, v in receipt.items() if k != "receiptSha256"})
                or receipt.get("taskId") != row["taskId"] or receipt.get("inputSha256") != frozen["inputSha256"]
                or receipt.get("runtimeOrigin") != self.runtime.base_url
                or state.get("runtimeOrigin") != self.runtime.base_url):
            raise ValueError("queue_unknown_receipt_binding_changed")
        identity = receipt.get("job", {}).get("job_id")
        if not isinstance(identity, str) or not identity:
            raise ValueError("queue_unknown_receipt_identity_missing")
        # A 404 or any error stays uncertain, never a new POST or a free slot.
        job = self.runtime.get_generation_job(identity)
        if job.job_id != identity:
            raise ValueError("queue_unknown_get_identity_changed")
        with TextbookBatchGenerationService(self.drafts)._lock(row["taskId"]) as locked:
            current = document(locked / "state.json")
            if current != {key: value for key, value in state.items() if key != "artifactDirectory"}:
                raise ValueError("queue_unknown_state_changed")
            current.update(status="generating", runtimeJobId=identity, upstreamStatus=job.status,
                           reconciledBy="get_returned_dispatch_identity", reconciledAt=int(time.time() * 1000))
            atomic_json(locked / "state.json", current)
        return current

    def run_once(self, *, max_starts=2, filters=None):
        if not 0 <= max_starts <= 2 or self.runtime is None:
            raise ValueError("queue_runtime_and_bounded_start_limit_required")
        with self._lock():
            manifest = self._manifest()
            rows = list(self._inventory())
            polled, errors = [], []
            # Poll every in-flight task, independent of new-admission filters.
            for row in rows:
                state = self._state(row, manifest)
                try:
                    if shutil.disk_usage(self.directory).free < 8 * 1024 * 1024:
                        raise ValueError("queue_capacity_too_low_to_preserve_get_result")
                    if state["status"] in UNCERTAIN or state.get("upstreamStatus") == "ambiguous":
                        state = self._recover_returned_identity(row, manifest, state)
                    if state["status"] == "generating":
                        polled.append(self._service(row, manifest).poll(row["taskId"]))
                except Exception as exc:
                    errors.append({"taskId": row["taskId"], "errorType": type(exc).__name__,
                                   "safeErrorCode": "queue_get_or_local_validation_failed_no_post"})
            occupied = [row["taskId"] for row in rows if self._occupies(self._state(row, manifest))]
            slots = min(max_starts, max(0, 2 - len(occupied)))
            if shutil.disk_usage(self.directory).free < self.minimum_free_bytes:
                slots = 0  # Recoverable capacity block, never a permanent task failure.
            if slots:
                self._prepare(manifest, slots, filters)
            started = []
            for row in rows:
                if len(started) >= slots:
                    break
                if not self._matches(row, filters) or self._state(row, manifest)["status"] != "prepared":
                    continue
                if self._operator_hold(row, manifest):
                    continue
                self._space()
                service = self._service(row, manifest)  # Full frozen source/design revalidation before POST.
                started.append(service.start(row["taskId"]))
            result = {"polled": polled, "started": started, "operatorErrors": errors,
                      "summary": self._status(manifest), "publicationAllowed": False}
            # Small aggregate report, never full requirement/provider credentials.
            atomic_json(self.directory / "latest-summary.json", result["summary"])
            return result

    @staticmethod
    def _occupies(state):
        return (state["status"] in UNCERTAIN | {"generating"}
                or state.get("upstreamStatus") == "ambiguous")

    def _status(self, manifest):
        counts, groups, occupied, blockers, audio_counts, holds = {}, {}, 0, {}, {}, []
        for row in self._inventory():
            state = self._state(row, manifest)
            status = state["status"]
            hold = self._operator_hold(row, manifest)
            if hold:
                holds.append({"taskId": row["taskId"], "inputSha256": hold["inputSha256"],
                              "holdSha256": hold["holdSha256"]})
            counts[status] = counts.get(status, 0) + 1
            for reason in state.get("blockers", []):
                blockers[reason] = blockers.get(reason, 0) + 1
            if status == "generated_needs_review":
                audio_path = self.drafts / row["taskId"] / "audio-state.json"
                if audio_path.exists():
                    audio = document(audio_path)
                    binding = audio.get("bound", {})
                    audio_status = audio.get("status", "audio_integrity_blocked")
                    if (binding.get("taskId") != row["taskId"]
                            or binding.get("inputSha256") != state["inputSha256"]
                            or binding.get("classroomSha256") != state["classroomSha256"]
                            or audio.get("publicationAllowed") is not False):
                        audio_status = "audio_integrity_blocked"
                    if audio_status == "audio_completed_needs_review":
                        audit_path = audio_path.parent / "audio-audit" / "audit.json"
                        if not audit_path.is_file():
                            audio_status = "audio_integrity_blocked"
                        else:
                            audit = document(audit_path)
                            if (digest(audit) != audio.get("auditSha256")
                                    or audit.get("allSegmentsPassed") is not True):
                                audio_status = "audio_integrity_blocked"
                else:
                    audio_status = "audio_pending"
                audio_counts[audio_status] = audio_counts.get(audio_status, 0) + 1
            occupied += self._occupies(state)
            for dimension in ("subject", "gradeCode", "editionId", "kind"):
                value = row["kind"] if dimension == "kind" else row["scope"][dimension]
                group = groups.setdefault(dimension, {}).setdefault(value, {})
                group[status] = group.get(status, 0) + 1
        free = shutil.disk_usage(self.directory).free
        return {"schemaVersion": SCHEMA, "queueSha256": manifest["queueSha256"],
            "taskCount": manifest["taskCount"], "statusCounts": counts, "by": groups,
            "blockerCounts": blockers,
            "operatorHoldCount": len(holds), "operatorHolds": holds,
            "capacity": {"status": "capacity_blocked" if free < self.minimum_free_bytes else "available",
                         "availableBytes": free, "minimumFreeBytes": self.minimum_free_bytes},
            "occupiedJobSlots": occupied, "maximumConcurrentJobs": 2,
            "audioStateCounts": audio_counts, "maximumConcurrentAudioTasks": 1,
            "generatedDraftCount": counts.get("generated_needs_review", 0),
            "audioCompletedDraftCount": audio_counts.get("audio_completed_needs_review", 0),
            "previewReadyCount": 0, "browserVerifiedCount": 0,
            "generatedDraftsAreReviewed": False, "publicationAllowed": False,
            "studentDeliveryAllowed": False, "updatedAt": int(time.time() * 1000)}

    def status(self):
        with self._lock():
            return self._status(self._manifest())

    def refresh_summary(self):
        with self._lock():
            summary = self._status(self._manifest())
            atomic_json(self.directory / "latest-summary.json", summary)
            return summary
