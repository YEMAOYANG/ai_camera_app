"""Fail closed when a new textbook release cannot show its own catalog picture.

The cover is navigation, not a change to the frozen lesson or its assessment.
An operator registers a derivative of a reviewed release image, rebuilds the
student site, and only then publishes the course. Historical publications are
handled separately by the callers and retain their original identities.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from PIL import Image, ImageChops, ImageOps, ImageStat

from core.errors import ApiError
from services.course_media_object_store import CourseMediaStorageError

ROOT = Path(__file__).resolve().parents[2]
SIZE = (960, 540)
PUBLIC_PREFIX = '/textbooks/course-pictures-v1/'
KEY = re.compile(r'[a-f0-9]{64}\Z')
MEDIA_PATH = re.compile(r'/api/classroom-media/([A-Za-z0-9_-]+)/media/([A-Za-z0-9_.-]+)\Z')
CHUNK = re.compile(rb'/_next/static/chunks/[A-Za-z0-9_./-]+\.js')


def cover_bytes(raw: bytes) -> bytes:
    """Use the established centre-crop cover recipe on the verified picture."""
    with Image.open(io.BytesIO(raw)) as image:
        image = image.convert('RGB')
        width, height = image.size
        if not 0 < width * height <= 40_000_000:
            raise ValueError('invalid cover source dimensions')
        crop = min(width, height * SIZE[0] // SIZE[1]), min(height, width * SIZE[1] // SIZE[0])
        if min(crop) < 1:
            raise ValueError('invalid cover source dimensions')
        left, top = (width - crop[0]) // 2, (height - crop[1]) // 2
        output = io.BytesIO()
        image.crop((left, top, left + crop[0], top + crop[1])).resize(SIZE, Image.Resampling.LANCZOS).save(
            output, 'WEBP', quality=86, method=6)
        return output.getvalue()


def _deny(message: str) -> None:
    raise ApiError('textbook_cover_unavailable', message, 409)


def _fingerprint(raw: bytes) -> Image.Image:
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        return ImageOps.fit(image.convert('RGB'), (64, 36), method=Image.Resampling.LANCZOS)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _compiled_cover_matches(raw: bytes, content_key: str, src: str) -> bool:
    """Check the mapping itself, not two unrelated strings in the bundle."""
    needle = json.dumps(content_key).encode('ascii') + b':'
    decoder = json.JSONDecoder()
    start = 0
    while (position := raw.find(needle, start)) >= 0:
        start = position + len(needle)
        try:
            value, _ = decoder.raw_decode(raw[start:].decode('utf-8').lstrip())
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and value.get('src') == src:
            return True
    return False


def _live_cover(student_root: Path, content_key: str, src: str, checksum: str, *, origin: str | None = None) -> None:
    """Verify the served catalog actually references the current compiled map."""
    if origin is None:
        port = os.environ.get('MIRA_LOCAL_TEST_STUDENT_WEB_PORT', '3000')
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            _deny('学生端封面校验地址无效')
        origin = 'http://127.0.0.1:' + port
    parsed = urlsplit(origin)
    if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}
            or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment
            or parsed.port is None):
        _deny('学生端封面校验仅支持本机地址')
    opener = build_opener(ProxyHandler({}), _NoRedirect())

    def get(path: str, limit: int) -> bytes:
        try:
            with opener.open(Request(origin.rstrip('/') + path, headers={'Cache-Control': 'no-store'}), timeout=8) as response:
                raw = response.read(limit + 1)
                if response.status != 200 or len(raw) > limit:
                    raise ValueError('invalid student response')
                return raw
        except (OSError, HTTPError, URLError, ValueError):
            _deny('学生端封面尚未部署或无法读取，请先更新学生端')

    html = get('/learning/textbooks', 2 * 1024 * 1024)
    candidates = list(dict.fromkeys(match.decode('ascii') for match in CHUNK.findall(html)))
    found = False
    for url in candidates:
        relative = Path(url.removeprefix('/_next/'))
        if '..' in relative.parts:
            continue
        path = student_root / '.next' / relative
        try:
            if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
                continue
            local = path.read_bytes()
        except OSError:
            continue
        if not _compiled_cover_matches(local, content_key, src):
            continue
        remote = get(url, 16 * 1024 * 1024)
        if remote == local:
            found = True
            break
    if not found:
        _deny('学生端当前版本尚未包含这节课的封面，请先重建并更新学生端')
    if hashlib.sha256(get(src, 4 * 1024 * 1024)).hexdigest() != checksum:
        _deny('学生端实际显示的封面与审核文件不一致')


def verify_textbook_cover(prepared: dict, *, media_root: Path, media_store,
                          student_root: Path = ROOT / 'student-web', origin: str | None = None) -> None:
    """Verify the course-bound picture, distinctness and live Student Web.

    This does not assess whether a picture communicates the lesson goal; the
    existing visual review and real student acceptance remain necessary.
    """
    try:
        frozen, release = prepared['frozen'], prepared['release']
        key, release_sha = frozen['contentKey'], release['sha256']
        if not KEY.fullmatch(key) or not KEY.fullmatch(release_sha) or release['contentKey'] != key:
            _deny('封面与课件发布身份不一致')
        listing = student_root / 'src/features/learning/lesson-pictures.json'
        listing_raw = listing.read_bytes()
        pictures = json.loads(listing_raw)
        item = pictures.get(key)
        if not isinstance(item, dict):
            _deny('这节课尚未登记专属封面，不能发布')
        src, checksum, source_sha, source_path = (item.get(k) for k in ('src', 'coverSha256', 'sourceSha256', 'sourceMediaPath'))
        if (not isinstance(src, str) or not isinstance(checksum, str) or not KEY.fullmatch(checksum)
                or not isinstance(source_sha, str) or not KEY.fullmatch(source_sha)
                or item.get('releaseSha256') != release_sha or item.get('width') != SIZE[0] or item.get('height') != SIZE[1]
                or not isinstance(item.get('alt'), str) or not 0 < len(item['alt'].strip()) <= 160
                or src != PUBLIC_PREFIX + key[:16] + '-' + checksum[:16] + '.webp'):
            _deny('课次封面的身份、图片或说明不完整')
        match = MEDIA_PATH.fullmatch(source_path) if isinstance(source_path, str) else None
        matches = [m for m in release['media'] if m.get('path') == source_path and m.get('sha256') == source_sha
                   and str(m.get('mimeType', '')).startswith('image/')]
        if (not match or match.group(1) != release['classroomId'] or len(matches) != 1
                or source_path not in json.dumps(release['classroom'], ensure_ascii=False)):
            _deny('封面来源不是本课已审核的课堂图片')
        asset = matches[0]
        root = Path(media_root).resolve()
        source = (root / match.group(1) / 'media' / match.group(2)).resolve()
        if not source.is_relative_to(root):
            _deny('封面来源位置无效')
        raw = media_store.read(source, expected_sha256=source_sha, expected_bytes=asset['byteSize'], max_bytes=32 * 1024 * 1024)
        if raw is None:
            raw = source.read_bytes()
        if len(raw) != asset['byteSize'] or hashlib.sha256(raw).hexdigest() != source_sha:
            _deny('课内原图已变化，无法核验封面')
        cover_path = student_root / 'public' / src.lstrip('/')
        cover = cover_path.read_bytes()
        if hashlib.sha256(cover).hexdigest() != checksum or cover_bytes(raw) != cover:
            _deny('封面文件与课内原图或登记摘要不一致')
        with Image.open(io.BytesIO(cover)) as picture:
            if picture.format != 'WEBP' or picture.size != SIZE:
                _deny('封面图片格式或尺寸不正确')
        fingerprint = _fingerprint(cover)
        for other_key, other in pictures.items():
            if other_key == key or not isinstance(other, dict):
                continue
            other_src = other.get('src')
            if not isinstance(other_src, str) or not other_src.startswith(PUBLIC_PREFIX):
                continue
            name = other_src[len(PUBLIC_PREFIX):]
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
                continue
            other_path = student_root / 'public' / PUBLIC_PREFIX.lstrip('/') / name
            if not other_path.is_file():
                continue  # An old missing file does not make this new image identical.
            difference = ImageStat.Stat(ImageChops.difference(fingerprint, _fingerprint(other_path.read_bytes())))
            if sum(difference.mean) / 3 <= 2:
                _deny('这节课的封面与已有课程重复，请选择可区分的课内画面')
        _live_cover(student_root, key, src, checksum, origin=origin)
        if listing.read_bytes() != listing_raw or hashlib.sha256(cover_path.read_bytes()).hexdigest() != checksum:
            _deny('封面在发布检查期间发生变化，请重试')
    except ApiError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, CourseMediaStorageError):
        _deny('课次封面无法核验，请先登记并更新学生端')
