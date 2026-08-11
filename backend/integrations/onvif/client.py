from __future__ import annotations

import base64
import hashlib
import ipaddress
import os
import re
import socket
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse, urlunparse
from urllib.request import (
    HTTPBasicAuthHandler,
    HTTPDigestAuthHandler,
    HTTPPasswordMgrWithDefaultRealm,
    HTTPRedirectHandler,
    Request,
    build_opener,
)


WS_DISCOVERY_ADDRESS = ("239.255.255.250", 3702)
SOAP_ENV = "http://www.w3.org/2003/05/soap-envelope"
WS_ADDRESSING = "http://schemas.xmlsoap.org/ws/2004/08/addressing"
WS_DISCOVERY = "http://schemas.xmlsoap.org/ws/2005/04/discovery"
WS_DISCOVERY_TO = "urn:schemas-xmlsoap-org:ws:2005:04:discovery"
ONVIF_DEVICE_WSDL = "http://www.onvif.org/ver10/device/wsdl"
ONVIF_MEDIA_WSDL = "http://www.onvif.org/ver10/media/wsdl"
ONVIF_SCHEMA = "http://www.onvif.org/ver10/schema"


class OnvifClientError(RuntimeError):
    pass


class OnvifUnavailableError(OnvifClientError):
    pass


class OnvifAuthenticationError(OnvifClientError):
    pass


class OnvifProtocolError(OnvifClientError):
    pass


class RtspUnavailableError(OnvifClientError):
    pass


class RtspAuthenticationError(OnvifClientError):
    pass


@dataclass(frozen=True)
class DiscoveredOnvifDevice:
    endpoint_reference: str
    device_service_url: str
    scopes: tuple[str, ...]
    types: tuple[str, ...]
    display_name: str
    manufacturer_hint: str | None = None
    model_hint: str | None = None


@dataclass(frozen=True)
class VerifiedOnvifDevice:
    manufacturer: str
    model: str
    firmware_version: str
    serial_number: str
    hardware_id: str
    profile_token: str
    profile_name: str
    video_encoding: str
    width: int | None
    height: int | None
    audio_encoding: str | None
    has_ptz: bool
    has_audio: bool
    rtsp_uri: str
    preview_profile_token: str | None = None
    preview_profile_name: str | None = None
    preview_video_encoding: str | None = None
    preview_width: int | None = None
    preview_height: int | None = None
    preview_audio_encoding: str | None = None
    preview_rtsp_uri: str | None = None


class OnvifClient:
    def __init__(
        self,
        *,
        discovery_timeout_seconds: float = 1.5,
        http_timeout_seconds: float = 4.0,
        rtsp_timeout_seconds: float = 4.0,
    ):
        self.discovery_timeout_seconds = max(0.2, float(discovery_timeout_seconds))
        self.http_timeout_seconds = max(0.5, float(http_timeout_seconds))
        self.rtsp_timeout_seconds = max(0.5, float(rtsp_timeout_seconds))

    def discover(
        self,
        *,
        target_ip: str | None = None,
        timeout_ms: int | None = None,
    ) -> list[DiscoveredOnvifDevice]:
        normalized_target = normalize_local_target_ip(target_ip) if target_ip else None
        destination = (normalized_target, WS_DISCOVERY_ADDRESS[1]) if normalized_target else WS_DISCOVERY_ADDRESS
        timeout_seconds = (
            self.discovery_timeout_seconds
            if timeout_ms is None
            else max(0.5, min(float(timeout_ms) / 1000, 5.0))
        )
        responses = self._send_probe(destination, timeout_seconds=timeout_seconds)
        candidates = self._parse_probe_responses(responses)
        if normalized_target:
            candidates = [
                candidate
                for candidate in candidates
                if url_host(candidate.device_service_url) == normalized_target
            ]
            if not candidates:
                fallback = self._directed_endpoint_fallback(normalized_target)
                if fallback is not None:
                    candidates = [fallback]
        return _deduplicate_candidates(candidates)

    def inspect_and_verify(
        self,
        *,
        device_service_url: str,
        username: str,
        password: str,
    ) -> VerifiedOnvifDevice:
        service_url = normalize_local_service_url(device_service_url)
        expected_host = url_host(service_url)
        device_info = self._soap_request(
            service_url,
            action=f"{ONVIF_DEVICE_WSDL}/GetDeviceInformation",
            body=f'<tds:GetDeviceInformation xmlns:tds="{ONVIF_DEVICE_WSDL}"/>',
            username=username,
            password=password,
        )
        manufacturer = _first_text(device_info, "Manufacturer")
        model = _first_text(device_info, "Model")
        firmware_version = _first_text(device_info, "FirmwareVersion")
        serial_number = _first_text(device_info, "SerialNumber")
        hardware_id = _first_text(device_info, "HardwareId")

        capabilities = self._soap_request(
            service_url,
            action=f"{ONVIF_DEVICE_WSDL}/GetCapabilities",
            body=(
                f'<tds:GetCapabilities xmlns:tds="{ONVIF_DEVICE_WSDL}">'
                "<tds:Category>All</tds:Category>"
                "</tds:GetCapabilities>"
            ),
            username=username,
            password=password,
        )
        media_url = _capability_xaddr(capabilities, "Media")
        if not media_url:
            media_url = f"http://{expected_host}/onvif/media_service"
        media_url = normalize_local_service_url(media_url, expected_host=expected_host)
        has_ptz = bool(_capability_xaddr(capabilities, "PTZ"))

        profiles_response = self._soap_request(
            media_url,
            action=f"{ONVIF_MEDIA_WSDL}/GetProfiles",
            body=f'<trt:GetProfiles xmlns:trt="{ONVIF_MEDIA_WSDL}"/>',
            username=username,
            password=password,
        )
        profiles = _media_profiles(profiles_response)
        if not profiles:
            raise OnvifProtocolError("ONVIF 设备没有可用的视频 Profile。")
        profile = profiles[0]
        preview_profile = _select_preview_profile(profiles)
        if (
            _normalized_video_encoding(
                preview_profile.get("video_encoding")
            )
            != "h264"
        ):
            raise OnvifProtocolError("摄像头没有可用于实时预览的 H.264 视频流。")
        rtsp_uri = self._get_stream_uri(
            media_url=media_url,
            profile_token=profile["token"],
            expected_host=expected_host,
            username=username,
            password=password,
        )
        self.verify_rtsp(rtsp_uri=rtsp_uri, username=username, password=password)
        preview_rtsp_uri = rtsp_uri
        if preview_profile["token"] != profile["token"]:
            preview_rtsp_uri = self._get_stream_uri(
                media_url=media_url,
                profile_token=preview_profile["token"],
                expected_host=expected_host,
                username=username,
                password=password,
            )
            self.verify_rtsp(
                rtsp_uri=preview_rtsp_uri,
                username=username,
                password=password,
            )

        return VerifiedOnvifDevice(
            manufacturer=manufacturer,
            model=model,
            firmware_version=firmware_version,
            serial_number=serial_number,
            hardware_id=hardware_id,
            profile_token=profile["token"],
            profile_name=profile["name"],
            video_encoding=profile["video_encoding"],
            width=profile["width"],
            height=profile["height"],
            audio_encoding=profile["audio_encoding"],
            has_ptz=has_ptz,
            has_audio=bool(
                profile["audio_encoding"] or preview_profile["audio_encoding"]
            ),
            rtsp_uri=rtsp_uri,
            preview_profile_token=preview_profile["token"],
            preview_profile_name=preview_profile["name"],
            preview_video_encoding=preview_profile["video_encoding"],
            preview_width=preview_profile["width"],
            preview_height=preview_profile["height"],
            preview_audio_encoding=preview_profile["audio_encoding"],
            preview_rtsp_uri=preview_rtsp_uri,
        )

    def _get_stream_uri(
        self,
        *,
        media_url: str,
        profile_token: str,
        expected_host: str,
        username: str,
        password: str,
    ) -> str:
        stream_uri_response = self._soap_request(
            media_url,
            action=f"{ONVIF_MEDIA_WSDL}/GetStreamUri",
            body=(
                f'<trt:GetStreamUri xmlns:trt="{ONVIF_MEDIA_WSDL}" '
                f'xmlns:tt="{ONVIF_SCHEMA}">'
                "<trt:StreamSetup>"
                "<tt:Stream>RTP-Unicast</tt:Stream>"
                "<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport>"
                "</trt:StreamSetup>"
                f"<trt:ProfileToken>{escape(profile_token)}</trt:ProfileToken>"
                "</trt:GetStreamUri>"
            ),
            username=username,
            password=password,
        )
        return normalize_local_rtsp_uri(
            _first_text(stream_uri_response, "Uri"),
            expected_host=expected_host,
        )

    def verify_rtsp(self, *, rtsp_uri: str, username: str, password: str) -> None:
        safe_uri = normalize_local_rtsp_uri(rtsp_uri)
        status, headers = self._rtsp_describe(safe_uri)
        if status == 200:
            return
        if status != 401:
            raise RtspUnavailableError("摄像头视频流暂时不可用。")

        challenge = headers.get("www-authenticate", "")
        authorization = _rtsp_authorization(
            challenge=challenge,
            username=username,
            password=password,
            method="DESCRIBE",
            request_uri=safe_uri,
        )
        if not authorization:
            raise RtspAuthenticationError("摄像头视频账号或密码不正确。")
        status, _ = self._rtsp_describe(safe_uri, authorization=authorization)
        if status == 200:
            return
        if status == 401:
            raise RtspAuthenticationError("摄像头视频账号或密码不正确。")
        raise RtspUnavailableError("摄像头视频流暂时不可用。")

    def fetch_snapshot(
        self,
        *,
        device_service_url: str,
        profile_token: str,
        username: str,
        password: str,
    ) -> tuple[bytes, str]:
        service_url = normalize_local_service_url(device_service_url)
        expected_host = url_host(service_url)
        capabilities = self._soap_request(
            service_url,
            action=f"{ONVIF_DEVICE_WSDL}/GetCapabilities",
            body=(
                f'<tds:GetCapabilities xmlns:tds="{ONVIF_DEVICE_WSDL}">'
                "<tds:Category>Media</tds:Category>"
                "</tds:GetCapabilities>"
            ),
            username=username,
            password=password,
        )
        media_url = _capability_xaddr(capabilities, "Media")
        if not media_url:
            media_url = f"http://{expected_host}/onvif/media_service"
        media_url = normalize_local_service_url(media_url, expected_host=expected_host)
        response = self._soap_request(
            media_url,
            action=f"{ONVIF_MEDIA_WSDL}/GetSnapshotUri",
            body=(
                f'<trt:GetSnapshotUri xmlns:trt="{ONVIF_MEDIA_WSDL}">'
                f"<trt:ProfileToken>{escape(profile_token)}</trt:ProfileToken>"
                "</trt:GetSnapshotUri>"
            ),
            username=username,
            password=password,
        )
        snapshot_url = normalize_local_service_url(
            _first_text(response, "Uri"),
            expected_host=expected_host,
        )
        return self._authenticated_get(
            snapshot_url,
            username=username,
            password=password,
            max_bytes=8 * 1024 * 1024,
        )

    def _send_probe(
        self,
        destination: tuple[str, int],
        *,
        timeout_seconds: float,
    ) -> list[tuple[bytes, str]]:
        responses: list[tuple[bytes, str]] = []
        started_at = time.monotonic()
        deadline = started_at + timeout_seconds
        probe_times = [
            started_at + offset
            for offset in _probe_send_offsets(timeout_seconds)
        ]
        next_probe = 0
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
                sock.bind(("", 0))
                while True:
                    now = time.monotonic()
                    while (
                        next_probe < len(probe_times)
                        and now >= probe_times[next_probe]
                    ):
                        sock.sendto(_discovery_probe_envelope(), destination)
                        next_probe += 1
                    if now >= deadline:
                        break

                    next_wakeup = min(
                        deadline,
                        probe_times[next_probe]
                        if next_probe < len(probe_times)
                        else deadline,
                        now + 0.25,
                    )
                    sock.settimeout(max(0.01, next_wakeup - now))
                    try:
                        body, sender = sock.recvfrom(65535)
                    except socket.timeout:
                        continue
                    if body:
                        responses.append((body, str(sender[0])))
        except OSError as exc:
            raise OnvifUnavailableError("当前网络无法搜索摄像头。") from exc
        return responses

    def _parse_probe_responses(
        self,
        responses: list[tuple[bytes, str]],
    ) -> list[DiscoveredOnvifDevice]:
        candidates: list[DiscoveredOnvifDevice] = []
        for response, sender_ip in responses:
            try:
                sender_ip = normalize_local_target_ip(sender_ip)
            except OnvifProtocolError:
                continue
            try:
                root = ET.fromstring(response)
            except ET.ParseError:
                continue
            for match in _elements(root, "ProbeMatch"):
                endpoint_reference = _descendant_text(match, "Address")
                xaddrs = _descendant_text(match, "XAddrs").split()
                scopes = tuple(item for item in _descendant_text(match, "Scopes").split() if item)
                types = tuple(item for item in _descendant_text(match, "Types").split() if item)
                if not any("NetworkVideoTransmitter" in item for item in types):
                    continue
                service_url = next(
                    (
                        normalized
                        for value in xaddrs
                        if (
                            normalized := _try_normalize_local_service_url(
                                value,
                                expected_host=sender_ip,
                            )
                        )
                        is not None
                    ),
                    None,
                )
                if not service_url:
                    continue
                name = _scope_value(scopes, "name")
                manufacturer_hint = _scope_value(scopes, "manufacturer")
                model_hint = _scope_value(scopes, "hardware")
                candidates.append(
                    DiscoveredOnvifDevice(
                        endpoint_reference=endpoint_reference or service_url,
                        device_service_url=service_url,
                        scopes=scopes,
                        types=types,
                        display_name=name or model_hint or "AI 看护摄像头",
                        manufacturer_hint=manufacturer_hint,
                        model_hint=model_hint,
                    )
                )
        return candidates

    def _directed_endpoint_fallback(self, target_ip: str) -> DiscoveredOnvifDevice | None:
        for path in ("/onvif/device_service", "/onvif/device_service/"):
            url = f"http://{target_ip}{path}"
            if not self._onvif_endpoint_exists(url):
                continue
            return DiscoveredOnvifDevice(
                endpoint_reference=f"onvif-device-service:{target_ip}",
                device_service_url=url,
                scopes=(),
                types=("dn:NetworkVideoTransmitter",),
                display_name="AI 看护摄像头",
            )
        return None

    def _onvif_endpoint_exists(self, url: str) -> bool:
        body = (
            f'<tds:GetSystemDateAndTime xmlns:tds="{ONVIF_DEVICE_WSDL}"/>'
        )
        envelope = _soap_envelope(body)
        request = Request(
            url,
            data=envelope,
            headers=_soap_headers(f"{ONVIF_DEVICE_WSDL}/GetSystemDateAndTime"),
            method="POST",
        )
        try:
            with build_opener(_RejectRedirectHandler()).open(
                request,
                timeout=self.http_timeout_seconds,
            ) as response:
                response.read(1024)
                return 200 <= response.status < 500
        except HTTPError as exc:
            return exc.code in {400, 401, 405, 500}
        except (URLError, TimeoutError, OSError):
            return False

    def _soap_request(
        self,
        url: str,
        *,
        action: str,
        body: str,
        username: str,
        password: str,
    ) -> ET.Element:
        envelope = _soap_envelope(
            body,
            ws_security=_ws_security_header(username, password),
        )
        request = Request(
            url,
            data=envelope,
            headers=_soap_headers(action),
            method="POST",
        )
        manager = HTTPPasswordMgrWithDefaultRealm()
        manager.add_password(None, url, username, password)
        opener = build_opener(
            _RejectRedirectHandler(),
            HTTPDigestAuthHandler(manager),
            HTTPBasicAuthHandler(manager),
        )
        try:
            with opener.open(request, timeout=self.http_timeout_seconds) as response:
                payload = response.read(1_048_577)
        except HTTPError as exc:
            payload = exc.read(1_048_577)
            if exc.code in {401, 403} or _soap_fault_not_authorized(payload):
                raise OnvifAuthenticationError("摄像头账号或密码不正确。") from exc
            raise OnvifUnavailableError("摄像头 ONVIF 服务暂时不可用。") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise OnvifUnavailableError("摄像头 ONVIF 服务暂时不可用。") from exc
        if len(payload) > 1_048_576:
            raise OnvifProtocolError("摄像头 ONVIF 响应异常。")
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise OnvifProtocolError("摄像头 ONVIF 响应格式不正确。") from exc
        fault = next(iter(_elements(root, "Fault")), None)
        if fault is not None:
            reason = _descendant_text(fault, "Text") or _descendant_text(fault, "Reason")
            if "author" in reason.lower() or "notauthorized" in ET.tostring(fault, encoding="unicode").lower():
                raise OnvifAuthenticationError("摄像头账号或密码不正确。")
            raise OnvifProtocolError("摄像头暂不支持所需的 ONVIF 能力。")
        return root

    def _authenticated_get(
        self,
        url: str,
        *,
        username: str,
        password: str,
        max_bytes: int,
    ) -> tuple[bytes, str]:
        manager = HTTPPasswordMgrWithDefaultRealm()
        manager.add_password(None, url, username, password)
        opener = build_opener(
            _RejectRedirectHandler(),
            HTTPDigestAuthHandler(manager),
            HTTPBasicAuthHandler(manager),
        )
        request = Request(
            url,
            headers={"User-Agent": "MiraGuardian/1.0", "Accept": "image/jpeg"},
            method="GET",
        )
        try:
            with opener.open(request, timeout=self.http_timeout_seconds) as response:
                body = response.read(max_bytes + 1)
                content_type = str(response.headers.get("content-type") or "image/jpeg")
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise OnvifAuthenticationError("摄像头账号或密码不正确。") from exc
            raise OnvifUnavailableError("摄像头快照暂时不可用。") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise OnvifUnavailableError("摄像头快照暂时不可用。") from exc
        if len(body) > max_bytes:
            raise OnvifProtocolError("摄像头快照响应过大。")
        if not body:
            raise OnvifUnavailableError("摄像头快照暂时不可用。")
        return body, content_type.split(";", 1)[0].strip() or "image/jpeg"

    def _rtsp_describe(
        self,
        rtsp_uri: str,
        *,
        authorization: str | None = None,
    ) -> tuple[int, dict[str, str]]:
        parsed = urlparse(rtsp_uri)
        host = parsed.hostname or ""
        port = parsed.port or 554
        lines = [
            f"DESCRIBE {rtsp_uri} RTSP/1.0",
            "CSeq: 1",
            "Accept: application/sdp",
            "User-Agent: MiraGuardian/1.0",
        ]
        if authorization:
            lines.append(f"Authorization: {authorization}")
        request = ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")
        try:
            with socket.create_connection((host, port), timeout=self.rtsp_timeout_seconds) as sock:
                sock.settimeout(self.rtsp_timeout_seconds)
                sock.sendall(request)
                response = _read_rtsp_headers(sock)
        except (TimeoutError, OSError) as exc:
            raise RtspUnavailableError("摄像头视频流暂时不可用。") from exc
        return _parse_rtsp_response(response)


def normalize_local_target_ip(value: str | None) -> str:
    text = str(value or "").strip()
    try:
        address = ipaddress.ip_address(text)
    except ValueError as exc:
        raise OnvifProtocolError("目标摄像头地址格式不正确。") from exc
    if not isinstance(address, ipaddress.IPv4Address):
        raise OnvifProtocolError("当前只支持局域网 IPv4 摄像头。")
    if not _is_local_camera_address(address):
        raise OnvifProtocolError("只能搜索当前局域网中的摄像头。")
    return str(address)


def normalize_local_service_url(value: str, *, expected_host: str | None = None) -> str:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise OnvifProtocolError("ONVIF 服务地址格式不正确。")
    if parsed.username or parsed.password:
        raise OnvifProtocolError("ONVIF 服务地址不能包含账号或密码。")
    host = _normalized_local_url_host(parsed.hostname, expected_host=expected_host)
    if expected_host and host != expected_host:
        raise OnvifProtocolError("ONVIF 服务地址不属于已发现的摄像头。")
    netloc = _netloc(host, parsed.port)
    path = parsed.path or "/onvif/device_service"
    return urlunparse((parsed.scheme, netloc, path, "", parsed.query, ""))


def normalize_local_rtsp_uri(value: str, *, expected_host: str | None = None) -> str:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme.lower() != "rtsp" or not parsed.hostname:
        raise OnvifProtocolError("摄像头未提供有效的视频流。")
    host = _normalized_local_url_host(parsed.hostname, expected_host=expected_host)
    if expected_host and host != expected_host:
        raise OnvifProtocolError("视频流地址不属于已发现的摄像头。")
    netloc = _netloc(host, parsed.port)
    path = parsed.path or "/"
    return urlunparse(("rtsp", netloc, path, "", parsed.query, ""))


def url_host(value: str) -> str:
    return str(urlparse(value).hostname or "")


def _normalized_local_url_host(value: str, *, expected_host: str | None) -> str:
    text = str(value or "").strip()
    if text in {"0.0.0.0", "::", "[::]"} and expected_host:
        return expected_host
    try:
        address = ipaddress.ip_address(text)
    except ValueError as exc:
        raise OnvifProtocolError("摄像头服务必须使用局域网 IP 地址。") from exc
    if not _is_local_camera_address(address):
        raise OnvifProtocolError("摄像头服务地址不在当前局域网。")
    return str(address)


def _is_local_camera_address(address: ipaddress._BaseAddress) -> bool:
    if (
        address.is_loopback
        or address.is_unspecified
        or address.is_multicast
        or address.is_link_local
        or address.is_reserved
    ):
        return False
    if isinstance(address, ipaddress.IPv4Address):
        return any(
            address in network
            for network in (
                ipaddress.ip_network("10.0.0.0/8"),
                ipaddress.ip_network("172.16.0.0/12"),
                ipaddress.ip_network("192.168.0.0/16"),
            )
        )
    return bool(address.is_private)


def _try_normalize_local_service_url(
    value: str,
    *,
    expected_host: str,
) -> str | None:
    try:
        return normalize_local_service_url(value, expected_host=expected_host)
    except OnvifProtocolError:
        return None


def _netloc(host: str, port: int | None) -> str:
    formatted_host = f"[{host}]" if ":" in host else host
    return f"{formatted_host}:{port}" if port else formatted_host


def _discovery_probe_envelope() -> bytes:
    message_id = f"uuid:{uuid.uuid4()}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<s:Envelope xmlns:s="{SOAP_ENV}" xmlns:a="{WS_ADDRESSING}" '
        f'xmlns:d="{WS_DISCOVERY}" xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
        "<s:Header>"
        f"<a:MessageID>{message_id}</a:MessageID>"
        f"<a:To>{WS_DISCOVERY_TO}</a:To>"
        f"<a:Action>{WS_DISCOVERY}/Probe</a:Action>"
        "<a:ReplyTo>"
        f"<a:Address>{WS_ADDRESSING}/role/anonymous</a:Address>"
        "</a:ReplyTo>"
        "</s:Header>"
        "<s:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></s:Body>"
        "</s:Envelope>"
    ).encode("utf-8")


def _probe_send_offsets(timeout_seconds: float) -> tuple[float, ...]:
    """Schedule three probes inside one discovery window.

    Some low-cost camera firmware drops individual multicast packets. Distinct
    WS-Discovery message IDs improve reliability without extending the API
    timeout or changing the response contract.
    """

    window = max(0.2, float(timeout_seconds))
    return (0.0, min(0.35, window * 0.25), min(0.8, window * 0.55))


def _soap_envelope(body: str, *, ws_security: str = "") -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<s:Envelope xmlns:s="{SOAP_ENV}">'
        f"<s:Header>{ws_security}</s:Header>"
        f"<s:Body>{body}</s:Body>"
        "</s:Envelope>"
    ).encode("utf-8")


def _soap_headers(action: str) -> dict[str, str]:
    return {
        "Content-Type": f'application/soap+xml; charset=utf-8; action="{action}"',
        "SOAPAction": f'"{action}"',
        "User-Agent": "MiraGuardian/1.0",
    }


def _ws_security_header(username: str, password: str) -> str:
    nonce = os.urandom(16)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    digest = hashlib.sha1(nonce + created.encode("utf-8") + password.encode("utf-8")).digest()
    return (
        '<wsse:Security s:mustUnderstand="1" '
        'xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/'
        'oasis-200401-wss-wssecurity-secext-1.0.xsd" '
        'xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/'
        'oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        "<wsse:UsernameToken>"
        f"<wsse:Username>{escape(username)}</wsse:Username>"
        '<wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/'
        'oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
        f"{base64.b64encode(digest).decode('ascii')}</wsse:Password>"
        '<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/'
        'oasis-200401-wss-soap-message-security-1.0#Base64Binary">'
        f"{base64.b64encode(nonce).decode('ascii')}</wsse:Nonce>"
        f'<wsu:Created>{created}</wsu:Created>'
        "</wsse:UsernameToken>"
        "</wsse:Security>"
    )


def _soap_fault_not_authorized(payload: bytes) -> bool:
    text = payload.decode("utf-8", "ignore").lower()
    return "notauthorized" in text or "not authorized" in text


def _elements(root: ET.Element, local_name: str):
    return (element for element in root.iter() if _local_name(element.tag) == local_name)


def _first_text(root: ET.Element, local_name: str) -> str:
    element = next(iter(_elements(root, local_name)), None)
    return str(element.text or "").strip() if element is not None else ""


def _descendant_text(root: ET.Element, local_name: str) -> str:
    return _first_text(root, local_name)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag.split(":", 1)[-1]


def _scope_value(scopes: tuple[str, ...], key: str) -> str | None:
    marker = f"/{key}/"
    for scope in scopes:
        if marker not in scope:
            continue
        value = scope.split(marker, 1)[1].split("/", 1)[0]
        decoded = unquote(value).replace("_", " ").strip()
        if decoded:
            return decoded[:120]
    return None


def _capability_xaddr(root: ET.Element, capability_name: str) -> str:
    for element in _elements(root, capability_name):
        for child in element.iter():
            if _local_name(child.tag) == "XAddr" and str(child.text or "").strip():
                return str(child.text).strip()
    return ""


def _media_profiles(root: ET.Element) -> list[dict]:
    profiles: list[dict] = []
    for element in _elements(root, "Profiles"):
        token = str(element.attrib.get("token") or "").strip()
        video = next(
            (child for child in element.iter() if _local_name(child.tag) == "VideoEncoderConfiguration"),
            None,
        )
        if not token or video is None:
            continue
        audio = next(
            (child for child in element.iter() if _local_name(child.tag) == "AudioEncoderConfiguration"),
            None,
        )
        resolution = next(
            (child for child in video.iter() if _local_name(child.tag) == "Resolution"),
            None,
        )
        profiles.append(
            {
                "token": token,
                "name": _child_text(element, "Name") or "主码流",
                "video_encoding": _child_text(video, "Encoding"),
                "width": _int_child(resolution, "Width") if resolution is not None else None,
                "height": _int_child(resolution, "Height") if resolution is not None else None,
                "audio_encoding": _child_text(audio, "Encoding") if audio is not None else None,
            }
        )
    return sorted(
        profiles,
        key=lambda item: int(item.get("width") or 0) * int(item.get("height") or 0),
        reverse=True,
    )


def _select_preview_profile(profiles: list[dict]) -> dict:
    """Prefer the largest WebRTC-friendly H.264 profile up to 720p."""

    if not profiles:
        raise OnvifProtocolError("ONVIF 设备没有可用的视频 Profile。")
    h264_profiles = [
        profile
        for profile in profiles
        if _normalized_video_encoding(profile.get("video_encoding")) == "h264"
    ]
    if not h264_profiles:
        return profiles[-1]
    bounded = [
        profile
        for profile in h264_profiles
        if int(profile.get("width") or 0) <= 1280
        and int(profile.get("height") or 0) <= 720
    ]
    candidates = bounded or h264_profiles
    return max(
        candidates,
        key=lambda item: int(item.get("width") or 0)
        * int(item.get("height") or 0),
    )


def _normalized_video_encoding(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())


def _child_text(root: ET.Element | None, local_name: str) -> str:
    if root is None:
        return ""
    for child in root:
        if _local_name(child.tag) == local_name:
            return str(child.text or "").strip()
    return ""


def _int_child(root: ET.Element | None, local_name: str) -> int | None:
    value = _child_text(root, local_name)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _deduplicate_candidates(
    candidates: list[DiscoveredOnvifDevice],
) -> list[DiscoveredOnvifDevice]:
    by_identity: dict[str, DiscoveredOnvifDevice] = {}
    for candidate in candidates:
        identity = candidate.endpoint_reference or candidate.device_service_url
        by_identity.setdefault(identity, candidate)
    return list(by_identity.values())


def _read_rtsp_headers(sock: socket.socket) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while size <= 65536:
        chunk = sock.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if b"\r\n\r\n" in b"".join(chunks):
            break
    if size > 65536:
        raise RtspUnavailableError("摄像头视频响应异常。")
    return b"".join(chunks)


def _parse_rtsp_response(payload: bytes) -> tuple[int, dict[str, str]]:
    header = payload.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1", "ignore")
    lines = header.split("\r\n")
    if not lines:
        raise RtspUnavailableError("摄像头视频响应异常。")
    match = re.match(r"RTSP/\d+\.\d+\s+(\d{3})", lines[0].strip())
    if not match:
        raise RtspUnavailableError("摄像头视频响应异常。")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return int(match.group(1)), headers


def _rtsp_authorization(
    *,
    challenge: str,
    username: str,
    password: str,
    method: str,
    request_uri: str,
) -> str | None:
    scheme, _, raw_params = challenge.partition(" ")
    scheme = scheme.strip().lower()
    if scheme == "basic":
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return f"Basic {encoded}"
    if scheme != "digest":
        return None
    params = _digest_params(raw_params)
    realm = params.get("realm", "")
    nonce = params.get("nonce", "")
    if not realm or not nonce:
        return None
    algorithm = params.get("algorithm", "MD5").upper()
    if algorithm not in {"MD5", "MD5-SESS"}:
        return None
    ha1 = _md5_hex(f"{username}:{realm}:{password}")
    cnonce = uuid.uuid4().hex
    if algorithm == "MD5-SESS":
        ha1 = _md5_hex(f"{ha1}:{nonce}:{cnonce}")
    ha2 = _md5_hex(f"{method}:{request_uri}")
    qop_values = [value.strip() for value in params.get("qop", "").split(",") if value.strip()]
    qop = "auth" if "auth" in qop_values else ""
    fields = [
        f'username="{_quote_digest(username)}"',
        f'realm="{_quote_digest(realm)}"',
        f'nonce="{_quote_digest(nonce)}"',
        f'uri="{_quote_digest(request_uri)}"',
    ]
    if qop:
        nc = "00000001"
        response = _md5_hex(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}")
        fields.extend([f"qop={qop}", f"nc={nc}", f'cnonce="{cnonce}"'])
    else:
        response = _md5_hex(f"{ha1}:{nonce}:{ha2}")
    fields.append(f'response="{response}"')
    if params.get("opaque"):
        fields.append(f'opaque="{_quote_digest(params["opaque"])}"')
    fields.append(f"algorithm={algorithm}")
    return "Digest " + ", ".join(fields)


def _digest_params(value: str) -> dict[str, str]:
    params: dict[str, str] = {}
    pattern = re.compile(r'([A-Za-z0-9_-]+)\s*=\s*(?:"((?:\\.|[^"])*)"|([^,\s]+))')
    for match in pattern.finditer(value):
        raw = match.group(2) if match.group(2) is not None else match.group(3)
        params[match.group(1).lower()] = raw.replace('\\"', '"')
    return params


def _md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def _quote_digest(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class _RejectRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None
