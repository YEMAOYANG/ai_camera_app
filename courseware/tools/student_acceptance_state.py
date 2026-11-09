"""Keep the authorized local grade-one browser fixture ready for course acceptance."""

import fcntl
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / ".local_backups/student-learning-demo-v1"
ORIGIN = "http://localhost:3000"
ACCESS = "mira_student_access"
COOKIE_NAMES = {ACCESS, "mira_student_refresh", "mira_student_device", "mira_student_browser_fingerprint"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def local_request(path, method, cookie, body=None):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    data = None if body is None else json.dumps(body).encode()
    request = Request(ORIGIN + path, method=method, data=data,
                      headers={"Cookie": cookie, "Content-Type": "application/json"})
    try:
        with opener.open(request, timeout=10) as response:
            return response.status, response.headers, json.loads(response.read(100_000))
    except HTTPError as error:
        with error:
            return error.code, error.headers, None


def private_bytes(path):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as handle:
        if os.fstat(handle.fileno()).st_mode & 0o077:
            raise ValueError("Acceptance fixture must be private")
        return handle.read(100_000)


def cookie_header(cookies, now):
    return "; ".join(f"{name}={cookie['value']}" for name, cookie in cookies.items()
                     if cookie['value'] and (cookie['expires'] < 0 or cookie['expires'] > now))


def apply_cookies(cookies, headers, now):
    for value in headers.get_all("Set-Cookie", []):
        parsed = SimpleCookie()
        parsed.load(value)
        for name, entry in parsed.items():
            if name not in cookies or entry["path"] != "/" or entry["domain"] not in ("", "localhost"):
                raise ValueError("Unexpected acceptance cookie scope")
            cookies[name] = {**cookies[name], "value": entry.value, "expires": int(now) + int(entry["max-age"]),
                             "httpOnly": bool(entry["httponly"]), "secure": bool(entry["secure"]),
                             "sameSite": entry["samesite"].capitalize()}


def ensure_state(directory=FIXTURE, *, request=local_request, clock=time.time):
    if directory.is_symlink():
        raise ValueError("Linked acceptance fixture directory")
    path = directory / "courseware-acceptance.storage.json"
    lock = directory / "courseware-acceptance.refresh.lock"
    with os.fdopen(os.open(lock, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600), "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        original = private_bytes(path)
        state = json.loads(original)
        demo = json.loads(private_bytes(directory / "pictures.json"))
        cookies = {row["name"]: row for row in state["cookies"]}
        if set(cookies) != COOKIE_NAMES or any(row["domain"] != "localhost" or row["path"] != "/" for row in cookies.values()):
            raise ValueError("Acceptance fixture scope mismatch")
        now = clock()
        status, headers, identity = (401, None, None)
        if cookies[ACCESS]["expires"] > now + 120:
            status, headers, identity = request("/api/auth/me", "GET", cookie_header(cookies, now))
        unlocked = status in (401, 403)
        if unlocked:
            pin = demo["pin"]
            if not isinstance(pin, str) or len(pin) != 4 or not pin.isascii() or not pin.isdecimal():
                raise ValueError("Invalid acceptance fixture PIN")
            status, headers, _ = request("/api/auth/unlock", "POST", cookie_header(cookies, now), {"pin": pin})
            if status != 200:
                raise RuntimeError(f"Local test unlock returned HTTP {status}")
            apply_cookies(cookies, headers, clock())
            status, headers, identity = request("/api/auth/me", "GET", cookie_header(cookies, clock()))
        if status != 200:
            raise RuntimeError(f"Local test identity returned HTTP {status}")
        student = identity["student"]
        if student["childId"] != demo["childId"] or student["gradeCode"] != "primary_1":
            raise ValueError("Local test student identity mismatch")
        apply_cookies(cookies, headers, clock())
        updated = list(cookies.values())
        if updated != state["cookies"]:
            state["cookies"] = updated
            with tempfile.NamedTemporaryFile(mode="w", dir=directory, prefix=".acceptance-", delete=False) as temporary:
                name = Path(temporary.name)
                try:
                    json.dump(state, temporary)
                    temporary.write("\n")
                    temporary.flush()
                    if private_bytes(path) != original:
                        raise RuntimeError("Acceptance fixture changed concurrently")
                    os.replace(name, path)
                finally:
                    name.unlink(missing_ok=True)
        return {"ok": True, "mode": "unlocked" if unlocked else "existing",
                "accessExpiresAt": cookies[ACCESS]["expires"]}


if __name__ == "__main__":
    try:
        print(json.dumps(ensure_state()))
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        raise SystemExit("Local grade-one acceptance state could not be prepared") from None
