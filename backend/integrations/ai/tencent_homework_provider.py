"""Tencent OCR grading jobs, with durable raw receipts and no submit retries.

Only the fixed official HTTPS endpoint is used. Provider text is untrusted data:
this adapter neither follows instructions in it nor treats suggestions as scores.
Receipt callbacks must durably save the body before returning. They receive no
credentials, authorization headers, request body, or signed request information.
"""
from __future__ import annotations

import base64
import csv
from datetime import datetime, timezone
import hashlib
import hmac
import http.client
import io
import json
import math
import os
from pathlib import Path
import re
import ssl
import time
from typing import Callable

HOST = "ocr.tencentcloudapi.com"
VERSION = "2018-11-19"
MAX_BASE64_BYTES = 10 * 1024 * 1024
MAX_RESPONSE_BYTES = 40 * 1024 * 1024
SUBMIT_QUESTION = "SubmitQuestionMarkAgentJob"
DESCRIBE_QUESTION = "DescribeQuestionMarkAgentJob"
SUBMIT_ESSAY = "SubmitMarkEssayAgentJob"
DESCRIBE_ESSAY = "DescribeMarkEssayAgentJob"
ACTION_KIND = {SUBMIT_QUESTION: "questions", DESCRIBE_QUESTION: "questions",
               SUBMIT_ESSAY: "essay", DESCRIBE_ESSAY: "essay"}
STATUSES = frozenset({"WAIT", "RUN", "DONE", "FAIL"})
QUESTION_CONFIG = {"KnowledgePoints": True, "TrueAnswer": True,
                   "OutputSubQuestionsAndCoords": True}
QUESTION_CONFIG_KEYS = frozenset({"KnowledgePoints", "TrueAnswer", "StepCorrection",
                                "DisableAnswerAnalysis", "OutputSubQuestionsAndCoords", "UseCoordAssist"})
ESSAY_CONFIG = {"StructureAndContent": "1"}
ReceiptCallback = Callable[[str, bytes, dict], None]


class TencentProviderError(Exception):
    classification = "provider_error"
    submitted = False
    retry_safe = False

    def __init__(self, code="ProviderError", *, request_id=None):
        self.code = code
        self.request_id = request_id
        # Never interpolate transport exceptions or provider Error.Message.
        super().__init__(f"Tencent grading: {code}")


class TencentConfigurationError(TencentProviderError):
    classification = "not_dispatched"
    retry_safe = True


class TencentSubmissionUnknown(TencentProviderError):
    classification = "submission_unknown"
    submitted = True
    retry_safe = False


class TencentKnownError(TencentProviderError):
    classification = "known_rejection"
    # The official Response.Error proves this call failed. The caller decides
    # whether a new paid action is appropriate; the adapter never retries it.
    submitted = False
    retry_safe = False


class TencentQueryError(TencentProviderError):
    classification = "query_unavailable"
    retry_safe = True


def load_tencent_credentials(csv_path):
    """Read one explicit absolute Tencent export path; never scan directories."""
    try:
        path = Path(csv_path)
        if not path.is_absolute() or not path.is_file() or path.stat().st_size > 65536:
            raise TencentConfigurationError("InvalidCredentialsFile")
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            pairs = []
            for row in reader:
                keys = {str(k).strip().lower().replace(" ", ""): (v or "").strip()
                        for k, v in row.items() if isinstance(v, str)}
                sid = keys.get("secretid") or keys.get("accesskeyid")
                skey = keys.get("secretkey") or keys.get("accesskeysecret")
                if sid or skey:
                    pairs.append((sid, skey))
        if len(pairs) != 1 or not all(pairs[0]):
            raise TencentConfigurationError("CredentialsPairRequired")
        return pairs[0]
    except TencentConfigurationError:
        raise
    except (OSError, UnicodeError, csv.Error, TypeError, ValueError):
        raise TencentConfigurationError("InvalidCredentialsFile") from None


def _encoded_image(image_path):
    try:
        path = Path(image_path)
        size = path.stat().st_size
        if size <= 0 or 4 * ((size + 2) // 3) > MAX_BASE64_BYTES:
            raise TencentConfigurationError("ImageBase64TooLargeOrEmpty")
        data = path.read_bytes()
    except TencentConfigurationError:
        raise
    except (OSError, TypeError, ValueError):
        raise TencentConfigurationError("ImageUnreadable") from None
    supported = (data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff")
                 or data.startswith(b"BM") or data.startswith(b"%PDF-"))
    if not supported:
        raise TencentConfigurationError("UnsupportedImageFormat")
    encoded = base64.b64encode(data).decode("ascii")
    if len(encoded) > MAX_BASE64_BYTES:
        raise TencentConfigurationError("ImageBase64TooLargeOrEmpty")
    return encoded


def _prepare_image(image_path):
    """Preserve dimensions, converting only an oversized upload copy to JPEG."""
    try:
        path = Path(image_path)
        if not 0 < path.stat().st_size <= 64 * 1024 * 1024:
            raise TencentConfigurationError("InputImageSizeLimit")
        data = path.read_bytes()
        metadata = {"inputSha256": hashlib.sha256(data).hexdigest(), "inputWidth": None,
                    "inputHeight": None, "submittedWidth": None, "submittedHeight": None,
                    "submittedFormat": "PDF" if data.startswith(b"%PDF-") else None}
        if data.startswith(b"%PDF-"):
            encoded = base64.b64encode(data).decode("ascii")
            if len(encoded) > MAX_BASE64_BYTES:
                raise TencentConfigurationError("ImageBase64TooLargeOrEmpty")
        else:
            from PIL import Image
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"PNG", "JPEG", "BMP"}:
                    raise TencentConfigurationError("UnsupportedImageFormat")
                width, height = image.size
                if width * height > 40_000_000:
                    raise TencentConfigurationError("InputPixelSizeLimit")
                metadata.update(inputWidth=width, inputHeight=height, submittedWidth=width,
                                submittedHeight=height, submittedFormat=image.format)
                if 4 * ((len(data) + 2) // 3) > MAX_BASE64_BYTES:
                    # Never rotate, crop, resize or modify the stored source image.
                    image.load()
                    if image.mode == "RGBA" or "transparency" in image.info:
                        rgba = image.convert("RGBA")
                        rgb = Image.new("RGB", image.size, "white")
                        rgb.paste(rgba, mask=rgba.getchannel("A"))
                    else:
                        rgb = image.convert("RGB")
                    for quality in (92, 85, 75, 60, 45):
                        stream = io.BytesIO()
                        rgb.save(stream, "JPEG", quality=quality, optimize=True, subsampling=0)
                        candidate = stream.getvalue()
                        if 4 * ((len(candidate) + 2) // 3) <= MAX_BASE64_BYTES:
                            data = candidate
                            metadata.update(submittedFormat="JPEG", jpegQuality=quality)
                            break
                    else:
                        raise TencentConfigurationError("ImageBase64TooLargeAtOriginalResolution")
                encoded = base64.b64encode(data).decode("ascii")
        metadata["submittedSha256"] = hashlib.sha256(data).hexdigest()
        return encoded, metadata
    except TencentConfigurationError:
        raise
    except Exception:
        raise TencentConfigurationError("ImageUnreadable") from None


def _config_string(value, *, essay=False):
    default = ESSAY_CONFIG if essay else QUESTION_CONFIG
    if value is None:
        value = dict(default)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            raise TencentConfigurationError("InvalidQuestionConfigMap") from None
    if not isinstance(value, dict):
        raise TencentConfigurationError("InvalidQuestionConfigMap")
    if essay:
        if set(value) - {"StructureAndContent"} or any(type(v) is not str or v not in {"0", "1"} for v in value.values()):
            raise TencentConfigurationError("InvalidEssayConfigMap")
    elif set(value) - QUESTION_CONFIG_KEYS or any(type(v) is not bool for v in value.values()):
        raise TencentConfigurationError("InvalidQuestionConfigMap")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _tc3_headers(secret_id, secret_key, action, body, timestamp, region=None):
    """TC3 v3 signing; headers are transient and must never be logged."""
    content_type = "application/json; charset=utf-8"
    signed_headers = "content-type;host;x-tc-action"
    canonical_headers = f"content-type:{content_type}\nhost:{HOST}\nx-tc-action:{action.lower()}\n"
    canonical_request = "\n".join(("POST", "/", "", canonical_headers, signed_headers,
                                    hashlib.sha256(body).hexdigest()))
    date = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")
    scope = f"{date}/ocr/tc3_request"
    to_sign = "\n".join(("TC3-HMAC-SHA256", str(timestamp), scope,
                          hashlib.sha256(canonical_request.encode()).hexdigest()))
    def sign(key, message):
        return hmac.new(key, message.encode(), hashlib.sha256).digest()
    key = sign(sign(sign(("TC3" + secret_key).encode(), date), "ocr"), "tc3_request")
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers = {"Authorization": f"TC3-HMAC-SHA256 Credential={secret_id}/{scope}, "
               f"SignedHeaders={signed_headers}, Signature={signature}",
               "Content-Type": content_type, "Host": HOST, "X-TC-Action": action,
               "X-TC-Version": VERSION, "X-TC-Timestamp": str(timestamp)}
    if region:
        headers["X-TC-Region"] = region
    return headers


def _https_transport(action, body, headers, timeout_seconds):
    """One direct TLS POST; http.client does not follow redirects or retry."""
    connection = http.client.HTTPSConnection(HOST, timeout=timeout_seconds,
                                             context=ssl.create_default_context())
    try:
        connection.request("POST", "/", body=body, headers=headers)
        response = connection.getresponse()
        try:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        except http.client.IncompleteRead as exc:
            raw = exc.partial  # Persist even an incomplete body before parsing.
        return response.status, raw
    finally:
        connection.close()


class TencentHomeworkProvider:
    provider_name = "tencent"
    model_name = "ocr-grading-agent-2018-11-19"
    is_tencent_grading = True

    def __init__(self, *, secret_id, secret_key, region=None, timeout_seconds=30,
                 receipt_callback=None, transport=None, clock=None):
        if not isinstance(secret_id, str) or not isinstance(secret_key, str) or not secret_id.strip() or not secret_key.strip():
            raise TencentConfigurationError("CredentialsPairRequired")
        if any(c in secret_id + secret_key for c in "\r\n"):
            raise TencentConfigurationError("InvalidCredentials")
        try:
            timeout = float(timeout_seconds)
        except (ValueError, TypeError):
            raise TencentConfigurationError("InvalidTimeout") from None
        if not math.isfinite(timeout) or not 1 <= timeout <= 120:
            raise TencentConfigurationError("InvalidTimeout")
        if region and (not isinstance(region, str) or not re.fullmatch(r"[a-z0-9-]{1,64}", region)):
            raise TencentConfigurationError("InvalidRegion")
        self._secret_id = secret_id.strip()
        self._secret_key = secret_key.strip()
        self.region = region or None
        self.timeout_seconds = timeout
        self.receipt_callback = receipt_callback
        self._transport = transport or _https_transport
        self._clock = clock or time.time

    @classmethod
    def from_config(cls, config=None, **overrides):
        config = os.environ if config is None else config
        if config.get("HOMEWORK_TENCENT_SECRET_ID") or config.get("HOMEWORK_TENCENT_SECRET_KEY"):
            sid, skey = config.get("HOMEWORK_TENCENT_SECRET_ID"), config.get("HOMEWORK_TENCENT_SECRET_KEY")
        else:
            sid, skey = config.get("TENCENTCLOUD_SECRET_ID"), config.get("TENCENTCLOUD_SECRET_KEY")
        if not sid and not skey and config.get("HOMEWORK_TENCENT_CREDENTIALS_CSV"):
            sid, skey = load_tencent_credentials(config["HOMEWORK_TENCENT_CREDENTIALS_CSV"])
        values = {"secret_id": sid, "secret_key": skey,
                  "region": config.get("HOMEWORK_TENCENT_REGION") or None,
                  "timeout_seconds": config.get("HOMEWORK_TENCENT_TIMEOUT_SECONDS") or 30}
        values.update(overrides)
        return cls(**values)

    from_env = from_config

    def _safe_id(self, value):
        if (isinstance(value, str) and 1 <= len(value) <= 128
                and re.fullmatch(r"[A-Za-z0-9_-]+", value)
                and self._secret_id not in value and self._secret_key not in value):
            return value
        return None

    def _safe_code(self, value):
        prefixes = {"AuthFailure", "FailedOperation", "InvalidParameter", "InvalidParameterValue",
                    "LimitExceeded", "MissingParameter", "RequestLimitExceeded", "ResourceInUse",
                    "ResourceInsufficient", "ResourceNotFound", "ResourceUnavailable", "ResourcesSoldOut",
                    "UnauthorizedOperation", "UnsupportedOperation", "InternalError"}
        if (isinstance(value, str) and value.split(".", 1)[0] in prefixes
                and re.fullmatch(r"[A-Za-z]{1,48}(?:\.[A-Za-z0-9]{1,64})?", value)
                and self._secret_id not in value and self._secret_key not in value):
            return value
        return "ProviderError"

    def parse_receipt(self, action, raw, *, http_status=200):
        """Parse an already durable private receipt; performs no network action."""
        if action not in ACTION_KIND:
            raise TencentConfigurationError("UnsupportedAction")
        submit = action in {SUBMIT_QUESTION, SUBMIT_ESSAY}
        invalid = TencentSubmissionUnknown if submit else TencentQueryError
        try:
            payload = json.loads(raw)
            response = payload.get("Response") if isinstance(payload, dict) else None
            if not isinstance(response, dict):
                raise ValueError()
        except (ValueError, TypeError, UnicodeError):
            raise invalid("InvalidResponse") from None
        request_id = self._safe_id(response.get("RequestId"))
        error = response.get("Error")
        if isinstance(error, dict):
            raise TencentKnownError(self._safe_code(error.get("Code")), request_id=request_id)
        if type(http_status) is not int or not 200 <= http_status < 300:
            raise invalid("UnexpectedHttpStatus", request_id=request_id)
        result = {"rawReceipt": payload, "providerRequestId": request_id, "analysisKind": ACTION_KIND[action]}
        if submit:
            raw_ids = [response.get("JobId")] if action == SUBMIT_QUESTION else response.get("JobIds")
            if not isinstance(raw_ids, list) or not raw_ids or any(self._safe_id(x) is None for x in raw_ids):
                raise TencentSubmissionUnknown("MissingJobIdentity", request_id=request_id)
            result.update(submitted=True, jobIds=list(raw_ids))
            if len(raw_ids) == 1:
                result["jobId"] = raw_ids[0]
            if action == SUBMIT_QUESTION:
                result["questionInfo"] = response.get("QuestionInfo", [])
                result["questionCount"] = response.get("QuestionCount")
            return result
        status = response.get("JobStatus")
        if not isinstance(status, str) or status not in STATUSES:
            raise TencentQueryError("InvalidJobStatus", request_id=request_id)
        result["status"] = status
        if status == "FAIL":
            result["errorCode"] = self._safe_code(response.get("ErrorCode"))
        if status == "DONE":
            name, key = ("MarkInfos", "markInfos") if action == DESCRIBE_QUESTION else ("SentenceSuggests", "sentenceSuggests")
            records = response.get(name)
            if not isinstance(records, list) or any(not isinstance(x, dict) for x in records):
                raise TencentQueryError("InvalidResultStructure", request_id=request_id)
            result[key] = records
            if action == DESCRIBE_QUESTION:
                result["questionDetails"] = records
            angle = response.get("Angle")
            try:
                result["angle"] = angle if type(angle) in {int, float} and math.isfinite(angle) else None
            except OverflowError:
                result["angle"] = None
        return result

    def _request(self, action, params, *, receipt_callback=None, image_metadata=None):
        callback = receipt_callback if receipt_callback is not None else self.receipt_callback
        if not callable(callback):
            raise TencentConfigurationError("DurableReceiptCallbackRequired")
        body = json.dumps(params, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = _tc3_headers(self._secret_id, self._secret_key, action, body,
                               int(self._clock()), self.region)
        invalid = TencentSubmissionUnknown if action in {SUBMIT_QUESTION, SUBMIT_ESSAY} else TencentQueryError
        try:
            http_status, raw = self._transport(action, body, headers, self.timeout_seconds)
        except Exception:
            raise invalid("TransportUnavailable") from None
        if not isinstance(raw, bytes):
            raise invalid("InvalidTransportReceipt")
        try:
            callback(action, raw, {"httpStatus": http_status, "action": action,
                                   "responseSha256": hashlib.sha256(raw).hexdigest(), **(image_metadata or {})})
        except Exception:
            raise invalid("ReceiptPersistenceFailed") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise invalid("ResponseSizeLimit")
        result = self.parse_receipt(action, raw, http_status=http_status)
        if image_metadata:
            result.update(image_metadata)
        return result

    def submit_question(self, image_path, *, receipt_callback=None, question_config=None):
        encoded, geometry = _prepare_image(image_path)
        params = {"ImageBase64": encoded,
                  "QuestionConfigMap": _config_string(question_config), "AssistMarkType": 0}
        return self._request(SUBMIT_QUESTION, params, receipt_callback=receipt_callback, image_metadata=geometry)

    def submit_essay(self, image_path, *, receipt_callback=None, essay_config=None):
        encoded, geometry = _prepare_image(image_path)
        params = {"ImageBase64List": [encoded],
                  "QuestionConfigMap": _config_string(essay_config, essay=True)}
        return self._request(SUBMIT_ESSAY, params, receipt_callback=receipt_callback, image_metadata=geometry)

    def _describe(self, action, job_id, receipt_callback):
        if not self._safe_id(job_id):
            raise TencentConfigurationError("InvalidJobIdentity")
        return self._request(action, {"JobId": job_id}, receipt_callback=receipt_callback)

    def describe_question(self, job_id, *, receipt_callback=None):
        return self._describe(DESCRIBE_QUESTION, job_id, receipt_callback)

    def describe_essay(self, job_id, *, receipt_callback=None):
        return self._describe(DESCRIBE_ESSAY, job_id, receipt_callback)

    poll_question = describe_question
    poll_essay = describe_essay
