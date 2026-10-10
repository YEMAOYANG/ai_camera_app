from __future__ import annotations

from dataclasses import dataclass, field
import base64
import http.client
import io
import json
import logging
import re
import urllib.error
import urllib.request
from typing import Protocol

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore


log = logging.getLogger(__name__)

_MAX_CAPTURED_RESPONSE_BYTES = 2 * 1024 * 1024
_FINISH_REASONS = {"stop", "length", "tool_calls", "content_filter", "function_call"}
_TOKEN_USAGE_FIELDS = {"prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"}


@dataclass(frozen=True)
class AiVisionResponse:
    text: str
    provider: str
    model: str
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    request_id: str | None = None
    response_error: str | None = None
    # Homework persists this private receipt before parsing. Never log it.
    raw_response: bytes | None = field(default=None, repr=False)


class AiVisionProvider(Protocol):
    provider_name: str
    model_name: str

    def analyze_image(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        content_type: str,
        max_tokens: int = 360,
        temperature: float = 1.0,
    ) -> AiVisionResponse | None:
        ...


class OpenAICompatibleVisionProvider:
    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str,
        base_url: str,
        model_name: str,
        timeout_seconds: float = 20.0,
        max_bytes: int = 524288,
        max_image_dimension: int = 1280,
        jpeg_quality: int = 85,
        disable_thinking: bool = False,
        json_output: bool = False,
        capture_received_response: bool = False,
    ):
        self.provider_name = provider_name.strip().lower() or "openai_compatible"
        self.api_key = api_key.strip()
        self.base_url = base_url.strip().rstrip("/")
        self.model_name = model_name.strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_bytes = max(8192, int(max_bytes))
        self.max_image_dimension = max(256, int(max_image_dimension))
        self.jpeg_quality = max(40, min(95, int(jpeg_quality)))
        self.disable_thinking = disable_thinking
        self.json_output = json_output
        self.capture_received_response = capture_received_response

    def analyze_image(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        content_type: str,
        max_tokens: int = 360,
        temperature: float = 1.0,
    ) -> AiVisionResponse | None:
        if not self.api_key or not self.base_url or not self.model_name:
            return None
        if not image_bytes:
            return None
        encoded = _encode_image(
            image_bytes,
            content_type,
            self.max_bytes,
            max_dimension=self.max_image_dimension,
            jpeg_quality=self.jpeg_quality,
        )
        if encoded is None:
            return None
        payload: dict = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": encoded}},
                    ],
                },
            ],
            "temperature": float(temperature),
            "max_tokens": max(64, int(max_tokens)),
        }
        if self.disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        if self.provider_name in {"qwen", "dashscope"}:
            payload["enable_thinking"] = False
        if self.json_output:
            payload["response_format"] = {"type": "json_object"}
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                if self.capture_received_response:
                    raw_body = response.read(_MAX_CAPTURED_RESPONSE_BYTES + 1)
                else:
                    raw_body = response.read()
                headers = getattr(response, "headers", None)
                if self.capture_received_response and len(raw_body) <= _MAX_CAPTURED_RESPONSE_BYTES and headers is not None:
                    declared_length = headers.get("Content-Length")
                    if isinstance(declared_length, str) and re.fullmatch(r"[0-9]{1,20}", declared_length):
                        missing_bytes = int(declared_length) - len(raw_body)
                        if missing_bytes > 0:
                            # A bounded read does not itself guarantee that the
                            # HTTP body arrived completely before disconnect.
                            raise http.client.IncompleteRead(raw_body, missing_bytes)
                header_request_id = _bounded_request_id(headers.get("x-request-id") if headers is not None else None)
        except urllib.error.HTTPError as exc:
            # Provider error bodies can echo private prompts or credentials.
            log.warning("vision provider HTTP error: status=%s", exc.code)
            return None
        except Exception as exc:
            log.warning("vision provider request failed: reason=%s", type(exc).__name__)
            return None
        if self.capture_received_response and len(raw_body) > _MAX_CAPTURED_RESPONSE_BYTES:
            return self._received_error("response_too_large", raw_body[:_MAX_CAPTURED_RESPONSE_BYTES], header_request_id)
        try:
            if self.capture_received_response:
                body = json.loads(raw_body.decode("utf-8-sig"),
                    object_pairs_hook=_unique_response_object, parse_constant=_reject_nonfinite_response_number)
            else:
                body = json.loads(raw_body.decode("utf-8", "ignore") or "{}")
        except UnicodeDecodeError:
            return self._received_error("response_invalid_encoding", raw_body, header_request_id)
        except RecursionError:
            if self.capture_received_response:
                return self._received_error("response_invalid_json", raw_body, header_request_id)
            raise
        except (ValueError, TypeError):
            if self.capture_received_response:
                return self._received_error("response_invalid_json", raw_body, header_request_id)
            log.warning("vision provider request failed: reason=InvalidResponseJson")
            return None
        if not isinstance(body, dict):
            if self.capture_received_response:
                return self._received_error("response_invalid_envelope", raw_body, header_request_id)
            return None
        choices = body.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        if choice is None or not isinstance(choice.get("message"), dict):
            if self.capture_received_response:
                return self._received_error("response_invalid_envelope", raw_body, header_request_id, body)
            return None
        if self.capture_received_response:
            finish_reason = choice.get("finish_reason")
            if finish_reason is not None and (not isinstance(finish_reason, str) or finish_reason not in _FINISH_REASONS):
                return self._received_error("response_invalid_envelope", raw_body, header_request_id, body)
            if finish_reason in {"content_filter", "tool_calls", "function_call"}:
                # These are explicitly not a final OCR transcription, even
                # when the partial content happens to be valid JSON.
                return self._received_error("response_incomplete_content", raw_body, header_request_id, body)
        text = _extract_completion_text(body)
        if self.capture_received_response:
            try:
                text.encode("utf-8")
            except UnicodeEncodeError:
                # Escaped lone surrogates are legal to Python's JSON decoder
                # but cannot be saved as valid UTF-8 text. Keep original bytes.
                return self._received_error("response_invalid_encoding", raw_body, header_request_id, body)
        if not text:
            if self.capture_received_response:
                return self._received_error("response_empty_content", raw_body, header_request_id, body)
            return None
        return AiVisionResponse(
            text=text,
            provider=self.provider_name,
            model=self.model_name,
            finish_reason=_finish_reason(body),
            usage=_token_usage(body),
            request_id=_bounded_request_id(body.get("id")) or header_request_id,
            raw_response=raw_body if self.capture_received_response else None,
        )

    def _received_error(
        self,
        error: str,
        raw_body: bytes,
        request_id: str | None,
        body: dict | None = None,
    ) -> AiVisionResponse:
        return AiVisionResponse(
            text="",
            provider=self.provider_name,
            model=self.model_name,
            finish_reason=_finish_reason(body) if body is not None else None,
            usage=_token_usage(body) if body is not None else None,
            request_id=(_bounded_request_id(body.get("id")) if body is not None else None) or request_id,
            response_error=error,
            raw_response=raw_body,
        )


def _bounded_request_id(value: object) -> str | None:
    if isinstance(value, str) and 0 < len(value) <= 200 and re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
        return value
    return None


def _unique_response_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate response key")
        result[name] = value
    return result


def _reject_nonfinite_response_number(value):
    raise ValueError("nonfinite response number")


def _finish_reason(body: dict) -> str | None:
    choices = body.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    value = choice.get("finish_reason")
    return value if isinstance(value, str) and value in _FINISH_REASONS else None


def _token_usage(body: dict) -> dict[str, int] | None:
    raw = body.get("usage")
    if not isinstance(raw, dict):
        return None
    usage = {name: value for name, value in raw.items()
        if name in _TOKEN_USAGE_FIELDS and type(value) is int and 0 <= value <= 1_000_000_000}
    return usage or None


def _encode_image(
    image_bytes: bytes,
    content_type: str,
    max_bytes: int,
    *,
    max_dimension: int = 1280,
    jpeg_quality: int = 85,
) -> str | None:
    if Image is None or not image_bytes or max_bytes <= 0:
        return None
    try:
        # max_bytes is the encoded upload budget, never a file-slicing limit.
        # A phone JPEG may have expanded to a larger normalized PNG upstream.
        with Image.open(io.BytesIO(image_bytes)) as source:
            source.load()
            image = source.convert("RGB")
        image.thumbnail((max_dimension, max_dimension))
        # Preserve the existing configured dimensions/quality on the first
        # attempt. Only an over-budget output tries lower JPEG qualities.
        quality = max(40, min(95, int(jpeg_quality)))
        qualities = list(range(quality, 39, -15))
        if qualities[-1] != 40:
            qualities.append(40)
        for current_quality in qualities:
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=current_quality, optimize=True)
            body = buffer.getvalue()
            if len(body) <= max_bytes:
                encoded = base64.b64encode(body).decode("ascii")
                return f"data:image/jpeg;base64,{encoded}"
        # Do not send incomplete bytes or silently make text illegibly small.
        return None
    except Exception:
        # No decoder or an invalid/truncated source must fail before HTTP.
        return None


def _extract_completion_text(body: dict) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts).strip()
    return ""
