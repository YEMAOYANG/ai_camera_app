"""Versioned writes of registered JSON work records, never local fallbacks.

The provider/authoring services still own their locks and business transactions.
This boundary preserves exact old bytes and advances a file head only by CAS.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

from pymysql.err import OperationalError

from core.course_storage_config import CourseStorageConfig
from repositories.course_storage_repository import (
    CourseStorageRegistryError, CourseStorageRepository, normalize_source_path,
    storage_id_for, storage_identity, _relative, _locator,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_WRITE_BYTES = 64 * 1024 * 1024
_NATIVE = "openmaic-runtime/.runtime/OpenMAIC/data/"
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_TERMINAL = {"succeeded", "failed", "ambiguous", "passed", "needs_revision", "completed", "cancelled"}


class CourseFileWriteError(ValueError):
    def __init__(self, code, status_code=409):
        super().__init__(code)
        self.code, self.status_code = code, status_code


def _require(condition, code="course_storage_write_forbidden", status=409):
    if not condition:
        raise CourseFileWriteError(code, status)


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _retry_deadlock(operation):
    """Retry only transactions MySQL has already rolled back as deadlocks.

    Lifecycle validation and the original expected head are repeated. This
    boundary never retries an upload, provider call, or ambiguous I/O failure.
    """
    for attempt in range(3):
        try:
            return operation()
        except OperationalError as error:
            if not error.args or error.args[0] != 1213:
                raise
            if attempt == 2:
                raise CourseFileWriteError('course_storage_write_conflict', 409) from None


def _quality_sha(value):
    # Match Native's JSON number and UTF-16 object-key serialization exactly.
    node = shutil.which(os.environ.get("MIRA_NODE_BINARY") or os.environ.get("COURSE_ARCHIVE_NODE") or "node")
    _require(node is not None, "course_storage_review_digest_unavailable", 502)
    code = "let s='';process.stdin.on('data',b=>s+=b);process.stdin.on('end',()=>{const c=v=>Array.isArray(v)?v.map(c):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,c(v[k])])):v;process.stdout.write(require('node:crypto').createHash('sha256').update(JSON.stringify(c(JSON.parse(s)))).digest('hex'));});"
    try:
        result = subprocess.run([node, "-e", code], input=json.dumps(value, ensure_ascii=False, allow_nan=False),
            text=True, capture_output=True, timeout=15)
        _require(result.returncode == 0 and bool(_SHA.fullmatch(result.stdout)), "course_storage_review_digest_unavailable", 502)
        return result.stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        raise CourseFileWriteError("course_storage_review_digest_unavailable", 502) from None


def _json_bytes(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        from services.course_archive_exporter import _inspect_original, _check_public
        _inspect_original(raw, Path("work-record.json"))
        _check_public(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise CourseFileWriteError("course_storage_json_unsafe", 400) from None


def _preserved(old, new, fields):
    _require(isinstance(old, dict) and isinstance(new, dict))
    _require(all(key not in old or new.get(key) == old[key] for key in fields))


def _ledger(old, new, *, key, started, terminal):
    """Append attempts without erasing a paid claim or changing a terminal one."""
    _require(isinstance(old, list) and isinstance(new, list) and len(new) >= len(old))
    identity = key if callable(key) else lambda record: record.get(key)
    ids = []
    for i, record in enumerate(new):
        _require(isinstance(record, dict) and isinstance(identity(record), str) and identity(record))
        ids.append(identity(record))
        status = record.get("status", record.get("state"))
        _require(status in started | terminal)
        if i < len(old):
            prior = old[i]
            _require(isinstance(prior, dict) and identity(prior) == identity(record))
            prior_status = prior.get("status", prior.get("state"))
            if prior_status in terminal:
                _require(record == prior)
            else:
                _require(prior_status in started)
                _preserved(prior, record, set(prior) - {"status", "state", "updatedAt", "browserRecheckedAt"})
    _require(len(set(ids)) == len(ids))


class NodeCourseFileUploader:
    def __init__(self, *, project_root=PROJECT_ROOT):
        self.root = Path(project_root)

    def upload(self, *, object_key, raw, storage):
        node = shutil.which(os.environ.get("MIRA_NODE_BINARY") or os.environ.get("COURSE_ARCHIVE_NODE") or "node")
        _require(node is not None, "course_storage_upload_unavailable", 502)
        payload = {"objectKey": object_key, "sha256": _hash(raw), "byteSize": len(raw),
                   "mimeType": "application/json", "bodyBase64": base64.b64encode(raw).decode("ascii"),
                   "storage": storage}
        try:
            result = subprocess.run([node, str(self.root / "openmaic-runtime/scripts/course-storage-file.mjs")],
                input=json.dumps(payload, ensure_ascii=False), text=True, capture_output=True,
                cwd=self.root, timeout=240)
            descriptor = json.loads(result.stdout) if result.returncode == 0 else None
        except (OSError, subprocess.SubprocessError, ValueError):
            raise CourseFileWriteError("course_storage_upload_failed", 502) from None
        _require(isinstance(descriptor, dict)
            and descriptor.get("objectKey") == object_key and descriptor.get("sha256") == payload["sha256"]
            and type(descriptor.get("byteSize")) is int and descriptor["byteSize"] == len(raw) and descriptor.get("storage") == storage,
            "course_storage_upload_not_verified", 502)
        try:
            return _locator({"kind": "object", **{k: descriptor[k] for k in ("objectKey", "etag", "versionId") if k in descriptor}})
        except CourseStorageRegistryError:
            raise CourseFileWriteError("course_storage_upload_not_verified", 502) from None


class CourseFileWriter:
    def __init__(self, config=None, repository=None):
        self.config = config or CourseStorageConfig.from_env()
        if repository is None:
            from core.config import AppConfig
            from core.database import Database
            from flask import current_app, has_app_context
            url = current_app.config["DATABASE_URL"] if has_app_context() else AppConfig.from_env().DATABASE_URL
            repository = CourseStorageRepository(Database(url))
        self.repository = repository
        self.root = PROJECT_ROOT
        self.uploader = NodeCourseFileUploader()

    def _source(self, path):
        source = Path(path)
        try:
            relative = source.absolute().relative_to(self.root).as_posix() if source.is_absolute() else source.as_posix()
            relative = normalize_source_path(relative)
            current = self.root
            for part in relative.split("/"):
                current = current / part
                _require(not current.is_symlink(), "course_storage_request_invalid", 400)
            return relative
        except (ValueError, CourseStorageRegistryError):
            raise CourseFileWriteError("course_storage_request_invalid", 400) from None

    def _read(self, path, sha=None):
        from services.course_file_store import CourseFileStore
        source = self.root / self._source(path)
        raw = CourseFileStore(config=self.config, repository=self.repository).read_bytes(
            source, expected_sha256=sha, max_bytes=MAX_WRITE_BYTES)
        if raw is None:
            with source.open("rb") as stream:
                raw = stream.read(MAX_WRITE_BYTES + 1)
            _require(len(raw) <= MAX_WRITE_BYTES and (sha is None or _hash(raw) == sha),
                     "course_storage_source_changed", 502)
        return raw

    def _exists(self, path):
        from services.course_file_store import CourseFileStore
        source = self.root / self._source(path)
        return CourseFileStore(config=self.config, repository=self.repository).resolve(source) is not None or source.is_file()

    def _paths(self, directory, pattern="*", *, recursive=False):
        directory = self._source(directory)
        root = self.root / directory
        local = root.rglob(pattern) if recursive else root.glob(pattern)
        found = {self._source(path) for path in local if path.is_file() or path.is_symlink()}
        storage_id = storage_id_for(self.config.endpoint, self.config.bucket, self.config.region)
        for path in self.repository.paths_under(directory, storage_id):
            relative = Path(path).relative_to(directory)
            if (recursive or len(relative.parts) == 1) and relative.match(pattern):
                found.add(path)
        _require(len(found) <= 2048, "course_storage_review_evidence_ambiguous")
        return sorted(found)

    def _no_review_dispatch(self, folder, snapshot):
        forbidden = [path for path in self._paths(folder.as_posix(), snapshot + "*")
                     if re.search(r"(?:provider|dispatch|visual)", Path(path).name.removeprefix(snapshot))]
        responses = _NATIVE + "formal-visual-provider-responses/" + snapshot
        _require(not forbidden and not self._paths(responses, recursive=True), "course_storage_review_already_dispatched")

    @staticmethod
    def _browser_only(result, snapshot):
        return (isinstance(result, dict) and result.get("status") == "needs_revision"
            and result.get("snapshotSha256") == snapshot and not result.get("receipt")
            and isinstance(result.get("issues"), list) and bool(result["issues"])
            and all(isinstance(issue, dict) and isinstance(issue.get("problem"), str)
                and issue["problem"].startswith("Browser check ") for issue in result["issues"]))

    def _review_claim(self, folder, snapshot, prior, updated, old_ledger_raw):
        _require(isinstance(prior, dict) and prior.get("status") == "needs_revision"
            and not prior.get("artifactPrefix") and not prior.get("grantId")
            and type(updated.get("browserRecheckedAt")) is int
            and updated["browserRecheckedAt"] > prior.get("browserRecheckedAt", prior.get("startedAt", 0)))
        _require({k: v for k, v in updated.items() if k != "browserRecheckedAt"}
            == {k: v for k, v in prior.items() if k != "browserRecheckedAt"})
        self._no_review_dispatch(folder, snapshot)
        self._review_input(folder, snapshot)
        result_raw = self._read((folder / (snapshot + ".json")).as_posix())
        browser_raw = self._read((folder / (snapshot + "-browser.json")).as_posix())
        result, browser = _json_bytes(result_raw), _json_bytes(browser_raw)
        _require(self._browser_only(result, snapshot) and isinstance(browser, list)
            and any(isinstance(check, dict) and check.get("passed") is False for check in browser))
        matches = []
        for path in self._paths(folder.as_posix(), snapshot + "-browser-rejection-*.json"):
            stamp = re.fullmatch(re.escape(snapshot) + r"-browser-rejection-([0-9]+)\.json", Path(path).name)
            if not stamp or int(stamp[1]) > updated["browserRecheckedAt"]:
                continue
            body = self._read(path)
            archive = _json_bytes(body)
            if isinstance(archive, dict) and set(archive) == {"result", "browser", "attempt"} \
                    and archive == {"result": result, "browser": browser, "attempt": prior}:
                matches.append((int(stamp[1]), path, _hash(body)))
        _require(bool(matches), "course_storage_review_rejection_archive_missing")
        _, path, sha = max(matches)
        return {"kind": "browser_recheck_claim", "snapshotSha256": snapshot,
            "rejectionPath": path, "rejectionSha256": sha, "originalResultSha256": _hash(result_raw),
            "originalBrowserSha256": _hash(browser_raw), "originalLedgerSha256": _hash(old_ledger_raw),
            "originalInputSha256": _hash(self._read((folder / (snapshot + "-input.json")).as_posix())),
            "browserRecheckedAt": updated["browserRecheckedAt"]}

    def _review_input(self, folder, snapshot):
        value = _json_bytes(self._read((folder / (snapshot + "-input.json")).as_posix()))
        fields = {"ownerId", "sessionId", "stageId", "modelPolicyId", "gradeBoundarySha256",
            "teachingBriefSha256", "selectionPlanSha256", "interactionDesignContextSha256",
            "playfulContextSha256", "difficultyPolicySha256"}
        identity = {k: v for k, v in value.items() if k in fields} if isinstance(value, dict) else {}
        _require(identity.get("sessionId") and identity.get("stageId")
            and _quality_sha(identity) == folder.name and _quality_sha(value.get("snapshot")) == snapshot,
            "course_storage_review_identity_mismatch")
        return value

    def _accepted_review_claim(self, folder, snapshot):
        storage_id = storage_id_for(self.config.endpoint, self.config.bucket, self.config.region)
        ledger_path = (folder / "attempts.json").as_posix()
        raw = self._read(ledger_path)
        scope = self.repository.head_scope(ledger_path, storage_id)
        meta = scope["metadata"] if scope else {}
        proof = meta.get("writePolicy")
        _require(isinstance(proof, dict) and proof.get("kind") == "browser_recheck_claim"
            and proof.get("snapshotSha256") == snapshot and meta.get("sourceDigest") == _hash(raw)
            and meta.get("previousSha256") == proof.get("originalLedgerSha256"), "course_storage_review_claim_missing")
        _require(Path(proof["rejectionPath"]).parent == folder
            and _hash(self._read(proof["rejectionPath"])) == proof["rejectionSha256"]
            and _hash(self._read((folder / (snapshot + "-input.json")).as_posix())) == proof["originalInputSha256"])
        archive = _json_bytes(self._read(proof["rejectionPath"]))
        ledger = _json_bytes(raw)
        matches = [entry for entry in ledger if isinstance(entry, dict) and entry.get("snapshotSha256") == snapshot]
        _require(len(matches) == 1 and matches[0].get("browserRecheckedAt") == proof["browserRecheckedAt"]
            and matches[0].get("status") == "needs_revision" and not matches[0].get("artifactPrefix")
            and self._browser_only(archive.get("result"), snapshot))
        _require({k: v for k, v in matches[0].items() if k != "browserRecheckedAt"}
            == {k: v for k, v in archive["attempt"].items() if k != "browserRecheckedAt"})
        return {**proof, "claimLedgerSha256": _hash(raw)}, archive

    def _grant_result_context(self, folder, snapshot, old_raw, new_raw):
        storage_id = storage_id_for(self.config.endpoint, self.config.bucket, self.config.region)
        ledger_path = (folder / "attempts.json").as_posix()
        scope = self.repository.head_scope(ledger_path, storage_id)
        meta = scope["metadata"] if scope else {}
        policy = meta.get("writePolicy")
        if not isinstance(policy, dict) or policy.get("kind") != "review_attempt_ledger" \
                or not any(item.get("kind") == "review_grant" for item in policy.get("recoveries", [])):
            return None
        ledger_raw = self._read(ledger_path)
        ledger = _json_bytes(ledger_raw)
        _require(meta.get("sourceDigest") == _hash(ledger_raw) and isinstance(ledger, list) and ledger)
        attempt = ledger[-1]
        _require(attempt.get("snapshotSha256") == snapshot and attempt.get("status") == "started" and attempt.get("grantId"))
        prior = ledger[:-1]
        _require(prior and all(item.get("status") in {"failed", "needs_revision"} for item in prior))
        proof = self._review_appended_recovery(folder, prior, attempt,
            [item for item in prior if item.get("snapshotSha256") == snapshot])
        _require(proof in policy["recoveries"])
        prefix = attempt["artifactPrefix"]
        previous_raw = self._read((folder / (prefix + "-previous-result.json")).as_posix())
        _require(_json_bytes(previous_raw) == _json_bytes(old_raw)
            and _json_bytes(old_raw).get("status") == "needs_revision"
            and self._read((folder / (prefix + ".json")).as_posix()) == new_raw
            and _json_bytes(self._read((folder / (prefix + "-input.json")).as_posix())) == self._review_input(folder, snapshot))
        grant = _json_bytes(self._read((folder / "operator-review-grant.json").as_posix()))
        return ({**proof, "snapshotSha256": snapshot, "claimLedgerSha256": _hash(ledger_raw),
            "originalResultSha256": _hash(old_raw), "previousResultSha256": _hash(previous_raw),
            "grantResultSha256": _hash(new_raw), "reservedAt": grant["reservedAt"]},
            {"result": _json_bytes(old_raw)}, prefix)

    def _review_result(self, folder, snapshot, old_raw, new, new_raw, *, browser=False):
        grant_context = None if browser else self._grant_result_context(folder, snapshot, old_raw, new_raw)
        if grant_context:
            proof, archive, prefix = grant_context
            _require(new.get("status") == "passed")
        else:
            proof, archive = self._accepted_review_claim(folder, snapshot)
            prefix = snapshot
        source_proofs = {}
        _require(_hash(old_raw) == proof["originalBrowserSha256" if browser else "originalResultSha256"])
        if browser:
            self._no_review_dispatch(folder, snapshot)
            _require(isinstance(new, list) and len(new) == len(archive["browser"]))
            for prior, current in zip(archive["browser"], new):
                _require(isinstance(prior, dict) and isinstance(current, dict)
                    and all(current.get(k) == prior.get(k) for k in ("sceneId", "sceneSha256", "viewport"))
                    and type(current.get("passed")) is bool)
        else:
            _require(isinstance(new, dict) and new.get("snapshotSha256") == snapshot
                and new.get("status") in {"passed", "needs_revision"} and isinstance(new.get("issues"), list))
            _preserved(archive["result"], new, {"reviewPromptVersion", "playfulContextSha256"})
            input_record = self._review_input(folder, snapshot)
            browser_raw = self._read((folder / (prefix + "-browser.json")).as_posix())
            observations = _json_bytes(browser_raw)
            source_proofs["browserSha256"] = _hash(browser_raw)
            if self._browser_only(new, snapshot):
                self._no_review_dispatch(folder, snapshot)
            else:
                _require(isinstance(observations, list) and observations
                    and all(isinstance(item, dict) and item.get("passed") is True for item in observations))
                dispatch_raw = self._read((folder / (prefix + "-provider-dispatch.json")).as_posix())
                response_raw = self._read((folder / (prefix + "-provider.json")).as_posix())
                dispatch, response = _json_bytes(dispatch_raw), _json_bytes(response_raw)
                source_proofs.update(dispatchSha256=_hash(dispatch_raw), providerResponseSha256=_hash(response_raw))
                _require(dispatch.get("snapshotSha256") == snapshot and type(dispatch.get("startedAt")) is int
                    and dispatch["startedAt"] >= proof.get("reservedAt", proof.get("browserRecheckedAt", -1)))
                if new["status"] == "passed":
                    receipt = new.get("receipt")
                    _require(not new["issues"] and isinstance(receipt, dict)
                        and receipt.get("schemaVersion") == "mira.openmaic.teaching-quality-receipt.v1"
                        and receipt.get("status") == "passed" and receipt.get("snapshotSha256") == snapshot
                        and receipt.get("receiptSha256") == _quality_sha({k: v for k, v in receipt.items() if k != "receiptSha256"})
                        and all(receipt.get(k) == input_record.get(k) for k in
                            ("sessionId", "stageId", "gradeBoundarySha256", "selectionPlanSha256", "teachingBriefSha256"))
                        and receipt.get("review", {}).get("requestIdHash") == response.get("providerRequestIdHash")
                        and bool(_SHA.fullmatch(str(response.get("providerRequestIdHash")))))
                    checks = [{key: item.get(key) for key in ("sceneId", "sceneSha256", "viewport", "screenshotSha256",
                        "domSha256", "passed", "probeCount")} for item in observations]
                    _require(receipt.get("renderChecks") == checks)
        return {**proof, **source_proofs, "kind": "review_grant_canonical" if grant_context else "browser_recheck_artifact",
            "artifact": "browser" if browser else "result"}

    def _review_ledger(self, path, old, new, old_raw, meta):
        _require(isinstance(old, list) and isinstance(new, list) and len(new) >= len(old))
        changed = [(i, before, new[i]) for i, before in enumerate(old) if before != new[i]]
        recovery = [(i, before, after) for i, before, after in changed if isinstance(before, dict)
                    and before.get("status") == "needs_revision"]
        if recovery:
            _require(len(changed) == len(recovery) == 1 and len(new) == len(old))
            _, prior, updated = recovery[0]
            snapshot = prior.get("snapshotSha256")
            _require(isinstance(snapshot, str) and bool(_SHA.fullmatch(snapshot)))
            folder = Path(path).parent
            if updated.get("browserRecheckedAt") != prior.get("browserRecheckedAt"):
                return self._review_claim(folder, snapshot, prior, updated, old_raw)
            proof, _ = self._accepted_review_claim(folder, snapshot)
            _preserved(prior, updated, set(prior) - {"status"})
            _require(updated.get("status") in {"passed", "needs_revision", "failed"})
            if updated["status"] != "failed":
                result = _json_bytes(self._read((folder / (snapshot + ".json")).as_posix()))
                _require(result.get("status") == updated["status"])
            return {**proof, "kind": "browser_recheck_completed"}
        _ledger(old, new, key=lambda record: record.get("artifactPrefix") or record.get("snapshotSha256"),
                started={"started"}, terminal={"passed", "needs_revision", "failed"})
        appended_proofs = []
        for entry in new[len(old):]:
            _require(entry.get("status") == "started")
            repeated = [prior for prior in old if prior.get("snapshotSha256") == entry.get("snapshotSha256")]
            if repeated:
                appended_proofs.append(self._review_appended_recovery(Path(path).parent, old, entry, repeated))
        return {"kind": "review_attempt_ledger", "recoveries": appended_proofs} if appended_proofs else "review_attempt_ledger"

    def _review_appended_recovery(self, folder, old, entry, repeated):
        snapshot = entry.get("snapshotSha256")
        _require(isinstance(snapshot, str) and bool(_SHA.fullmatch(snapshot)))
        prior_sha = _quality_sha(old)
        _require(entry.get("priorAttemptsSha256") == prior_sha)
        if entry.get("grantId"):
            grant_raw = self._read((folder / "operator-review-grant.json").as_posix())
            grant = _json_bytes(grant_raw)
            unsigned = {k: v for k, v in grant.items() if k != "reservedAt"}
            original_input = self._review_input(folder, snapshot)
            _require(grant.get("schemaVersion") == "mira.formal-quality-review-grant.v1"
                and grant.get("grantId") == entry["grantId"] and grant.get("approvalRef") == entry.get("approvalRef")
                and grant.get("priorAttemptsSha256") == prior_sha and grant.get("snapshotSha256") == snapshot
                and grant.get("reviewIdentitySha256") == folder.name and grant.get("maxAdditionalReviews") == 1
                and grant.get("sessionId") == original_input.get("sessionId") and grant.get("stageId") == original_input.get("stageId")
                and type(grant.get("reservedAt")) is int and entry.get("startedAt", -1) >= grant["reservedAt"]
                and entry.get("artifactPrefix") == snapshot + "-grant-" + _quality_sha(unsigned))
            return {"kind": "review_grant", "grantSha256": _hash(grant_raw), "priorAttemptsSha256": prior_sha}
        evidence_sha = entry.get("predispatchRecoverySha256")
        _require(isinstance(evidence_sha, str) and bool(_SHA.fullmatch(evidence_sha))
            and entry.get("artifactPrefix") == snapshot + "-predispatch-" + evidence_sha
            and len(repeated) == 1 and repeated[0].get("status") == "failed"
            and not repeated[0].get("artifactPrefix") and not repeated[0].get("grantId"))
        self._no_review_dispatch(folder, snapshot)
        _require(not self._exists((folder / (snapshot + ".json")).as_posix()))
        original_input_raw = self._read((folder / (snapshot + "-input.json")).as_posix())
        original_input = self._review_input(folder, snapshot)
        recoveries = Path(_NATIVE + "formal-saved-stage-recoveries")
        claims = self._paths(recoveries.as_posix(), "*/complete-" + snapshot + "-visual-predispatch.claim", recursive=True)
        accepted = []
        for path in claims:
            if Path(path).parent.parent != recoveries:
                continue
            claim_raw = self._read(path)
            claim = _json_bytes(claim_raw)
            if not isinstance(claim, dict):
                continue
            evidence = {k: v for k, v in claim.items() if k not in {"evidenceSha256", "createdAt", "pid"}}
            if (claim.get("schemaVersion") != "mira.english1.visual-predispatch-recovery.v1"
                    or claim.get("evidenceSha256") != evidence_sha or _quality_sha(evidence) != evidence_sha
                    or claim.get("jobId") != Path(path).parent.name
                    or claim.get("priorAttemptsSha256") != prior_sha
                    or claim.get("priorInputSha256") != _hash(original_input_raw)
                    or claim.get("error") != "MIRA_PAID_BUDGET_DISPATCH_ALREADY_CLAIMED"
                    or not isinstance(claim.get("failureLog"), str)
                    or not claim["failureLog"].strip().endswith(claim["error"])
                    or _hash(claim["failureLog"].encode()) != claim.get("failureLogSha256")):
                continue
            identity = claim.get("identity", {})
            if (identity.get("repairSnapshotSha256") != snapshot
                    or identity.get("sessionId") != original_input.get("sessionId")
                    or identity.get("stageId") != original_input.get("stageId")):
                continue
            prior_claim_raw = self._read((Path(path).parent / ("complete-" + snapshot + ".claim")).as_posix())
            prior_claim = _json_bytes(prior_claim_raw)
            _require(_hash(prior_claim_raw) == claim.get("priorClaimSha256")
                and all(prior_claim.get(k) == v for k, v in identity.items()) and not prior_claim.get("reviewGrantSha256")
                and not self._exists((Path(path).parent / "completion.json").as_posix()))
            browser = _json_bytes(self._read((folder / (snapshot + "-browser.json")).as_posix()))
            _require(isinstance(browser, list) and len(browser) == 16 and _quality_sha(browser) == claim.get("browserSha256")
                and all(isinstance(row, dict) and row.get("passed") is True for row in browser))
            sources = []
            for source_path in self._paths(folder.as_posix(), "*-visual.json"):
                visual = _json_bytes(self._read(source_path))
                if isinstance(visual, dict) and visual.get("receiptSha256") == claim.get("sourceVisualReceiptSha256"):
                    _require(visual.get("status") == "passed" and visual.get("snapshotSha256") != snapshot
                        and visual["receiptSha256"] == _quality_sha({k: v for k, v in visual.items() if k != "receiptSha256"}))
                    source_browser = _json_bytes(self._read((folder / (visual["snapshotSha256"] + "-browser.json")).as_posix()))
                    _require(isinstance(source_browser, list) and len(source_browser) == len(browser)
                        and all(before.get("passed") is True and all(before.get(k) == after.get(k) for k in
                            ("sceneId", "viewport", "screenshotSha256")) for before, after in zip(source_browser, browser)))
                    sources.append(source_path)
            _require(len(sources) == 1)
            try:
                claim_at = int(datetime.fromisoformat(prior_claim["createdAt"].replace("Z", "+00:00")).timestamp() * 1000)
                recovery_at = int(datetime.fromisoformat(claim["createdAt"].replace("Z", "+00:00")).timestamp() * 1000)
                collision = claim["collisionReservation"]
                _require(collision.get("authorization_id") == claim.get("authorizationId")
                    and collision.get("state") == "settled" and type(collision.get("dispatched_at")) is int
                    and type(collision.get("settled_at")) is int
                    and collision["dispatched_at"] < collision["settled_at"] < claim_at
                    and repeated[0].get("startedAt", -1) >= claim_at and entry.get("startedAt", -1) >= recovery_at)
            except (KeyError, TypeError, ValueError):
                raise CourseFileWriteError("course_storage_review_predispatch_not_proven") from None
            accepted.append({"kind": "visual_predispatch", "claimPath": path, "claimSha256": _hash(claim_raw),
                "evidenceSha256": evidence_sha, "priorAttemptsSha256": prior_sha})
        _require(len(accepted) == 1, "course_storage_review_predispatch_not_proven")
        return accepted[0]

    def _preview_guard(self, conn, meta, classroom_id, *, required=False):
        preview_key = meta.get("previewKey")
        if not preview_key and not classroom_id:
            _require(not required)
            return
        rows = conn.execute("SELECT preview_key,classroom_id,status FROM learning_textbook_course_previews "
            "WHERE preview_key=? OR classroom_id=? FOR UPDATE", (preview_key or "", classroom_id or "")).fetchall()
        if required:
            _require(len(rows) == 1 and rows[0]["classroom_id"] == classroom_id
                and rows[0]["status"] in {"preview_ready", "review_required"})
        for row in rows:
            _require(not preview_key or row["preview_key"] == preview_key)
            published = conn.execute("SELECT content_key FROM learning_textbook_course_builds WHERE status='published' "
                "AND JSON_UNQUOTE(JSON_EXTRACT(input_json,'$.previewKey'))=? LIMIT 1 FOR UPDATE",
                (row["preview_key"],)).fetchone()
            _require(published is None, "course_storage_published_immutable")

    def _amendment(self, path, old_raw, new_raw, old, new):
        from services.course_file_store import course_glob
        from services.textbook_workbench_authoring import TextbookWorkbenchAuthoring, amendment_draft
        job = Path(path).parent
        state = _json_bytes(self._read((job / "state.json").as_posix()))
        _require(state.get("status") == "prepared" and not any(state.get(k) for k in
            ("sessionId", "stageId", "classroomId", "runtimeJobId", "existingArtifacts")))
        _require(not self._exists((job / "dispatch.json").as_posix()))
        candidates = list(course_glob(self.root / job / "amendments", "*"))
        _require(len(candidates) <= 128)
        matches = []
        for folder in candidates:
            if not _SHA.fullmatch(folder.name):
                continue
            try:
                intent = TextbookWorkbenchAuthoring._amendment_intent(folder)
            except ValueError:
                continue
            name = Path(path).name
            if (intent["files"].get("source-" + name, "").encode() == old_raw
                    and intent["files"].get("target-" + name, "").encode() == new_raw):
                amendment_draft(json.loads(intent["files"]["source-draft.json"]),
                                json.loads(intent["files"]["target-draft.json"]))
                source_frozen = json.loads(intent["files"]["source-frozen.json"])
                target_frozen = json.loads(intent["files"]["target-frozen.json"])
                _preserved(source_frozen, target_frozen, set(source_frozen) - {
                    "draftAmendmentId", "draftSha256", "draftCanonicalSha256", "requestSha256", "payloadSha256", "sceneContract"})
                matches.append(folder.name)
        _require(len(matches) == 1, "course_storage_amendment_required")
        return matches[0]

    def _formal_tts(self, request, plan, classroom_id):
        """Read an existing paid job; this adapter cannot dispatch or retry it."""
        from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
        from services.textbook_preview_audio import pronunciation_client_options
        job = _json_bytes(self._read(_NATIVE + "formal-audio/jobs/tts/" + _hash(request.encode()) + ".json"))
        _require(isinstance(job, dict) and job.get("schemaVersion") == "mira.openmaic.formal-audio-job.v1"
            and job.get("kind") == "tts" and job.get("requestId") == request
            and job.get("classroomId") == classroom_id
            and job.get("classroomContentSha256") == plan.get("classroomSha256"))
        return OpenMaicFullRuntimeClient._validate_formal_tts_response(
            {**job, "success": True}, request_id=request, **pronunciation_client_options(plan))

    def _audio_revision(self, folder, revision, old_raw, new_raw, classroom, parent, meta):
        from content.textbook_catalog import digest
        from content.textbook_preview_audio_contract import revision_audio_plan
        from services.textbook_preview_narration_revision import validate_patch, persisted
        _require(isinstance(revision, str) and bool(_SHA.fullmatch(revision)))
        archive = folder / "narration-revisions" / revision
        intent = _json_bytes(self._read((archive / "intent.json").as_posix()))
        required = {"source.json", "source-row.json", "target-text.json", "original-plan.json",
                    "original-receipts.json", "failed-audit.json", "plan.json"}
        _require(isinstance(intent, dict) and intent.get("schemaVersion") == "mira.textbook.preview-narration-intent.v1"
            and intent.get("revisionId") == revision and intent.get("previewKey") == parent["previewKey"]
            and intent.get("classroomId") == classroom["stage"]["id"]
            and intent.get("sha256") == digest({k: v for k, v in intent.items() if k != "sha256"})
            and isinstance(intent.get("files"), dict) and set(intent["files"]) == required)
        files = {name: self._read((archive / name).as_posix()) for name in sorted(required)}
        _require(all(_hash(body) == intent["files"][name] for name, body in files.items()))
        validate_patch(intent["patch"])
        _require(revision == digest({"previewKey": parent["previewKey"], "patch": intent["patch"],
            "failedAuditSha256": _hash(files["failed-audit.json"])}))
        source, child = _json_bytes(files["source.json"]), _json_bytes(files["plan.json"])
        _require(intent["patch"]["expectedSourceSha256"] == digest(source)
            and _json_bytes(files["original-plan.json"]) == parent
            and files["original-receipts.json"] == old_raw
            and self._read((archive / "receipts.json").as_posix()) == new_raw
            and persisted(_json_bytes(self._read((archive / "saved.json").as_posix()))) == persisted(classroom))
        expected = revision_audio_plan(parent, revision_id=revision,
            classroom_sha256=child.get("classroomSha256"), core_sha256=child.get("coreSha256"),
            frozen_input=parent.get("binding") or {"subject": "chinese"},
            policy_version=intent["patch"].get("policyVersion"))
        _require(child == expected and child["classroomSha256"] == digest(_json_bytes(files["target-text.json"])))
        return child

    def _audio_receipts(self, path, old, new, classroom_id, meta, old_raw, new_raw):
        from content.textbook_catalog import digest
        from services.textbook_preview_audio import (preserved_receipts, confirmed_success_transition,
            resolve_audio_contract, tts_request_id, core_content)
        _require(isinstance(old, list) and isinstance(new, list) and len(new) >= len(old))
        folder = Path(path).parent
        plan = _json_bytes(self._read((folder / "plan.json").as_posix()))
        contract = resolve_audio_contract(plan)
        _require(not meta.get("previewKey") or plan["previewKey"] == meta["previewKey"])
        classroom = _json_bytes(self._read(_NATIVE + "classrooms/" + classroom_id + ".json"))
        by_old = {entry.get("requestId"): entry for entry in old if isinstance(entry, dict)}
        _require(len(by_old) == len(old))
        revisions = {entry.get("narrationRevisionId") for entry in new if isinstance(entry, dict)
                     and entry.get("requestId") not in by_old and entry.get("narrationRevisionId") is not None}
        _require(len(revisions) <= 1)
        children = {revision: self._audio_revision(folder, revision, old_raw, new_raw, classroom, plan, meta)
                    for revision in revisions}
        _require(bool(children) or digest(core_content(classroom)) == plan["coreSha256"])
        actuals, identities = {}, {}

        def request_plan(receipt):
            return children.get(receipt.get("narrationRevisionId"), plan)

        def binding(receipt):
            request = receipt.get("requestId")
            if request not in identities:
                selected_plan = request_plan(receipt)
                given = receipt.get("previewAudioIdentity")
                attempts = [given.get("attempt")] if isinstance(given, dict) else range(1, 21)
                found = [attempt for attempt in attempts if type(attempt) is int and 1 <= attempt <= 20
                    and any(request == tts_request_id(selected_plan, scene["id"], action["id"], action["text"], attempt=attempt)
                        for scene in classroom["scenes"] for action in scene.get("actions", []) if action.get("type") == "speech")]
                _require(len(found) == 1)
                identities[request] = {"planSha256": digest(selected_plan), "attempt": found[0]}
            if "previewAudioIdentity" in receipt:
                _require(receipt["previewAudioIdentity"] == identities[request])
            return identities[request]

        def actual(receipt):
            request = receipt["requestId"]
            binding(receipt)
            if request not in actuals:
                actuals[request] = self._formal_tts(request, request_plan(receipt), classroom_id)
            value = actuals[request]
            _require(all(receipt.get(k) == v for k, v in value.items()))
            return value

        def confirm(prior, receipt):
            status, before = receipt.get("status"), prior.get("status")
            if before == status == "succeeded":
                # A duration/plan identity enriches the aggregate, never the
                # original terminal provider receipt or its immutable fields.
                _preserved(prior, receipt, set(prior) - {"durationSeconds", "previewAudioIdentity"})
                _require(set(receipt) - set(prior) <= {"durationSeconds", "previewAudioIdentity"})
                if prior.get("durationSeconds") is not None:
                    _require(receipt.get("durationSeconds") == prior["durationSeconds"])
                if prior.get("previewAudioIdentity") is not None:
                    _require(receipt.get("previewAudioIdentity") == prior["previewAudioIdentity"])
                if "previewAudioIdentity" in receipt:
                    binding(receipt)
                duration = receipt.get("durationSeconds")
                _require(duration is None or (type(duration) in {int, float} and math.isfinite(duration) and 0 < duration <= 3600))
                return True
            _require(before in {"unknown", "running", "ambiguous"} and status in {"running", "succeeded", "failed", "ambiguous"})
            _require(before != "ambiguous" or status == "succeeded")
            mutable = {"status", "audioSha256", "mimeType"}
            _preserved(prior, receipt, set(prior) - mutable)
            _require(all(prior.get(k) in (None, receipt.get(k)) for k in {"audioSha256", "mimeType"}))
            value = actual(receipt)
            if status == "succeeded" and not contract["legacy"]:
                class RecordedRuntime:
                    def get_formal_audio_tts(self, *_args, **_kwargs):
                        return value
                _require(confirmed_success_transition(request_plan(receipt), prior, receipt, RecordedRuntime(), classroom))
            return True

        merged = preserved_receipts(plan, old, new, confirm_transition=confirm)
        _require([entry.get("requestId") for entry in new[:len(old)]] == [entry.get("requestId") for entry in old])
        _require(list(merged.values()) == new)  # no omitted old fields or claims
        for receipt in new:
            prior = by_old.get(receipt["requestId"])
            if prior == receipt:
                continue
            status = receipt.get("status")
            _require(status in {"unknown", "running", "succeeded", "failed", "ambiguous"})
            if prior is None:
                binding(receipt)
                if status == "unknown":
                    _require(receipt.get("audioSha256") is None and receipt.get("mimeType") is None
                        and set(receipt) <= {"requestId", "status", "audioSha256", "mimeType", "previewAudioIdentity"})
                else:
                    actual(receipt)
            elif prior.get("status") == status == "succeeded":
                confirm(prior, receipt)
            elif prior != receipt:
                confirm(prior, receipt)

        return "audio_receipts_aggregate"

    def _pronunciation_rotation(self, path, old_raw, new_raw, classroom_id, meta, conn):
        """Rotate only the exact archived, provider-free pronunciation intent.

        This exception replaces aggregate pointers, never terminal paid jobs or
        their WAVs. Both original and target bytes remain immutable versions.
        """
        from content.textbook_catalog import canonical, digest
        from content.textbook_preview_audio_contract import new_pinyin_audio_plan
        from services.textbook_preview_audio import core_content
        from services.textbook_preview_pronunciation_revision import SCHEMA, PENDING, AUDIO_FIELDS, validate_patch, _evidence
        from services.textbook_preview_visual_revision import persisted
        folder = Path(path).parent
        _require(self._exists((folder / PENDING).as_posix()), "course_storage_pronunciation_rotation_not_proven")
        pending_raw = self._read((folder / PENDING).as_posix())
        pending = _json_bytes(pending_raw)
        _require(isinstance(pending, dict) and set(pending) == {"revisionId", "intentSha256"}
            and bool(_SHA.fullmatch(str(pending.get("revisionId")))))
        revision = pending["revisionId"]
        archive = folder / "pronunciation-revisions" / revision
        intent_raw = self._read((archive / "intent.json").as_posix())
        intent = _json_bytes(intent_raw)
        _require(isinstance(intent, dict) and intent.get("schemaVersion") == SCHEMA
            and set(intent) == {"schemaVersion", "revisionId", "previewKey", "classroomId", "patch", "files", "parentWavs", "sha256"}
            and intent.get("classroomId") == classroom_id and intent.get("previewKey") == meta.get("previewKey")
            and intent.get("revisionId") == revision and intent.get("sha256") == pending["intentSha256"]
            and intent["sha256"] == digest({k: v for k, v in intent.items() if k != "sha256"}))
        validate_patch(intent["patch"])
        _require(revision == digest({"previewKey": intent["previewKey"], "patch": intent["patch"]}))
        required = {"parent/plan.json", "parent/receipts.json", "parent/checkpoint.json", "parent/classroom-file.json",
                    "parent/row.json", "parent/classroom.json", "parent/result.json", "parent/input.json", "target.json", "plan.json"}
        required |= {"parent/human-feedback.json", "parent/approved-probes.json"}
        required |= {"parent/probes/" + label + "/" + name for label in
            ("e-base", "a-tone-2", "o-tone-2", "e-tone-2") for name in
            ("request.json", "intent.json", "receipt.json", "playback-validation.json", "audio.wav", "playback.wav")}
        _require(isinstance(intent.get("files"), dict) and required == set(intent["files"]))
        files = {}
        for name, sha in intent["files"].items():
            _relative(name)
            _require(bool(_SHA.fullmatch(str(sha))))
            body = self._read((archive / name).as_posix())
            _require(_hash(body) == sha)
            files[name] = body
        parent = _json_bytes(files["parent/plan.json"])
        source = _json_bytes(files["parent/classroom.json"])
        original_row = _json_bytes(files["parent/row.json"])
        frozen = _json_bytes(files["parent/input.json"])
        result = _json_bytes(files["parent/result.json"])
        receipts = _json_bytes(files["parent/receipts.json"])
        current_row = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE',
            (intent["previewKey"],)).fetchone()
        current_row = dict(current_row) if current_row is not None else None
        _require(current_row is not None and all(current_row.get(k) == original_row.get(k) for k in
            ("preview_key", "classroom_id", "input_json", "classroom_json", "classroom_sha256", "result_json", "status", "updated_at"))
            and original_row.get("status") == "review_required" and original_row.get("classroom_id") == classroom_id
            and original_row.get("classroom_sha256") == digest(source)
            and original_row.get("classroom_json", "").encode() == files["parent/classroom.json"]
            and original_row.get("input_json", "").encode() == files["parent/input.json"]
            and original_row.get("result_json", "").encode() == files["parent/result.json"])
        _require(parent.get("previewKey") == intent["previewKey"]
            and digest(parent) == intent["patch"]["parentPlanSha256"]
            and digest(source) == intent["patch"]["expectedSourceSha256"]
            and result.get("audioPartial") is True and not result.get("audioStopCode")
            and receipts == result.get("audioReceipts") and isinstance(receipts, list) and bool(receipts)
            and all(isinstance(r, dict) and r.get("status") == "succeeded" for r in receipts))
        evidence = _evidence(intent["patch"], intent["previewKey"], source, receipts,
            source_files={name.removeprefix("parent/"): body for name, body in files.items() if name.startswith("parent/")})
        _require(all(files.get("parent/" + name) == body for name, body in evidence.items()))
        target = deepcopy(source)
        used = set()
        for scene in target["scenes"]:
            for action in scene.get("actions", []):
                if action.get("type") == "speech":
                    if action.get("audioId"):
                        used.add(action["audioId"])
                    for field in AUDIO_FIELDS:
                        action.pop(field, None)
        _require(used == {r.get("requestId") for r in receipts} and len(used) == len(receipts))
        wavs = intent.get("parentWavs")
        _require(isinstance(wavs, dict) and set(wavs) == {request + ".wav" for request in used})
        for receipt in receipts:
            name = receipt["requestId"] + ".wav"
            _require(bool(re.fullmatch(r"[A-Za-z0-9_-]+\.wav", name))
                and wavs[name] == receipt.get("audioSha256")
                and _hash(self._read(_NATIVE + "classrooms/" + classroom_id + "/audio/" + name)) == wavs[name])
        _require(_json_bytes(files["target.json"]) == target)
        expected = new_pinyin_audio_plan(preview_key=intent["previewKey"], classroom_sha256=digest(target),
            core_sha256=digest(core_content(target)), frozen_input=frozen, parent_plan=parent, revision_id=revision)
        _require(_json_bytes(files["plan.json"]) == expected)
        saved_raw = self._read((archive / "saved.json").as_posix())
        saved = _json_bytes(saved_raw)
        _require(persisted(saved) == persisted(target)
            and _json_bytes(self._read(_NATIVE + "classrooms/" + classroom_id + ".json")) == saved)
        name = Path(path).name
        expected_raw = files["plan.json"] if name == "plan.json" else canonical([]).encode()
        _require(name in {"plan.json", "receipts.json"}
            and old_raw == files["parent/" + name] and new_raw == expected_raw)
        return {"kind": "pronunciation_rotation", "revisionId": revision, "intentSha256": _hash(intent_raw),
            "pendingSha256": _hash(pending_raw), "savedSha256": _hash(saved_raw),
            "files": intent["files"], "parentWavs": wavs}

    def _policy(self, path, old_raw, new_raw, old, new, meta, conn):
        storage_id = storage_id_for(self.config.endpoint, self.config.bucket, self.config.region)
        bound = json.dumps({"sourcePathSha256": _hash(path.encode()), "sha256": _hash(old_raw)}, separators=(",", ":"))
        parent = conn.execute("SELECT scope_key FROM course_storage_scopes WHERE storage_id=? "
            "AND JSON_UNQUOTE(JSON_EXTRACT(scope_json,'$.status'))='published' "
            "AND JSON_CONTAINS(bindings_json,?) LIMIT 1 FOR UPDATE", (storage_id, bound)).fetchone()
        _require(parent is None, "course_storage_published_immutable")
        native = path.removeprefix(_NATIVE) if path.startswith(_NATIVE) else ""
        classroom = re.fullmatch(r"classrooms/([A-Za-z0-9_-]+)\.json", native)
        audio = re.fullmatch(r"classrooms/([A-Za-z0-9_-]+)/textbook-preview-audio/(checkpoint|receipts|plan)\.json", native)
        job = re.fullmatch(r"formal-audio/jobs/(tts|asr)/([a-f0-9]{64})\.json", native)
        ledger = re.fullmatch(r"formal-quality-reviews/[a-f0-9]{64}/attempts\.json", native)
        review_artifact = re.fullmatch(r"formal-quality-reviews/[a-f0-9]{64}/([a-f0-9]{64})(-browser)?\.json", native)
        author = re.fullmatch(r"output/.+/authoring-job/(state|draft|frozen|saved-([A-Za-z0-9_-]+))\.json", path)
        cid = classroom[1] if classroom else audio[1] if audio else meta.get("classroomId")
        _require(meta.get("status") != "published", "course_storage_published_immutable")
        _require(meta.get("status") in {"generated_saved", "preview_ready", "review_required", "prepared", "running", "generating"})
        self._preview_guard(conn, meta, cid, required=bool(classroom or audio))
        if classroom or (audio and audio[2] == "checkpoint"):
            _require(not cid.startswith("tbpub_"), "course_storage_published_immutable")
            _require(isinstance(old, dict) and isinstance(new, dict)
                and old.get("stage", {}).get("id") == cid and new.get("stage", {}).get("id") == cid
                and old.get("id") == new.get("id") and isinstance(new.get("scenes"), list))
            return "saved_preview_classroom"
        if audio:
            if audio[2] == "plan" or (isinstance(old, list) and bool(old) and new == []):
                return self._pronunciation_rotation(path, old_raw, new_raw, cid, meta, conn)
            return self._audio_receipts(path, old, new, cid, meta, old_raw, new_raw)
        if job:
            _require(isinstance(old, dict) and isinstance(new, dict)
                and old.get("schemaVersion") == "mira.openmaic.formal-audio-job.v1"
                and old.get("kind") == job[1] and isinstance(old.get("requestId"), str)
                and _hash(old["requestId"].encode()) == job[2]
                and old.get("state") == "running" and new.get("state") in {"running", "succeeded", "failed", "ambiguous"})
            result_fields = {"audioSha256", "mimeType", "assetId", "assetFileName", "sizeBytes", "providerRequestId",
                "providerUsage", "providerAudioSha256", "pcmSha256", "audioNormalization", "transcriptSha256", "transcript"}
            _preserved(old, new, set(old) - {"state", "updatedAt", "completedAt", "providerCompletedAt", "downloadAttemptedAt", "safeErrorCode"}
                - {key for key in result_fields if old.get(key) is None})
            return "running_audio_job"
        if ledger:
            return self._review_ledger(path, old, new, old_raw, meta)
        if review_artifact:
            return self._review_result(Path(path).parent, review_artifact[1], old_raw, new, new_raw,
                                       browser=bool(review_artifact[2]))
        if author:
            kind = author[1]
            if kind in {"draft", "frozen"}:
                return "traceable_amendment:" + self._amendment(path, old_raw, new_raw, old, new)
            if kind.startswith("saved-"):
                state = _json_bytes(self._read((Path(path).parent / "state.json").as_posix()))
                _require(state.get("status") in {"session_queued", "session_running", "session_pending", "session_generating"})
                _require(isinstance(old, dict) and isinstance(new, dict)
                    and old.get("stage", {}).get("id") == author[2]
                    and new.get("stage", {}).get("id") == author[2]
                    and old.get("id") == new.get("id") and isinstance(new.get("scenes"), list))
                return "running_authoring_snapshot"
            _require(isinstance(old, dict) and isinstance(new, dict))
            before, after = old.get("status"), new.get("status")
            active = {"prepared", "reuse_review_required", "dispatch_unknown", "session_queued", "session_pending", "session_running", "session_generating"}
            terminal = {"saved_stage_available", "session_succeeded", "session_failed", "session_cancelled"}
            _require(before in active | terminal and after in active | terminal)
            _require(before == after or (before in active and after != "prepared"))
            _preserved(old, new, {"sessionId", "stageId", "classroomId", "runtimeJobId", "requestSha256", "payloadSha256", "ownerFingerprint"})
            if old.get("savedStages"):
                _require(all(entry in new.get("savedStages", []) for entry in old["savedStages"]))
            return "authoring_state"
        raise CourseFileWriteError("course_storage_write_forbidden")

    def write_bytes(self, path, raw, *, expected_sha256):
        _require(self.config.mode == "registry", "course_storage_write_mode_invalid", 409)
        path = self._source(path)
        _require(isinstance(expected_sha256, str) and bool(_SHA.fullmatch(expected_sha256)),
                 "course_storage_if_match_required", 428)
        _require(isinstance(raw, bytes) and len(raw) <= MAX_WRITE_BYTES,
                 "course_storage_file_too_large", 413)
        _require(path.endswith(".json"), "course_storage_write_forbidden")
        storage = storage_identity(self.config.endpoint, self.config.bucket, self.config.region)
        storage_id = storage_id_for(**storage)
        current = self.repository.resolve(path, storage_id)
        _require(current is not None, "course_storage_asset_not_found", 404)
        _require(current["mimeType"] == "application/json" and current["byteSize"] <= MAX_WRITE_BYTES)
        _require(current["sha256"] == expected_sha256, "course_storage_head_conflict")
        scope = self.repository.head_scope(path, storage_id)
        _require(scope is not None, "course_storage_record_invalid", 502)
        new = _json_bytes(raw)
        if _hash(raw) == expected_sha256:
            return {**current, "storage": storage}
        old_raw = self._read(path, expected_sha256)
        _require(isinstance(old_raw, bytes) and _hash(old_raw) == expected_sha256, "course_storage_source_changed", 502)
        old = _json_bytes(old_raw)
        meta = scope["metadata"]
        def preflight():
            with self.repository.database.transaction() as conn:
                return self._policy(path, old_raw, raw, old, new, meta, conn)
        policy = _retry_deadlock(preflight)
        directory = _relative(meta.get("storageDirectory"), max_bytes=800)
        title = re.sub(r'[\\/:*?"<>|#%\x00-\x1f\x7f-\x9f]', "-", str(meta.get("title") or directory.rsplit("/", 1)[-1])).strip(" .")[:80]
        while len(title.encode("utf-8")) > 140:
            title = title[:-1]
        _require(bool(title), "course_storage_directory_invalid", 502)
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        key = directory + "/" + title + "-工作记录-" + now + "-" + uuid.uuid4().hex[:8] + ".json"
        locator = self.uploader.upload(object_key=key, raw=raw, storage=storage)
        digest = _hash(raw)
        version = {k: deepcopy(v) for k, v in meta.items() if k in
            {"previewKey", "contentKey", "classroomId", "courseId", "courseVersion", "status", "storageDirectory", "title"}}
        version.update(scopeKey=_hash(("mira.course-file-write.v1:" + key).encode()),
            sourceKind="course_file_version", sourceDigest=digest, previousScopeKey=scope["scopeKey"],
            previousSha256=expected_sha256, writePolicy=policy, writtenAt=now)
        record = {"sourcePath": path, "sha256": digest, "byteSize": len(raw), "mimeType": "application/json", "locator": locator}
        def guard(conn):
            _require(self._policy(path, old_raw, raw, old, new, meta, conn) == policy)
        try:
            _retry_deadlock(lambda: self.repository.compare_and_activate(version, [record], storage_id,
                expected_old_sha=expected_sha256, expected_scope_key=scope["scopeKey"], before_activate=guard))
        except CourseStorageRegistryError as error:
            code = str(error)
            raise CourseFileWriteError(code if code in {"course_storage_head_conflict", "course_storage_head_not_found"}
                else "course_storage_version_commit_failed", 409) from None
        # Return the exact committed version, never a concurrently advanced head.
        result = self.repository.resolve(path, storage_id, expected_sha=digest)
        _require(result is not None, "course_storage_version_commit_failed", 502)
        return {**result, "storage": storage}
