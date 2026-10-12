"""Paid, fenced vision observations over exact public textbook source receipts.

Model output remains a candidate. It cannot approve its own catalog or publish
courseware. A durable request prevents accidental duplicate paid dispatch.
"""
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from io import BytesIO
import json
from pathlib import Path
import urllib.error
import urllib.request

from PIL import Image

from content.textbook_catalog import digest
from services.textbook_source_acquisition import immutable, save_json


PROMPT = Path(__file__).resolve().parents[1] / "prompts/textbook-source-review.v2.json"


def verified_picture(receipt):
    raw = Path(receipt["path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != receipt["sha256"] or len(raw) != receipt["bytes"]:
        raise ValueError("source_page_bytes_changed")
    with Image.open(BytesIO(raw)) as picture:
        picture.load()
        picture = picture.convert("RGB")
        picture.thumbnail((1600, 2200))
        encoded = BytesIO()
        picture.save(encoded, format="JPEG", quality=91)
    return "data:image/jpeg;base64," + base64.b64encode(encoded.getvalue()).decode()


def observe_directory(source, output, config):
    source = Path(source).resolve()
    evidence = json.loads(source.read_text())
    if evidence["status"] != "source_pages_ready_for_review" or not evidence["pages"]:
        raise ValueError("source_pages_not_ready")
    root = Path(output).resolve() / evidence["taskId"]
    root.mkdir(parents=True, exist_ok=True)
    prompt = json.loads(PROMPT.read_text())
    metadata = {"schemaVersion": "mira.textbook.source-observation-request.v1", "taskId": evidence["taskId"],
                "binding": evidence["binding"], "sourceReceiptPath": str(source),
                "sourceReceiptSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "promptSha256": digest(prompt), "provider": config.HOMEWORK_VISION_PROVIDER,
                "model": config.HOMEWORK_VISION_MODEL, "candidateOnly": True}
    request_file, response_file = root / "request.json", root / "response.json"
    if request_file.exists():
        if json.loads(request_file.read_text()) != metadata:
            raise ValueError("source_review_request_changed")
        if not response_file.exists():
            return {"taskId": evidence["taskId"], "status": "unacknowledged_call_fenced"}
    else:
        content = [{"type": "text", "text": json.dumps({"exactCatalogBinding": evidence["binding"],
            "officialMetadataTitle": evidence.get("title"), "instructions": prompt["directory"]}, ensure_ascii=False)}]
        for page in evidence["pages"]:
            content.extend([{"type": "text", "text": "previewKey=" + page["key"]},
                            {"type": "image_url", "image_url": {"url": verified_picture(page)}}])
        if config.HOMEWORK_VISION_PROVIDER not in {"qwen", "dashscope"} or not config.HOMEWORK_VISION_API_KEY:
            raise ValueError("configured_source_vision_provider_required")
        payload = {"model": config.HOMEWORK_VISION_MODEL, "messages": [
            {"role": "system", "content": prompt["system"]}, {"role": "user", "content": content}],
            "max_tokens": 9000, "temperature": 0.1, "enable_thinking": False,
            "response_format": {"type": "json_object"}}
        request = urllib.request.Request(config.HOMEWORK_VISION_BASE_URL.rstrip("/") + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode(), method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + config.HOMEWORK_VISION_API_KEY})
        # Exactly one sender owns this reservation, even across concurrent CLIs.
        with request_file.open("x") as stream:
            stream.write(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                raw = response.read(2 * 1024**2 + 1)
            immutable(response_file, raw)
        except Exception as exc:
            save_json(root / "dispatch-error.json", {"type": type(exc).__name__, "httpStatus": getattr(exc, "code", None),
                "automaticRedispatchAllowed": False})
            return {"taskId": evidence["taskId"], "status": "unacknowledged_call_fenced", "errorType": type(exc).__name__}
    raw = response_file.read_bytes()
    if len(raw) > 2 * 1024**2:
        raise ValueError("source_observation_response_too_large")
    envelope = json.loads(raw)
    choice = envelope["choices"][0]
    if choice.get("finish_reason") != "stop":
        return {"taskId": evidence["taskId"], "status": "incomplete_response_preserved"}
    observation = json.loads(choice["message"]["content"])
    keys = {p["key"] for p in evidence["pages"]}
    if (observation.get("schemaVersion") != "mira.textbook.directory-observation.v1"
            or type(observation.get("completeDirectory")) is not bool
            or type(observation.get("identityConflict")) is not bool
            or not isinstance(observation.get("units"), list)
            or not isinstance(observation.get("uncertainties"), list)):
        raise ValueError("source_observation_invalid")
    for page in observation.get("pages", []):
        if page.get("previewKey") not in keys:
            raise ValueError("invented_source_page_reference")
    for unit in observation["units"]:
        for item in [unit, *unit.get("lessons", [])]:
            if not isinstance(item.get("title"), str) or not item["title"].strip() or item.get("sourcePreviewKey") not in keys:
                raise ValueError("directory_item_missing_exact_source")
            if item.get("printedPage") is not None and (type(item["printedPage"]) is not int or item["printedPage"] < 0):
                raise ValueError("directory_printed_page_invalid")
    save_json(root / "observation.json", {**observation, "request": metadata,
        "responseSha256": hashlib.sha256(raw).hexdigest(), "usage": envelope.get("usage"),
        "reviewStatus": "candidate", "publicationAllowed": False})
    return {"taskId": evidence["taskId"], "status": "observation_ready", "completeDirectory": observation["completeDirectory"],
            "identityConflict": observation["identityConflict"], "units": len(observation["units"]),
            "leaves": sum(len(u.get("lessons", [])) or 1 for u in observation["units"]),
            "uncertainties": len(observation["uncertainties"])}


def observe_sources(sources, output, config, *, concurrency=2, emit=print):
    def work(source):
        try:
            return observe_directory(source, output, config)
        except Exception as exc:
            return {"source": str(source), "status": "observation_needs_review", "errorType": type(exc).__name__,
                    "reason": str(exc) if isinstance(exc, ValueError) else "Inspect preserved response"}
    counts = {}
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for future in as_completed([pool.submit(work, path) for path in sources]):
            result = future.result()
            counts[result["status"]] = counts.get(result["status"], 0) + 1
            emit({"finished": sum(counts.values()), "total": len(sources), "counts": counts, **result})
