#!/usr/bin/env python3
"""Prepare synthetic samples; run at most three paid submits only with --execute.

No family/student data or database writes. Reuse the SAME private output folder
to resume polls. A dispatched submit without durable JobIds is never replayed.
These printed samples verify transport/receipts, not handwriting quality.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from integrations.ai.tencent_homework_provider import (
    TencentHomeworkProvider, TencentConfigurationError, TencentKnownError,
    TencentQueryError, TencentSubmissionUnknown, SUBMIT_QUESTION, SUBMIT_ESSAY,
    load_tencent_credentials,
)

SCHEMA = "mira.tencent-homework-smoke.v1"
KINDS = ("questions", "essay-zh", "essay-en")
SAMPLE_LINES = {
    "questions": ["Synthetic arithmetic worksheet", "1 + 2 = 4", "2 + 3 = 5"],
    "essay-zh": ["公园里的小事", "星期六，我去公园看春天。", "小鸟在树上唱歌，我走到湖边。",
                 "花儿开的很漂亮。", "我把垃级放进垃圾桶，公园又干净了。", "我觉得这是一件快乐的小事。"],
    "essay-en": ["A small good deed", "I go to the park yesterday.", "We saw a red bird by the lake.",
                 "The flowers was bright.", "I picked up a paper bag and put it in the bin.", "I felt happy."],
}


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")


def private_write(path, data):
    """Atomically replace a private file and fsync file AND containing directory."""
    path = Path(path)
    if path.is_symlink():
        raise TencentConfigurationError("UnsafeOutputFile")
    temporary = path.parent / ("." + path.name + "." + uuid.uuid4().hex)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


def _font(size, explicit=None, *, chinese=False):
    from PIL import ImageFont
    candidates = ([explicit] if explicit else [
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf" if not chinese else None,
    ])
    for value in candidates:
        if value and Path(value).is_file():
            return ImageFont.truetype(value, size)
    if chinese:
        raise TencentConfigurationError("LocalChineseFontRequired")
    return ImageFont.load_default(size=size)


def sample_image(kind, *, font_path=None):
    from PIL import Image, ImageDraw
    import io
    image = Image.new("RGB", (1400, 1800), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 55), "ORIGINAL SYNTHETIC TEST - NO PERSONAL DATA",
              font=_font(32, font_path), fill="#555555")
    for index, line in enumerate(SAMPLE_LINES[kind]):
        size = 110 if kind == "questions" and index else (52 if kind == "essay-zh" else 43)
        y = 260 + index * (370 if kind == "questions" else 170)
        draw.text((90, y), line, font=_font(size, font_path, chinese=kind == "essay-zh"), fill="#111111")
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


class SmokeRun:
    def __init__(self, folder, *, selected=KINDS, font_path=None):
        self.folder = Path(folder)
        if not self.folder.is_absolute() or self.folder.is_symlink():
            raise TencentConfigurationError("AbsolutePrivateOutputFolderRequired")
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.folder, 0o700)
        self._lock_fd = os.open(self.folder / "run.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self._lock_fd)
            self._lock_fd = None
            raise TencentConfigurationError("RunAlreadyLocked") from None
        self.state_path = self.folder / "state.json"
        if self.state_path.is_symlink():
            raise TencentConfigurationError("UnsafeStateFile")
        if self.state_path.exists():
            try:
                self.state = json.loads(self.state_path.read_bytes())
            except (OSError, ValueError):
                raise TencentConfigurationError("InvalidDurableState") from None
            if self.state.get("schema") != SCHEMA or self.state.get("source") != "synthetic_printed":
                raise TencentConfigurationError("UnexpectedDurableState")
            if not isinstance(self.state.get("cases"), dict) or set(self.state["cases"]) - set(KINDS):
                raise TencentConfigurationError("InvalidDurableState")
        else:
            self.state = {"schema": SCHEMA, "source": "synthetic_printed", "submitCount": 0,
                          "pollCount": 0, "lastEssayDispatch": 0, "cases": {}}
        self.selected = tuple(selected)
        for kind in self.selected:
            path = self.folder / (kind + ".png")
            case = self.state["cases"].get(kind)
            if case:
                if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != case.get("sampleSha256"):
                    raise TencentConfigurationError("SyntheticSourceChanged")
                continue
            image = sample_image(kind, font_path=font_path)
            private_write(path, image)
            self.state["cases"][kind] = {"status": "prepared", "sampleSha256": hashlib.sha256(image).hexdigest(),
                                         "jobIds": [], "jobs": {}, "receipts": []}
        self.save()

    def save(self):
        private_write(self.state_path, _json_bytes(self.state))

    def close(self):
        if getattr(self, "_lock_fd", None) is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    def __del__(self):
        self.close()

    def callback(self, kind):
        def persist(action, raw, metadata):
            name = kind + "-" + action + "-" + uuid.uuid4().hex + ".receipt.json"
            private_write(self.folder / name, raw)
            self.state["cases"][kind]["receipts"].append({"file": name, **metadata})
            self.save()
        return persist

    def _record_submit(self, case, result):
        case.update(status="submitted", jobIds=result["jobIds"], providerRequestId=result["providerRequestId"])
        case["jobs"] = {identity: "WAIT" for identity in result["jobIds"]}
        self.save()

    def _recover_dispatch(self, provider, kind, case):
        action = SUBMIT_QUESTION if kind == "questions" else SUBMIT_ESSAY
        receipt = next((r for r in reversed(case["receipts"]) if r.get("action") == action), None)
        if receipt is None:
            case["status"] = "submission_unknown"
            self.save()
            return False
        # Receipt filenames come only from this run, never from the provider.
        name = receipt.get("file", "")
        if Path(name).name != name or not name.endswith(".receipt.json"):
            raise TencentConfigurationError("InvalidDurableReceiptPath")
        try:
            result = provider.parse_receipt(action, (self.folder / name).read_bytes(), http_status=receipt["httpStatus"])
            self._record_submit(case, result)
            return True
        except TencentKnownError as exc:
            case.update(status="known_rejection", errorCode=exc.code)
        except (TencentSubmissionUnknown, OSError, KeyError):
            case["status"] = "submission_unknown"
        self.save()
        return False

    def execute(self, provider, *, max_polls=40, poll_interval=5, sleep=time.sleep, clock=time.time):
        if not 1 <= max_polls <= 40 or not 2 <= poll_interval <= 30:
            raise TencentConfigurationError("InvalidSmokeBounds")
        if not 0 <= self.state.get("submitCount", -1) <= 3 or not 0 <= self.state.get("pollCount", -1) <= 40:
            raise TencentConfigurationError("InvalidDurableCounters")
        # An ambiguous paid dispatch blocks further submits, even for other cases.
        for kind, case in self.state["cases"].items():
            if case["status"] == "dispatching":
                self._recover_dispatch(provider, kind, case)
            if case["status"] == "submission_unknown":
                return self.summary()
        for kind in self.selected:
            case = self.state["cases"][kind]
            if case["status"] != "prepared":
                continue
            if self.state["submitCount"] >= 3:
                break
            if kind != "questions" and self.state["lastEssayDispatch"]:
                wait = 31 - (clock() - self.state["lastEssayDispatch"])
                if wait > 0:
                    sleep(wait)
            case["status"] = "dispatching"
            self.state["submitCount"] += 1
            if kind != "questions":
                self.state["lastEssayDispatch"] = clock()
            self.save()  # Durable intent before any provider call.
            try:
                method = provider.submit_question if kind == "questions" else provider.submit_essay
                result = method(self.folder / (kind + ".png"), receipt_callback=self.callback(kind))
                self._record_submit(case, result)
            except TencentConfigurationError as exc:
                case.update(status="not_dispatched", errorCode=exc.code)
                self.save()
            except TencentKnownError as exc:
                case.update(status="known_rejection", errorCode=exc.code)
                self.save()
            except TencentSubmissionUnknown as exc:
                case.update(status="submission_unknown", errorCode=exc.code)
                self.save()
                return self.summary()
        # Both this invocation and the durable run are bounded by 40 query calls.
        used = 0
        while used < max_polls and self.state["pollCount"] < 40:
            pending = [(kind, identity) for kind in self.selected
                       for identity, status in self.state["cases"][kind]["jobs"].items() if status in {"WAIT", "RUN"}]
            if not pending:
                break
            for kind, identity in pending:
                if used >= max_polls or self.state["pollCount"] >= 40:
                    break
                case = self.state["cases"][kind]
                self.state["pollCount"] += 1
                used += 1
                self.save()
                try:
                    method = provider.describe_question if kind == "questions" else provider.describe_essay
                    result = method(identity, receipt_callback=self.callback(kind))
                    case["jobs"][identity] = result["status"]
                    if result["status"] == "FAIL":
                        case["errorCode"] = result.get("errorCode", "ProviderError")
                except TencentQueryError:
                    case["lastQueryError"] = "query_unavailable"
                except TencentKnownError as exc:
                    case.update(lastQueryError="known_rejection", errorCode=exc.code)
                    # Invalid identity/auth errors need investigation, not 40 retries.
                    self.save()
                    return self.summary()
                states = tuple(case["jobs"].values())
                if states and all(value in {"DONE", "FAIL"} for value in states):
                    case["status"] = "completed" if all(value == "DONE" for value in states) else "failed"
                self.save()
            if used < max_polls and self.state["pollCount"] < 40 and any(
                status in {"WAIT", "RUN"} for kind in self.selected for status in self.state["cases"][kind]["jobs"].values()
            ):
                sleep(poll_interval)
        return self.summary()

    def summary(self):
        return {"schema": SCHEMA, "synthetic": True, "submitCount": self.state["submitCount"],
                "pollCount": self.state["pollCount"], "cases": [
                    {"kind": kind, "status": case["status"], "jobCount": len(case["jobIds"]),
                     "doneJobs": sum(status == "DONE" for status in case["jobs"].values()),
                     "receiptCount": len(case["receipts"])} for kind, case in self.state["cases"].items()]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, help="Explicit absolute private run folder; reuse for recovery")
    parser.add_argument("--kind", choices=("all", *KINDS), default="all")
    parser.add_argument("--credentials-csv", help="One exact absolute CSV; otherwise credentials come from environment")
    parser.add_argument("--font-path", help="Optional local CJK font for synthetic samples")
    parser.add_argument("--execute", "--execute-paid-validation", dest="execute", action="store_true")
    parser.add_argument("--max-polls", type=int, default=40)
    parser.add_argument("--poll-interval", type=float, default=5)
    args = parser.parse_args(argv)
    run = None
    try:
        run = SmokeRun(args.output_dir, selected=KINDS if args.kind == "all" else (args.kind,), font_path=args.font_path)
        if args.execute:
            if args.credentials_csv:
                sid, skey = load_tencent_credentials(args.credentials_csv)
                provider = TencentHomeworkProvider(secret_id=sid, secret_key=skey)
            else:
                provider = TencentHomeworkProvider.from_config()
            summary = run.execute(provider, max_polls=args.max_polls, poll_interval=args.poll_interval)
        else:
            summary = run.summary()
            summary["networkExecuted"] = False
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if not args.execute or all(x["status"] == "completed" for x in summary["cases"] if x["kind"] in run.selected) else 2
    except (TencentConfigurationError, OSError, ImportError, ValueError):
        # No traceback, path, CSV content, provider message or credential value.
        print(json.dumps({"schema": SCHEMA, "status": "local_preflight_failed"}))
        return 2
    finally:
        if run:
            run.close()


if __name__ == "__main__":
    raise SystemExit(main())
