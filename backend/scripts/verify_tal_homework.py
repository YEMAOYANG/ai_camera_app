#!/usr/bin/env python3
"""One private TAL grading smoke call; dry-run by default, never resubmit a run.

The caller supplies an HTTPS image URL. This tool never uploads local images,
loads application configuration, connects to a database, or changes providers.
Keep the output directory: its journal prevents replay of an uncertain paid call.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import sys
import time
from urllib.parse import urlencode, urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_tencent_homework import private_write

HOST = "openai.100tal.com"
PATH = "/aisvc/correct/open-correct/api/v1/correct/sse"
SCHEMA = "mira.tal-homework-smoke.v1"
MAX_BYTES = 8 * 1024 * 1024


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def signature(query, body, secret):
    values = {**query, "request_body": body.decode("utf-8")}
    text = "&".join(f"{key}={values[key]}" for key in sorted(values))
    return base64.b64encode(hmac.new((secret + "&").encode(), text.encode(), hashlib.sha1).digest()).decode()


def credentials(path=None):
    if path:
        file = Path(path)
        if not file.is_absolute() or file.is_symlink() or file.stat().st_mode & 0o077 or file.stat().st_size > 65536:
            raise ValueError("invalid credential file")
        value = json.loads(file.read_bytes())
        pair = value["access_key_id"], value["access_key_secret"]
    else:
        pair = os.environ.get("TAL_ACCESS_KEY_ID"), os.environ.get("TAL_ACCESS_KEY_SECRET")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 1024 or any(ord(c) < 32 for c in item) for item in pair):
        raise ValueError("invalid credentials")
    return pair


def image_binding(url, path):
    if url:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
            raise ValueError("HTTPS image URL required")
    return {"imageUrlSha256": hashlib.sha256(url.encode()).hexdigest() if url else None,
            "localImageSha256": hashlib.sha256(Path(path).read_bytes()).hexdigest() if path else None}


def _failure(value):
    if isinstance(value, list):
        return any(_failure(item) for item in value)
    if not isinstance(value, dict):
        return False
    return any((key == "execute_result" and item not in (0, "0")) or
               (key == "error" and bool(item)) or _failure(item) for key, item in value.items())


class Events:
    def __init__(self):
        self.pending = b""
        self.count = 0
        self.ended = self.failed = False
        self.questions = {}

    @staticmethod
    def identity(value):
        return ("uuid", value["uuid"]) if isinstance(value.get("uuid"), str) and value["uuid"] else (
            ("index", str(value["index"])) if type(value.get("index")) in (int, str) else None)

    @staticmethod
    def merge(target, item):
        if "correct_result" in item:
            target["result"] = item["correct_result"]
        if "bbox" in item:
            target["coordinates"] = bool(item["bbox"])

    def feed(self, chunk):
        self.pending += chunk
        # Decode complete events only, preserving split UTF-8 characters.
        while not self.ended:
            boundary = re.search(br"\r?\n\r?\n", self.pending)
            if boundary is None:
                return
            block, self.pending = self.pending[:boundary.start()], self.pending[boundary.end():]
            event, data = "message", []
            for line in block.decode("utf-8").splitlines():
                field, separator, value = line.partition(":")
                if separator and field == "event":
                    event = value.lstrip(" ")
                elif separator and field == "data":
                    data.append(value[1:] if value.startswith(" ") else value)
            if not data and event != "end":
                continue
            self.count += 1
            payload = json.loads("\n".join(data)) if data else {}
            if not isinstance(payload, dict):
                raise ValueError("invalid event")
            self.failed = self.failed or event == "error" or _failure(payload)
            results = payload.get("results", [])
            if not isinstance(results, list):
                raise ValueError("invalid results")
            for item in results:
                if not isinstance(item, dict) or self.identity(item) is None:
                    raise ValueError("missing question identity")
                question = self.questions.setdefault(self.identity(item), {"answers": {}})
                self.merge(question, item)
                answers = item.get("answers", [])
                if not isinstance(answers, list):
                    raise ValueError("invalid answers")
                # A finished question supplies the authoritative answer snapshot;
                # earlier bbox events can contain temporary answer identities.
                if "answers" in item and type(item.get("is_finish")) is int and item["is_finish"] == 1:
                    question["answers"] = {}
                for answer in answers:
                    if not isinstance(answer, dict) or self.identity(answer) is None:
                        raise ValueError("missing answer identity")
                    self.merge(question["answers"].setdefault(self.identity(answer), {}), answer)
            self.ended = event == "end"  # JSON event fields and [DONE] are not terminal receipts.

    def summary(self):
        records = [answer for question in self.questions.values()
                   for answer in (list(question["answers"].values()) or [question])]
        counts = {"ungradedCount": 0, "correctCount": 0, "incorrectCount": 0, "unansweredCount": 0, "unknownCount": 0}
        names = ("ungradedCount", "correctCount", "incorrectCount", "unansweredCount")
        for record in records:
            result = record.get("result")
            counts[names[result] if type(result) is int and 0 <= result <= 3 else "unknownCount"] += 1
        return {"questionCount": len(self.questions), "answerCount": sum(len(q["answers"]) for q in self.questions.values()),
                "coordinatesPresent": any(q.get("coordinates") for q in self.questions.values()) or any(r.get("coordinates") for r in records), **counts}


def https_stream(path, headers, body, timeout):
    """One TLS request, without redirects or retries; bound total read time."""
    deadline = time.monotonic() + timeout
    connection = http.client.HTTPSConnection(HOST, timeout=timeout, context=ssl.create_default_context())
    try:
        connection.request("POST", path, body=body, headers=headers)
        response = connection.getresponse()
        yield response.status, b""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            if connection.sock:
                connection.sock.settimeout(remaining)
            chunk = response.read1(65536)
            if not chunk:
                break
            yield response.status, chunk
    finally:
        connection.close()


def execute(folder, state, url, pair, *, account, device, timeout, transport):
    started = time.monotonic()
    body = encoded({"image_url_list": [{"image_url": url}]})
    query = {"access_key_id": pair[0], "timestamp": str(int(time.time() * 1000)), "signature_nonce": str(uuid.uuid4())}
    query["signature"] = signature(query, body, pair[1])
    path = PATH + "?" + urlencode(query)
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream", "Cache-Control": "no-cache",
               "Connection": "keep-alive", "X-TAL-AccountId": account, "X-TAL-DeviceId": device, "X-Channel": "mira-smoke"}
    events, total, source, response_hash = Events(), 0, None, hashlib.sha256()
    state.update(status="dispatching", submitCount=1, responseComplete=False,
                 requestSha256=hashlib.sha256(body).hexdigest())
    private_write(folder / "state.json", encoded(state))  # Durable intent before network access.
    try:
        descriptor = os.open(folder / "response.sse", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as receipt:
            directory = os.open(folder, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            source = transport(path, headers, body, timeout)
            for status, chunk in source:
                if state.get("httpStatus") != status:
                    state["httpStatus"] = status
                    private_write(folder / "state.json", encoded(state))
                bounded = chunk[:MAX_BYTES - total]
                receipt.write(bounded)
                receipt.flush()
                os.fsync(receipt.fileno())
                total += len(bounded)
                response_hash.update(bounded)
                if len(bounded) != len(chunk):
                    raise ValueError("response limit")
                if status != 200:
                    continue  # Preserve non-SSE rejection bodies before classifying.
                events.feed(chunk)
                if events.ended:
                    break
        state["responseComplete"] = state.get("httpStatus") != 200 or events.ended
        state["status"] = ("http_rejected" if state.get("httpStatus") not in (None, 200)
                           else "provider_error" if events.failed else "incomplete" if not events.ended
                           else "completed" if events.questions else "no_results")
    except (Exception, KeyboardInterrupt):
        state["status"] = "http_rejected" if state.get("httpStatus") not in (None, 200) else "submission_unknown"
    finally:
        if source is not None and hasattr(source, "close"):
            source.close()
        state.update(eventCount=events.count, responseBytes=total, responseSha256=response_hash.hexdigest(),
                     elapsedSeconds=round(time.monotonic() - started, 3), summary=events.summary())
        private_write(folder / "state.json", encoded(state))
    return state


def main(argv=None, *, transport=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--image-url")
    parser.add_argument("--image-path", help="Optional local image hash only; never uploaded")
    parser.add_argument("--credentials-file", help="Absolute private JSON file; otherwise use TAL_ACCESS_KEY_ID/SECRET")
    parser.add_argument("--account-id", default="mira-smoke")
    parser.add_argument("--device-id", default="mira-smoke")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    lock = None
    try:
        folder = Path(args.output_dir)
        if not folder.is_absolute() or folder.is_symlink() or not 1 <= args.timeout_seconds <= 120:
            raise ValueError("invalid local arguments")
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", item) for item in (args.account_id, args.device_id)):
            raise ValueError("invalid business identity")
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        folder.chmod(0o700)
        lock = os.open(folder / "run.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = folder / "state.json"
        if state_path.is_symlink():
            raise ValueError("invalid state path")
        state = json.loads(state_path.read_bytes()) if state_path.exists() else {"schema": SCHEMA, "status": "prepared", "submitCount": 0}
        if state.get("schema") != SCHEMA or state.get("status") != "prepared" or type(state.get("submitCount")) is not int or state["submitCount"] != 0:
            print(encoded({"status": "replay_blocked"}).decode())
            return 2
        binding = image_binding(args.image_url, args.image_path)
        if any(state.get(key) is not None and value is not None and state[key] != value for key, value in binding.items()):
            raise ValueError("prepared source changed")
        state.update({key: value for key, value in binding.items() if value is not None or key not in state})
        private_write(state_path, encoded(state))
        if args.execute:
            if not args.image_url:
                raise ValueError("image URL required")
            state = execute(folder, state, args.image_url, credentials(args.credentials_file), account=args.account_id,
                            device=args.device_id, timeout=args.timeout_seconds, transport=transport or https_stream)
        print(encoded({key: state[key] for key in ("status", "submitCount", "eventCount", "summary") if key in state}).decode())
        return 0 if not args.execute or state["status"] == "completed" else 2
    except (Exception, KeyboardInterrupt):
        print(encoded({"status": "local_preflight_failed"}).decode())
        return 2
    finally:
        if lock is not None:
            os.close(lock)


if __name__ == "__main__":
    raise SystemExit(main())
