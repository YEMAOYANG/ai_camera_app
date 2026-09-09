from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Callable, Mapping, Sequence


OPENMAIC_INPUT_SCHEMA = "mira.openmaic.generate.v1"
OPENMAIC_DRAFT_SCHEMA = "mira.openmaic.draft.v1"


class OpenMaicDraftError(RuntimeError):
    """A stable failure raised by the optional OpenMAIC draft generator."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class DraftGenerationResult:
    schema_version: str
    request_id: str
    generator: str
    draft: dict[str, Any]
    provider: str
    model: str
    elapsed_ms: int

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "DraftGenerationResult":
        try:
            schema_version = str(payload["schemaVersion"])
            request_id = str(payload["requestId"])
            generator = str(payload["generator"])
            draft = payload["draft"]
            provider = str(payload["provider"])
            model = str(payload["model"])
            elapsed_ms = int(payload["elapsedMs"])
        except (KeyError, TypeError, ValueError) as exc:
            raise OpenMaicDraftError(
                "invalid_response", "OpenMAIC sidecar returned an incomplete result"
            ) from exc
        if schema_version != OPENMAIC_DRAFT_SCHEMA or generator != "openmaic":
            raise OpenMaicDraftError(
                "invalid_response", "OpenMAIC sidecar returned an unsupported contract"
            )
        if not isinstance(draft, dict):
            raise OpenMaicDraftError(
                "invalid_response", "OpenMAIC sidecar draft must be an object"
            )
        return cls(
            schema_version=schema_version,
            request_id=request_id,
            generator=generator,
            draft=draft,
            provider=provider,
            model=model,
            elapsed_ms=max(0, elapsed_ms),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "requestId": self.request_id,
            "generator": self.generator,
            "draft": self.draft,
            "provider": self.provider,
            "model": self.model,
            "elapsedMs": self.elapsed_ms,
        }


ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]


class OpenMaicDraftAdapter:
    """Runs one isolated OpenMAIC draft generation request in a Node process.

    The child receives only provider metadata and the *name* of the key
    environment variable. The secret itself remains in the inherited process
    environment and is never serialized into stdin or command arguments.
    """

    def __init__(
        self,
        *,
        sidecar_root: str | Path | None = None,
        node_binary: str = "node",
        timeout_seconds: float = 120.0,
        provider_name: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        api_key_env: str = "APP_AI_API_KEY",
        provider_timeout_ms: int = 90000,
        max_tokens: int = 6000,
        temperature: float = 0.2,
        include_scene_content: bool = True,
        fake_mode: bool = False,
        fake_responses: Sequence[str] | None = None,
        process_runner: ProcessRunner = subprocess.run,
    ):
        backend_root = Path(__file__).resolve().parents[1]
        self.sidecar_root = Path(sidecar_root or backend_root / "openmaic-sidecar").resolve()
        self.node_binary = node_binary
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.provider_name = (provider_name or os.getenv("APP_AI_PROVIDER") or "kimi").strip()
        self.model_name = (model_name or os.getenv("APP_AI_MODEL") or "").strip()
        self.base_url = (base_url or os.getenv("APP_AI_BASE_URL") or "").strip()
        self.api_key_env = api_key_env.strip()
        self.provider_timeout_ms = int(provider_timeout_ms)
        self.max_tokens = int(max_tokens)
        self.temperature = float(temperature)
        self.include_scene_content = bool(include_scene_content)
        self.fake_mode = bool(fake_mode)
        self.fake_responses = list(fake_responses or [])
        self._run = process_runner

    @property
    def cli_path(self) -> Path:
        return self.sidecar_root / "src" / "cli.mjs"

    def availability(self) -> dict[str, Any]:
        if not self.cli_path.is_file():
            return self._unavailable("OpenMAIC sidecar CLI is missing")
        if not self._node_is_available():
            return self._unavailable("Node.js runtime is unavailable")
        try:
            completed = self._run_process([self.node_binary, str(self.cli_path), "--availability"])
        except subprocess.TimeoutExpired:
            return self._unavailable("OpenMAIC availability check timed out")
        except OSError:
            return self._unavailable("Node.js runtime could not be started")
        payload = self._parse_json(completed.stdout, raise_on_error=False)
        runtime_available = bool(payload and payload.get("available") and completed.returncode == 0)
        provider_configured = self.fake_mode or bool(
            self.model_name and self.base_url and os.getenv(self.api_key_env, "").strip()
        )
        available = runtime_available and provider_configured
        reason = None
        if not runtime_available:
            reason = str((payload or {}).get("reason") or "OpenMAIC npm packages are unavailable")
        elif not provider_configured:
            reason = "OpenMAIC AI provider is not fully configured"
        return {
            "available": available,
            "runtimeAvailable": runtime_available,
            "providerConfigured": provider_configured,
            "generator": "openmaic",
            "schemaVersion": OPENMAIC_DRAFT_SCHEMA,
            "provider": self.provider_name,
            "model": self.model_name,
            "reason": reason,
            "packages": (payload or {}).get("packages", {}),
            "node": (payload or {}).get("node"),
        }

    def generate(
        self, skill_boundary: Mapping[str, Any], request_id: str
    ) -> DraftGenerationResult:
        if not isinstance(skill_boundary, Mapping):
            raise OpenMaicDraftError("invalid_input", "skill_boundary must be an object")
        if not str(request_id).strip():
            raise OpenMaicDraftError("invalid_input", "request_id is required")
        if not self.cli_path.is_file() or not self._node_is_available():
            raise OpenMaicDraftError("openmaic_unavailable", "OpenMAIC sidecar is unavailable")

        payload = {
            "schemaVersion": OPENMAIC_INPUT_SCHEMA,
            "requestId": str(request_id).strip(),
            "skillBoundary": dict(skill_boundary),
            "includeSceneContent": self.include_scene_content,
            "mode": "fake" if self.fake_mode else "live",
            "provider": {
                "name": self.provider_name,
                "model": self.model_name,
                "baseUrl": self.base_url,
                "apiKeyEnv": self.api_key_env,
                "timeoutMs": self.provider_timeout_ms,
                "maxTokens": self.max_tokens,
                "temperature": self.temperature,
            },
        }
        if self.fake_mode:
            payload["fakeResponses"] = self.fake_responses

        started_at = time.monotonic()
        try:
            completed = self._run_process(
                [self.node_binary, str(self.cli_path)],
                input_text=json.dumps(payload, ensure_ascii=False),
                fake_mode=self.fake_mode,
            )
        except subprocess.TimeoutExpired as exc:
            raise OpenMaicDraftError(
                "openmaic_timeout",
                f"OpenMAIC draft generation timed out after {self.timeout_seconds:g}s",
            ) from exc
        except OSError as exc:
            raise OpenMaicDraftError(
                "openmaic_unavailable", "OpenMAIC sidecar could not be started"
            ) from exc

        response = self._parse_json(completed.stdout, raise_on_error=False)
        if completed.returncode != 0:
            error = response.get("error") if isinstance(response, dict) else None
            code = str(error.get("code")) if isinstance(error, dict) else "generation_failed"
            message = (
                str(error.get("message"))
                if isinstance(error, dict)
                else "OpenMAIC draft generation failed"
            )
            raise OpenMaicDraftError(code, message)
        if not isinstance(response, dict):
            raise OpenMaicDraftError(
                "invalid_response", "OpenMAIC sidecar returned invalid JSON"
            )
        result = DraftGenerationResult.from_payload(response)
        if result.request_id != str(request_id).strip():
            raise OpenMaicDraftError(
                "invalid_response", "OpenMAIC response requestId does not match"
            )
        # The sidecar owns model-call timing. This fallback only guards malformed
        # clocks while preserving the stable result shape.
        if result.elapsed_ms == 0:
            result = DraftGenerationResult(
                schema_version=result.schema_version,
                request_id=result.request_id,
                generator=result.generator,
                draft=result.draft,
                provider=result.provider,
                model=result.model,
                elapsed_ms=max(0, round((time.monotonic() - started_at) * 1000)),
            )
        return result

    def _node_is_available(self) -> bool:
        if Path(self.node_binary).is_absolute():
            return Path(self.node_binary).is_file()
        return shutil.which(self.node_binary) is not None

    def _run_process(
        self,
        command: list[str],
        *,
        input_text: str | None = None,
        fake_mode: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        child_env = os.environ.copy()
        if fake_mode:
            child_env["OPENMAIC_FAKE_MODE"] = "1"
        return self._run(
            command,
            cwd=str(self.sidecar_root),
            input=input_text,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            env=child_env,
            check=False,
        )

    @staticmethod
    def _parse_json(stdout: str, *, raise_on_error: bool) -> dict[str, Any] | None:
        try:
            payload = json.loads((stdout or "").strip())
        except (json.JSONDecodeError, TypeError):
            if raise_on_error:
                raise OpenMaicDraftError(
                    "invalid_response", "OpenMAIC sidecar returned invalid JSON"
                )
            return None
        return payload if isinstance(payload, dict) else None

    def _unavailable(self, reason: str) -> dict[str, Any]:
        return {
            "available": False,
            "runtimeAvailable": False,
            "providerConfigured": False,
            "generator": "openmaic",
            "schemaVersion": OPENMAIC_DRAFT_SCHEMA,
            "provider": self.provider_name,
            "model": self.model_name,
            "reason": reason,
            "packages": {},
            "node": None,
        }
