from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)


class Go2RtcClientError(RuntimeError):
    """Base error for the go2rtc media-gateway boundary."""


class Go2RtcConfigurationError(Go2RtcClientError):
    """Raised when a media-gateway URL or stream value is unsafe."""


class Go2RtcUnavailableError(Go2RtcClientError):
    """Raised when the media gateway cannot complete a request."""


class Go2RtcProtocolError(Go2RtcClientError):
    """Raised when the media gateway returns an invalid response."""


class _RejectRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Go2RtcClient:
    """Small, credential-safe client for the go2rtc HTTP and WebSocket APIs."""

    _MAX_JSON_BYTES = 1_048_576
    _MAX_WRITE_RESPONSE_BYTES = 65_536

    def __init__(
        self,
        api_base_url: str,
        *,
        public_base_url: str | None = None,
        timeout_seconds: float = 3.0,
        opener=None,
        request_factory: Callable[..., Any] = Request,
    ):
        self.api_base_url = _normalize_http_base_url(api_base_url)
        public_value = str(public_base_url or "").strip()
        self.public_base_url = (
            _normalize_http_base_url(public_value)
            if public_value
            else self.api_base_url
        )
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self._opener = opener or build_opener(_RejectRedirectHandler())
        self._request_factory = request_factory

    def health(self) -> dict[str, Any]:
        """Return go2rtc's service metadata when its API is healthy."""

        payload = self._request_json("/api")
        if not isinstance(payload, dict):
            raise Go2RtcProtocolError("媒体网关返回了无效的健康状态。")
        return payload

    def is_healthy(self) -> bool:
        try:
            self.health()
        except Go2RtcClientError:
            return False
        return True

    def stream_exists(self, name: str) -> bool:
        """Check whether a named stream is registered without exposing its source."""

        stream_name = _normalize_stream_name(name)
        payload = self._request_json("/api/streams")
        if not isinstance(payload, Mapping):
            raise Go2RtcProtocolError("媒体网关返回了无效的流列表。")
        return stream_name in payload

    def register_stream(self, name: str, source: str) -> bool:
        """Register or replace a non-persistent stream in go2rtc memory."""

        stream_name = _normalize_stream_name(name)
        stream_source = _normalize_rtsp_source(source)
        query = urlencode({"name": stream_name, "src": stream_source})
        self._request(
            f"/api/streams?{query}",
            method="PATCH",
            max_bytes=self._MAX_WRITE_RESPONSE_BYTES,
        )
        return True

    def delete_stream(self, name: str) -> bool:
        """Remove a named stream from the running media gateway."""

        stream_name = _normalize_stream_name(name)
        query = urlencode({"src": stream_name})
        self._request(
            f"/api/streams?{query}",
            method="DELETE",
            max_bytes=self._MAX_WRITE_RESPONSE_BYTES,
        )
        return True

    def websocket_url(self, stream_name: str) -> str:
        """Build the public go2rtc WebRTC signaling URL for a named stream."""

        name = _normalize_stream_name(stream_name)
        parsed = urlsplit(self.public_base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        path = _joined_path(parsed.path, "/api/ws")
        query = urlencode({"src": name})
        return urlunsplit((scheme, parsed.netloc, path, query, ""))

    def _request_json(self, path: str) -> Any:
        body = self._request(path, method="GET", max_bytes=self._MAX_JSON_BYTES)
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise Go2RtcProtocolError("媒体网关返回了无效的 JSON 响应。") from None

    def _request(self, path: str, *, method: str, max_bytes: int) -> bytes:
        url = _endpoint_url(self.api_base_url, path)
        body: bytes | None = None
        failure_message = ""
        try:
            request = self._request_factory(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "MiraGuardian/1.0",
                },
                method=method,
            )
            with self._open(request) as response:
                status = int(getattr(response, "status", 200) or 200)
                if not 200 <= status < 300:
                    raise Go2RtcUnavailableError(
                        f"媒体网关请求失败（HTTP {status}）。"
                    )
                body = response.read(max_bytes + 1)
        except Go2RtcClientError:
            raise
        except HTTPError as exc:
            failure_message = f"媒体网关请求失败（HTTP {int(exc.code)}）。"
        except (URLError, TimeoutError, OSError):
            failure_message = "暂时无法连接媒体网关。"
        except Exception:
            # The original request URL can contain an RTSP password in `src`.
            # Never chain or interpolate transport exceptions across this boundary.
            failure_message = "暂时无法连接媒体网关。"
        if failure_message:
            # Raise after leaving the except block so the transport exception is
            # not retained as a context that could reveal the request URL.
            raise Go2RtcUnavailableError(failure_message)
        if body is None:
            raise Go2RtcProtocolError("媒体网关没有返回响应。")
        if len(body) > max_bytes:
            raise Go2RtcProtocolError("媒体网关响应过大。")
        return body

    def _open(self, request):
        open_method = getattr(self._opener, "open", None)
        if callable(open_method):
            return open_method(request, timeout=self.timeout_seconds)
        if callable(self._opener):
            return self._opener(request, timeout=self.timeout_seconds)
        raise Go2RtcConfigurationError("媒体网关 HTTP opener 配置无效。")


def _normalize_http_base_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw or any(character.isspace() for character in raw):
        raise Go2RtcConfigurationError("媒体网关地址配置无效。")
    try:
        parsed = urlsplit(raw)
        _ = parsed.port
    except ValueError:
        raise Go2RtcConfigurationError("媒体网关地址配置无效。") from None
    if parsed.scheme.lower() not in {"http", "https"}:
        raise Go2RtcConfigurationError("媒体网关地址仅支持 HTTP 或 HTTPS。")
    if not parsed.netloc or not parsed.hostname:
        raise Go2RtcConfigurationError("媒体网关地址配置无效。")
    if parsed.username is not None or parsed.password is not None:
        raise Go2RtcConfigurationError("媒体网关地址不允许包含用户凭据。")
    if parsed.query or parsed.fragment:
        raise Go2RtcConfigurationError("媒体网关地址不能包含查询参数或片段。")
    path = parsed.path.rstrip("/")
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc,
            path,
            "",
            "",
        )
    )


def _normalize_stream_name(value: str) -> str:
    name = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", name):
        raise Go2RtcConfigurationError("媒体流名称配置无效。")
    return name


def _normalize_rtsp_source(value: str) -> str:
    source = str(value or "").strip()
    if not source or any(character.isspace() for character in source):
        raise Go2RtcConfigurationError("摄像头媒体源配置无效。")
    try:
        parsed = urlsplit(source)
        _ = parsed.port
    except ValueError:
        raise Go2RtcConfigurationError("摄像头媒体源配置无效。") from None
    if parsed.scheme.lower() not in {"rtsp", "rtsps"}:
        raise Go2RtcConfigurationError("摄像头媒体源必须使用 RTSP。")
    if not parsed.netloc or not parsed.hostname:
        raise Go2RtcConfigurationError("摄像头媒体源配置无效。")
    return source


def _endpoint_url(base_url: str, path: str) -> str:
    parsed = urlsplit(base_url)
    endpoint_path = _joined_path(parsed.path, path.split("?", 1)[0])
    query = path.split("?", 1)[1] if "?" in path else ""
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            endpoint_path,
            query,
            "",
        )
    )


def _joined_path(base_path: str, endpoint_path: str) -> str:
    return f"{base_path.rstrip('/')}/{endpoint_path.lstrip('/')}"
