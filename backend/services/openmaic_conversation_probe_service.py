from __future__ import annotations

from typing import Any, Mapping

from core.database import Database, DatabaseRow
from core.security import hash_value, new_token, now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
from repositories.openmaic_runtime_repository import OpenMaicRuntimeRepository


class OpenMaicConversationProbeError(RuntimeError):
    """A safe, operator-facing error for the isolated gateway probe flow."""

    def __init__(self, code: str, safe_message: str, *, status_code: int = 422):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.status_code = status_code


class OpenMaicConversationProbeService:
    """Issues and verifies one-time probe credentials for a ready classroom.

    This is deliberately separate from a student launch session: it creates no
    principal, family, child or learning-session association.  The gateway gets
    only a short-lived runtime token and must ask ``validate_runtime_token`` on
    every protected probe request.
    """

    REQUIRED_CHAT_RECEIPT = {
        "noCookieStatus": 401,
        "exchangeStatus": 204,
        "cookieHttpOnly": True,
        "wrongStageStatus": 403,
        "chatStatus": 200,
    }
    REQUIRED_TRANSCRIPTION_RECEIPT = {
        "overrideStatus": 400,
        "cleanStatus": 200,
    }

    def __init__(
        self,
        database_url: str | None = None,
        *,
        enabled: bool = False,
        ttl_seconds: int = 90,
        repository: OpenMaicRuntimeRepository | None = None,
    ):
        if repository is None:
            if not database_url:
                raise ValueError("database_url is required when repository is omitted")
            repository = OpenMaicRuntimeRepository(Database(database_url))
        self.repository = repository
        self.enabled = bool(enabled)
        self.ttl_seconds = int(ttl_seconds)
        if not 30 <= self.ttl_seconds <= 300:
            raise ValueError("Conversation probe TTL must be between 30 and 300 seconds.")

    def issue_probe(self, runtime_id: str) -> dict[str, Any]:
        self._require_enabled()
        normalized_runtime_id = _identifier(runtime_id, "runtime_id")
        issued_at = now_ms()
        expires_at = issued_at + self.ttl_seconds * 1000
        ticket = new_token("ompt")
        probe_id = new_token("omp")
        challenge = new_token("ompc")

        with self.repository.transaction() as conn:
            runtime = self.repository.get_runtime_classroom(
                conn, runtime_id=normalized_runtime_id, for_update=True
            )
            if runtime is None:
                raise OpenMaicConversationProbeError(
                    "openmaic_runtime_not_found", "课件运行时不存在", status_code=404
                )
            if (
                str(runtime.get("status") or "") != "ready"
                or str(runtime.get("quality_status") or "") != "approved"
                or runtime.get("retired_at") is not None
                or not str(runtime.get("upstream_classroom_id") or "").strip()
            ):
                raise OpenMaicConversationProbeError(
                    "openmaic_probe_runtime_unavailable",
                    "课件尚未通过可验证发布，不能创建对话探针",
                    status_code=409,
                )
            self._require_no_existing_probe(conn, str(runtime["id"]))
            self.repository.create_conversation_probe(
                conn,
                probe_id=probe_id,
                ticket_hash=hash_value(ticket),
                runtime_classroom_id=str(runtime["id"]),
                upstream_classroom_id=str(runtime["upstream_classroom_id"]),
                challenge=challenge,
                expires_at=expires_at,
                now=issued_at,
                candidate_kind="release",
            )
        return {
            "ok": True,
            "probeId": probe_id,
            "ticket": ticket,
            "runtimeId": normalized_runtime_id,
            "classroomId": str(runtime["upstream_classroom_id"]),
            "challenge": challenge,
            "expiresAt": expires_at,
        }

    def issue_generation_candidate(
        self, runtime_id: str, upstream_classroom_id: str
    ) -> dict[str, Any]:
        """Create a probe while attempt three is still awaiting mark-ready.

        This service-only bridge breaks no release gate: the public/internal
        issue route remains restricted to a ready, approved runtime, and the
        caller must supply the successful upstream classroom id before it has
        been persisted onto the runtime row.
        """
        self._require_enabled()
        normalized_runtime_id = _identifier(runtime_id, "runtime_id")
        normalized_classroom_id = _identifier(
            upstream_classroom_id, "upstream_classroom_id"
        )
        issued_at = now_ms()
        expires_at = issued_at + self.ttl_seconds * 1000
        ticket = new_token("ompt")
        probe_id = new_token("omp")
        challenge = new_token("ompc")
        with self.repository.transaction() as conn:
            runtime = self.repository.get_runtime_classroom(
                conn, runtime_id=normalized_runtime_id, for_update=True
            )
            if runtime is None:
                raise OpenMaicConversationProbeError(
                    "openmaic_runtime_not_found", "课件运行时不存在", status_code=404
                )
            if (
                str(runtime.get("status") or "") != "generating"
                or str(runtime.get("quality_status") or "") != "pending_review"
                or int(runtime.get("attempt_ordinal") or 0) != 3
                or not str(runtime.get("upstream_job_id") or "").strip()
                or str(runtime.get("upstream_classroom_id") or "").strip()
                or runtime.get("retired_at") is not None
            ):
                raise OpenMaicConversationProbeError(
                    "openmaic_probe_candidate_unavailable",
                    "当前生成尝试不允许创建对话探针",
                    status_code=409,
                )
            self._require_no_existing_probe(conn, str(runtime["id"]))
            self.repository.create_conversation_probe(
                conn,
                probe_id=probe_id,
                ticket_hash=hash_value(ticket),
                runtime_classroom_id=str(runtime["id"]),
                upstream_classroom_id=normalized_classroom_id,
                challenge=challenge,
                expires_at=expires_at,
                now=issued_at,
                candidate_kind="generation",
            )
        return {
            "ok": True,
            "probeId": probe_id,
            "ticket": ticket,
            "runtimeId": normalized_runtime_id,
            "classroomId": normalized_classroom_id,
            "challenge": challenge,
            "expiresAt": expires_at,
            "candidate": True,
            "candidateKind": "generation",
        }

    def issue_formal_candidate(self, runtime_id: str) -> dict[str, Any]:
        """Issue the route-only proof session for a bound formal candidate.

        Formal publication is machine-reviewed, so this path intentionally
        accepts ``ready/pending_review`` only when the immutable candidate
        binding and formal Runtime manifest are both present.  It does not
        grant a student session and it never performs a Provider call.
        """

        self._require_enabled()
        normalized_runtime_id = _identifier(runtime_id, "runtime_id")
        issued_at = now_ms()
        expires_at = issued_at + self.ttl_seconds * 1000
        ticket = new_token("ompt")
        probe_id = new_token("omp")
        challenge = new_token("ompc")
        with self.repository.transaction() as conn:
            runtime = self.repository.get_runtime_classroom(
                conn, runtime_id=normalized_runtime_id, for_update=True
            )
            manifest = (
                self.repository.decode_json(
                    runtime.get("feature_manifest_json"), {}
                )
                if runtime is not None
                else {}
            )
            upstream_classroom_id = str(
                (runtime or {}).get("upstream_classroom_id") or ""
            )
            if not (
                runtime is not None
                and str(runtime.get("status") or "") == "ready"
                and str(runtime.get("quality_status") or "")
                == "pending_review"
                and runtime.get("retired_at") is None
                and upstream_classroom_id
                and str(runtime.get("candidate_build_item_id") or "")
                and str(runtime.get("candidate_release_id") or "")
                and str(runtime.get("candidate_grade_code") or "")
                and str(runtime.get("candidate_target_fingerprint") or "")
                and str(
                    runtime.get("candidate_binding_contract_version") or ""
                )
                == "mira.learning.candidate-runtime-binding.v1"
                and isinstance(manifest, Mapping)
                and manifest.get("formalRuntimeContract")
                == OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CLASSROOM_CONTRACT
            ):
                raise OpenMaicConversationProbeError(
                    "openmaic_formal_probe_candidate_unavailable",
                    "正式候选课件尚未进入路由验证阶段",
                    status_code=409,
                )
            self._require_no_existing_probe(conn, normalized_runtime_id)
            self.repository.create_conversation_probe(
                conn,
                probe_id=probe_id,
                ticket_hash=hash_value(ticket),
                runtime_classroom_id=normalized_runtime_id,
                upstream_classroom_id=upstream_classroom_id,
                challenge=challenge,
                expires_at=expires_at,
                now=issued_at,
                candidate_kind="release",
            )
        return {
            "ok": True,
            "probeId": probe_id,
            "ticket": ticket,
            "runtimeId": normalized_runtime_id,
            "classroomId": upstream_classroom_id,
            "challenge": challenge,
            "expiresAt": expires_at,
            "candidate": True,
            "candidateKind": "formal_publication",
        }

    def issue_recovery_candidate(
        self,
        runtime_id: str,
        upstream_classroom_id: str,
        deterministic_recovery_id: str,
    ) -> dict[str, Any]:
        """Create the dedicated probe for a validated recovery artifact.

        This path cannot be substituted for ``issue_generation_candidate``:
        the runtime must be ``recovering`` and its unique recovery audit row
        must already be in the ``validating`` state with the same classroom.
        """

        self._require_enabled()
        normalized_runtime_id = _identifier(runtime_id, "runtime_id")
        normalized_classroom_id = _identifier(
            upstream_classroom_id, "upstream_classroom_id"
        )
        normalized_recovery_id = _identifier(
            deterministic_recovery_id, "deterministic_recovery_id"
        )
        issued_at = now_ms()
        expires_at = issued_at + self.ttl_seconds * 1000
        ticket = new_token("ompt")
        probe_id = new_token("omp")
        challenge = new_token("ompc")
        with self.repository.transaction() as conn:
            runtime = self.repository.get_runtime_classroom(
                conn, runtime_id=normalized_runtime_id, for_update=True
            )
            recovery = self.repository.get_deterministic_recovery_by_runtime(
                conn, runtime_id=normalized_runtime_id, for_update=True
            )
            if runtime is None or recovery is None:
                raise OpenMaicConversationProbeError(
                    "openmaic_recovery_probe_candidate_unavailable",
                    "确定性恢复课件尚未进入对话验证阶段",
                    status_code=409,
                )
            if (
                str(runtime.get("status") or "") != "recovering"
                or str(runtime.get("quality_status") or "") != "pending_review"
                or int(runtime.get("attempt_ordinal") or 0) != 3
                or runtime.get("retired_at") is not None
                or str(runtime.get("upstream_classroom_id") or "").strip()
                or str(recovery.get("id") or "") != normalized_recovery_id
                or str(recovery.get("status") or "") != "validating"
                or str(recovery.get("upstream_classroom_id") or "")
                != normalized_classroom_id
                or not str(recovery.get("source_job_snapshot_sha256") or "")
            ):
                raise OpenMaicConversationProbeError(
                    "openmaic_recovery_probe_candidate_unavailable",
                    "当前确定性恢复记录不允许创建对话探针",
                    status_code=409,
                )
            self._require_no_existing_probe(conn, normalized_runtime_id)
            self.repository.create_conversation_probe(
                conn,
                probe_id=probe_id,
                ticket_hash=hash_value(ticket),
                runtime_classroom_id=normalized_runtime_id,
                upstream_classroom_id=normalized_classroom_id,
                challenge=challenge,
                expires_at=expires_at,
                now=issued_at,
                candidate_kind="recovery",
                deterministic_recovery_id=normalized_recovery_id,
            )
        return {
            "ok": True,
            "probeId": probe_id,
            "ticket": ticket,
            "runtimeId": normalized_runtime_id,
            "classroomId": normalized_classroom_id,
            "challenge": challenge,
            "expiresAt": expires_at,
            "candidate": True,
            "candidateKind": "recovery",
            "deterministicRecoveryId": normalized_recovery_id,
        }

    def issue_tts_credential_recovery_candidate(
        self,
        runtime_id: str,
        upstream_classroom_id: str,
        deterministic_recovery_id: str,
        tts_credential_recovery_id: str,
    ) -> dict[str, Any]:
        """Issue the probe bound to both the terminal parent and its child."""

        self._require_enabled()
        normalized_runtime_id = _identifier(runtime_id, "runtime_id")
        normalized_classroom_id = _identifier(
            upstream_classroom_id, "upstream_classroom_id"
        )
        normalized_parent_id = _identifier(
            deterministic_recovery_id, "deterministic_recovery_id"
        )
        normalized_child_id = _identifier(
            tts_credential_recovery_id, "tts_credential_recovery_id"
        )
        issued_at = now_ms()
        expires_at = issued_at + self.ttl_seconds * 1000
        ticket = new_token("ompt")
        probe_id = new_token("omp")
        challenge = new_token("ompc")
        with self.repository.transaction() as conn:
            runtime = self.repository.get_runtime_classroom(
                conn, runtime_id=normalized_runtime_id, for_update=True
            )
            parent = self.repository.get_deterministic_recovery_by_runtime(
                conn, runtime_id=normalized_runtime_id, for_update=True
            )
            child = self.repository.get_tts_credential_recovery_by_runtime(
                conn, runtime_id=normalized_runtime_id, for_update=True
            )
            if runtime is None or parent is None or child is None:
                raise OpenMaicConversationProbeError(
                    "openmaic_tts_credential_probe_candidate_unavailable",
                    "TTS 凭证恢复课件尚未进入对话验证阶段",
                    status_code=409,
                )
            if (
                str(runtime.get("status") or "") != "recovering"
                or str(runtime.get("quality_status") or "") != "pending_review"
                or int(runtime.get("attempt_ordinal") or 0) != 3
                or runtime.get("retired_at") is not None
                or str(runtime.get("upstream_classroom_id") or "").strip()
                or str(parent.get("id") or "") != normalized_parent_id
                or str(parent.get("status") or "") != "failed"
                or int(parent.get("dispatch_count") or 0) != 2
                or str(child.get("id") or "") != normalized_child_id
                or str(child.get("parent_recovery_id") or "")
                != normalized_parent_id
                or str(child.get("status") or "") != "validating"
                or str(child.get("upstream_classroom_id") or "")
                != normalized_classroom_id
                or int(child.get("scene_count") or 0) != 10
                or int(child.get("audio_count") or 0) != 10
                or not bool(child.get("static_contract_verified"))
                or bool(child.get("conversation_probe_verified"))
            ):
                raise OpenMaicConversationProbeError(
                    "openmaic_tts_credential_probe_candidate_unavailable",
                    "当前 TTS 凭证恢复记录不允许创建对话探针",
                    status_code=409,
                )
            self._require_no_existing_probe(conn, normalized_runtime_id)
            self.repository.create_conversation_probe(
                conn,
                probe_id=probe_id,
                ticket_hash=hash_value(ticket),
                runtime_classroom_id=normalized_runtime_id,
                upstream_classroom_id=normalized_classroom_id,
                challenge=challenge,
                expires_at=expires_at,
                now=issued_at,
                candidate_kind="tts_credential_recovery",
                deterministic_recovery_id=normalized_parent_id,
                tts_credential_recovery_id=normalized_child_id,
            )
        return {
            "ok": True,
            "probeId": probe_id,
            "ticket": ticket,
            "runtimeId": normalized_runtime_id,
            "classroomId": normalized_classroom_id,
            "challenge": challenge,
            "expiresAt": expires_at,
            "candidate": True,
            "candidateKind": "tts_credential_recovery",
            "deterministicRecoveryId": normalized_parent_id,
            "ttsCredentialRecoveryId": normalized_child_id,
        }

    def exchange_ticket(self, ticket: str) -> dict[str, Any]:
        self._require_enabled()
        normalized_ticket = _probe_token(ticket, "ompt", "ticket")
        exchanged_at = now_ms()
        runtime_token = new_token("ompr")
        runtime_session_id = new_token("omps")
        with self.repository.transaction() as conn:
            row = self.repository.get_conversation_probe_by_ticket_for_update(
                conn, ticket_hash=hash_value(normalized_ticket)
            )
            self._require_active(row, now=exchanged_at, expected_consumed=False)
            assert row is not None
            consumed = self.repository.consume_conversation_probe_ticket(
                conn,
                probe_id=str(row["id"]),
                runtime_token_hash=hash_value(runtime_token),
                runtime_session_id=runtime_session_id,
                now=exchanged_at,
            )
            if not consumed:
                raise OpenMaicConversationProbeError(
                    "openmaic_probe_ticket_replayed",
                    "探针票据已使用",
                    status_code=409,
                )
            return {
                **self._runtime_context(row, runtime_session_id=runtime_session_id),
                "runtimeToken": runtime_token,
            }
        # Kept unreachable to make the returned context easy to audit.

    def validate_runtime_token(self, runtime_token: str) -> dict[str, Any]:
        self._require_enabled()
        normalized_token = _probe_token(runtime_token, "ompr", "runtime_token")
        checked_at = now_ms()
        with self.repository.transaction() as conn:
            row = self.repository.get_conversation_probe_by_runtime_token_for_update(
                conn, runtime_token_hash=hash_value(normalized_token)
            )
            self._require_active(row, now=checked_at, expected_consumed=True)
            assert row is not None
            return self._runtime_context(row)

    def finalize_probe(
        self,
        probe_id: str,
        *,
        chat_receipt: Mapping[str, Any],
        transcription_receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Atomically persist valid gateway evidence and revoke the probe."""

        self._require_enabled()
        normalized_probe_id = _probe_token(probe_id, "omp", "probe_id")
        finalized_at = now_ms()
        with self.repository.transaction() as conn:
            row = self.repository.get_conversation_probe_by_id_for_update(
                conn, probe_id=normalized_probe_id
            )
            self._require_active(row, now=finalized_at, expected_consumed=True)
            assert row is not None
            self._validate_receipts(
                row,
                chat_receipt=chat_receipt,
                transcription_receipt=transcription_receipt,
            )
            finalized = self.repository.finalize_conversation_probe(
                conn,
                probe_id=normalized_probe_id,
                chat_receipt=dict(chat_receipt),
                transcription_receipt=dict(transcription_receipt),
                now=finalized_at,
            )
            if not finalized:
                raise OpenMaicConversationProbeError(
                    "openmaic_probe_finalize_conflict",
                    "探针回执已提交或已撤销",
                    status_code=409,
                )
        return {"ok": True, "probeId": normalized_probe_id, "revoked": True}

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise OpenMaicConversationProbeError(
                "openmaic_conversation_probe_disabled",
                "对话探针未启用",
                status_code=503,
            )

    def _require_no_existing_probe(self, conn: object, runtime_id: str) -> None:
        existing = self.repository.get_conversation_probe_by_runtime_classroom_for_update(
            conn, runtime_classroom_id=runtime_id
        )
        if existing is not None:
            raise OpenMaicConversationProbeError(
                "openmaic_probe_already_issued",
                "该课件已创建过对话探针",
                status_code=409,
            )

    @staticmethod
    def _runtime_context(
        row: DatabaseRow, *, runtime_session_id: str | None = None
    ) -> dict[str, Any]:
        session_id = runtime_session_id or str(row.get("runtime_session_id") or "")
        if not session_id:
            raise OpenMaicConversationProbeError(
                "openmaic_probe_session_missing", "探针会话不存在", status_code=401
            )
        return {
            "ok": True,
            "probe": True,
            "purpose": "conversation_probe",
            "runtimeSessionId": session_id,
            "runtimeClassroomId": str(row["runtime_classroom_id"]),
            "classroomId": str(row["upstream_classroom_id"]),
            "challenge": str(row["challenge"]),
            "expiresAt": int(row["expires_at"]),
        }

    @staticmethod
    def _require_active(
        row: DatabaseRow | None, *, now: int, expected_consumed: bool
    ) -> None:
        if row is None:
            raise OpenMaicConversationProbeError(
                "openmaic_probe_unauthorized", "探针凭据无效", status_code=401
            )
        if row.get("revoked_at") is not None or row.get("finalized_at") is not None:
            raise OpenMaicConversationProbeError(
                "openmaic_probe_revoked", "探针凭据已撤销", status_code=401
            )
        if int(row.get("expires_at") or 0) <= now:
            raise OpenMaicConversationProbeError(
                "openmaic_probe_expired", "探针凭据已过期", status_code=401
            )
        is_consumed = row.get("consumed_at") is not None
        if is_consumed != expected_consumed:
            raise OpenMaicConversationProbeError(
                "openmaic_probe_ticket_replayed" if is_consumed else "openmaic_probe_not_exchanged",
                "探针票据已使用" if is_consumed else "探针票据尚未交换",
                status_code=409 if is_consumed else 401,
            )

    def _validate_receipts(
        self,
        row: DatabaseRow,
        *,
        chat_receipt: Mapping[str, Any],
        transcription_receipt: Mapping[str, Any],
    ) -> None:
        if not isinstance(chat_receipt, Mapping) or not isinstance(
            transcription_receipt, Mapping
        ):
            raise OpenMaicConversationProbeError(
                "invalid_openmaic_probe_receipt", "探针回执格式无效", status_code=400
            )
        for receipt in (chat_receipt, transcription_receipt):
            if receipt.get("verified") is not True:
                raise OpenMaicConversationProbeError(
                    "openmaic_probe_receipt_binding_invalid",
                    "探针回执未绑定到当前课件会话",
                    status_code=400,
                )
        for field, expected in self.REQUIRED_CHAT_RECEIPT.items():
            if chat_receipt.get(field) != expected:
                raise OpenMaicConversationProbeError(
                    "openmaic_probe_chat_receipt_invalid",
                    "对话网关验证未通过",
                    status_code=400,
                )
        self._validate_proof(row, chat_receipt.get("proof"), require_asr=False)
        for field, expected in self.REQUIRED_TRANSCRIPTION_RECEIPT.items():
            if transcription_receipt.get(field) != expected:
                raise OpenMaicConversationProbeError(
                    "openmaic_probe_transcription_receipt_invalid",
                    "语音识别网关验证未通过",
                    status_code=400,
                )
        self._validate_proof(row, transcription_receipt.get("proof"), require_asr=True)

    @staticmethod
    def _validate_proof(
        row: DatabaseRow, proof: object, *, require_asr: bool
    ) -> None:
        if not isinstance(proof, Mapping) or (
            proof.get("schemaVersion") != "mira.openmaic.conversation-proof.v1"
            or proof.get("challenge") != row["challenge"]
            or proof.get("runtimeSessionId") != row["runtime_session_id"]
            or proof.get("classroomId") != row["upstream_classroom_id"]
            or proof.get("providerCall") is not False
        ):
            raise OpenMaicConversationProbeError(
                "openmaic_probe_proof_invalid", "网关证明未绑定到当前探针", status_code=400
            )
        if require_asr:
            policy = proof.get("asrPolicy")
            if not isinstance(policy, Mapping) or (
                policy.get("providerId") != "qwen-asr"
                or policy.get("modelId") != "qwen3-asr-flash"
                or policy.get("fallbackAllowed") is not False
            ):
                raise OpenMaicConversationProbeError(
                    "openmaic_probe_asr_policy_invalid",
                    "语音识别策略证明无效",
                    status_code=400,
                )


def _identifier(value: object, label: str) -> str:
    normalized = str(value or "").strip()
    if (
        not normalized
        or len(normalized) > 128
        or not all(character.isalnum() or character in {"-", "_", "."} for character in normalized)
    ):
        raise OpenMaicConversationProbeError(
            f"invalid_{label}", f"{label} 无效", status_code=400
        )
    return normalized


def _probe_token(value: object, prefix: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized.startswith(f"{prefix}_") or len(normalized) > 160:
        raise OpenMaicConversationProbeError(
            f"invalid_openmaic_probe_{label}", "探针凭据无效", status_code=400
        )
    suffix = normalized[len(prefix) + 1 :]
    if len(suffix) < 32 or not all(character.isalnum() or character in {"-", "_"} for character in suffix):
        raise OpenMaicConversationProbeError(
            f"invalid_openmaic_probe_{label}", "探针凭据无效", status_code=400
        )
    return normalized
