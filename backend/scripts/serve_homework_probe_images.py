#!/usr/bin/env python3
"""Serve one or two frozen JPEGs on loopback for a bounded operator probe.

This foreground tool does not upload, tunnel, call a provider, or load app
configuration. Its private state contains bearer paths; stdout never does.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import os
from pathlib import Path
import secrets
import stat
import threading
import time

from PIL import Image

MAX_BYTES = 3_000_000
MAX_SIDE = 2048
MAX_TTL_SECONDS = 1800
HOST = "127.0.0.1"
SCHEMA = "mira.homework-image-probe.v1"


class ProbeError(ValueError):
    """Only fixed, non-sensitive error codes reach the terminal."""


@dataclass(frozen=True)
class ProbeImage:
    body: bytes = field(repr=False)
    sha256: str
    width: int
    height: int


def load_image(filename: str | Path) -> ProbeImage:
    source = Path(filename)
    if not source.is_absolute():
        raise ProbeError("absolute_image_required")
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_BYTES:
            raise ProbeError("image_size_or_type_invalid")
        body = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    if (len(body) != before.st_size or len(body) > MAX_BYTES
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
        raise ProbeError("image_changed_during_read")
    if not body.startswith(b"\xff\xd8") or not body.endswith(b"\xff\xd9"):
        raise ProbeError("jpeg_required")
    try:
        with Image.open(io.BytesIO(body)) as image:
            if image.format != "JPEG" or not 1 <= min(image.size) <= max(image.size) <= MAX_SIDE:
                raise ProbeError("jpeg_dimensions_invalid")
            # JPEG application markers can carry EXIF, XMP, comments or private
            # editor data. JFIF/Adobe color markers alone are harmless here.
            if (any(marker not in {"APP0", "APP14"} for marker, _ in image.applist)
                    or any(key in image.info for key in ("exif", "xmp", "comment", "icc_profile"))
                    or image.getexif()):
                raise ProbeError("jpeg_metadata_forbidden")
            width, height = image.size
            image.verify()
        with Image.open(io.BytesIO(body)) as image:
            image.load()
    except ProbeError:
        raise
    except Exception:
        raise ProbeError("jpeg_invalid") from None
    return ProbeImage(body, hashlib.sha256(body).hexdigest(), width, height)


def _private_file(path: Path, body: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.rfile.close()
        self.rfile = io.BufferedReader(_DeadlineReader(self.connection, self.server.probe))

    def log_message(self, *_args):
        pass

    def _respond(self, status: int, *, index: int | None = None):
        probe = self.server.probe
        headers = getattr(self, "headers", {})
        method = getattr(self, "command", "OTHER")
        probe.log_access(index, status, method, headers.get("User-Agent", ""))
        body = probe.images[index].body if status == 200 and index is not None else b""
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        if status == 200:
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("ETag", '"' + probe.images[index].sha256 + '"')
        if status == 405:
            self.send_header("Allow", "GET, HEAD")
        self.end_headers()
        if method != "HEAD" and body:
            self.wfile.write(body)
        self.close_connection = True

    def _read(self):
        probe = self.server.probe
        if probe.expired():
            self._respond(410)
        elif "?" in self.path or "#" in self.path:
            self._respond(400)
        elif self.path not in probe.paths:
            self._respond(404)
        else:
            self._respond(200, index=probe.paths.index(self.path))

    do_GET = _read
    do_HEAD = _read

    def _unsupported(self):
        self._respond(405)

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_CONNECT = _unsupported

    def send_error(self, code, message=None, explain=None):
        # Default error HTML can echo request data. Return a fixed empty body.
        self._respond(405 if code == 501 else code)


class _DeadlineReader(io.RawIOBase):
    """A client dripping headers cannot extend the absolute probe deadline."""

    def __init__(self, connection, probe):
        self.connection, self.probe = connection, probe

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self.probe.remaining()
        if remaining <= 0:
            raise TimeoutError()
        self.connection.settimeout(min(0.5, remaining))
        return self.connection.recv_into(buffer)


class _LoopbackServer(HTTPServer):
    allow_reuse_address = False

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(max(0.01, min(0.5, self.probe.remaining())))
        return connection, address

    def handle_error(self, _request, _client_address):
        # Never emit IPs, request paths or bearer tokens on error.
        pass


class ImageProbe:
    def __init__(self, images, output_dir, *, ttl_seconds=1800, port=0):
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= MAX_TTL_SECONDS:
            raise ProbeError("ttl_out_of_range")
        if type(port) is not int or not 0 <= port <= 65535:
            raise ProbeError("port_out_of_range")
        if not 1 <= len(images) <= 2:
            raise ProbeError("one_or_two_images_required")
        self.images = tuple(load_image(filename) for filename in images)
        self.folder = Path(output_dir)
        if not self.folder.is_absolute():
            raise ProbeError("absolute_output_directory_required")
        self.folder.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.folder.mkdir(mode=0o700)
        except FileExistsError:
            raise ProbeError("output_directory_already_exists") from None
        self.folder.chmod(0o700)
        self._stop = threading.Event()
        self._closed = False
        token = secrets.token_hex(32)
        self.paths = tuple(f"/homework-probe/{token}/{index}.jpg" for index in range(len(self.images)))
        self.server = _LoopbackServer((HOST, port), _Handler)
        self.server.probe = self
        self.server.timeout = 0.25
        self.started = time.monotonic()
        self.deadline = self.started + ttl_seconds
        self.state = {"schemaVersion": SCHEMA, "status": "serving", "pid": os.getpid(),
                      "localBaseUrl": f"http://{HOST}:{self.server.server_port}",
                      "expiresAt": (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat(),
                      "ttlSeconds": ttl_seconds,
                      "images": [{"index": index, "sha256": image.sha256,
                                  "width": image.width, "height": image.height,
                                  "byteSize": len(image.body), "path": self.paths[index]}
                                 for index, image in enumerate(self.images)]}
        try:
            _private_file(self.folder / "state.json", self._state_bytes())
            self._events = os.fdopen(os.open(self.folder / "access.jsonl",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "w")
        except Exception:
            self.server.server_close()
            raise

    def _state_bytes(self):
        return json.dumps(self.state, separators=(",", ":")).encode()

    def remaining(self):
        return max(0.0, self.deadline - time.monotonic())

    def expired(self):
        return time.monotonic() >= self.deadline

    def log_access(self, index, status, method, user_agent):
        # Retain bounded UA metadata, not its attacker-controlled contents.
        event = {"pageIndex": index, "status": status,
                 "method": method if method in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"} else "OTHER",
                 "elapsedSeconds": round(time.monotonic() - self.started, 3),
                 "userAgentLength": min(len(user_agent), 128)}
        self._events.write(json.dumps(event, separators=(",", ":")) + "\n")
        self._events.flush()
        os.fsync(self._events.fileno())

    def stop(self):
        self._stop.set()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.server.server_close()
        self._events.close()
        self.state["status"] = "expired" if self.expired() else "stopped"
        temporary = self.folder / (".state-" + secrets.token_hex(12))
        _private_file(temporary, self._state_bytes())
        os.replace(temporary, self.folder / "state.json")

    def serve(self):
        try:
            while not self._stop.is_set() and not self.expired():
                self.server.handle_request()
        finally:
            self.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", action="append", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--ttl-seconds", type=int, default=1800)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    probe = None
    try:
        probe = ImageProbe(args.image, args.output_dir, ttl_seconds=args.ttl_seconds, port=args.port)
        print(json.dumps({"status": "serving", "pid": os.getpid(), "imageCount": len(probe.images),
                          "ttlSeconds": args.ttl_seconds, "stateFile": str(probe.folder / "state.json")}), flush=True)
        probe.serve()
    except KeyboardInterrupt:
        if probe:
            probe.close()
    except Exception:
        print(json.dumps({"status": "local_preflight_or_server_failed"}), flush=True)
        return 2
    finally:
        if probe:
            probe.close()
    print(json.dumps({"status": probe.state["status"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
