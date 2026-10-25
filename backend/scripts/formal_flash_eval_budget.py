"""Isolated, durable production accounting for the formal Flash acceptance.

Uses the production policy/service/repository and production internal token
guard. Only a newly created SQLite file can be initialized; no business DB is
opened or migrated. HTTP cannot mint grants. Import/create_app do not start a
server or call a provider. The trusted operator supplies reviewed authorization
and official-price evidence, including a protective USD-to-CNY conversion.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import urlparse

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from content.learning_budget_policy import LearningBudgetPolicy, PURPOSES, UNITS, canonical, digest
from core.errors import ApiError, error_response
from core.security import now_ms
from repositories.care_repository import CareRepository
from services.internal_request_guard import InternalRequestGuard
from services.learning_budget_service import LearningBudgetService
from scripts.evaluate_formal_flash_course import validate_frozen, write_json_new

LEDGER_SCHEMA = "mira.eval.formal-flash-isolated-ledger.v1"
APPROVAL_SCHEMA = "mira.eval.formal-flash-operator-approval.v1"
PRICE_SCHEMA = "mira.eval.formal-flash-price-evidence.v1"
PRICE_VERSION = "official-2026-10-08-peak-ceiling.v1"
# Actual formal callers, not a made-up 16K catalog capacity:
# agent-runtime/generation-ai-call.ts requests 65_536 for structured scenes;
# mira-formal-agent-budget.ts requests 16_384 for the driver;
# mira-courseware-provider.ts requests 8_000 for authoring/quality review;
# mira-formal-visual-review.ts requests 8_192. Native measures input using a
# conservative byte ceiling, including tools and vision. Overall CNY/call caps
# remain authoritative, regardless of the model's larger 384K output capacity.
MODEL_INPUT_MAX = 1_048_576
MODEL_OUTPUT_MAX = 65_536
TTS_CHARACTERS_MAX = 10_000  # Native accepts 8K source plus pronunciation expansion.
ASR_AUDIO_MS_MAX = 2_400_000  # Covers Native's 16MiB WAV at minimum 8KHz/8bit mono.
OFFICIAL_DOMAINS = {"deepseek": {"api-docs.deepseek.com"},
                    "aliyun": {"help.aliyun.com"}, "baidu": {"ai.baidu.com", "cloud.baidu.com"}}
REQUIRED_QUOTES = {
    "deepseek-flash": ("deepseek", "deepseek", "deepseek-flash"),
    "qwen-tts": ("aliyun", "qwen-tts", "qwen3-tts-flash"),
    "qwen-asr": ("aliyun", "qwen-asr", "qwen3-asr-flash"),
    "qwen-image": ("aliyun", "qwen-image", "qwen-image-max"),
    "happyhorse-video": ("aliyun", "happyhorse", "happyhorse-1.0-t2v"),
    "baidu-search": ("baidu", "baidu", "baidu-web-search"),
}
_FIELDS = {
    "authorization_context": {"authorizationId": "authorization_id"},
    "reserve": {"authorizationId": "authorization_id", "dispatchId": "dispatch_id",
                "requestSha256": "request_sha256", "priceKey": "price_key", "maxUnits": "max_units"},
    "dispatch": {"authorizationId": "authorization_id", "reservationId": "reservation_id", "requestSha256": "request_sha256"},
    "settle": {"authorizationId": "authorization_id", "reservationId": "reservation_id",
               "actualUnits": "actual_units", "providerRequestId": "provider_request_id", "evidenceSha256": "evidence_sha256"},
    "unknown": {"authorizationId": "authorization_id", "reservationId": "reservation_id", "reasonCode": "reason_code"},
    "release": {"authorizationId": "authorization_id", "reservationId": "reservation_id", "reasonCode": "reason_code"},
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _decimal(value, name):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9]+(?:\.[0-9]{1,8})?", value), "invalid " + name)
    number = Decimal(value)
    _require(0 < number <= 10000, "invalid " + name)
    return number


def _price_profiles(evidence):
    _require(isinstance(evidence, dict) and evidence.get("schemaVersion") == PRICE_SCHEMA,
             "official price evidence is required")
    quotes = evidence.get("quotes")
    _require(isinstance(quotes, dict) and set(quotes) == set(REQUIRED_QUOTES), "missing official provider quote")
    fx = _decimal(evidence.get("protectiveCnyPerUsd"), "protective exchange rate")
    _require(fx >= 8 and evidence.get("fxPurpose") == "budget_upper_bound_not_vendor_exchange_rate",
             "explicit protective conversion of at least 8 CNY/USD is required")
    for key, (vendor, provider, model) in REQUIRED_QUOTES.items():
        quote = quotes[key]
        _require(isinstance(quote, dict), "invalid official quote")
        parsed = urlparse(str(quote.get("sourceUrl", "")))
        _require(parsed.scheme == "https" and parsed.hostname in OFFICIAL_DOMAINS[vendor]
                 and not parsed.username and not parsed.password,
                 "official quote URL is not authoritative")
        _require(quote.get("provider") == provider and quote.get("model") == model
                 and quote.get("priceVersion") == PRICE_VERSION
                 and quote.get("verifiedAt", "").startswith("2026-10-08")
                 and quote.get("operatorVerified") is True
                 and isinstance(quote.get("sourceSnapshotSha256"), str)
                 and re.fullmatch(r"[a-f0-9]{64}", quote["sourceSnapshotSha256"]),
                 "quote identity/version/current official evidence is incomplete")
    # Frozen official numbers, not rates from untrusted HTTP request JSON.
    expected = {
        "deepseek-flash": {"currency": "USD", "inputMissPerMillion": "0.30", "outputPerMillion": "1.20"},
        "qwen-tts": {"currency": "CNY", "per10000Characters": "0.8"},
        "qwen-asr": {"currency": "CNY", "perSecond": "0.00022"},
        "qwen-image": {"currency": "CNY", "perImage": "0.5"},
        "happyhorse-video": {"currency": "CNY", "perSecond720p": "0.9"},
        "baidu-search": {"currency": "CNY", "perStandardCall": "0.036"},
    }
    _require(all(quotes[key].get("rates") == rates for key, rates in expected.items()),
             "official quote differs from frozen 2026-10-08 pricing; review a new version")
    def price(key, maximum, rates):
        _, provider, model = REQUIRED_QUOTES[key]
        return {"provider": provider, "model": model, "version": PRICE_VERSION,
                "allowedUnits": list(maximum), "perCallMax": maximum, "microsPerMillionUnits": rates}
    ceil = lambda value: int(value.to_integral_value(rounding=ROUND_CEILING))
    return {
        "deepseek-v4.1-flash-peak": price("deepseek-flash", {"calls": 1, "input_tokens": MODEL_INPUT_MAX, "output_tokens": MODEL_OUTPUT_MAX},
            {"calls": 0, "input_tokens": ceil(Decimal("0.30") * fx * 1000000),
             "output_tokens": ceil(Decimal("1.20") * fx * 1000000)}),
        "qwen-tts": price("qwen-tts", {"calls": 1, "characters": TTS_CHARACTERS_MAX}, {"calls": 0, "characters": 80000000}),
        "qwen-asr": price("qwen-asr", {"calls": 1, "audio_ms": ASR_AUDIO_MS_MAX}, {"calls": 0, "audio_ms": 220000}),
        "qwen-image": price("qwen-image", {"calls": 1, "images": 1}, {"calls": 0, "images": 500000000000}),
        "happyhorse-video": price("happyhorse-video", {"calls": 1, "video_ms": 5000}, {"calls": 0, "video_ms": 900000000}),
        "baidu-search": price("baidu-search", {"calls": 1, "search_requests": 1}, {"calls": 0, "search_requests": 36000000000}),
    }


def build_plan(frozen_courses: list[dict], *, approval: dict, price_evidence: dict, now=None) -> dict:
    """Read-only preflight; no grant exists merely because a plan validates."""
    now = now_ms() if now is None else now
    _require(isinstance(frozen_courses, list) and 1 <= len(frozen_courses) <= 2, "one or two frozen formal courses required")
    for frozen in frozen_courses:
        validate_frozen(frozen)
    _require(len({f["subject"] for f in frozen_courses}) == len(frozen_courses), "duplicate formal subject")
    _require(isinstance(approval, dict) and approval.get("schemaVersion") == APPROVAL_SCHEMA,
             "trusted operator authorization evidence required")
    _require(approval.get("humanAuthorizationVerified") is True
             and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}", str(approval.get("approvalReference", "")))
             and re.fullmatch(r"[a-f0-9]{64}", str(approval.get("humanAuthorizationSha256", ""))),
             "human authorization provenance missing")
    _require(approval.get("frozenTemplateSha256s") == sorted(f["templateSha256"] for f in frozen_courses),
             "authorization does not cover these frozen formal inputs")
    ledger_path = approval.get("ledgerPath")
    _require(isinstance(ledger_path, str) and Path(ledger_path).is_absolute()
             and str(Path(ledger_path).absolute()) == ledger_path,
             "authorization must name one exact fresh isolated ledger path")
    start, end = approval.get("startsAt"), approval.get("expiresAt")
    _require(type(start) is int and type(end) is int and start <= now < end <= start + 31 * 86400000,
             "operator authorization is outside its fixed window")
    max_calls, per_course = approval.get("maxCalls"), approval.get("perCourseMaxCalls")
    _require(type(max_calls) is int and 1 <= max_calls <= 1000 and type(per_course) is int and 1 <= per_course <= max_calls,
             "explicit bounded call caps required")
    usd = _decimal(approval.get("maxNewSpendUsd"), "new spend ceiling")
    _require(usd <= 100, "unreviewed acceptance spend ceiling")
    prices = _price_profiles(price_evidence)
    fx = _decimal(price_evidence["protectiveCnyPerUsd"], "protective exchange rate")
    money = int((usd * fx * 1000000).to_integral_value(rounding=ROUND_CEILING))
    limits = {"calls": max_calls, "input_tokens": max_calls * MODEL_INPUT_MAX, "output_tokens": max_calls * MODEL_OUTPUT_MAX,
              "characters": max_calls * TTS_CHARACTERS_MAX, "audio_ms": max_calls * ASR_AUDIO_MS_MAX,
              "video_ms": max_calls * 5000, "images": max_calls, "search_requests": max_calls,
              "money_micros": money}
    per_limit = {**limits, "calls": per_course}
    zero = dict.fromkeys(UNITS, 0)
    global_window = {"day": limits, "month": limits}
    scopes = []
    for frozen in frozen_courses:
        contract = json.loads(frozen["nativeInputTemplate"]["requirement"])
        scopes.append({"purpose": "production", "gradeCode": "primary_1", "subject": frozen["subject"],
            "courseId": contract["course"]["id"], "courseVersion": contract["course"]["version"],
            "productionJobId": contract["buildItemId"], "userId": None, "sessionId": None,
            "approvalReference": approval["approvalReference"]})
    policy = {"schemaVersion": "mira.learning.budget-policy.v1", "version": "formal-flash-isolated-acceptance.v1",
              "enabled": True, "currency": "CNY", "timezone": "Asia/Shanghai", "allowUnpriced": False,
              "aggregateLimitsEnabled": True,
              "limits": {"global": {**global_window, "maxInflightCalls": 4},
                         "purposes": {p: global_window if p == "production" else {"day": zero, "month": zero} for p in PURPOSES},
                         "user": global_window, "course": {"lifetime": per_limit}, "authorization": per_limit},
              "prices": prices, "authorizationTemplates": {p: ({"maxUnits": per_limit, "priceKeys": list(prices),
                  "ttlMs": end - start} if p == "production" else None) for p in PURPOSES},
              "productionAuthorizationWindow": {"startsAt": start, "expiresAt": end, "scopes": scopes}}
    parsed = LearningBudgetPolicy(policy)
    return {"schemaVersion": LEDGER_SCHEMA, "frozenTemplateSha256s": approval["frozenTemplateSha256s"],
            "frozenCourses": deepcopy(frozen_courses),
            "approval": deepcopy(approval), "priceEvidence": deepcopy(price_evidence),
            "policy": parsed.raw, "policySha256": parsed.sha256,
            "authorizationIds": {scope["subject"]: digest({"schema": LEDGER_SCHEMA, "scope": scope,
                "policySha256": parsed.sha256, "frozenTemplateSha256s": approval["frozenTemplateSha256s"]}) for scope in scopes},
            "externalCalls": 0, "businessDatabase": None, "publications": 0}


def validate_plan(plan):
    _require(isinstance(plan, dict) and plan.get("schemaVersion") == LEDGER_SCHEMA, "invalid isolated budget plan")
    expected = build_plan(plan.get("frozenCourses"), approval=plan.get("approval"),
                          price_evidence=plan.get("priceEvidence"), now=plan["approval"]["startsAt"])
    _require(plan == expected, "isolated plan differs from its exact frozen scope/approval/prices/caps")
    policy = LearningBudgetPolicy(plan["policy"])
    _require(plan.get("policySha256") == policy.sha256, "isolated policy hash drifted")
    _require(policy.raw["enabled"] and policy.aggregate_limits_enabled and not policy.raw["allowUnpriced"],
             "isolated accounting must enforce priced aggregate caps")
    _require(policy.raw["prices"] == _price_profiles(plan["priceEvidence"]), "isolated official prices drifted")
    _require(plan["approval"]["frozenTemplateSha256s"] == plan["frozenTemplateSha256s"], "frozen authority drifted")
    _require(set(plan["authorizationIds"]) == {s["subject"] for s in policy.raw["productionAuthorizationWindow"]["scopes"]},
             "isolated authorization scope drifted")
    for scope in policy.raw["productionAuthorizationWindow"]["scopes"]:
        expected = digest({"schema": LEDGER_SCHEMA, "scope": scope, "policySha256": policy.sha256,
                           "frozenTemplateSha256s": plan["frozenTemplateSha256s"]})
        _require(plan["authorizationIds"][scope["subject"]] == expected, "isolated authorization identity drifted")
    return policy


class IsolatedBudgetDatabase:
    def __init__(self, path: Path):
        path = Path(path).absolute()
        _require(path.is_file() and not path.is_symlink(), "isolated ledger is missing")
        self.path = str(path)

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect("file:" + self.path + "?mode=rw", uri=True, timeout=30)
        conn.row_factory = lambda cur, row: {d[0]: v for d, v in zip(cur.description, row)}
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def initialize_ledger(path: Path, plan: dict, *, now=None) -> tuple[LearningBudgetService, dict]:
    """Explicit fresh ledger only. Reinitialization never resets unresolved cost."""
    policy = validate_plan(plan)
    clock = now_ms if now is None else lambda: now
    now = clock()
    window = policy.raw["productionAuthorizationWindow"]
    _require(window["startsAt"] <= now < window["expiresAt"], "isolated authorization expired")
    path = Path(path).absolute()
    _require(str(path) == plan["approval"]["ledgerPath"], "ledger path is outside the exact operator grant")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    # The private SQLite ledger reuses the historical MySQL table definitions.
    schema = (BACKEND / "migrations/mysql/076_learning_paid_budget.sql").read_text()
    schema = schema.replace("BIGINT AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT").replace(" ENGINE=InnoDB", "")
    care = (BACKEND / "migrations/mysql/022_care_observation_contract.sql").read_text()
    audit = care[care.index("CREATE TABLE IF NOT EXISTS audit_events"):]
    audit = audit[:audit.index(";", audit.index("created_at BIGINT")) + 1]
    try:
        with sqlite3.connect(str(path)) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=FULL")
            conn.executescript(schema + "\n" + audit)
            conn.execute("CREATE TABLE formal_flash_eval_manifest (id INTEGER PRIMARY KEY CHECK(id=1), plan_json TEXT NOT NULL, plan_sha256 TEXT NOT NULL)")
            conn.execute("INSERT INTO formal_flash_eval_manifest VALUES(1,?,?)", (canonical(plan), digest(plan)))
        database = IsolatedBudgetDatabase(path)
        service = LearningBudgetService(database, policy=policy, clock=clock)
        bindings = {}
        for scope in window["scopes"]:
            bindings[scope["subject"]] = service.issue_course_authorization(
                authorization_id=plan["authorizationIds"][scope["subject"]], scope=scope)
        with open(path, "rb") as stream:
            os.fsync(stream.fileno())
        return service, bindings
    except Exception:
        # A failed fresh initialization stays as evidence and cannot be reused
        # as a reset path. The operator must inspect it before another ledger.
        raise


def open_ledger(path: Path, *, expected_plan_sha256: str, clock=now_ms) -> LearningBudgetService:
    database = IsolatedBudgetDatabase(path)
    with database.transaction() as conn:
        row = conn.execute("SELECT * FROM formal_flash_eval_manifest WHERE id=1").fetchone()
    _require(row is not None and row["plan_sha256"] == expected_plan_sha256, "isolated ledger ownership mismatch")
    plan = json.loads(row["plan_json"])
    _require(digest(plan) == expected_plan_sha256, "isolated ledger manifest changed")
    _require(str(Path(path).absolute()) == plan["approval"]["ledgerPath"], "copied ledger cannot create another spending instance")
    return LearningBudgetService(database, policy=validate_plan(plan), clock=clock)


class IsolatedInternalGuard(InternalRequestGuard):
    def __init__(self, database, token):
        _require(isinstance(token, str) and 32 <= len(token) <= 512 and token == token.strip(), "isolated internal token required")
        # Keep production authorize/token handling/audit behavior, substituting
        # only the fresh SQLite storage adapter (production Database is MySQL).
        self.repository = CareRepository(database)
        self.token = token
        self.allowed_sources = {"127.0.0.1", "::1"}


def create_app(service: LearningBudgetService, *, token: str):
    """Return an unstarted loopback-only accounting app; no grant issuance route."""
    from flask import Flask, jsonify, request
    _require(isinstance(service.repository.database, IsolatedBudgetDatabase), "only isolated ledger may serve acceptance accounting")
    guard = IsolatedInternalGuard(service.repository.database, token)
    app = Flask("formal_flash_eval_budget")
    app.config["MAX_CONTENT_LENGTH"] = 16384
    def handle(operation):
        try:
            guard.authorize(route=request.path, headers=request.headers, source_ip=request.remote_addr)
            if request.args or (request.content_length or 0) > 16384:
                raise ApiError("learning_budget_invalid_request", "预算请求格式错误。", 400)
            if operation == "status":
                result = service.status()
            else:
                body = request.get_json(silent=True)
                fields = _FIELDS[operation]
                if not isinstance(body, dict) or set(body) != set(fields):
                    raise ApiError("learning_budget_invalid_request", "预算请求字段错误。", 400)
                result = getattr(service, operation)(**{fields[k]: v for k, v in body.items()})
            response = jsonify({"ok": True, "budget": result})
            response.headers["Cache-Control"] = "no-store"
            return response
        except ApiError as exc:
            return error_response(exc)
        except (ValueError, TypeError, KeyError):
            return error_response(ApiError("learning_budget_invalid_request", "预算计量或策略无效。", 400))
    prefix = "/internal/learning/budget/"
    for operation in _FIELDS:
        path = "context" if operation == "authorization_context" else operation
        app.add_url_rule(prefix + path, operation, lambda op=operation: handle(op), methods=["POST"])
    app.add_url_rule(prefix + "status", "status", lambda: handle("status"), methods=["GET"])
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", type=Path, action="append", required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--price-evidence", type=Path, required=True)
    parser.add_argument("--plan-output", type=Path, required=True)
    args = parser.parse_args(argv)
    read = lambda path: json.loads(path.read_text())
    plan = build_plan([read(path) for path in args.frozen], approval=read(args.approval), price_evidence=read(args.price_evidence))
    write_json_new(args.plan_output, plan)
    print(canonical({"ok": True, "planSha256": digest(plan), "planPath": str(args.plan_output.absolute()),
                     "initialized": False, "externalCalls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
