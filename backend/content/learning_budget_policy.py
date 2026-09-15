"""Server-owned limits and versioned prices; this registry never grants spending."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

UNITS = ("calls", "input_tokens", "output_tokens", "characters", "audio_ms",
         "video_ms", "images", "search_requests", "money_micros")
PURPOSES = ("production", "required_teaching", "optional_interaction")
MAX_UNITS = 10**12
DEFAULT_POLICY_PATH = Path(__file__).with_name("learning_budget_policy.json")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def units(value, *, money=False, complete=False):
    allowed = set(UNITS if money else UNITS[:-1])
    if not isinstance(value, dict) or not set(value) <= allowed:
        raise ValueError("unsupported budget measurement")
    if complete and set(value) != allowed:
        raise ValueError("budget limits must explicitly cover all measurements")
    if any(type(v) is not int or not 0 <= v <= MAX_UNITS for v in value.values()):
        raise ValueError("budget measurements must be bounded nonnegative integers")
    return {key: value.get(key, 0) for key in UNITS}


def _exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("invalid budget policy fields")


class LearningBudgetPolicy:
    def __init__(self, raw):
        raw = deepcopy(raw)
        allowed_window = raw.pop("authorizationWindow", None)
        fields = {"schemaVersion", "version", "enabled", "currency", "timezone",
                  "allowUnpriced", "limits", "prices", "authorizationTemplates"}
        if "aggregateLimitsEnabled" in raw:
            fields.add("aggregateLimitsEnabled")
        if "renewTeachingAuthorizations" in raw:
            fields.add("renewTeachingAuthorizations")
        if "productionInflightOverride" in raw:
            fields.add("productionInflightOverride")
        _exact(raw, fields)
        # Keep absent fields absent so legacy frozen policy hashes remain valid.
        self.aggregate_limits_enabled = raw.get("aggregateLimitsEnabled", True)
        if type(self.aggregate_limits_enabled) is not bool:
            raise ValueError("aggregate budget switch must be a boolean")
        self.renew_teaching_authorizations = raw.get("renewTeachingAuthorizations", False)
        if type(self.renew_teaching_authorizations) is not bool:
            raise ValueError("teaching renewal switch must be a boolean")
        if self.renew_teaching_authorizations and allowed_window is not None:
            raise ValueError("fixed authorization windows cannot renew teaching authorizations")
        if raw["schemaVersion"] != "mira.learning.budget-policy.v1":
            raise ValueError("unsupported budget policy schema")
        if not isinstance(raw["version"], str) or not 1 <= len(raw["version"]) <= 128:
            raise ValueError("invalid budget policy version")
        if type(raw["enabled"]) is not bool or type(raw["allowUnpriced"]) is not bool:
            raise ValueError("budget switches must be booleans")
        if raw["currency"] != "CNY":
            raise ValueError("unsupported budget currency")
        self.timezone = ZoneInfo(raw["timezone"])
        limits = raw["limits"]
        _exact(limits, {"global", "purposes", "user", "course", "authorization"})
        _exact(limits["global"], {"day", "month", "maxInflightCalls"})
        maximum = limits["global"]["maxInflightCalls"]
        if type(maximum) is not int or not 0 <= maximum <= 10000:
            raise ValueError("invalid global inflight limit")
        _exact(limits["purposes"], PURPOSES)
        _exact(limits["user"], {"day", "month"})
        _exact(limits["course"], {"lifetime"})
        for pool in [limits["global"], limits["user"], *limits["purposes"].values()]:
            if pool is not limits["global"]:
                _exact(pool, {"day", "month"})
            for window in ("day", "month"):
                units(pool[window], money=True, complete=True)
        units(limits["course"]["lifetime"], money=True, complete=True)
        units(limits["authorization"], money=True, complete=True)
        if not isinstance(raw["prices"], dict):
            raise ValueError("prices must be a registry")
        for key, price in raw["prices"].items():
            if not isinstance(key, str) or not 1 <= len(key) <= 128:
                raise ValueError("invalid price key")
            _exact(price, {"provider", "model", "version", "allowedUnits", "perCallMax",
                           "microsPerMillionUnits"})
            if any(not isinstance(price[k], str) or not 1 <= len(price[k]) <= 128
                   for k in ("provider", "model", "version")):
                raise ValueError("price identity is missing")
            allowed = price["allowedUnits"]
            if (not isinstance(allowed, list) or len(set(allowed)) != len(allowed)
                    or "calls" not in allowed or not set(allowed) <= set(UNITS[:-1])):
                raise ValueError("invalid price measurement units")
            if set(price["perCallMax"]) != set(allowed):
                raise ValueError("price must cap every allowed measurement")
            maximum = units(price["perCallMax"])
            if maximum["calls"] != 1:
                raise ValueError("each dispatch reserves exactly one external request")
            rates = price["microsPerMillionUnits"]
            if rates is None:
                if not raw["allowUnpriced"]:
                    raise ValueError("unpriced profiles need explicit units-only policy")
            else:
                if not isinstance(rates, dict) or set(rates) != set(allowed):
                    raise ValueError("price must rate all allowed measurements")
                units(rates)
        _exact(raw["authorizationTemplates"], PURPOSES)
        for template in raw["authorizationTemplates"].values():
            if template is None:
                continue
            _exact(template, {"maxUnits", "priceKeys", "ttlMs"})
            maximum = units(template["maxUnits"], money=True, complete=True)
            if self.aggregate_limits_enabled and any(maximum[k] > limits["authorization"][k] for k in UNITS):
                raise ValueError("authorization template exceeds policy")
            keys = template["priceKeys"]
            if (not isinstance(keys, list) or not keys or any(not isinstance(k, str) for k in keys)
                    or len(set(keys)) != len(keys) or not set(keys) <= set(raw["prices"])):
                raise ValueError("authorization template price scope is invalid")
            if type(template["ttlMs"]) is not int or not 1 <= template["ttlMs"] <= 31 * 86400000:
                raise ValueError("authorization template expiry is invalid")
        if allowed_window is not None:
            _exact(allowed_window, {"startsAt", "expiresAt", "scopes"})
            start, end = allowed_window["startsAt"], allowed_window["expiresAt"]
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= start + 31 * 86400000:
                raise ValueError("invalid fixed budget authorization window")
            scopes = allowed_window["scopes"]
            fields = {"purpose", "gradeCode", "subject", "courseId", "courseVersion",
                      "userId", "sessionId", "productionJobId", "approvalReference"}
            if not isinstance(scopes, list) or not 1 <= len(scopes) <= 32:
                raise ValueError("explicit budget scopes are required")
            for scope in scopes:
                _exact(scope, fields)
                if scope["purpose"] not in PURPOSES:
                    raise ValueError("invalid fixed budget purpose")
            if len({canonical(scope) for scope in scopes}) != len(scopes):
                raise ValueError("duplicate fixed budget scope")
            raw["authorizationWindow"] = allowed_window
        override = raw.get("productionInflightOverride")
        if "productionInflightOverride" in raw:
            _exact(override, {"scopeSha256", "authorizationId", "maxInflightCalls", "auditReferenceSha256"})
            for key in ("scopeSha256", "authorizationId", "auditReferenceSha256"):
                if not isinstance(override[key], str) or not re.fullmatch(r"[a-f0-9]{64}", override[key]):
                    raise ValueError("invalid production inflight override identity")
            scopes = (allowed_window or {}).get("scopes", [])
            production = [scope for scope in scopes if scope["purpose"] == "production"]
            if (len(production) != 1 or digest(production[0]) != override["scopeSha256"]
                    or production[0]["userId"] is not None or production[0]["sessionId"] is not None
                    or not isinstance(production[0]["productionJobId"], str)
                    or production[0]["courseId"] != "catalog-item:" + production[0]["productionJobId"]
                    or override["authorizationId"] != digest({"schema": "mira.catalog-paid-budget.v1", "scope": production[0]})):
                raise ValueError("production inflight override requires one exact allowed catalog scope")
            if (self.aggregate_limits_enabled or limits["global"]["maxInflightCalls"] != 4
                    or type(override["maxInflightCalls"]) is not int or override["maxInflightCalls"] != 5):
                raise ValueError("production inflight override permits only one temporary slot above four")
        self.raw = raw
        self.sha256 = digest(raw)

    def production_inflight_override(self, *, scope, authorization_id, now):
        """A fixed-window admission exception; unresolved accounting stays intact."""
        override = self.raw.get("productionInflightOverride")
        window = self.raw.get("authorizationWindow")
        if (override is not None and window is not None
                and window["startsAt"] <= now < window["expiresAt"]
                and scope in window["scopes"] and scope["purpose"] == "production"
                and digest(scope) == override["scopeSha256"]
                and authorization_id == override["authorizationId"]):
            return deepcopy(override)
        return None

    @classmethod
    def load(cls, path=None):
        return cls(json.loads(Path(path or DEFAULT_POLICY_PATH).read_text()))

    def price(self, key):
        price = self.raw["prices"].get(key)
        if price is None:
            raise ValueError("price profile is not registered")
        return deepcopy(price)

    @staticmethod
    def measure(value, price, *, reservation, enforce_per_call_limits=True):
        if not isinstance(value, dict) or not set(value) <= set(price["allowedUnits"]):
            raise ValueError("request measurements differ from price profile")
        if set(value) != set(price["allowedUnits"]):
            raise ValueError("all price measurements must be explicitly supplied")
        result = units(value)
        if result["calls"] != 1:
            raise ValueError("a dispatched request always counts as one call")
        if reservation and enforce_per_call_limits:
            maximum = units(price["perCallMax"])
            if any(result[k] > maximum[k] for k in UNITS):
                raise ValueError("request exceeds per-call resource limits")
        rates = price["microsPerMillionUnits"]
        if rates is not None:
            # Round up once per request, using integers, never float currency.
            total = sum(result[k] * rates[k] for k in price["allowedUnits"])
            result["money_micros"] = (total + 999999) // 1000000
            if result["money_micros"] > MAX_UNITS:
                raise ValueError("request price exceeds accounting bound")
        return result
