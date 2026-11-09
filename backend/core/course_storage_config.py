"""Typed server configuration for COURSE_STORAGE_* and private v1/v2 manifests.

PREFIX is unchanged for legacy v1 hash objects; a v2 readable layout typically
uses a date such as 2026-10-23, followed by subject/course/media-name segments.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from typing import Literal, Mapping, cast
from urllib.parse import urlsplit


@dataclass(frozen=True)
class CourseStorageConfig:
    mode: Literal["local", "manifest", "remote", "registry"] = "local"
    provider: Literal["s3-compatible", "tencent-cos"] = "s3-compatible"
    addressing_style: Literal["path", "virtual"] = "path"
    endpoint: str = ""
    bucket: str = ""
    prefix: str = "mira-courseware/v1"
    region: str = "us-east-1"
    access_key: str = field(default="", repr=False)
    secret_key: str = field(default="", repr=False)
    manifest_path: str = ""
    archive_enabled: bool = False

    @classmethod
    def from_env(cls, environment: Mapping[str, str] | None = None) -> CourseStorageConfig:
        # core.config already loads the backend-owned dotenv. Do not source a
        # second credential file or create another precedence chain here.
        env = os.environ if environment is None else environment
        def value(key: str, default: str = "") -> str:
            return str(env.get(f"COURSE_STORAGE_{key}", default)).strip()
        mode = value("MODE", "local") or "local"
        if mode not in {"local", "manifest", "remote", "registry"}:
            raise ValueError("Invalid course storage mode")
        provider = value("PROVIDER", "s3-compatible") or "s3-compatible"
        if provider not in {"s3-compatible", "tencent-cos"}:
            raise ValueError("Invalid course storage provider")
        addressing_style = value(
            "ADDRESSING_STYLE", "virtual" if provider == "tencent-cos" else "path"
        ) or ("virtual" if provider == "tencent-cos" else "path")
        if addressing_style not in {"path", "virtual"}:
            raise ValueError("Invalid course storage addressing style")
        archive_enabled = value("ARCHIVE_ENABLED", "0").lower()
        if archive_enabled not in {"0", "1", "false", "true"}:
            raise ValueError("Invalid course archive flag")
        config = cls(
            mode=cast(Literal["local", "manifest", "remote", "registry"], mode),
            provider=cast(Literal["s3-compatible", "tencent-cos"], provider),
            addressing_style=cast(Literal["path", "virtual"], addressing_style),
            endpoint=value("ENDPOINT"), bucket=value("BUCKET"),
            prefix=value("PREFIX", "mira-courseware/v1") or "mira-courseware/v1",
            region=value("REGION", "us-east-1") or "us-east-1",
            access_key=value("ACCESS_KEY"), secret_key=value("SECRET_KEY"),
            manifest_path=value("MANIFEST_PATH"),
            archive_enabled=archive_enabled in {"1", "true"},
        )
        if config.mode == "local" and not config.archive_enabled:
            return config
        try:
            endpoint = urlsplit(config.endpoint)
            valid_endpoint = (
                endpoint.scheme in {"http", "https"} and endpoint.hostname
                and not endpoint.username and not endpoint.password
                and endpoint.path in {"", "/"} and not endpoint.query and not endpoint.fragment
            )
            endpoint.port  # Reject malformed port syntax without revealing it.
        except ValueError:
            valid_endpoint = False
            endpoint = None
        cos_endpoint = bool(
            endpoint
            and endpoint.scheme == "https"
            and endpoint.port is None
            and endpoint.hostname == f"cos.{config.region}.myqcloud.com"
        )
        if (
            not valid_endpoint
            or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", config.bucket)
            or ".." in config.bucket
            or not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", config.prefix)
            or not re.fullmatch(r"[A-Za-z0-9_-]+", config.region)
            or (config.mode in {"manifest", "remote"} and not Path(config.manifest_path).is_absolute())
            or (
                config.provider == "tencent-cos"
                and (
                    config.addressing_style != "virtual"
                    or not cos_endpoint
                    or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,48}-[1-9][0-9]{4,}", config.bucket)
                    or not config.access_key
                    or not config.secret_key
                )
            )
        ):
            raise ValueError("Invalid course storage configuration")
        return config
