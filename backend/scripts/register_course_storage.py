"""One-time registry import of current, verified courses; no upload or cleanup."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from core.config import AppConfig
from core.course_storage_config import CourseStorageConfig
from core.database import Database
from repositories.course_storage_repository import CourseStorageRepository, storage_id_for
from services.course_archive_queue import CourseArchiveQueue, _read
from services.course_storage_registration import archive_registration, media_registration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-courses", type=int, required=True)
    args = parser.parse_args()
    AppConfig.from_env()  # Backend-owned dotenv only.
    config = CourseStorageConfig.from_env()
    state = BACKEND / "data/course-storage"
    queue = CourseArchiveQueue(state, {"endpoint": config.endpoint, "bucket": config.bucket, "region": config.region})
    registrations = [media_registration(state, queue.storage)]
    with queue.lock():
        jobs = [json.loads(_read(p)) for p in queue.items.glob("*.json")]
        current = [j for j in jobs if j.get("priority", 99) <= 1 and j.get("status") == "complete"
                   and j.get("stagingPruned") is True and j["identity"]["storage"] == queue.storage]
        if len(current) != args.expected_courses:
            raise ValueError("course_storage_current_count_changed")
        for job in sorted(current, key=lambda j: j["key"]):
            registrations.append(archive_registration(queue, job))
        candidates = defaultdict(dict)
        media = {e["sourcePath"]: e["sha256"] for e in registrations[0][1]}
        for metadata, files in registrations:
            for entry in files:
                candidates[entry["sourcePath"]][entry["sha256"]] = (metadata["scopeKey"], entry)
        heads = defaultdict(dict)
        ambiguous, current_missing = [], []
        for path, versions in sorted(candidates.items()):
            checksum = media.get(path)
            local = BACKEND.parent / path
            if checksum is None and local.is_file():
                before = local.stat()
                with local.open("rb") as stream:
                    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
                after = local.stat()
                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_ino):
                    raise ValueError("course_storage_source_changed")
                if checksum not in versions:
                    current_missing.append(path)
                    continue
            if checksum is None:
                if len(versions) != 1:
                    ambiguous.append(path)
                    continue
                checksum = next(iter(versions))
            scope, _ = versions[checksum]
            heads[scope][path] = checksum
        summary = {"courses": len(current), "scopes": len(registrations), "paths": len(candidates),
            "versions": sum(map(len, candidates.values())), "ambiguous": ambiguous,
            "currentNotArchived": current_missing, "applied": False}
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        if ambiguous or current_missing:
            raise ValueError("course_storage_current_original_not_covered")
        if args.apply:
            repo = CourseStorageRepository(Database(AppConfig.from_env().DATABASE_URL))
            storage_id = storage_id_for(**queue.storage)
            for metadata, files in registrations:
                repo.register_scope(metadata, files, storage_id, activate=False)
            for scope, selected in sorted(heads.items()):
                repo.activate_heads(scope, selected, storage_id)
            print(json.dumps({**{k: v for k,v in summary.items() if k not in ("ambiguous", "currentNotArchived")}, "applied": True}), flush=True)


if __name__ == "__main__":
    main()
