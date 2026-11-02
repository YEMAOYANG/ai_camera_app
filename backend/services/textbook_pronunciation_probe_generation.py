"""Bounded, auditable generation of the registered Garden 4 TTS probes.

The registered pronunciation policy owns every model, voice, SSML and input
parameter.  This module owns only the operator lifecycle around those frozen
bytes: prepare, persist intent, make at most one POST per label, preserve the
provider response and original WAV, and build protocol-only review evidence.

An intent without a conclusive receipt is deliberately terminal.  It is never
turned into another paid POST.  A saved successful provider response may be
used to finish the idempotent WAV download/validation step.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
from typing import Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from content import textbook_pinyin_pronunciation as pronunciation
from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_operator_review import validate_operator_authorization
from services import textbook_preview_pronunciation_initialization as initialization


PLAN_SCHEMA = "mira.operator.phonetic-ssml-probe.v1"
INTENT_SCHEMA = "mira.operator.phonetic-ssml-probe-intent.v1"
RECEIPT_SCHEMA = "mira.operator.phonetic-ssml-probe-receipt.v1"
DISPATCH_AUTHORIZATION_SCHEMA = "mira.operator.phonetic-probe-dispatch-authorization.v1"
REVIEW_CONTEXT_SCHEMA = "mira.operator.phonetic-probe-review-context.v1"
WAV_VALIDATION_SCHEMA = "mira.operator.probe-wav-validation.v1"
POLICY_VERSION = pronunciation.GARDEN4_POLICY_VERSION
PROBE_FILES = initialization.PROBE_FILES

_SHA = re.compile(r"[a-f0-9]{64}\Z")
_LABEL = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")
_ISO_DATE = re.compile(r"\d{8}\Z")
_UUID_PATTERN = r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
_UUID = re.compile(_UUID_PATTERN + r"\Z")
_UUID_WAV = re.compile(_UUID_PATTERN + r"\.wav\Z")
_PROVIDER_BASE_URLS = {"aliyun-cosyvoice": "https://dashscope.aliyuncs.com/api/v1"}
_PROVIDER_KEY_ENVIRONMENTS = {
    "aliyun-cosyvoice": ("TTS_QWEN_API_KEY", "DASHSCOPE_API_KEY", "QWEN_API_KEY"),
}
_AUDIO_HOST = "dashscope-result-bj.oss-cn-beijing.aliyuncs.com"
_MAX_JSON_BYTES = 2 * 1024 * 1024
_MAX_WAV_BYTES = 32 * 1024 * 1024


class PronunciationProbeError(RuntimeError):
    """Safe operator-facing failure with a stable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ProviderOutcomeUnknown(PronunciationProbeError):
    """The POST may have reached the provider; it must never be replayed."""


class ProviderRejected(PronunciationProbeError):
    """A provider HTTP response conclusively rejected the one POST."""

    def __init__(self, status: int, response_sha256: str | None = None):
        super().__init__("provider_rejected", f"provider rejected the request with HTTP {status}")
        self.status = status
        self.response_sha256 = response_sha256


class ProbeTransport(Protocol):
    endpoint: str

    def post(self, request_bytes: bytes) -> bytes:
        """Perform exactly one POST and return the exact JSON response bytes."""

    def download(self, media_url: str, *, model: str) -> bytes:
        """Download a successful response's WAV without issuing another POST."""


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_bytes(value: object) -> bytes:
    return canonical(value).encode("utf-8")


def _json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse_json(raw: bytes, *, description: str) -> dict:
    if not isinstance(raw, bytes) or not raw or len(raw) > _MAX_JSON_BYTES:
        raise PronunciationProbeError("invalid_json", f"{description} is empty or too large")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_json_pairs)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise PronunciationProbeError("invalid_json", f"{description} is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PronunciationProbeError("invalid_json", f"{description} must be a JSON object")
    return value


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _iso_time(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").tzinfo is not None
    except ValueError:
        return False


def _plain_file(path: Path) -> bool:
    return path.exists() and not path.is_symlink() and path.is_file()


def _plain_directory(path: Path) -> bool:
    return path.exists() and not path.is_symlink() and path.is_dir()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def immutable_write(path: Path, raw: bytes) -> None:
    """Publish complete bytes without replacing an existing artifact."""
    if _plain_file(path):
        if path.read_bytes() != raw:
            raise PronunciationProbeError("artifact_conflict", f"existing artifact differs: {path.name}")
        return
    if path.exists() or path.is_symlink():
        raise PronunciationProbeError("artifact_conflict", f"artifact is not a plain file: {path.name}")
    if not _plain_directory(path.parent):
        raise PronunciationProbeError("unsafe_output", "artifact parent is not a plain directory")
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
        try:
            os.link(temporary, path)
        except FileExistsError:
            if not _plain_file(path) or path.read_bytes() != raw:
                raise PronunciationProbeError("artifact_conflict", f"concurrent artifact differs: {path.name}")
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _safe_output_root(output_dir: Path, *, create: bool) -> Path:
    requested = output_dir.expanduser()
    if requested.is_symlink():
        raise PronunciationProbeError("unsafe_output", "output directory cannot be a symbolic link")
    if create:
        requested.mkdir(parents=True, exist_ok=True)
    if requested.is_symlink():
        raise PronunciationProbeError("unsafe_output", "output directory cannot be a symbolic link")
    try:
        path = requested.resolve(strict=True)
    except OSError as exc:
        raise PronunciationProbeError("unsafe_output", "output directory cannot be resolved") from exc
    broad = {Path("/").resolve(), Path.home().resolve(), Path.home().resolve().parent,
             Path(__file__).resolve().parents[1], Path(__file__).resolve().parents[2]}
    if path in broad:
        raise PronunciationProbeError("unsafe_output", "output directory is too broad")
    if not _plain_directory(path):
        raise PronunciationProbeError("unsafe_output", "output directory must be a plain directory")
    return path


@contextmanager
def _locked(output_dir: Path, *, create: bool):
    root = _safe_output_root(output_dir, create=create)
    lock_path = root / ".probe.lock"
    if lock_path.is_symlink() or (lock_path.exists() and not lock_path.is_file()):
        raise PronunciationProbeError("unsafe_output", "probe lock is not a plain file")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise PronunciationProbeError("unsafe_output", "probe lock cannot be opened safely") from exc
    with os.fdopen(descriptor, "a+b", closefd=True) as lock:
        if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
            raise PronunciationProbeError("unsafe_output", "probe lock is not a regular file")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PronunciationProbeError("probe_busy", "another probe operator is using this directory") from exc
        yield root


def _binding(source_lesson: Mapping[str, object]) -> dict:
    fields = {"editionId", "revisionId", "nodeId", "gradeCode", "subject", "teachingRevision"}
    if (not isinstance(source_lesson, Mapping) or set(source_lesson) != fields
            or any(not isinstance(source_lesson[key], str) or not source_lesson[key].strip() for key in fields)):
        raise PronunciationProbeError("lesson_binding_invalid", "source lesson binding is incomplete")
    return {
        "editionId": source_lesson["editionId"],
        "alignmentRevisionId": source_lesson["revisionId"],
        "nodeId": source_lesson["nodeId"],
        "gradeCode": source_lesson["gradeCode"],
        "subject": source_lesson["subject"],
    }


def build_plan(source_lesson: Mapping[str, object]) -> dict:
    """Derive the exact four requests exclusively from registered contracts."""
    binding = _binding(source_lesson)
    try:
        policy = pronunciation.select_policy(binding)
    except Exception as exc:
        raise PronunciationProbeError("lesson_binding_invalid", "lesson is not bound to a registered policy") from exc
    if policy.get("policyVersion") != POLICY_VERSION:
        raise PronunciationProbeError("wrong_policy", "this CLI only accepts the registered Garden 4 policy")
    targets, _ = initialization._probe_contract(policy)
    texts = initialization._GARDEN4_PROBE_TEXTS
    tokens = initialization._GARDEN4_PROBE_TOKENS
    if tuple(targets) != tuple(texts) or tuple(targets) != tuple(tokens) or len(targets) != 4:
        raise PronunciationProbeError("probe_contract_changed", "Garden 4 fixed probe contract changed")
    samples = []
    for number, (label, target) in enumerate(targets.items(), 1):
        if not _LABEL.fullmatch(label):
            raise PronunciationProbeError("probe_contract_changed", "probe label is unsafe")
        entry = policy["symbols"].get(target)
        if not isinstance(entry, dict):
            raise PronunciationProbeError("probe_contract_changed", "probe target is no longer registered")
        body = pronunciation.provider_body(texts[label], policy_version=POLICY_VERSION)
        request_raw = json_bytes(body)
        ssml = body["input"]["text"]
        samples.append({
            "number": number,
            "label": label,
            "target": target,
            "phonemeCandidate": entry["ph"],
            "carrier": entry["carrier"],
            "sourceText": texts[label],
            "tokens": list(tokens[label]),
            "body": body,
            "requestSha256": sha_bytes(request_raw),
            "ssmlSha256": sha_bytes(ssml.encode("utf-8")),
        })
    return {
        "schemaVersion": PLAN_SCHEMA,
        "status": "prepared-not-dispatched",
        "sourceLesson": dict(source_lesson),
        "provider": policy["providerId"],
        "model": policy["modelId"],
        "voice": policy["voiceId"],
        "endpointPath": policy["endpointPath"],
        "policyVersion": policy["policyVersion"],
        "policyCanonicalSha256": digest(policy),
        "plannedCalls": 4,
        "maximumPostAttemptsPerSample": 1,
        "formalUseAllowed": False,
        "retryPolicy": "intent-before-call; no automatic POST retry; stop on failed or unknown outcome",
        "samples": samples,
    }


def _allowed_entries(plan: Mapping[str, object]) -> set[str]:
    return {".probe.lock", "plan.json", "operator-probe-review.json"} | {
        sample["label"] for sample in plan["samples"]
    }


def _verify_root_shape(root: Path, plan: Mapping[str, object]) -> None:
    allowed = _allowed_entries(plan)
    unknown = {path.name for path in root.iterdir()} - allowed
    if unknown:
        raise PronunciationProbeError("unexpected_artifact", "probe directory contains unrelated artifacts")
    for sample in plan["samples"]:
        folder = root / sample["label"]
        if not _plain_directory(folder):
            raise PronunciationProbeError("artifact_missing", f"missing sample directory: {sample['label']}")
        names = {path.name for path in folder.iterdir()}
        if not names <= set(PROBE_FILES):
            raise PronunciationProbeError("unexpected_artifact", f"unexpected artifact in {sample['label']}")
        if any(path.is_symlink() or not path.is_file() for path in folder.iterdir()):
            raise PronunciationProbeError("unsafe_output", f"sample artifacts must be plain files: {sample['label']}")


def prepare(output_dir: Path, source_lesson: Mapping[str, object]) -> dict:
    plan = build_plan(source_lesson)
    raw_plan = json_bytes(plan)
    with _locked(output_dir, create=True) as root:
        existing = {path.name for path in root.iterdir()}
        if existing - _allowed_entries(plan):
            raise PronunciationProbeError("unexpected_artifact", "probe directory is not empty or compatible")
        immutable_write(root / "plan.json", raw_plan)
        for sample in plan["samples"]:
            folder = root / sample["label"]
            folder.mkdir(exist_ok=True)
            if not _plain_directory(folder):
                raise PronunciationProbeError("unsafe_output", "sample path is not a plain directory")
            immutable_write(folder / "request.json", json_bytes(sample["body"]))
        _verify_root_shape(root, plan)
    return {"prepared": True, "planSha256": sha_bytes(raw_plan), "plannedCalls": 4,
            "providerCalls": 0, "formalUseAllowed": False}


def _load_plan(root: Path) -> tuple[dict, bytes]:
    path = root / "plan.json"
    if not _plain_file(path):
        raise PronunciationProbeError("plan_missing", "prepare the probe plan before running it")
    raw = path.read_bytes()
    plan = parse_json(raw, description="probe plan")
    expected = build_plan(plan.get("sourceLesson", {}))
    if plan != expected or raw != json_bytes(expected):
        raise PronunciationProbeError("plan_changed", "probe plan is not the canonical registered Garden 4 plan")
    _verify_root_shape(root, plan)
    for sample in plan["samples"]:
        request = root / sample["label"] / "request.json"
        if not _plain_file(request) or request.read_bytes() != json_bytes(sample["body"]):
            raise PronunciationProbeError("request_changed", f"request bytes changed: {sample['label']}")
    return plan, raw


def provider_endpoint(policy: Mapping[str, object]) -> str:
    base = _PROVIDER_BASE_URLS.get(policy.get("providerId"))
    path = policy.get("endpointPath")
    if (not base or not isinstance(path, str) or not path.startswith("/")
            or "?" in path or "#" in path or "//" in path):
        raise PronunciationProbeError("provider_configuration_invalid", "registered provider endpoint is invalid")
    return base.rstrip("/") + path


def _read_limited(response, limit: int) -> bytes:
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise PronunciationProbeError("provider_response_too_large", "provider response exceeds the evidence limit")
    return raw


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


class AliyunCosyVoiceProbeTransport:
    """Minimal official transport; credentials never enter artifacts or logs."""

    def __init__(self, api_key: str, *, endpoint: str, timeout_seconds: int = 60):
        if not isinstance(api_key, str) or not api_key.strip():
            raise PronunciationProbeError("provider_key_missing", "CosyVoice API key is not configured")
        parsed = urlparse(endpoint)
        if (parsed.scheme, parsed.hostname, parsed.port, parsed.username, parsed.password, parsed.query, parsed.fragment) != (
                "https", "dashscope.aliyuncs.com", None, None, None, "", ""):
            raise PronunciationProbeError("provider_configuration_invalid", "provider endpoint must be official HTTPS")
        self._api_key = api_key.strip()
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self._opener = build_opener(_NoRedirects())

    @classmethod
    def from_environment(cls, policy: Mapping[str, object], environ: Mapping[str, str] | None = None):
        environment = os.environ if environ is None else environ
        provider = policy.get("providerId")
        names = _PROVIDER_KEY_ENVIRONMENTS.get(provider, ())
        key = next((str(environment.get(name, "")).strip() for name in names
                    if str(environment.get(name, "")).strip()), "")
        return cls(key, endpoint=provider_endpoint(policy))

    def post(self, request_bytes: bytes) -> bytes:
        request = Request(self.endpoint, data=request_bytes, method="POST", headers={
            "Authorization": "Bearer " + self._api_key,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        })
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                status = int(getattr(response, "status", 0))
                raw = _read_limited(response, _MAX_JSON_BYTES)
        except HTTPError as exc:
            try:
                response_raw = _read_limited(exc, _MAX_JSON_BYTES)
            except PronunciationProbeError:
                response_raw = b""
            raise ProviderRejected(int(exc.code), sha_bytes(response_raw) if response_raw else None) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderOutcomeUnknown("provider_outcome_unknown", "provider POST outcome is unknown; do not retry") from exc
        if not 200 <= status < 300:
            raise ProviderRejected(status, sha_bytes(raw) if raw else None)
        return raw

    def download(self, media_url: str, *, model: str) -> bytes:
        secure_url = validated_media_url(media_url, model=model)
        request = Request(secure_url, method="GET", headers={"Accept": "audio/wav"})
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                if not 200 <= int(getattr(response, "status", 0)) < 300:
                    raise PronunciationProbeError("audio_download_failed", "provider WAV download failed")
                return _read_limited(response, _MAX_WAV_BYTES)
        except HTTPError as exc:
            raise PronunciationProbeError("audio_download_failed", "provider WAV download failed without another POST") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise PronunciationProbeError("audio_download_unknown", "provider WAV download failed; only download recovery is allowed") from exc


def validated_media_url(raw_url: str, *, model: str) -> str:
    if (not isinstance(raw_url, str) or not raw_url or len(raw_url) > 8192
            or any(ord(char) < 32 or ord(char) == 127 for char in raw_url)):
        raise PronunciationProbeError("media_url_invalid", "provider media URL is invalid")
    try:
        parsed = urlparse(raw_url)
    except (TypeError, ValueError) as exc:
        raise PronunciationProbeError("media_url_invalid", "provider media URL is invalid") from exc
    path_parts = parsed.path.split("/")
    valid_path = (len(path_parts) == 6 and path_parts[:3] == ["", "prod", model]
                  and _ISO_DATE.fullmatch(path_parts[3]) is not None
                  and path_parts[4].isdigit() and _UUID_WAV.fullmatch(path_parts[5]) is not None)
    if (parsed.scheme not in {"http", "https"} or parsed.hostname != _AUDIO_HOST
            or parsed.port is not None or parsed.username is not None or parsed.password is not None
            or parsed.fragment or not parsed.query or not valid_path):
        raise PronunciationProbeError("media_url_rejected", "provider media URL is outside the registered WAV route")
    return urlunparse(("https", _AUDIO_HOST, parsed.path, "", parsed.query, ""))


def normalize_wav(provider_audio: bytes) -> tuple[bytes, dict]:
    if not isinstance(provider_audio, bytes) or not 44 < len(provider_audio) <= _MAX_WAV_BYTES:
        raise PronunciationProbeError("media_wav_pcm_invalid", "provider WAV size is invalid")
    header = provider_audio[:44]
    if (header[:4] != b"RIFF" or header[8:16] != b"WAVEfmt " or header[36:40] != b"data"
            or struct.unpack_from("<IHHIIHH", header, 16) != (16, 1, 1, 24000, 48000, 2, 16)):
        raise PronunciationProbeError("media_wav_pcm_invalid", "provider WAV must be 24kHz mono PCM16")
    provider_riff_size = struct.unpack_from("<I", header, 4)[0]
    provider_data_size = struct.unpack_from("<I", header, 40)[0]
    data_size = len(provider_audio) - 44
    riff_size = data_size + 36
    if data_size <= 0 or data_size % 2:
        raise PronunciationProbeError("media_wav_pcm_invalid", "provider WAV PCM length is invalid")
    sizes = (provider_riff_size, provider_data_size)
    applied = sizes != (riff_size, data_size)
    if applied and sizes != (0x7FFFFFBF, 0x7FFFFF9B):
        raise PronunciationProbeError("media_wav_size_invalid", "provider WAV has unregistered streaming lengths")
    playback = bytearray(provider_audio)
    struct.pack_into("<I", playback, 4, riff_size)
    struct.pack_into("<I", playback, 40, data_size)
    normalization = {
        "policyVersion": "mira.wav.streaming-pcm-lengths.v1",
        "applied": applied,
        "providerRiffSize": provider_riff_size,
        "providerDataSize": provider_data_size,
        "riffSize": riff_size,
        "dataSize": data_size,
        "pcmByteLength": data_size,
        "sampleRate": 24000,
        "channels": 1,
        "bitsPerSample": 16,
    }
    return bytes(playback), normalization


def _validated_response(raw: bytes, *, model: str) -> tuple[dict, str]:
    response = parse_json(raw, description="provider response")
    request_id = response.get("request_id")
    output, usage = response.get("output"), response.get("usage")
    audio = output.get("audio") if isinstance(output, dict) else None
    media_url = audio.get("url") if isinstance(audio, dict) else None
    if (not isinstance(request_id, str) or _UUID.fullmatch(request_id) is None
            or not isinstance(output, dict) or output.get("finish_reason") != "stop"
            or not isinstance(audio, dict) or audio.get("id") != "audio_" + request_id
            or not isinstance(media_url, str)
            or not isinstance(usage, dict) or set(usage) != {"characters"}
            or type(usage.get("characters")) is not int or usage["characters"] < 0):
        raise PronunciationProbeError("provider_response_invalid", "provider response lacks successful audio identity or usage")
    secure_url = validated_media_url(media_url, model=model)
    if Path(urlparse(secure_url).path).name != request_id + ".wav":
        raise PronunciationProbeError("provider_response_invalid", "provider response audio identity is inconsistent")
    return response, media_url


def _ensure_unique_provider_response(root: Path, plan: Mapping[str, object]) -> None:
    seen: dict[str, str] = {}
    for planned in plan["samples"]:
        path = root / planned["label"] / "provider-response.json"
        if not path.exists():
            continue
        if not _plain_file(path):
            raise PronunciationProbeError("artifact_conflict", "provider response is not a plain file")
        response, _ = _validated_response(path.read_bytes(), model=str(plan["model"]))
        request_id = response["request_id"]
        previous = seen.get(request_id)
        if previous is not None and previous != planned["label"]:
            raise PronunciationProbeError(
                "provider_response_reused",
                f"provider request identity is reused by {previous} and {planned['label']}",
            )
        seen[request_id] = planned["label"]


def _load_dispatch_authorization(raw: bytes, plan: Mapping[str, object], plan_sha: str,
                                 *, now_ms: int) -> dict:
    value = parse_json(raw, description="dispatch authorization")
    fields = {"schemaVersion", "source", "statement", "recordedAt", "sourceLesson", "policyVersion",
              "planSha256", "provider", "plannedCalls", "paidProviderCallsAuthorized",
              "maximumPostAttemptsPerSample", "formalUseAllowed", "sha256"}
    if (set(value) != fields or value.get("sha256") != digest({k: v for k, v in value.items() if k != "sha256"})
            or value.get("schemaVersion") != DISPATCH_AUTHORIZATION_SCHEMA
            or value.get("source") != "user-message" or not isinstance(value.get("statement"), str)
            or not value["statement"].strip() or type(value.get("recordedAt")) is not int
            or not 0 < value["recordedAt"] <= now_ms or value.get("sourceLesson") != plan["sourceLesson"]
            or value.get("policyVersion") != plan["policyVersion"] or value.get("planSha256") != plan_sha
            or value.get("provider") != plan["provider"] or value.get("plannedCalls") != 4
            or value.get("paidProviderCallsAuthorized") is not True
            or value.get("maximumPostAttemptsPerSample") != 1 or value.get("formalUseAllowed") is not False):
        raise PronunciationProbeError("dispatch_not_authorized", "paid probe authorization does not match this exact four-call plan")
    return value


def _intent(sample: Mapping[str, object], plan: Mapping[str, object], plan_sha: str,
            authorization_sha: str, *, endpoint: str, created_at: str) -> dict:
    return {
        "schemaVersion": INTENT_SCHEMA,
        "createdAt": created_at,
        "provider": plan["provider"],
        "model": plan["model"],
        "voice": plan["voice"],
        "endpoint": endpoint,
        "target": sample["target"],
        "phonemeCandidate": sample["phonemeCandidate"],
        "requestSha256": sample["requestSha256"],
        "planSha256": plan_sha,
        "authorizationSha256": authorization_sha,
        "maxPostAttempts": 1,
        "formalUseAllowed": False,
    }


def _validated_intent(raw: bytes, sample: Mapping[str, object], plan: Mapping[str, object],
                      plan_sha: str, *, authorization_sha: str | None = None) -> dict:
    intent = parse_json(raw, description="probe intent")
    auth_sha = str(intent.get("authorizationSha256", ""))
    policy = pronunciation.registered_policy(str(plan["policyVersion"]))
    expected = _intent(sample, plan, plan_sha, auth_sha,
                       endpoint=str(intent.get("endpoint", "")), created_at=str(intent.get("createdAt", "")))
    if (intent != expected or not _SHA.fullmatch(auth_sha)
            or (authorization_sha is not None and auth_sha != authorization_sha)
            or intent.get("endpoint") != provider_endpoint(policy) or not _iso_time(intent.get("createdAt"))):
        raise PronunciationProbeError("intent_changed", f"intent is invalid: {sample['label']}")
    return intent


def _terminal_receipt(sample: Mapping[str, object], plan: Mapping[str, object], plan_sha: str,
                      authorization_sha: str, *, status: str, reason_code: str,
                      provider_response_sha256: str | None = None) -> dict:
    result = {
        "schemaVersion": RECEIPT_SCHEMA,
        "status": status,
        "reasonCode": reason_code,
        "recordedAt": _utc_iso(),
        "provider": plan["provider"],
        "model": plan["model"],
        "voice": plan["voice"],
        "target": sample["target"],
        "phonemeCandidate": sample["phonemeCandidate"],
        "requestSha256": sample["requestSha256"],
        "planSha256": plan_sha,
        "authorizationSha256": authorization_sha,
        "postAttempts": 1,
        "formalUseAllowed": False,
        "humanListeningVerified": False,
        "perceptualToneVerified": False,
        "pronunciationApproved": False,
    }
    if provider_response_sha256 is not None:
        result["providerResponseSha256"] = provider_response_sha256
    return result


def _finish_success(root: Path, sample: Mapping[str, object], plan: Mapping[str, object], plan_sha: str,
                    response_raw: bytes, transport: ProbeTransport) -> dict:
    folder = root / sample["label"]
    response, media_url = _validated_response(response_raw, model=str(plan["model"]))
    response_path = folder / "provider-response.json"
    immutable_write(response_path, response_raw)
    _ensure_unique_provider_response(root, plan)
    audio_path = folder / "audio.wav"
    if _plain_file(audio_path):
        provider_audio = audio_path.read_bytes()
    elif audio_path.exists() or audio_path.is_symlink():
        raise PronunciationProbeError("artifact_conflict", "audio.wav is not a plain file")
    else:
        provider_audio = transport.download(media_url, model=str(plan["model"]))
    playback, normalization = normalize_wav(provider_audio)
    immutable_write(audio_path, provider_audio)
    playback_path = folder / "playback.wav"
    immutable_write(playback_path, playback)
    hashes = {
        "providerAudioSha256": sha_bytes(provider_audio),
        "playbackSha256": sha_bytes(playback),
        "pcmSha256": sha_bytes(playback[44:]),
    }
    validation = {
        "schemaVersion": WAV_VALIDATION_SCHEMA,
        "verifiedAt": _utc_iso(),
        "pcmUnchanged": provider_audio[44:] == playback[44:],
        "audioNormalization": normalization,
        **hashes,
    }
    validation_path = folder / "playback-validation.json"
    if _plain_file(validation_path):
        old = parse_json(validation_path.read_bytes(), description="playback validation")
        validation["verifiedAt"] = old.get("verifiedAt")
    immutable_write(validation_path, json_bytes(validation))
    intent = _validated_intent((folder / "intent.json").read_bytes(), sample, plan, plan_sha)
    receipt = {
        "schemaVersion": RECEIPT_SCHEMA,
        "status": "succeeded",
        "completedAt": _utc_iso(),
        "provider": plan["provider"],
        "model": plan["model"],
        "voice": plan["voice"],
        "target": sample["target"],
        "phonemeCandidate": sample["phonemeCandidate"],
        "requestSha256": sample["requestSha256"],
        "ssmlSha256": sample["ssmlSha256"],
        "sourceTextSha256": sha_bytes(str(sample["sourceText"]).encode("utf-8")),
        "providerResponseSha256": sha_bytes(response_raw),
        "providerRequestId": response["request_id"],
        "planSha256": plan_sha,
        "authorizationSha256": intent["authorizationSha256"],
        "postAttempts": 1,
        "usage": response["usage"],
        "audioSha256": hashes["playbackSha256"],
        **hashes,
        "audioNormalization": normalization,
        "sampleRate": 24000,
        "channels": 1,
        "bitsPerSample": 16,
        "durationSeconds": normalization["dataSize"] / 48000,
        "downloadTransport": "HTTPS exact validated provider host/path/query; redirects refused",
        "formalUseAllowed": False,
        "humanReview": "not-requested",
        "humanListeningVerified": False,
        "perceptualToneVerified": False,
        "pronunciationApproved": False,
    }
    immutable_write(folder / "receipt.json", json_bytes(receipt))
    verify_completed_sample(root, plan, sample, plan_sha)
    return receipt


def verify_completed_sample(root: Path, plan: Mapping[str, object], sample: Mapping[str, object],
                            plan_sha: str) -> dict:
    folder = root / sample["label"]
    missing = [name for name in PROBE_FILES if not _plain_file(folder / name)]
    if missing:
        raise PronunciationProbeError("artifact_missing", f"completed sample lacks files: {sample['label']}")
    request_raw = (folder / "request.json").read_bytes()
    if request_raw != json_bytes(sample["body"]) or sha_bytes(request_raw) != sample["requestSha256"]:
        raise PronunciationProbeError("request_changed", f"request bytes changed: {sample['label']}")
    intent = _validated_intent((folder / "intent.json").read_bytes(), sample, plan, plan_sha)
    response_raw = (folder / "provider-response.json").read_bytes()
    response, _ = _validated_response(response_raw, model=str(plan["model"]))
    provider_audio = (folder / "audio.wav").read_bytes()
    expected_playback, normalization = normalize_wav(provider_audio)
    playback = (folder / "playback.wav").read_bytes()
    if playback != expected_playback:
        raise PronunciationProbeError("playback_changed", f"playback WAV changed: {sample['label']}")
    hashes = {"providerAudioSha256": sha_bytes(provider_audio), "playbackSha256": sha_bytes(playback),
              "pcmSha256": sha_bytes(playback[44:])}
    validation = parse_json((folder / "playback-validation.json").read_bytes(), description="playback validation")
    if (set(validation) != {"schemaVersion", "verifiedAt", "pcmUnchanged", "audioNormalization", *hashes}
            or validation.get("schemaVersion") != WAV_VALIDATION_SCHEMA or validation.get("pcmUnchanged") is not True
            or not _iso_time(validation.get("verifiedAt")) or validation.get("audioNormalization") != normalization
            or any(validation.get(key) != value for key, value in hashes.items())):
        raise PronunciationProbeError("playback_validation_changed", f"playback validation is invalid: {sample['label']}")
    receipt = parse_json((folder / "receipt.json").read_bytes(), description="probe receipt")
    expected = {
        "status": "succeeded", "provider": plan["provider"], "model": plan["model"], "voice": plan["voice"],
        "target": sample["target"], "phonemeCandidate": sample["phonemeCandidate"],
        "requestSha256": sample["requestSha256"], "ssmlSha256": sample["ssmlSha256"],
        "sourceTextSha256": sha_bytes(str(sample["sourceText"]).encode("utf-8")),
        "providerResponseSha256": sha_bytes(response_raw), "providerRequestId": response["request_id"],
        "planSha256": plan_sha, "authorizationSha256": intent["authorizationSha256"], "postAttempts": 1,
        "usage": response["usage"], "audioSha256": hashes["playbackSha256"], **hashes,
        "audioNormalization": normalization, "sampleRate": 24000, "channels": 1, "bitsPerSample": 16,
        "formalUseAllowed": False, "humanReview": "not-requested", "humanListeningVerified": False,
        "perceptualToneVerified": False, "pronunciationApproved": False,
    }
    if (receipt.get("schemaVersion") != RECEIPT_SCHEMA or not _iso_time(receipt.get("completedAt"))
            or any(receipt.get(key) != value for key, value in expected.items())
            or receipt.get("durationSeconds") != normalization["dataSize"] / 48000
            or receipt.get("downloadTransport") != "HTTPS exact validated provider host/path/query; redirects refused"):
        raise PronunciationProbeError("receipt_changed", f"receipt is invalid: {sample['label']}")
    pronunciation.validate_receipt_wav(receipt, playback)
    return receipt


def _preflight_states(root: Path, plan: Mapping[str, object], plan_sha: str,
                      authorization_sha: str) -> list[str]:
    """Validate the complete four-sample directory before any new paid POST."""
    states = []
    for sample in plan["samples"]:
        folder = root / sample["label"]
        receipt_path = folder / "receipt.json"
        intent_path = folder / "intent.json"
        response_path = folder / "provider-response.json"
        if receipt_path.exists():
            if not _plain_file(receipt_path):
                raise PronunciationProbeError("artifact_conflict", "receipt is not a plain file")
            receipt = parse_json(receipt_path.read_bytes(), description="probe receipt")
            if receipt.get("status") != "succeeded":
                raise PronunciationProbeError(
                    "prior_provider_outcome_" + str(receipt.get("status", "invalid")),
                    "prior provider outcome is terminal; do not retry the POST",
                )
            verify_completed_sample(root, plan, sample, plan_sha)
            if receipt.get("authorizationSha256") != authorization_sha:
                raise PronunciationProbeError("authorization_changed", "completed sample belongs to another authorization")
            states.append("succeeded")
            continue
        if intent_path.exists():
            if not _plain_file(intent_path):
                raise PronunciationProbeError("artifact_conflict", "intent is not a plain file")
            _validated_intent(intent_path.read_bytes(), sample, plan, plan_sha,
                              authorization_sha=authorization_sha)
            if not _plain_file(response_path):
                raise PronunciationProbeError("prior_provider_outcome_unknown",
                                              "intent exists without a successful response; do not retry the POST")
            _validated_response(response_path.read_bytes(), model=str(plan["model"]))
            audio_path, playback_path = folder / "audio.wav", folder / "playback.wav"
            if _plain_file(audio_path):
                provider_audio = audio_path.read_bytes()
                expected_playback, normalization = normalize_wav(provider_audio)
                if playback_path.exists() and not _plain_file(playback_path):
                    raise PronunciationProbeError("artifact_conflict", "pending playback is not a plain file")
                if _plain_file(playback_path):
                    playback = playback_path.read_bytes()
                    if playback != expected_playback:
                        raise PronunciationProbeError("playback_changed", "pending playback WAV is invalid")
                    validation_path = folder / "playback-validation.json"
                    if validation_path.exists():
                        if not _plain_file(validation_path):
                            raise PronunciationProbeError("artifact_conflict", "pending validation is not a plain file")
                        validation = parse_json(validation_path.read_bytes(), description="playback validation")
                        hashes = {"providerAudioSha256": sha_bytes(provider_audio),
                                  "playbackSha256": sha_bytes(playback), "pcmSha256": sha_bytes(playback[44:])}
                        if (set(validation) != {"schemaVersion", "verifiedAt", "pcmUnchanged",
                                               "audioNormalization", *hashes}
                                or validation.get("schemaVersion") != WAV_VALIDATION_SCHEMA
                                or validation.get("pcmUnchanged") is not True
                                or not _iso_time(validation.get("verifiedAt"))
                                or validation.get("audioNormalization") != normalization
                                or any(validation.get(key) != value for key, value in hashes.items())):
                            raise PronunciationProbeError(
                                "playback_validation_changed", "pending playback validation is invalid")
                elif (folder / "playback-validation.json").exists():
                    raise PronunciationProbeError("artifact_conflict", "pending validation exists before playback")
            elif audio_path.exists() or playback_path.exists() or (folder / "playback-validation.json").exists():
                raise PronunciationProbeError("artifact_conflict", "pending download artifacts are out of order")
            states.append("download-pending")
            continue
        if any((folder / name).exists() for name in PROBE_FILES if name != "request.json"):
            raise PronunciationProbeError("artifact_conflict", "provider artifacts exist without an intent")
        states.append("prepared")
    _ensure_unique_provider_response(root, plan)
    order = {"succeeded": 0, "download-pending": 1, "prepared": 2}
    if (any(order[right] < order[left] for left, right in zip(states, states[1:]))
            or states.count("download-pending") > 1):
        raise PronunciationProbeError(
            "probe_state_out_of_order",
            "probe state must be a succeeded prefix, at most one download recovery, then prepared samples",
        )
    return states


def run(output_dir: Path, authorization_file: Path, *, transport: ProbeTransport | None = None,
        now_ms: int | None = None) -> dict:
    """Execute remaining labels once; never replay an existing intent."""
    with _locked(output_dir, create=False) as root:
        plan, plan_raw = _load_plan(root)
        plan_sha = sha_bytes(plan_raw)
        if not _plain_file(authorization_file):
            raise PronunciationProbeError("dispatch_not_authorized", "dispatch authorization file is missing")
        authorization = _load_dispatch_authorization(
            authorization_file.read_bytes(), plan, plan_sha, now_ms=_now_ms() if now_ms is None else now_ms)
        states = _preflight_states(root, plan, plan_sha, authorization["sha256"])
        policy = pronunciation.registered_policy(str(plan["policyVersion"]))
        active_transport = None

        def resolve_transport():
            nonlocal active_transport
            if active_transport is None:
                active_transport = transport or AliyunCosyVoiceProbeTransport.from_environment(policy)
                if active_transport.endpoint != provider_endpoint(policy):
                    raise PronunciationProbeError(
                        "provider_configuration_invalid", "transport endpoint differs from registered policy")
            return active_transport

        completed = 0
        for sample, state in zip(plan["samples"], states):
            folder = root / sample["label"]
            receipt_path = folder / "receipt.json"
            intent_path = folder / "intent.json"
            response_path = folder / "provider-response.json"
            if state == "succeeded":
                completed += 1
                continue
            if state == "download-pending":
                _finish_success(root, sample, plan, plan_sha, response_path.read_bytes(), resolve_transport())
                completed += 1
                continue
            current_transport = resolve_transport()
            intent = _intent(sample, plan, plan_sha, authorization["sha256"],
                             endpoint=current_transport.endpoint, created_at=_utc_iso())
            immutable_write(intent_path, json_bytes(intent))
            try:
                response_raw = current_transport.post((folder / "request.json").read_bytes())
            except ProviderOutcomeUnknown as exc:
                terminal = _terminal_receipt(sample, plan, plan_sha, authorization["sha256"],
                                             status="unknown", reason_code=exc.code)
                immutable_write(receipt_path, json_bytes(terminal))
                raise
            except ProviderRejected as exc:
                terminal = _terminal_receipt(sample, plan, plan_sha, authorization["sha256"],
                                             status="failed", reason_code=exc.code,
                                             provider_response_sha256=exc.response_sha256)
                immutable_write(receipt_path, json_bytes(terminal))
                raise
            _finish_success(root, sample, plan, plan_sha, response_raw, current_transport)
            completed += 1
        return {"completed": True, "plannedCalls": 4, "completedSamples": completed,
                "formalUseAllowed": False, "humanListeningVerified": False,
                "perceptualToneVerified": False}


def _load_review_context(raw: bytes, plan: Mapping[str, object], *, now_ms: int) -> dict:
    value = parse_json(raw, description="operator review context")
    fields = {"schemaVersion", "previewKey", "sourceSha256", "coreSha256", "reviewer", "recordedAt",
              "authorization"}
    if (set(value) != fields or value.get("schemaVersion") != REVIEW_CONTEXT_SCHEMA
            or not isinstance(value.get("previewKey"), str) or not value["previewKey"].strip()
            or any(_SHA.fullmatch(str(value.get(key))) is None for key in ("sourceSha256", "coreSha256"))
            or not isinstance(value.get("reviewer"), str) or not value["reviewer"].strip()
            or type(value.get("recordedAt")) is not int or not 0 < value["recordedAt"] <= now_ms):
        raise PronunciationProbeError("review_context_invalid", "operator review context is incomplete")
    try:
        validate_operator_authorization(value["authorization"], binding=_binding(plan["sourceLesson"]),
                                        recorded_at=value["recordedAt"])
    except Exception as exc:
        raise PronunciationProbeError("review_context_invalid", "operator authorization does not match the lesson") from exc
    return value


def build_operator_review(output_dir: Path, review_context_file: Path, *, now_ms: int | None = None) -> dict:
    """Build protocol/WAV evidence while explicitly denying human listening."""
    with _locked(output_dir, create=False) as root:
        plan, plan_raw = _load_plan(root)
        plan_sha = sha_bytes(plan_raw)
        if not _plain_file(review_context_file):
            raise PronunciationProbeError("review_context_invalid", "operator review context file is missing")
        context = _load_review_context(review_context_file.read_bytes(), plan,
                                       now_ms=_now_ms() if now_ms is None else now_ms)
        samples = []
        for sample in plan["samples"]:
            receipt = verify_completed_sample(root, plan, sample, plan_sha)
            samples.append({
                "label": sample["label"],
                "target": sample["target"],
                "phonemeCandidate": sample["phonemeCandidate"],
                "providerRequestId": receipt["providerRequestId"],
                "requestSha256": receipt["requestSha256"],
                "providerResponseSha256": receipt["providerResponseSha256"],
                "providerAudioSha256": receipt["providerAudioSha256"],
                "playbackSha256": receipt["playbackSha256"],
                "pcmSha256": receipt["pcmSha256"],
                "result": initialization.OPERATOR_RESULT,
            })
        _ensure_unique_provider_response(root, plan)
        policy = pronunciation.registered_policy(str(plan["policyVersion"]))
        review = {
            "schemaVersion": initialization.OPERATOR_REVIEW_SCHEMA,
            "method": initialization.OPERATOR_METHOD,
            "previewKey": context["previewKey"],
            "sourceSha256": context["sourceSha256"],
            "coreSha256": context["coreSha256"],
            "pronunciationPolicyVersion": policy["policyVersion"],
            "pronunciationPolicySha256": digest(policy),
            "reviewer": context["reviewer"],
            "recordedAt": context["recordedAt"],
            "authorization": deepcopy(context["authorization"]),
            "result": initialization.OPERATOR_RESULT,
            "humanListeningVerified": False,
            "perceptualToneVerified": False,
            "formalUseAllowed": False,
            "probePlanSha256": plan_sha,
            "samples": samples,
            "evidenceLimit": initialization.OPERATOR_EVIDENCE_LIMIT,
        }
        review["sha256"] = digest(review)
        # Exercise the same byte-level verifier used by pronunciation activation.
        files = {"evidence/plan.json": plan_raw}
        for sample in plan["samples"]:
            for name in PROBE_FILES:
                files[f"evidence/{sample['label']}/{name}"] = (root / sample["label"] / name).read_bytes()
        initialization._verify_probe_files(
            files, review, _binding(plan["sourceLesson"]), policy,
            initialization._probe_contract(policy)[0], sample_result=initialization.OPERATOR_RESULT)
        immutable_write(root / "operator-probe-review.json", json_bytes(review))
        return review


def status(output_dir: Path) -> dict:
    root = _safe_output_root(output_dir, create=False)
    plan, plan_raw = _load_plan(root)
    plan_sha = sha_bytes(plan_raw)
    states = []
    for sample in plan["samples"]:
        folder = root / sample["label"]
        receipt_path = folder / "receipt.json"
        if _plain_file(receipt_path):
            receipt = parse_json(receipt_path.read_bytes(), description="probe receipt")
            state = str(receipt.get("status", "invalid"))
            if state == "succeeded":
                try:
                    verify_completed_sample(root, plan, sample, plan_sha)
                except Exception:
                    state = "invalid-evidence"
        elif _plain_file(folder / "provider-response.json"):
            state = "provider-succeeded-download-pending"
        elif _plain_file(folder / "intent.json"):
            state = "unknown-stop-no-retry"
        else:
            state = "prepared"
        states.append({"label": sample["label"], "state": state})
    _ensure_unique_provider_response(root, plan)
    return {"planSha256": sha_bytes(plan_raw), "formalUseAllowed": False, "samples": states,
            "operatorReviewPresent": _plain_file(root / "operator-probe-review.json")}
