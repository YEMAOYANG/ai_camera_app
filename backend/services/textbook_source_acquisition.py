"""Resumable acquisition of exact, publicly declared textbook source pages.

Source pages are private alignment evidence. Acquisition does not approve a
directory, create a teaching scope, change a database, or publish source art.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import shutil
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from content.textbook_catalog import digest, validate_manifest


UUID = re.compile(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}\Z")
HOSTS = {"s-file-1.ykt.cbern.com.cn", *(f"r{i}-ndr.ykt.cbern.com.cn" for i in (1, 2, 3))}
PAGE = re.compile(r"Slide([1-9][0-9]{0,3})\Z")


def immutable(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("source_evidence_conflict")
        return
    with path.open("xb") as stream:
        stream.write(raw)


def save_json(path, value):
    immutable(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class TextbookSourceAcquisition:
    def __init__(self, output, *, maximum_bytes=2 * 1024**3, minimum_free_bytes=3 * 1024**3):
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.maximum_bytes, self.minimum_free_bytes = maximum_bytes, minimum_free_bytes
        self.bytes = 0
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, url, maximum):
        p = urlsplit(url)
        if (p.scheme != "https" or p.hostname not in HOSTS or p.username or p.password
                or p.port not in (None, 443) or p.query or p.fragment):
            raise ValueError("unapproved_public_source_url")
        if self.stop.is_set():
            raise ValueError("source_acquisition_stopped")
        if shutil.disk_usage(self.output).free < self.minimum_free_bytes:
            self.stop.set()
            raise ValueError("preserving_free_disk_space")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,image/*"})
        try:
            with self.opener.open(req, timeout=30) as response:
                raw = response.read(maximum + 1)
                mime = response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                self.stop.set()
            raise
        with self.lock:
            self.bytes += len(raw)
            if self.bytes > self.maximum_bytes:
                self.stop.set()
                raise ValueError("source_acquisition_byte_budget")
        if len(raw) > maximum:
            raise ValueError("source_response_size_limit")
        return raw, mime

    def asset(self, url, suffix, maximum, *, receipt_path):
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            raw = Path(receipt["path"]).read_bytes()
            if (receipt["url"] != url or len(raw) != receipt["bytes"]
                    or hashlib.sha256(raw).hexdigest() != receipt["sha256"]):
                raise ValueError("saved_source_evidence_changed")
            return receipt, raw
        raw, mime = self.request(url, maximum)
        sha = hashlib.sha256(raw).hexdigest()
        path = self.output / "assets" / (sha + suffix)
        immutable(path, raw)
        receipt = {"url": url, "path": str(path), "sha256": sha, "bytes": len(raw), "mimeType": mime}
        save_json(receipt_path, receipt)
        return receipt, raw

    def book(self, task, *, mode, front_pages=8):
        manifest = validate_manifest(json.loads(Path(task["sourcePaths"][0]).read_text()))
        if digest(manifest) != task["manifestSha256"] or any(
                validate_manifest(json.loads(Path(p).read_text())) != manifest for p in task["sourcePaths"]):
            raise ValueError("exact_source_manifest_changed")
        if any(task["scope"].get(k) != manifest[k] for k in (
                "editionId", "revisionId", "gradeCode", "subject", "schoolSystem", "volume")):
            raise ValueError("source_binding_changed")
        rid = manifest["source"]["resourceId"]
        result = {"taskId": task["taskId"], "binding": task["scope"],
                  "manifestSha256": task["manifestSha256"], "resourceId": rid,
                  "coverage": manifest["coverage"]["status"], "pages": [], "sourceApproved": False}
        if not UUID.fullmatch(rid):
            return {**result, "status": "requires_publisher_source"}
        root = self.output / "books" / task["taskId"]
        metadata, raw = self.asset(
            "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/" + rid + ".json",
            ".json", 2 * 1024**2, receipt_path=root / "metadata.json")
        detail = json.loads(raw)
        if detail.get("id") != rid or detail.get("status") != "ONLINE":
            raise ValueError("exact_online_resource_required")
        previews = detail.get("custom_properties", {}).get("preview", {})
        if not isinstance(previews, dict):
            raise ValueError("declared_preview_map_invalid")
        result.update(metadata=metadata, title=detail.get("title"), availablePreviewCount=len(previews))
        keys = (["Slide" + str(i) for i in range(1, front_pages + 1)] if mode == "front"
                else sorted((k for k in previews if PAGE.fullmatch(k)), key=lambda k: int(PAGE.fullmatch(k)[1])))
        for key in keys:
            if key not in previews:
                result.setdefault("unavailableKeys", []).append(key)
                continue
            url = previews[key]
            if not isinstance(url, str):
                raise ValueError("declared_page_url_invalid")
            # The official metadata sometimes declares a shared image resource.
            # Preserve that fact for identity review; never invent a replacement
            # URL or treat reuse as proof that two editions have equal contents.
            same_resource_path = "/" + rid + ".t/" in urlsplit(url).path
            try:
                receipt, _ = self.asset(url, ".image", 4 * 1024**2, receipt_path=root / (key + ".json"))
            except urllib.error.HTTPError as exc:
                result.setdefault("unavailablePages", []).append({"key": key, "httpStatus": exc.code})
                if self.stop.is_set():
                    break
                continue
            if receipt["mimeType"] not in {"image/jpeg", "image/png", "image/webp"}:
                raise ValueError("declared_page_not_image")
            result["pages"].append({"key": key, **receipt, "metadataDeclaresSharedResource": not same_resource_path})
        result["status"] = "source_pages_ready_for_review" if result["pages"] else "source_unavailable"
        # Earlier acquisitions did not include the shared-resource marker. An
        # immutable existing receipt remains authoritative when its asset list
        # already contains the same pages; extension is stored separately.
        target = root / (mode + "-sources.json")
        if target.exists():
            previous = json.loads(target.read_text())
            if [(p["key"], p["sha256"]) for p in previous["pages"]] == [(p["key"], p["sha256"]) for p in result["pages"]]:
                return previous
        save_json(target, result)
        return result

    def run(self, tasks, *, mode, front_pages=8, concurrency=3, emit=print):
        counts = {}
        def work(task):
            try:
                return self.book(task, mode=mode, front_pages=front_pages)
            except Exception as exc:
                result = {"taskId": task["taskId"], "binding": task["scope"], "status": "source_unavailable",
                        "errorType": type(exc).__name__, "httpStatus": getattr(exc, "code", None),
                        "reason": str(exc) if isinstance(exc, ValueError) else "Read source acquisition receipts"}
                save_json(self.output / "errors" / task["taskId"] / (digest(result) + ".json"), result)
                return result
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(work, task): task for task in tasks}
            for future in as_completed(futures):
                result = future.result()
                counts[result["status"]] = counts.get(result["status"], 0) + 1
                emit({"finished": sum(counts.values()), "total": len(tasks), "counts": counts,
                      "editionId": result["binding"]["editionId"], "status": result["status"],
                      "httpStatus": result.get("httpStatus"), "reason": result.get("reason"),
                      "downloadedBytes": self.bytes})
        return counts
