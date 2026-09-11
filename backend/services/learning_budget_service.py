"""Reserve before dispatch; ambiguous external outcomes retain their full hold.

This is an accounting boundary, not a Provider client. The caller MUST acquire
dispatch permission before the external call and enforce the returned maxima.
Authorizations can only be created by trusted business/operator code after it
has validated ownership and the user's approved production/teaching scope.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re

from content.learning_budget_policy import LearningBudgetPolicy, PURPOSES, UNITS, canonical, digest, units
from core.errors import ApiError
from core.security import now_ms
from repositories.learning_budget_repository import LearningBudgetRepository

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}")
_SHA = re.compile(r"[0-9a-f]{64}")
_PENDING = {"reserved", "dispatched", "unknown"}


def _fail(code, status=409):
    raise ApiError("learning_budget_" + code, "教学调用预算未通过校验：" + code, status)


def _identifier(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        _fail("invalid_identity", 400)
    return value


def _sha(value):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        _fail("invalid_digest", 400)
    return value


def _key(value):
    return hashlib.sha256(value.encode()).hexdigest()


class LearningBudgetService:
    def __init__(self, database, *, policy=None, clock=now_ms):
        self.repository = LearningBudgetRepository(database)
        self.policy = policy or LearningBudgetPolicy.load()
        self.clock = clock

    def _enabled(self, conn):
        if not self.policy.raw["enabled"]:
            _fail("disabled", 503)
        if self.repository.control(conn)["halted"]:
            _fail("halted", 503)

    def _scope_allowed(self, scope, now):
        window = self.policy.raw.get("authorizationWindow")
        if window is not None:
            if not window["startsAt"] <= now < window["expiresAt"]:
                _fail("authorization_window_closed", 403)
            if scope not in window["scopes"]:
                _fail("scope_not_approved", 403)

    @staticmethod
    def validate_scope(scope):
        required = {"purpose", "gradeCode", "subject", "courseId", "courseVersion",
                    "userId", "sessionId", "productionJobId", "approvalReference"}
        if not isinstance(scope, dict) or set(scope) != required:
            _fail("invalid_scope", 400)
        if scope["purpose"] not in PURPOSES or scope["gradeCode"] not in {
            f"primary_{n}" for n in range(1, 7)
        } or scope["subject"] not in {"chinese", "math", "english"}:
            _fail("invalid_scope", 400)
        for field in ("courseId", "courseVersion", "approvalReference"):
            _identifier(scope[field])
        if scope["purpose"] == "production":
            _identifier(scope["productionJobId"])
            if scope["userId"] is not None or scope["sessionId"] is not None:
                _fail("production_scope_has_student", 400)
        else:
            _identifier(scope["userId"])
            _identifier(scope["sessionId"])
            if scope["productionJobId"] is not None:
                _fail("teaching_scope_has_production", 400)
        return dict(scope)

    def _catalog_production_scope(self, conn, build_item_id, *, expected_grade=None,
                                  expected_subject=None, expected_skill=None,
                                  expected_course_id=None, expected_course_version=None):
        from services.learning_curriculum_preparation_contract import preparation_target_fingerprint
        _identifier(build_item_id)
        item = conn.execute("""SELECT item.*, build.target_spec_json, build.request_id AS build_request_id
            FROM learning_catalog_build_items AS item
            JOIN learning_catalog_build_jobs AS build ON build.id = item.build_job_id
            WHERE item.id = ?""", (build_item_id,)).fetchone()
        if item is None:
            _fail("catalog_item_required", 403)
        for field, expected in (("grade_code", expected_grade), ("subject", expected_subject),
                                ("skill_id", expected_skill), ("course_id", expected_course_id),
                                ("course_version", expected_course_version)):
            if expected is not None and str(item[field] or "") != str(expected):
                _fail("catalog_scope_mismatch", 403)
        target = json.loads(item["target_spec_json"])
        if (target.get("gradeCode") != item["grade_code"] or not any(
                isinstance(slot, dict) and slot.get("subject") == item["subject"]
                and slot.get("skillId") == item["skill_id"]
                and slot.get("variantOrdinal") == item["variant_ordinal"]
                and slot.get("boundaryVersion") == item["boundary_version"]
                for slot in target.get("courseTargets", []))):
            _fail("catalog_target_scope_mismatch", 403)
        fingerprint = preparation_target_fingerprint(target)
        from integrations.openmaic_formal_media import policy_from_target
        try:
            policy = policy_from_target(target)
        except ValueError:
            _fail("catalog_target_policy_invalid", 403)
        required = item["grade_code"] != "primary_1" or "interactionDesignPolicy" in policy or self.policy.raw["enabled"]
        owner = conn.execute("SELECT id FROM learning_curriculum_preparation_plans WHERE catalog_build_id = ? AND library_target_fingerprint IS NOT NULL", (item["build_job_id"],)).fetchone()
        if required and owner is None:
            _fail("catalog_shared_scope_required", 403)
        if owner is not None:
            from services.learning_curriculum_preparation_contract import build_preparation_target
            current_fingerprint = preparation_target_fingerprint(build_preparation_target(item["grade_code"]))
            if fingerprint != current_fingerprint and conn.execute(
                    "SELECT 1 FROM learning_curriculum_preparation_plans WHERE library_target_fingerprint = ? AND grade_code = ?",
                    (current_fingerprint, item["grade_code"])).fetchone() is not None:
                _fail("catalog_scope_superseded", 403)
            enabled = conn.execute("""SELECT enabled FROM learning_course_supply_requests
                WHERE target_fingerprint = ? AND subject = ? AND skill_id = ? AND variant_ordinal = ?""",
                (fingerprint, item["subject"], item["skill_id"], item["variant_ordinal"])).fetchone()
            if enabled is None or not enabled["enabled"]:
                _fail("catalog_scope_disabled", 403)
        scope = {"purpose": "production", "gradeCode": item["grade_code"], "subject": item["subject"],
            "courseId": "catalog-item:" + build_item_id,
            "courseVersion": digest({"curriculumVersion": item["curriculum_version"],
                "boundaryVersion": item["boundary_version"], "targetSpec": target}),
            "productionJobId": build_item_id, "userId": None, "sessionId": None,
            "approvalReference": item["build_request_id"]}
        return self.validate_scope(scope), required

    def catalog_production_dispatch_context(self, *, build_item_id, **expected):
        # Freeze one course package across logical attempts, phases, review and media.
        # The DB lookup is repeated by reserve/dispatch, so a later scope reduction wins.
        with self.repository.database.transaction() as conn:
            scope, required = self._catalog_production_scope(conn, build_item_id, **expected)
        binding = self.issue_course_authorization(
            authorization_id=digest({"schema": "mira.catalog-paid-budget.v1", "scope": scope}), scope=scope) if required else None
        return {"required": required, "binding": binding}

    def issue_catalog_production_authorization(self, *, build_item_id, **expected):
        return self.catalog_production_dispatch_context(build_item_id=build_item_id, **expected)["binding"]

    def issue_course_authorization(self, *, authorization_id, scope, existing_only=False):
        """Derive all limits/prices from trusted operational policy, never request JSON."""
        scope = self.validate_scope(scope)
        template = self.policy.raw["authorizationTemplates"][scope["purpose"]]
        if not self.policy.raw["enabled"] or template is None:
            return None
        now = self.clock()
        self._scope_allowed(scope, now)
        expires_at = now + template["ttlMs"]
        if self.policy.raw.get("authorizationWindow"):
            expires_at = min(expires_at, self.policy.raw["authorizationWindow"]["expiresAt"])
        self.create_authorization(authorization_id=authorization_id, scope=scope,
            max_units=template["maxUnits"], price_keys=template["priceKeys"],
            expires_at=expires_at, _reuse_expiry=True, _existing_only=existing_only)
        return {"schemaVersion": "mira.learning.paid-budget-binding.v1",
                "authorizationId": authorization_id, "required": True}

    def create_authorization(self, *, authorization_id, scope, max_units, price_keys, expires_at,
                             _reuse_expiry=False, _existing_only=False):
        """Internal Python API ONLY. Never expose this method directly to Runtime.

        The owning business service must derive scope from an authorized stored
        job/session. The HTTP reserve endpoint cannot mint or broaden it.
        """
        identity = _sha(authorization_id)
        scope = self.validate_scope(scope)
        maximum = units(max_units, money=True, complete=True)
        if (not isinstance(price_keys, list) or not price_keys
                or any(not isinstance(k, str) for k in price_keys)
                or len(price_keys) != len(set(price_keys))):
            _fail("invalid_price_scope", 400)
        for key in price_keys:
            self.policy.price(key)
        prices = {"keys": sorted(price_keys), "prices": {key: self.policy.price(key) for key in sorted(price_keys)}}
        now = self.clock()
        if type(expires_at) is not int or not now < expires_at <= now + 31 * 86400000:
            _fail("invalid_authorization_expiry", 400)
        self._scope_allowed(scope, now)
        with self.repository.locked() as conn:
            self._enabled(conn)
            existing = self.repository.authorization(conn, identity)
            if existing is not None:
                price_scope_matches = existing["price_keys_json"] == canonical(prices)
                if not price_scope_matches:
                    from services.learning_single_search_transition import transition_allows_template
                    price_scope_matches = transition_allows_template(conn, existing, prices)
                if (existing["scope_json"] != canonical(scope)
                        or existing["limits_json"] != canonical(maximum)
                        or not price_scope_matches
                        or not _reuse_expiry and existing["expires_at"] != expires_at):
                    _fail("authorization_conflict")
                if existing["revoked_at"] is not None:
                    _fail("authorization_expired", 403)
                if existing["expires_at"] <= now:
                    if not (_reuse_expiry and scope["purpose"] == "required_teaching"
                            and self.policy.renew_teaching_authorizations
                            and self.policy.raw.get("authorizationWindow") is None):
                        _fail("authorization_expired", 403)
                    self._renew_teaching_authorization(conn, existing, scope, expires_at, now)
                return {"authorizationId": identity, "created": False}
            if _existing_only:
                _fail("authorization_required", 403)
            caps = self.policy.raw["limits"]["authorization"]
            if maximum["calls"] < 1 or (self.policy.aggregate_limits_enabled
                    and any(maximum[k] > caps[k] for k in UNITS)):
                _fail("authorization_limit")
            if scope["purpose"] == "required_teaching":
                # Reserve the whole promised teaching package before admission;
                # production cannot spend money promised to active lessons.
                self._check_capacity(conn, {"id": identity, "limits_json": canonical(maximum)},
                                     scope, maximum, now, check_inflight=False)
            self.repository.insert_authorization(conn, identity, scope, maximum, prices,
                                                 self.policy.sha256, expires_at, now)
        return {"authorizationId": identity, "created": True}

    def _renew_teaching_authorization(self, conn, existing, scope, expires_at, now):
        # The trusted learning admission path has revalidated the active stored
        # session. Renew only expiry, under the same lock as revoke and reserve.
        # Existing spending and unknown holds continue to consume this grant.
        remaining = json.loads(existing["limits_json"])
        ledger = self.repository.authorization_ledger(conn, existing["id"])
        for allocation in ledger:
            used = json.loads(allocation["actual_units_json"] if allocation["state"] == "settled"
                              else allocation["max_units_json"])
            remaining = {key: max(0, remaining[key] - used[key]) for key in UNITS}
        self._check_capacity(conn, existing, scope, remaining, now, check_inflight=False)
        audit = {"schemaVersion": "mira.learning.teaching-authorization-renewal.v1",
                 "authorizationId": existing["id"], "scopeSha256": digest(scope),
                 "previousAuthorizationSha256": digest(dict(existing)),
                 "previousExpiresAt": existing["expires_at"], "expiresAt": expires_at,
                 "policySha256": self.policy.sha256, "renewedAt": now,
                 "reason": "active_learning_session", "providerDispatch": False}
        updated = conn.execute("""UPDATE learning_budget_authorizations SET expires_at = ?
            WHERE id = ? AND expires_at = ? AND revoked_at IS NULL""",
            (expires_at, existing["id"], existing["expires_at"]))
        if updated.rowcount != 1:
            _fail("authorization_conflict")
        # Events have a reservation FK. Reuse a real historical row when one
        # exists; otherwise a released, zero-unit audit marker is never dispatchable.
        anchor = conn.execute("SELECT id FROM learning_budget_reservations WHERE authorization_id = ? ORDER BY created_at, id LIMIT 1",
                              (existing["id"],)).fetchone()
        if anchor is None:
            marker = digest({"schema": "mira.learning.authorization-audit-marker.v1", "authorizationId": existing["id"]})
            self.repository.insert_reservation(conn, {
                "id": marker, "authorization_id": existing["id"],
                "dispatch_id": "authorization-audit:" + existing["id"],
                "request_sha256": digest(audit), "request_identity_sha256": marker,
                "purpose": scope["purpose"], "user_key": _key(scope["userId"]),
                "course_key": digest([scope["gradeCode"], scope["subject"], scope["courseId"], scope["courseVersion"]]),
                "policy_sha256": self.policy.sha256,
                "price_json": canonical({"key": "authorization-audit-only", "version": "v1",
                    "provider": "internal", "model": "authorization-audit",
                    "allowedUnits": ["calls"], "perCallMax": {"calls": 1},
                    "microsPerMillionUnits": {"calls": 0},
                    "kind": "authorization_audit_only", "providerDispatch": False}),
                "max_units_json": canonical(dict.fromkeys(UNITS, 0)),
                "state": "released", "created_at": now, "charge_at": now})
            anchor = {"id": marker}
        self.repository.event(conn, anchor["id"], "teaching_authorization_renewed",
                              {"renewalSha256": digest(audit), "audit": audit}, now)

    def _authority(self, conn, identity, now, *, active=True):
        row = self.repository.authorization(conn, _sha(identity))
        if row is None:
            _fail("authorization_required", 403)
        if active and (row["revoked_at"] is not None or row["expires_at"] <= now):
            _fail("authorization_expired", 403)
        if active:
            scope = json.loads(row["scope_json"])
            self._scope_allowed(scope, now)
            if scope["purpose"] == "production" and scope["courseId"].startswith("catalog-item:"):
                current, _required = self._catalog_production_scope(conn, scope["productionJobId"])
                if current != scope:
                    _fail("catalog_scope_changed", 403)
        return row

    def _windows(self, now):
        dt = datetime.fromtimestamp(now / 1000, self.policy.timezone)
        day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return {"day": int(day.timestamp() * 1000), "month": int(day.replace(day=1).timestamp() * 1000)}

    def _check_capacity(self, conn, authority, scope, requested, now, *, exclude_id=None, check_inflight=True):
        windows = self._windows(now)
        user_key = _key(scope["userId"]) if scope["userId"] else ""
        course_key = digest([scope["gradeCode"], scope["subject"], scope["courseId"], scope["courseVersion"]])
        rows = self.repository.ledger(conn, since=windows["month"],
            authorization_id=authority["id"], course_key=course_key)
        rows = [r for r in rows if r["id"] != exclude_id and r["state"] != "released"]
        limits = self.policy.raw["limits"]
        inflight = sum(json.loads(r["max_units_json"])["calls"] for r in rows if r["state"] in _PENDING)
        if check_inflight and inflight + requested["calls"] > limits["global"]["maxInflightCalls"]:
            _fail("inflight_limit", 429)
        if not self.policy.aggregate_limits_enabled:
            # Metering-only policy: preserve prices, identity and durable holds;
            # SDK/model technical limits remain at the actual provider boundary.
            return user_key, course_key
        for package in self.repository.open_authorizations(conn, now):
            package_scope = json.loads(package["scope_json"])
            if package_scope["purpose"] != "required_teaching" or package["id"] == authority["id"]:
                continue
            remaining = json.loads(package["limits_json"])
            for allocation in self.repository.authorization_ledger(conn, package["id"]):
                used = json.loads(allocation["actual_units_json"] if allocation["state"] == "settled" else allocation["max_units_json"])
                remaining = {key: max(0, remaining[key] - used[key]) for key in UNITS}
            rows.append({"id": "package:" + package["id"], "authorization_id": package["id"],
                "purpose": "required_teaching", "user_key": _key(package_scope["userId"]),
                "course_key": digest([package_scope["gradeCode"], package_scope["subject"],
                    package_scope["courseId"], package_scope["courseVersion"]]),
                "state": "reserved", "charge_at": package["created_at"], "max_units_json": canonical(remaining)})
        checks = [
            ("authorization", json.loads(authority["limits_json"]), lambda r: r["authorization_id"] == authority["id"]),
            ("course", limits["course"]["lifetime"], lambda r: r["course_key"] == course_key),
        ]
        for window, start in windows.items():
            # All unresolved holds survive day/month changes and process restarts.
            def current(r, start=start):
                return r["state"] in _PENDING or r["charge_at"] >= start
            checks.extend([
                ("global_" + window, limits["global"][window], current),
                ("purpose_" + window, limits["purposes"][scope["purpose"]][window],
                    lambda r, current=current: current(r) and r["purpose"] == scope["purpose"]),
            ])
            if user_key:
                checks.append(("user_" + window, limits["user"][window],
                    lambda r, current=current: current(r) and r["user_key"] == user_key))
        for name, maximum, applies in checks:
            consumed = dict.fromkeys(UNITS, 0)
            for row in rows:
                if applies(row):
                    amounts = json.loads(row["actual_units_json"] if row["state"] == "settled" else row["max_units_json"])
                    for key in UNITS:
                        consumed[key] += amounts[key]
            if any(consumed[k] + requested[k] > maximum[k] for k in UNITS):
                _fail(name + "_limit", 429)
        return user_key, course_key

    def reserve(self, *, authorization_id, dispatch_id, request_sha256, price_key, max_units):
        _identifier(dispatch_id)
        _sha(request_sha256)
        identity = _key(dispatch_id)
        request_identity = digest({"authorizationId": authorization_id, "dispatchId": dispatch_id,
            "requestSha256": request_sha256, "priceKey": price_key, "maxUnits": max_units})
        now = self.clock()
        with self.repository.locked() as conn:
            authority = self._authority(conn, authorization_id, now, active=False)
            existing = self.repository.reservation(conn, identity)
            if existing is not None:
                if existing["request_identity_sha256"] != request_identity:
                    _fail("dispatch_conflict")
                return self._view(existing, reused=True)
            self._enabled(conn)
            self._authority(conn, authorization_id, now)
            frozen = json.loads(authority["price_keys_json"])
            if not isinstance(frozen, dict) or "prices" not in frozen:
                _fail("authorization_price_snapshot_required", 409)
            if price_key not in frozen["prices"]:
                _fail("price_not_authorized", 403)
            from services.learning_single_search_transition import transition_active_prices
            active_prices = transition_active_prices(conn, authority)
            if active_prices is not None and price_key not in active_prices:
                _fail("price_not_authorized", 403)
            price = frozen["prices"][price_key]
            maximum = self.policy.measure(max_units, price, reservation=True,
                enforce_per_call_limits=self.policy.aggregate_limits_enabled)
            scope = json.loads(authority["scope_json"])
            user_key, course_key = self._check_capacity(conn, authority, scope, maximum, now)
            self.repository.insert_reservation(conn, {
                "id": identity, "authorization_id": authorization_id, "dispatch_id": dispatch_id,
                "request_sha256": request_sha256, "request_identity_sha256": request_identity,
                "purpose": scope["purpose"], "user_key": user_key, "course_key": course_key,
                "policy_sha256": self.policy.sha256, "price_json": canonical({"key": price_key, **price}),
                "max_units_json": canonical(maximum), "state": "reserved", "created_at": now, "charge_at": now,
            })
            self.repository.event(conn, identity, "reserved", {"requestSha256": request_sha256}, now)
            return self._view(self.repository.reservation(conn, identity))

    def _bound(self, conn, reservation_id, authorization_id):
        row = self.repository.reservation(conn, _sha(reservation_id))
        if row is None or row["authorization_id"] != _sha(authorization_id):
            _fail("reservation_required", 403)
        return row

    def dispatch(self, *, reservation_id, authorization_id, request_sha256):
        _sha(request_sha256)
        now = self.clock()
        with self.repository.locked() as conn:
            row = self._bound(conn, reservation_id, authorization_id)
            if row["request_sha256"] != request_sha256:
                _fail("request_conflict")
            if row["state"] != "reserved":
                return {**self._view(row, reused=True), "dispatchAllowed": False}
            self._enabled(conn)
            authority = self._authority(conn, authorization_id, now)
            from services.learning_single_search_transition import transition_active_prices
            active_prices = transition_active_prices(conn, authority)
            if active_prices is not None and json.loads(row['price_json'])['key'] not in active_prices:
                _fail("price_not_authorized", 403)
            self._check_capacity(conn, authority, json.loads(authority["scope_json"]),
                                 json.loads(row["max_units_json"]), now, exclude_id=row["id"])
            conn.execute("""UPDATE learning_budget_reservations SET state = 'dispatched',
                dispatched_at = ?, charge_at = ? WHERE id = ?""", (now, now, row["id"]))
            self.repository.event(conn, row["id"], "dispatched", {"requestSha256": request_sha256}, now)
            return {**self._view(self.repository.reservation(conn, row["id"])), "dispatchAllowed": True}

    def settle(self, *, reservation_id, authorization_id, actual_units, provider_request_id, evidence_sha256):
        _sha(evidence_sha256)
        if provider_request_id is not None and (not isinstance(provider_request_id, str) or not 1 <= len(provider_request_id) <= 255):
            _fail("invalid_provider_receipt", 400)
        now = self.clock()
        with self.repository.locked() as conn:
            row = self._bound(conn, reservation_id, authorization_id)
            actual = self.policy.measure(actual_units, json.loads(row["price_json"]), reservation=False)
            settlement = digest({"actualUnits": actual, "providerRequestId": provider_request_id,
                                 "evidenceSha256": evidence_sha256})
            if row["state"] == "settled":
                if row["settlement_sha256"] != settlement:
                    _fail("settlement_conflict")
                return self._view(row, reused=True)
            if row["state"] not in {"dispatched", "unknown"}:
                _fail("not_dispatched")
            maximum = json.loads(row["max_units_json"])
            overrun = any(actual[k] > maximum[k] for k in UNITS)
            conn.execute("""UPDATE learning_budget_reservations SET state = 'settled',
                actual_units_json = ?, settlement_sha256 = ?, provider_request_id = ?, settled_at = ? WHERE id = ?""",
                (canonical(actual), settlement, provider_request_id, now, row["id"]))
            self.repository.event(conn, row["id"], "settled", {"evidenceSha256": evidence_sha256,
                "overrun": overrun, "settlementSha256": settlement}, now)
            if overrun:
                # Never hide real overuse by rejecting settlement or refunding it.
                self.repository.halt(conn, "provider_usage_exceeded_reservation")
            return {**self._view(self.repository.reservation(conn, row["id"])), "overrun": overrun}

    def unknown(self, *, reservation_id, authorization_id, reason_code):
        _identifier(reason_code)
        with self.repository.locked() as conn:
            row = self._bound(conn, reservation_id, authorization_id)
            if row["state"] == "unknown":
                return self._view(row, reused=True)
            if row["state"] != "dispatched":
                _fail("not_dispatched")
            conn.execute("UPDATE learning_budget_reservations SET state = 'unknown' WHERE id = ?", (row["id"],))
            self.repository.event(conn, row["id"], "unknown", {"reasonCode": reason_code}, self.clock())
            return self._view(self.repository.reservation(conn, row["id"]))

    def release(self, *, reservation_id, authorization_id, reason_code):
        _identifier(reason_code)
        with self.repository.locked() as conn:
            row = self._bound(conn, reservation_id, authorization_id)
            if row["state"] == "released":
                return self._view(row, reused=True)
            if row["state"] != "reserved":
                _fail("cannot_release_dispatched")
            conn.execute("UPDATE learning_budget_reservations SET state = 'released' WHERE id = ?", (row["id"],))
            self.repository.event(conn, row["id"], "released", {"reasonCode": reason_code}, self.clock())
            return self._view(self.repository.reservation(conn, row["id"]))

    def status(self):
        with self.repository.locked() as conn:
            control = self.repository.control(conn)
            return {"schemaVersion": "mira.learning.budget-status.v1", "enabled": self.policy.raw["enabled"],
                    "aggregateLimitsEnabled": self.policy.aggregate_limits_enabled,
                    "policyVersion": self.policy.raw["version"], "policySha256": self.policy.sha256,
                    "halted": bool(control["halted"]), "reasonCode": control["reason_code"],
                    "states": self.repository.status(conn), "integrationCoverage": "caller_enforced"}

    def authorization_context(self, *, authorization_id):
        """Internal transport lookup; no client-supplied price/rate substitution."""
        with self.repository.locked() as conn:
            self._enabled(conn)
            authority = self._authority(conn, authorization_id, self.clock())
            from services.learning_single_search_transition import transition_active_prices
            active_prices = transition_active_prices(conn, authority)
            ledger = self.repository.authorization_ledger(conn, authorization_id)
            return {"authorizationId": authorization_id,
                    "purpose": json.loads(authority["scope_json"])["purpose"],
                    "aggregateLimitsEnabled": self.policy.aggregate_limits_enabled,
                    "unsettledReservationCount": sum(row["state"] in _PENDING
                        for row in ledger),
                    "latestProviderDispatchAt": max((int(row["dispatched_at"]) for row in ledger
                        if row.get("dispatched_at") is not None), default=None),
                    "prices": active_prices if active_prices is not None else json.loads(authority["price_keys_json"])["prices"]}

    def close_authorization(self, *, authorization_id):
        """Trusted owner closes a lesson/package; dispatched holds remain charged."""
        with self.repository.locked() as conn:
            self._authority(conn, authorization_id, self.clock(), active=False)
            conn.execute("UPDATE learning_budget_authorizations SET revoked_at = COALESCE(revoked_at, ?) WHERE id = ?",
                         (self.clock(), authorization_id))

    @staticmethod
    def _view(row, *, reused=False):
        price = json.loads(row["price_json"])
        return {"schemaVersion": "mira.learning.budget-reservation.v1", "reservationId": row["id"],
                "authorizationId": row["authorization_id"], "dispatchId": row["dispatch_id"],
                "requestSha256": row["request_sha256"], "state": row["state"], "reused": reused,
                "priceKey": price["key"], "priceVersion": price["version"],
                "provider": price["provider"], "model": price["model"],
                "maxUnits": json.loads(row["max_units_json"]),
                "actualUnits": json.loads(row["actual_units_json"]) if row["actual_units_json"] else None,
                "pricingStatus": "versioned_estimate" if price["microsPerMillionUnits"] is not None else "unpriced_units_only",
                "currency": "CNY", "dispatchAllowed": False}
