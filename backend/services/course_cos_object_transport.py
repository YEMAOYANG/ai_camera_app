"""Bounded signed reads from a private Tencent COS bucket.

The rest of course storage keeps its existing S3-compatible/MinIO transport.
This adapter is selected only for ``provider=tencent-cos`` and never logs the
endpoint, object key, SecretId, SecretKey, or provider exception text.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.course_storage_config import CourseStorageConfig


class _Headers:
    def __init__(self, values: Mapping[str, Any]):
        self._values = {str(key).lower(): value for key, value in values.items()}

    def get(self, name: str, default=None):
        return self._values.get(name.lower(), default)


class CourseCosResponse:
    """Small urllib-like response facade over the official COS SDK stream."""

    def __init__(self, response: Mapping[str, Any], *, session):
        body = response.get("Body")
        if body is None or not callable(getattr(body, "get_raw_stream", None)):
            raise OSError("COS response body unavailable")
        self._raw = body.get_raw_stream()
        self.status = self._raw.status
        self.headers = _Headers({key: value for key, value in response.items() if key != "Body"})
        self._session = session
        self._closed = False

    def read(self, size: int = -1) -> bytes:
        if self._closed:
            return b""
        try:
            # SDK iter_content() transparently decompresses. The callers hash
            # exact stored bytes and validate Content-Encoding themselves.
            result = self._raw.read(size if size >= 0 else None, decode_content=False)
            if not isinstance(result, bytes):
                raise OSError("COS response chunk unavailable")
            return result
        except Exception:
            raise OSError("Tencent COS object read unavailable") from None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._raw.close()
        finally:
            self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        self.close()
        return False


def open_cos_object(
    config: CourseStorageConfig,
    key: str,
    *,
    range_header: str | None = None,
    if_match: str | None = None,
    version_id: str | None = None,
) -> CourseCosResponse:
    """Open one signed private COS object without exposing provider errors."""
    session = None
    try:
        from qcloud_cos import CosConfig, CosS3Client
        from requests import Session

        sdk_config = CosConfig(
            Region=config.region,
            SecretId=config.access_key,
            SecretKey=config.secret_key,
            Scheme="https",
            Timeout=10,
            AllowRedirects=False,
            SignHost=True,
            AutoSwitchDomainOnRetry=False,
        )
        session = Session()
        session.trust_env = False
        client = CosS3Client(sdk_config, retry=0, session=session)
        options: dict[str, str] = {"AcceptEncoding": "identity"}
        if range_header is not None:
            options["Range"] = range_header
        if if_match is not None:
            options["IfMatch"] = if_match
        if version_id is not None:
            options["VersionId"] = version_id
        response = client.get_object(Bucket=config.bucket, Key=key, **options)
        return CourseCosResponse(response, session=session)
    except Exception:
        if session is not None:
            session.close()
        # Only the transport's own sanitized exception crosses this boundary.
        raise OSError("Tencent COS object read unavailable") from None
