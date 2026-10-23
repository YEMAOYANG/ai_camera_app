"""Private, loopback-only reader/dispatcher for the existing Pro workbench API."""
from __future__ import annotations

import hashlib
from http.cookiejar import DefaultCookiePolicy, MozillaCookieJar
import json
import os
from pathlib import Path
import re
import socket
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import (HTTPRedirectHandler, HTTPCookieProcessor, ProxyHandler,
                            Request, build_opener)


class WorkbenchError(Exception):
    def __init__(self, code, message, *, http_status=None):
        super().__init__(message)
        self.code, self.http_status = code, http_status


def local_origin(value):
    try:
        url = urlsplit(value)
        if (url.scheme not in ('http', 'https') or url.hostname not in ('127.0.0.1', 'localhost', '::1')
                or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment
                or not url.port):
            raise ValueError()
    except (ValueError, TypeError):
        raise WorkbenchError('local_origin_required', '工作台地址必须为含端口的本机 HTTP(S) origin') from None
    return value.rstrip('/')


def private_write(path, data):
    """Atomic replace, fsync, and private permissions for requests and receipts."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.authoring-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise WorkbenchError('redirect_refused', '本机工作台重定向已拒绝')


class OpenMaicWorkbenchClient:
    def __init__(self, origin, cookie_path, *, timeout=20):
        self.origin = local_origin(origin)
        self.cookie_path = Path(cookie_path)
        self.timeout = timeout
        self.scene_contract_schema = None
        # Production emits Secure even on its loopback HTTP listener. Browsers
        # trust localhost; this jar is likewise used ONLY at the validated origin.
        self.jar = MozillaCookieJar(policy=DefaultCookiePolicy(secure_protocols=('https', 'http')))
        if self.cookie_path.is_symlink():
            raise WorkbenchError('owner_cookie_invalid', '私有身份文件不能为符号链接')
        if self.cookie_path.exists():
            os.chmod(self.cookie_path, 0o600)
            try:
                self.jar.load(str(self.cookie_path), ignore_discard=True, ignore_expires=True)
            except (OSError, ValueError):
                raise WorkbenchError('owner_cookie_invalid', '私有身份文件不可读，保留原文件后核查') from None
        self.opener = build_opener(ProxyHandler({}), _NoRedirect(), HTTPCookieProcessor(self.jar))

    def owner_fingerprint(self):
        owners = [cookie.value for cookie in self.jar if cookie.name == 'anonymous_id'
                  and re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}', cookie.value)]
        if len(owners) != 1:
            raise WorkbenchError('owner_cookie_missing', '缺少原会话私有身份；不能新建身份后重派发')
        return hashlib.sha256(owners[0].encode()).hexdigest()

    def _save_owner(self):
        self.owner_fingerprint()
        fd, temporary = tempfile.mkstemp(prefix='.owner-', dir=self.cookie_path.parent)
        os.close(fd)
        try:
            self.jar.save(temporary, ignore_discard=True, ignore_expires=True)
            private_write(self.cookie_path, Path(temporary).read_bytes())
        finally:
            os.unlink(temporary)

    def _open(self, path, payload=None, *, raw=None, headers=None):
        before = self.owner_fingerprint() if self.cookie_path.exists() else None
        if (payload is not None or raw is not None) and before is None:
            raise WorkbenchError('owner_cookie_missing', '派发前须先 GET 并保存工作台身份')
        request = Request(self.origin + path,
                          data=raw if raw is not None else (
                              json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None),
                          headers={'Content-Type': 'application/json', 'Accept': 'application/json', **(headers or {})})
        try:
            response = self.opener.open(request, timeout=self.timeout)
            after = self.owner_fingerprint()
            if before and before != after:
                response.close()
                raise WorkbenchError('owner_changed', '工作台身份改变，已停止自动恢复')
            self._save_owner()
            return response
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise WorkbenchError('workbench_http_error', '本机工作台返回 HTTP 错误', http_status=status) from None
        except (URLError, TimeoutError, socket.timeout, OSError):
            raise WorkbenchError('workbench_unavailable', '本机工作台连接失败；保留已派发状态') from None

    def _json(self, path, payload=None):
        try:
            with self._open(path, payload) as response:
                raw = response.read(64 * 1024 * 1024 + 1)
                if path == '/api/agent/sessions' and payload is None:
                    self.scene_contract_schema = getattr(response, 'headers', {}).get(
                        'x-mira-textbook-scene-contract')
            if len(raw) > 64 * 1024 * 1024:
                raise ValueError()
            return json.loads(raw)
        except (ValueError, UnicodeError):
            raise WorkbenchError('workbench_invalid_response', '工作台响应不是可识别的 JSON') from None
        except (TimeoutError, OSError):
            raise WorkbenchError('workbench_unavailable', '工作台响应中断；保留已派发状态') from None

    def sessions(self):
        result = self._json('/api/agent/sessions')
        if not isinstance(result, list):
            raise WorkbenchError('workbench_invalid_response', '工作台会话列表格式无效')
        return result

    def create_session(self, payload):
        return self._json('/api/agent/sessions', payload)

    def upload_material(self, raw, filename, request_id, mime_type):
        """One raw-byte upload. Callers persist an intent before entering here."""
        if mime_type not in ('image/png', 'text/plain'):
            raise WorkbenchError('material_mime_invalid', '仅支持 PNG 和 UTF-8 纯文本附件')
        try:
            with self._open('/api/materials', raw=raw, headers={
                    'Content-Type': mime_type, 'Content-Length': str(len(raw)),
                    'x-material-filename': quote(filename, safe=''), 'x-request-id': request_id}) as response:
                status = response.status
                echoed = response.headers.get('x-request-id')
                body = response.read(1024 * 1024 + 1)
            if status != 201 or echoed != request_id or len(body) > 1024 * 1024:
                raise ValueError()
            return {'httpStatus': status, 'requestId': echoed, 'material': json.loads(body)}
        except (ValueError, UnicodeError):
            raise WorkbenchError('material_upload_response_unknown', '素材上传响应无法核验；禁止重复上传') from None
        except (TimeoutError, OSError):
            raise WorkbenchError('material_upload_response_unknown', '素材上传响应中断；禁止重复上传') from None

    def upload_png(self, raw, filename, request_id):
        return self.upload_material(raw, filename, request_id, 'image/png')

    def session_materials(self, session_id):
        result = self._json('/api/materials?sessionId=' + quote(session_id, safe='') + '&limit=200')
        if not isinstance(result, dict) or not isinstance(result.get('materials'), list):
            raise WorkbenchError('workbench_invalid_response', '会话素材列表格式无效')
        return result['materials']

    def session(self, session_id):
        return self._json('/api/agent/sessions/' + quote(session_id, safe=''))

    def stage(self, stage_id):
        return self._json('/api/stages/' + quote(stage_id, safe=''))

    def stage_events(self, session_id):
        """Read finite durable SSE backlog; never follow the live tail."""
        events, frame, consumed = [], [], 0
        try:
            with self._open('/api/agent/sessions/' + quote(session_id, safe='') + '/events') as response:
                while True:
                    line = response.readline(4 * 1024 * 1024 + 1)
                    consumed += len(line)
                    if consumed > 64 * 1024 * 1024 or len(line) > 4 * 1024 * 1024 or not line:
                        raise ValueError()
                    if line.strip():
                        frame.append(line.decode('utf-8').rstrip('\r\n'))
                        continue
                    data = '\n'.join(item[5:].lstrip() for item in frame if item.startswith('data:'))
                    name = next((item[6:].strip() for item in frame if item.startswith('event:')), '')
                    frame = []
                    if not data:
                        continue
                    value = json.loads(data)
                    if name == 'caught_up':
                        if value.get('degraded'):
                            raise WorkbenchError('events_incomplete', '会话事件回放尚未完整，请稍后只读重试')
                        return events
                    if name in ('stage_link', 'course_link', 'library_changed', 'user_message'):
                        events.append(value)
        except (ValueError, UnicodeError):
            raise WorkbenchError('events_incomplete', '会话事件回放不完整，请稍后只读重试') from None
        except (TimeoutError, OSError):
            raise WorkbenchError('events_incomplete', '会话事件读取中断，请稍后只读重试') from None
