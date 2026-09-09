from __future__ import annotations

import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import PurePath
import secrets
from typing import Any, Callable, Mapping
from urllib import error as urlerror
from urllib import request as urlrequest


_SUPPORTED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/tiff",
        "image/bmp",
    }
)


class MinerUDocumentError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code or "mineru_failed")
        self.message = str(message or "MinerU document parsing failed")


@dataclass(frozen=True)
class MinerUImage:
    key: str
    base64_data: str
    page_number: int
    bbox: tuple[float, float, float, float] | None
    caption: str | None


@dataclass(frozen=True)
class MinerUDocument:
    file_name: str
    markdown: str
    images: tuple[MinerUImage, ...]
    content_list: tuple[dict[str, Any], ...]
    page_count: int
    parser: str = "mineru"


Transport = Callable[[str, bytes, Mapping[str, str], float], tuple[int, bytes]]


class MinerUDocumentAdapter:
    """Parse an authorized source document through a self-hosted MinerU API.

    MinerU is deliberately kept before the curriculum and classroom generator:
    this adapter extracts grounded text and media metadata, but never chooses a
    grade, skill order, answer, or publication status.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key_env: str = "MINERU_API_KEY",
        backend: str | None = None,
        timeout_seconds: float = 180.0,
        max_file_bytes: int = 150 * 1024 * 1024,
        transport: Transport | None = None,
    ):
        self.base_url = str(base_url or os.getenv("MINERU_BASE_URL") or "").strip().rstrip("/")
        self.api_key_env = str(api_key_env or "MINERU_API_KEY").strip()
        self.backend = str(backend or os.getenv("MINERU_BACKEND") or "pipeline").strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_file_bytes = max(1, int(max_file_bytes))
        self._transport = transport or self._http_transport

    def availability(self) -> dict[str, Any]:
        return {
            "available": self.base_url.startswith(("http://", "https://")),
            "provider": "mineru",
            "mode": "self_hosted",
            "baseUrlConfigured": bool(self.base_url),
            "backend": self.backend,
            "capabilities": ["text", "images", "tables", "formulas", "layout"],
        }

    def parse(
        self,
        *,
        file_name: str,
        content: bytes,
        mime_type: str | None = None,
    ) -> MinerUDocument:
        normalized_name = self._file_name(file_name)
        payload = bytes(content or b"")
        if not payload:
            raise MinerUDocumentError("mineru_empty_file", "解析材料不能为空")
        if len(payload) > self.max_file_bytes:
            raise MinerUDocumentError(
                "mineru_file_too_large",
                "解析材料超过允许大小",
            )
        normalized_mime = str(
            mime_type or mimetypes.guess_type(normalized_name)[0] or ""
        ).strip().lower()
        if normalized_mime not in _SUPPORTED_MIME_TYPES:
            raise MinerUDocumentError(
                "mineru_unsupported_file",
                "MinerU 不支持这种材料格式",
            )
        if not self.base_url.startswith(("http://", "https://")):
            raise MinerUDocumentError(
                "mineru_not_configured",
                "MinerU 文档解析服务尚未配置",
            )

        boundary = f"----MiraMinerU{secrets.token_hex(16)}"
        body = self._multipart(
            boundary=boundary,
            file_name=normalized_name,
            mime_type=normalized_mime,
            content=payload,
        )
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        api_key = os.getenv(self.api_key_env, "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            status, response_body = self._transport(
                f"{self.base_url}/file_parse",
                body,
                headers,
                self.timeout_seconds,
            )
        except (OSError, TimeoutError) as exc:
            raise MinerUDocumentError(
                "mineru_unavailable",
                "MinerU 文档解析服务暂时不可用",
            ) from exc
        if status < 200 or status >= 300:
            raise MinerUDocumentError(
                "mineru_request_failed",
                f"MinerU 文档解析失败（HTTP {status}）",
            )
        try:
            response = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MinerUDocumentError(
                "mineru_invalid_response",
                "MinerU 返回了无法识别的结果",
            ) from exc
        return self._document(response, normalized_name)

    def grounding_payload(
        self,
        document: MinerUDocument,
        *,
        max_text_chars: int = 50_000,
        max_images: int = 20,
    ) -> dict[str, Any]:
        """Return the bounded, answer-neutral context allowed into generation."""

        text_limit = min(max(int(max_text_chars), 1), 50_000)
        image_limit = min(max(int(max_images), 0), 20)
        return {
            "sourceType": "authorized_material",
            "parser": "mineru",
            "fileName": document.file_name,
            "markdown": document.markdown[:text_limit],
            "truncated": len(document.markdown) > text_limit,
            "pageCount": document.page_count,
            "images": [
                {
                    "key": image.key,
                    "data": image.base64_data,
                    "pageNumber": image.page_number,
                    "bbox": list(image.bbox) if image.bbox is not None else None,
                    "caption": image.caption,
                }
                for image in document.images[:image_limit]
            ],
        }

    def _multipart(
        self,
        *,
        boundary: str,
        file_name: str,
        mime_type: str,
        content: bytes,
    ) -> bytes:
        chunks: list[bytes] = []

        def field(name: str, value: str) -> None:
            chunks.extend(
                (
                    f"--{boundary}\r\n".encode("ascii"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"),
                    value.encode("utf-8"),
                    b"\r\n",
                )
            )

        chunks.extend(
            (
                f"--{boundary}\r\n".encode("ascii"),
                (
                    'Content-Disposition: form-data; name="files"; '
                    f'filename="{file_name}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {mime_type}\r\n\r\n".encode("ascii"),
                content,
                b"\r\n",
            )
        )
        field("parse_method", "auto")
        field("backend", self.backend)
        field("return_content_list", "true")
        field("return_images", "true")
        chunks.append(f"--{boundary}--\r\n".encode("ascii"))
        return b"".join(chunks)

    @staticmethod
    def _document(response: object, file_name: str) -> MinerUDocument:
        if not isinstance(response, Mapping):
            raise MinerUDocumentError(
                "mineru_invalid_response",
                "MinerU 返回了无法识别的结果",
            )
        results = response.get("results")
        if not isinstance(results, Mapping) or not results:
            raise MinerUDocumentError(
                "mineru_no_result",
                "MinerU 没有返回材料内容",
            )
        raw = results.get(file_name)
        if not isinstance(raw, Mapping):
            raw = next((item for item in results.values() if isinstance(item, Mapping)), None)
        if not isinstance(raw, Mapping):
            raise MinerUDocumentError(
                "mineru_no_result",
                "MinerU 没有返回材料内容",
            )
        markdown = str(raw.get("md_content") or "")
        content_list = MinerUDocumentAdapter._content_list(raw.get("content_list"))
        metadata_by_image: dict[str, dict[str, Any]] = {}
        pages: set[int] = set()
        for item in content_list:
            page_index = item.get("page_idx")
            if isinstance(page_index, int) and page_index >= 0:
                pages.add(page_index)
            image_path = str(item.get("img_path") or "").strip()
            if item.get("type") in {"image", "figure", "picture"} and image_path:
                metadata_by_image[image_path] = item
                metadata_by_image[PurePath(image_path).name] = item
        images_value = raw.get("images")
        images: list[MinerUImage] = []
        if isinstance(images_value, Mapping):
            for key, value in images_value.items():
                image_key = str(key)
                image_data = str(value or "")
                if not image_data:
                    continue
                if not image_data.startswith("data:"):
                    image_data = f"data:image/png;base64,{image_data}"
                meta = metadata_by_image.get(image_key) or metadata_by_image.get(
                    PurePath(image_key).name
                )
                bbox = None
                caption = None
                page_number = 0
                if isinstance(meta, Mapping):
                    page_index = meta.get("page_idx")
                    if isinstance(page_index, int) and page_index >= 0:
                        page_number = page_index + 1
                    raw_bbox = meta.get("bbox")
                    if (
                        isinstance(raw_bbox, list)
                        and len(raw_bbox) == 4
                        and all(isinstance(point, (int, float)) for point in raw_bbox)
                    ):
                        bbox = tuple(float(point) for point in raw_bbox)
                    captions = meta.get("image_caption")
                    if isinstance(captions, list) and captions:
                        caption = str(captions[0] or "").strip() or None
                images.append(
                    MinerUImage(
                        key=image_key,
                        base64_data=image_data,
                        page_number=page_number,
                        bbox=bbox,
                        caption=caption,
                    )
                )
        return MinerUDocument(
            file_name=file_name,
            markdown=markdown,
            images=tuple(images),
            content_list=tuple(content_list),
            page_count=len(pages),
        )

    @staticmethod
    def _content_list(value: object) -> list[dict[str, Any]]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return []
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, Mapping)]

    @staticmethod
    def _file_name(value: str) -> str:
        name = PurePath(str(value or "").replace("\\", "/")).name.strip()
        if not name or name in {".", ".."} or "\x00" in name or len(name) > 255:
            raise MinerUDocumentError("mineru_invalid_file_name", "材料文件名无效")
        return name

    @staticmethod
    def _http_transport(
        url: str,
        body: bytes,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> tuple[int, bytes]:
        request = urlrequest.Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urlrequest.urlopen(request, timeout=timeout_seconds) as response:
                return int(response.status), response.read()
        except urlerror.HTTPError as exc:
            return int(exc.code), exc.read()
