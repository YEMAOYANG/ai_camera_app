"""Loopback-only sample player, isolated from all real accounts and databases."""
import argparse
from contextlib import closing
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from services.textbook_sample_service import LESSON_HASH, SampleError, apply, new_state, report, view

WEB = ROOT / 'backend/content/textbooks/samples/tiandiren-v2'
COOKIE = 'tiandiren_sample_v2'
IDENTIFIER = re.compile(r'^[a-zA-Z0-9_-]{16,96}$')


class Store:
    def __init__(self, path):
        self.path = path
        with closing(self.connect()) as conn, conn:
            conn.executescript('''CREATE TABLE IF NOT EXISTS sample_sessions (id TEXT PRIMARY KEY,state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sample_requests (session TEXT, id TEXT, request TEXT NOT NULL, response TEXT NOT NULL,
                PRIMARY KEY(session,id));''')

    def connect(self):
        return sqlite3.connect(str(self.path), timeout=15)

    def session(self, sid, now):
        with closing(self.connect()) as conn, conn:
            row = conn.execute('SELECT state FROM sample_sessions WHERE id=?', (sid,)).fetchone() if sid else None
            if row:
                state = json.loads(row[0])
                if state['lessonHash'] == LESSON_HASH:
                    return sid, state, False
            sid, state = secrets.token_urlsafe(32), new_state(now)
            conn.execute('INSERT INTO sample_sessions VALUES (?,?)', (sid, json.dumps(state)))
            return sid, state, True

    def act(self, sid, request, now):
        if (not isinstance(request, dict) or set(request) - {'requestId', 'revision', 'action', 'choice'}
                or not isinstance(request.get('requestId'), str) or not IDENTIFIER.fullmatch(request['requestId'])
                or type(request.get('revision')) is not int):
            raise SampleError('请求格式无效。')
        canonical = json.dumps(request, sort_keys=True)
        with closing(self.connect()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            previous = conn.execute('SELECT request,response FROM sample_requests WHERE session=? AND id=?', (sid, request['requestId'])).fetchone()
            if previous:
                if previous[0] != canonical:
                    raise SampleError('同一次操作内容发生变化，请刷新。')
                return json.loads(previous[1])
            row = conn.execute('SELECT state FROM sample_sessions WHERE id=?', (sid,)).fetchone()
            if not row:
                raise SampleError('体验会话已结束，请刷新。')
            state = json.loads(row[0])
            if state['revision'] != request['revision']:
                raise SampleError('进度已变化，请恢复进度后继续。')
            state = apply(state, {k: request[k] for k in ('action', 'choice') if k in request}, now)
            response = view(state, now)
            conn.execute('UPDATE sample_sessions SET state=? WHERE id=?', (json.dumps(state), sid))
            conn.execute('INSERT INTO sample_requests VALUES (?,?,?,?)', (sid, request['requestId'], canonical, json.dumps(response)))
            return response


def make_server(bundle, port, state_file=None):
    manifest = json.loads((bundle / 'assets.json').read_text())
    if manifest['lessonHash'] != LESSON_HASH:
        raise ValueError('Lesson changed. Run prepare_textbook_sample.py first.')
    assets = {}
    for key, item in manifest['assets'].items():
        path = (bundle / item['file']).resolve()
        if not path.is_relative_to(bundle.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError(f'Invalid sample asset: {key}')
        assets[key] = (path.read_bytes(), item['mimeType'])
    store = Store(state_file or bundle / 'sample-progress.sqlite3')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # No cookie or learner choices in process logs.

        def send(self, status, body, mime='application/json; charset=utf-8', cookie=None):
            body = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'")
            if cookie:
                self.send_header('Set-Cookie', f'{COOKIE}={cookie}; Path=/; HttpOnly; SameSite=Strict; Max-Age=1209600')
            self.end_headers()
            self.wfile.write(body)

        def allowed(self, write=False):
            hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            host = self.headers.get('Host')
            if host not in hosts or (write and self.headers.get('Origin') != f'http://{host}'):
                self.send(403, {'error': '只接受本机样板页面的操作。'})
                return False
            return True

        def session(self):
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get('Cookie', ''))
                sid = cookies[COOKIE].value if COOKIE in cookies else None
            except Exception:
                sid = None
            return store.session(sid if sid and IDENTIFIER.fullmatch(sid) else None, time.time())

        def do_GET(self):
            if not self.allowed():
                return
            path = urlsplit(self.path).path
            static = {'/': ('index.html', 'text/html'), '/lesson.css': ('lesson.css', 'text/css'), '/lesson.js': ('lesson.js', 'text/javascript')}
            if path in static:
                file, mime = static[path]
                self.send(200, (WEB / file).read_bytes(), mime + '; charset=utf-8')
            elif path.startswith('/assets/') and path[len('/assets/'):] in assets:
                data, mime = assets[path[len('/assets/'):]]
                self.send(200, data, mime)
            elif path in ('/api/session', '/api/report'):
                sid, state, created = self.session()
                self.send(200, view(state, time.time()) if path == '/api/session' else report(state, time.time()), cookie=sid if created else None)
            else:
                self.send(404, {'error': '找不到这一页。'})

        def do_POST(self):
            if not self.allowed(write=True):
                return
            if urlsplit(self.path).path != '/api/action':
                self.send(404, {'error': '操作不存在。'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096 or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError()
                request = json.loads(self.rfile.read(length))
            except (ValueError, json.JSONDecodeError):
                self.send(400, {'error': '请求格式无效。'})
                return
            sid, _, created = self.session()
            try:
                result = store.act(sid, request, time.time())
                self.send(200, result, cookie=sid if created else None)
            except SampleError as error:
                self.send(409, {'error': str(error)}, cookie=sid if created else None)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'output/tiandiren-play-v2')
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args()
    server = make_server(args.bundle.resolve(), args.port)
    print(f'Tiandiren sample: http://127.0.0.1:{server.server_port} (isolated sample records only)', flush=True)
    server.serve_forever()
