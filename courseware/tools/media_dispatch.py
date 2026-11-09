"""Dispatch lesson media with durable receipts and no automatic paid retries.

Only calls made through this tool are covered by its ledger. Historical paid
requests must be reconciled by the operator before using a fresh work folder.
Keep the work folder and its .media-dispatch receipts together when recovering.
There is no force or reset option. A received 500 needs a separate exact,
one-use owner authorization; missing-response claims remain blocked.
"""
import argparse
import base64
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from threading import Lock
import time
import urllib.error
import urllib.request
import uuid

from courseware.tools import picture, voice


SOURCE_ROOT = Path(__file__).resolve().parents[1] / 'lessons'
SLOTS_DIR = SOURCE_ROOT.parents[1] / 'output' / 'courseware-production' / 'media-dispatch-slots'
DEFAULT_ENDPOINT = 'http://127.0.0.1:3100'
SCHEMA = 'mira.courseware.media-dispatch.v1'
MINIMUM_FREE_BYTES = 2 * 1024**3


class DispatchError(Exception):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise DispatchError('record_invalid', f'{path}: {exc}') from exc


def _atomic_record(path, value):
    """Publish a complete, fsynced immutable JSON record without overwriting."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(_json_bytes(value) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary:
            os.unlink(temporary)


@contextmanager
def work_lock(work, lesson):
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    # Keep the inode: unlinking a lock file could let two processes own it.
    with (work / '.media-dispatch.lock').open('a+b') as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise DispatchError('work_locked', str(work)) from exc
        try:
            owner_path = work / '.media-dispatch' / 'owner.json'
            if owner_path.exists():
                owner = _load(owner_path)
                if not isinstance(owner, dict) or owner.get('lesson') != lesson:
                    raise DispatchError('work_owner_mismatch', str(owner_path))
            else:
                _atomic_record(owner_path, {'schemaVersion': SCHEMA, 'lesson': lesson,
                                           'createdAt': _now()})
            yield work
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def default_health_get(url):
    request = urllib.request.Request(url, method='GET', headers={'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read()


def default_post(url, payload):
    # Preserve each existing helper's HTTP adapter and timeout.
    adapter = picture.default_post if url.endswith('/api/generate/image') else voice.default_post
    return adapter(url, payload)


def _raw_response(status, body):
    if isinstance(status, bool) or not isinstance(status, int) or not isinstance(body, bytes):
        raise ValueError('HTTP adapter must return an integer status and bytes body')
    return {'httpStatus': status, 'bodyBase64': base64.b64encode(body).decode('ascii'),
            'bodySha256': hashlib.sha256(body).hexdigest(), 'bodyBytes': len(body)}


def _require_disk_space(destination):
    try:
        existing = Path(destination).resolve()
        while not existing.exists() and existing != existing.parent:
            existing = existing.parent
        free = shutil.disk_usage(existing).free
    except OSError as exc:
        raise DispatchError('disk_space_check_failed', f'{destination}: {exc}') from exc
    if free < MINIMUM_FREE_BYTES:
        raise DispatchError('disk_space_insufficient',
                            f'{destination} has {free} bytes available, requires at least 2 GiB')


@contextmanager
def post_slot(url, directory=SLOTS_DIR, *, check=None):
    """Bound actual requests across processes; kernel locks die with the owner."""
    if url.endswith('/api/generate/image'):
        kind, count = 'images', 2
    elif url.endswith('/api/generate/tts'):
        kind, count = 'tts', 2
    else:
        raise DispatchError('endpoint_invalid', url)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stream = None
    try:
        while stream is None:
            if check is not None:
                check()
            for index in range(count):
                candidate = (directory / f'{kind}-{index}.lock').open('a+b')
                try:
                    fcntl.flock(candidate.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    candidate.close()
                else:
                    stream = candidate
                    break
            if stream is None:
                time.sleep(0.05)
        yield
    finally:
        if stream is not None:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            stream.close()


@contextmanager
def recovery_spacing(directory, *, check):
    """Serialize explicit recoveries, with a global second before admission.

    Hold the lock through the response. Every next holder waits a full second,
    even if its predecessor died, so no mutable timestamp or wall-clock change
    can bypass the interval. This is independent of normal TTS concurrency.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'tts-recovery-rate.lock').open('a+b') as stream:
        while True:
            check()
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(0.05)
        try:
            admitted_at = time.monotonic() + 1
            while time.monotonic() < admitted_at:
                check()
                time.sleep(max(0, min(0.05, admitted_at - time.monotonic())))
            check()
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _retryable_rate_limit(url, status, body):
    if status != 429 or not url.endswith('/api/generate/tts'):
        return False
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return False
    if (not isinstance(data, dict) or data.get('success') is not False
            or data.get('errorCode') != 'RATE_LIMITED'):
        return False
    def has_result(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == 'success' and item is True:
                    return True
                if (key.lower() in {'data', 'result', 'base64', 'audio', 'audiourl',
                                    'audio_url', 'url', 'wav', 'bytes'}
                        and item not in (None, '', False, {}, [])):
                    return True
                if has_result(item):
                    return True
        elif isinstance(value, list):
            return any(has_result(item) for item in value)
        return False
    return not has_result(data)


def _successful_tts(status, body):
    if status != 200:
        return False
    try:
        voice._validate_wav(voice._wav_bytes(body))
        return True
    except Exception:
        return False


def _settled_image_rejection(url, status, body):
    """Recognize the image route's exact envelope for an upstream rejection."""
    if status != 500 or not url.endswith('/api/generate/image'):
        return False
    prefix = 'Qwen Image generation failed (400): '
    try:
        response = json.loads(body)
        if (not isinstance(response, dict) or set(response) != {'success', 'errorCode', 'error'}
                or response['success'] is not False or response['errorCode'] != 'INTERNAL_ERROR'
                or not isinstance(response['error'], str) or not response['error'].startswith(prefix)):
            return False
        upstream = json.loads(response['error'][len(prefix):])
    except ValueError:
        return False
    if not isinstance(upstream, dict) or set(upstream) != {'request_id', 'code', 'message'}:
        return False
    request_id = upstream['request_id']
    return (isinstance(request_id, str)
            and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', request_id) is not None
            and upstream['code'] == 'DataInspectionFailed'
            and upstream['message'] in ('Green net check rejected text (input)',
                                        'Green net check rejected image (output)'))


def _validate_authorization(authorization, *, lesson, work, digest, response_path):
    if (not isinstance(authorization, dict)
            or authorization.get('schemaVersion') != 'mira.courseware.media-retry-authorization.v1'
            or authorization.get('lesson') != lesson
            or not isinstance(authorization.get('work'), str)
            or not Path(authorization['work']).is_absolute()
            or Path(authorization['work']).resolve() != Path(work).resolve()
            or authorization.get('payloadSha256') != digest
            or type(authorization.get('maxResends')) is not int
            or authorization['maxResends'] != 1
            or authorization.get('acceptedPossibleDuplicateCharge') is not True
            or any(not isinstance(authorization.get(key), str) or not authorization[key].strip()
                   for key in ['question', 'userAnswer', 'recordedAt'])
            or authorization.get('previousResponseSha256') != hashlib.sha256(
                Path(response_path).read_bytes()).hexdigest()):
        raise DispatchError('authorization_mismatch', str(response_path))
    try:
        recorded_at = datetime.fromisoformat(authorization['recordedAt'].replace('Z', '+00:00'))
        if recorded_at.tzinfo is None:
            raise ValueError('timezone required')
    except ValueError as exc:
        raise DispatchError('authorization_invalid', 'recordedAt must include a timezone') from exc


class RecordedPost:
    """Each attempt posts once; known 429 recovery needs an explicit new run."""

    def __init__(self, work, *, post, health_get=default_health_get, slots_dir=SLOTS_DIR,
                 retry_rate_limited=False, picture_assets=None):
        self.work = Path(work).resolve()
        self.directory = self.work / '.media-dispatch'
        self.requests = self.directory / 'requests'
        self.post = post
        self.health_get = health_get
        self.slots_dir = slots_dir
        self.retry_rate_limited = retry_rate_limited
        self.picture_assets = picture_assets
        self._mutex = Lock()
        self._locks = {}
        self._preflight_failures = {}
        self._posted_this_run = set()
        self._unresolved = set()
        owner_path = self.directory / 'owner.json'
        self.lesson = _load(owner_path).get('lesson') if owner_path.exists() else None
        for base in self.requests.iterdir() if self.requests.exists() else []:
            if not base.is_dir():
                raise DispatchError('record_invalid', str(base))
            claim = _load(base / 'claim.json')
            latest, _ = self._latest_attempt(base, claim['url'], claim['payload'], base.name)
            response_path = latest / 'response.json'
            if not response_path.exists():
                self._unresolved.add(str(latest / 'claim.json'))
                continue
            response = _load(response_path)
            latest_claim = _load(latest / 'claim.json')
            if not isinstance(response, dict):
                self._unresolved.add(str(latest / 'claim.json'))
            elif response.get('httpStatus') == 500:
                status, body = self._read_attempt(latest, claim['url'], claim['payload'], base.name)
                if not _settled_image_rejection(claim['url'], status, body):
                    self._unresolved.add(str(latest / 'claim.json'))
            elif latest_claim.get('retryReason') == 'explicit_owner_authorization':
                status, body = self._read_attempt(latest, claim['url'], claim['payload'], base.name)
                if not _successful_tts(status, body):
                    self._unresolved.add(str(latest / 'claim.json'))

    def _latest_attempt(self, directory, url, payload, digest):
        attempts = directory / 'attempts'
        latest, number = directory, 1
        for child in sorted(attempts.iterdir()) if attempts.exists() else []:
            if not child.is_dir() or child.name != f'{number + 1:04d}':
                raise DispatchError('attempt_chain_invalid', str(child))
            status, body = self._read_attempt(latest, url, payload, digest)
            child_claim = _load(child / 'claim.json')
            if (child_claim.get('previousAttempt') != str(latest.relative_to(directory))
                    or child_claim.get('previousResponseSha256') != hashlib.sha256(
                        (latest / 'response.json').read_bytes()).hexdigest()):
                raise DispatchError('attempt_chain_invalid', str(child))
            if child_claim.get('retryReason') == 'explicit_owner_authorization':
                try:
                    raw = base64.b64decode(child_claim['authorizationRawBase64'], validate=True)
                    frozen = json.loads(raw)
                    if (hashlib.sha256(raw).hexdigest() != child_claim['authorizationSha256']
                            or frozen != child_claim['authorization'] or status != 500
                            or child_claim.get('previousClaimSha256') != hashlib.sha256(
                                (latest / 'claim.json').read_bytes()).hexdigest()
                            or not url.endswith('/api/generate/tts')):
                        raise ValueError('invalid frozen authorization')
                    _validate_authorization(frozen, lesson=self.lesson or frozen.get('lesson'),
                                            work=self.work, digest=digest,
                                            response_path=latest / 'response.json')
                except (KeyError, ValueError, TypeError) as exc:
                    raise DispatchError('authorization_invalid', str(child)) from exc
            elif not _retryable_rate_limit(url, status, body):
                raise DispatchError('attempt_chain_invalid', str(child))
            latest, number = child, number + 1
        return latest, number

    def _mark_unresolved(self, claim_path):
        with self._mutex:
            self._unresolved.add(str(claim_path))

    def _check_unresolved(self, allowed=()):
        with self._mutex:
            blocked = self._unresolved - set(allowed)
            if blocked:
                raise DispatchError('unreconciled_claim', '; '.join(sorted(blocked)))

    def _record_unknown(self, directory, url, digest, exc):
        # Latch BEFORE releasing the slot or writing diagnostics. Other waiting
        # threads must stop even if diagnostic I/O is slow or fails.
        self._mark_unresolved(directory / 'claim.json')
        _atomic_record(directory / 'error.json', {
            'schemaVersion': SCHEMA, 'url': url, 'payloadSha256': digest,
            'recordedAt': _now(), 'errorType': type(exc).__name__, 'reason': str(exc),
            'outcome': 'unknown_no_response', 'retryAllowed': False})

    def _health(self, url, digest):
        health_url = url.rsplit('/api/', 1)[0] + '/api/health'
        receipt = {'schemaVersion': SCHEMA, 'url': health_url, 'checkedAt': _now(),
                   'payloadSha256': digest}
        try:
            try:
                status, body = self.health_get(health_url)
            except urllib.error.HTTPError as exc:
                status, body = exc.code, exc.read()
            receipt.update(_raw_response(status, body))
            data = json.loads(body)
            if (status != 200 or not isinstance(data, dict)
                    or data.get('success') is not True or data.get('status') != 'ok'):
                raise ValueError('health requires HTTP 200, success=true and status=ok')
            receipt['ok'] = True
        except Exception as exc:
            receipt.update(ok=False, errorType=type(exc).__name__, reason=str(exc))
        path = self.directory / 'preflights' / (digest + '-' + uuid.uuid4().hex + '.json')
        _atomic_record(path, receipt)
        if not receipt['ok']:
            raise DispatchError('health_failed', str(path))
        return {'receipt': str(path.relative_to(self.directory)), 'checkedAt': receipt['checkedAt'],
                'bodySha256': receipt['bodySha256']}

    def _read_attempt(self, directory, url, payload, digest):
        claim = _load(directory / 'claim.json')
        if (not isinstance(claim, dict) or claim.get('url') != url
                or claim.get('payloadSha256') != digest or claim.get('payload') != payload):
            raise DispatchError('claim_mismatch', str(directory))
        if hashlib.sha256(_json_bytes(payload)).hexdigest() != digest:
            raise DispatchError('claim_mismatch', str(directory))
        response_path = directory / 'response.json'
        if not response_path.exists():
            raise DispatchError('unreconciled_claim', str(directory))
        response = _load(response_path)
        try:
            if response['payloadSha256'] != digest or response['url'] != url:
                raise ValueError('response identity mismatch')
            body = base64.b64decode(response['bodyBase64'], validate=True)
            expected = _raw_response(response['httpStatus'], body)
            if any(response.get(key) != value for key, value in expected.items()):
                raise ValueError('response checksum mismatch')
            return response['httpStatus'], body
        except (KeyError, ValueError, TypeError) as exc:
            raise DispatchError('response_invalid', str(response_path)) from exc

    def _replay(self, directory, url, payload, digest):
        try:
            status, body = self._read_attempt(directory, url, payload, digest)
        except DispatchError as exc:
            if exc.args[0] == 'unreconciled_claim':
                self._mark_unresolved(directory / 'claim.json')
            raise
        claim = _load(directory / 'claim.json')
        if status == 500 and not _settled_image_rejection(url, status, body):
            self._mark_unresolved(directory / 'claim.json')
            raise DispatchError('unknown_upstream_outcome', str(directory / 'response.json'))
        if (claim.get('retryReason') == 'explicit_owner_authorization'
                and not _successful_tts(status, body)):
            self._mark_unresolved(directory / 'claim.json')
            raise DispatchError('authorized_retry_failed', str(directory / 'response.json'))
        return status, body

    def __call__(self, url, payload):
        digest = hashlib.sha256(_json_bytes(payload)).hexdigest()
        with self._mutex:
            lock = self._locks.setdefault(digest, Lock())
        with lock:
            base_directory = directory = self.requests / digest
            claim_path = directory / 'claim.json'
            retry = False
            previous = None
            if claim_path.exists():
                latest, number = self._latest_attempt(directory, url, payload, digest)
                status, body = self._replay(latest, url, payload, digest)
                if (not self.retry_rate_limited or digest in self._posted_this_run
                        or not _retryable_rate_limit(url, status, body)):
                    return status, body
                if number >= 9999:
                    raise DispatchError('attempt_limit', str(directory))
                previous = {'previousAttempt': str(latest.relative_to(base_directory)),
                            'previousResponseSha256': hashlib.sha256(
                                (latest / 'response.json').read_bytes()).hexdigest()}
                directory = base_directory / 'attempts' / f'{number + 1:04d}'
                claim_path = directory / 'claim.json'
                retry = True
            if directory.exists() and any(directory.iterdir()):
                raise DispatchError('orphaned_receipt', str(directory))
            return self._send_attempt(directory, url, payload, digest, retry=retry, previous=previous)

    def _send_attempt(self, directory, url, payload, digest, *, retry=False,
                      previous=None, authorization=None, allowed_unknown=(), before_claim=None,
                      continuation=None, tolerated_unknown=()):
        # allowed_unknown: the claims this attempt resolves when it succeeds.
        # tolerated_unknown: other owner-authorized claims that may stay open while it is sent.
        claim_path = directory / 'claim.json'
        media_directory = self.work / 'media'
        if self.picture_assets is not None and url.endswith('/api/generate/image'):
            media_directory = self.picture_assets

        def check_disk():
            _require_disk_space(directory)
            _require_disk_space(media_directory)

        check = lambda: self._check_unresolved(set(allowed_unknown) | set(tolerated_unknown))
        check()
        check_disk()
        if digest in self._preflight_failures:
            raise DispatchError('health_failed', self._preflight_failures[digest])
        try:
            health = self._health(url, digest)
        except DispatchError as exc:
            self._preflight_failures[digest] = str(exc)
            raise
        # Neither the cooldown queue nor the global slot queue owns a claim.
        spacing = recovery_spacing(self.slots_dir, check=check) if retry else nullcontext()
        with spacing, post_slot(url, self.slots_dir, check=check):
            with self._mutex:
                blocked = self._unresolved - set(allowed_unknown) - set(tolerated_unknown)
                if blocked:
                    raise DispatchError('unreconciled_claim', '; '.join(sorted(blocked)))
                if before_claim is not None:
                    before_claim()
                check_disk()
                try:
                    _atomic_record(claim_path, {
                        'schemaVersion': SCHEMA, 'url': url, 'payload': payload,
                        'payloadSha256': digest, 'claimedAt': _now(), 'health': health,
                        **({'retryReason': 'verified_rate_limited', **previous} if retry else {}),
                        **({'firstTimeContinuation': continuation} if continuation else {}),
                        **(authorization or {})})
                    self._posted_this_run.add(digest)
                except BaseException:
                    # Publication may have succeeded before fsync failed.
                    if claim_path.exists():
                        self._unresolved.add(str(claim_path))
                    raise
            http_reason = None
            try:
                try:
                    status, body = self.post(url, payload)
                except urllib.error.HTTPError as exc:
                    status, body = exc.code, exc.read()
                    http_reason = str(exc.reason)
                rejected = _settled_image_rejection(url, status, body)
                response = {'schemaVersion': SCHEMA, 'url': url, 'payloadSha256': digest,
                            'receivedAt': _now(), **_raw_response(status, body),
                            'outcome': ('settled_rejected' if rejected else
                                        'unknown_upstream_outcome' if status == 500 else
                                        'http_success' if status == 200 else 'http_error')}
                if status != 200:
                    response['reason'] = http_reason or f'HTTP {status}'
                if status == 500 and not rejected:
                    self._mark_unresolved(claim_path)
                elif authorization and not _successful_tts(status, body):
                    response['outcome'] = 'authorized_retry_failed'
                    self._mark_unresolved(claim_path)
            except BaseException as exc:
                self._record_unknown(directory, url, digest, exc)
                if not isinstance(exc, Exception):
                    raise
                raise DispatchError('unreconciled_claim', str(directory)) from exc
        try:
            _atomic_record(directory / 'response.json', response)
        except BaseException as exc:
            self._record_unknown(directory, url, digest, exc)
            raise
        if status == 500 and not rejected:
            raise DispatchError('unknown_upstream_outcome', str(directory / 'response.json'))
        if authorization:
            if not _successful_tts(status, body):
                raise DispatchError('authorized_retry_failed', str(directory / 'response.json'))
            with self._mutex:
                self._unresolved.difference_update(allowed_unknown)
        return status, body

    def _open_authorized_claim(self, authorization_path):
        """Validate a one-use owner authorization against its still-open TTS 500 in this work."""
        path = Path(authorization_path).resolve()
        raw = path.read_bytes()
        authorization = json.loads(raw)
        digest = authorization.get('payloadSha256') if isinstance(authorization, dict) else None
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise DispatchError('authorization_invalid', str(path))
        base = self.requests / digest
        original = _load(base / 'claim.json')
        url, payload = original['url'], original['payload']
        if not url.endswith('/api/generate/tts') or self.lesson is None:
            raise DispatchError('authorization_invalid', str(path))
        latest, number = self._latest_attempt(base, url, payload, digest)
        status, _ = self._read_attempt(latest, url, payload, digest)
        if status != 500 or number >= 9999:
            raise DispatchError('authorization_consumed_or_inapplicable', str(path))
        _validate_authorization(authorization, lesson=self.lesson, work=self.work,
                                digest=digest, response_path=latest / 'response.json')
        # A copied or edited authorization cannot consume the same prior response again.
        for consumed in base.glob('attempts/*/claim.json'):
            claim = _load(consumed)
            if (claim.get('retryReason') == 'explicit_owner_authorization'
                    and claim.get('previousResponseSha256') == authorization['previousResponseSha256']):
                raise DispatchError('authorization_consumed', str(consumed))
        return path, raw, authorization, digest, base, url, payload, latest, number

    def retry_authorized(self, authorization_path, companions=()):
        """Resend one authorized TTS 500.

        Each companion names another still-open TTS 500 of this work that has its own valid
        one-use owner authorization: it may stay open while this one is sent, and is not sent.
        Any other open claim still blocks the resend.
        """
        path, raw, authorization, digest, base, url, payload, latest, number = (
            self._open_authorized_claim(authorization_path))
        tolerated = set()
        for companion in companions:
            opened = self._open_authorized_claim(companion)
            companion_path, companion_digest, companion_latest = opened[0], opened[3], opened[7]
            if companion_digest == digest:
                raise DispatchError('authorization_duplicate', str(companion_path))
            tolerated.add(str(companion_latest / 'claim.json'))
        allowed = {str(latest / 'claim.json')}
        self._check_unresolved(allowed | tolerated)
        previous = {'previousAttempt': str(latest.relative_to(base)),
                    'previousResponseSha256': authorization['previousResponseSha256'],
                    'previousClaimSha256': hashlib.sha256((latest / 'claim.json').read_bytes()).hexdigest()}
        def recheck():
            if path.read_bytes() != raw:
                raise DispatchError('authorization_changed', str(path))
            if hashlib.sha256((latest / 'claim.json').read_bytes()).hexdigest() != previous['previousClaimSha256']:
                raise DispatchError('claim_changed', str(latest))
            _validate_authorization(authorization, lesson=self.lesson, work=self.work,
                                    digest=digest, response_path=latest / 'response.json')
            self._read_attempt(latest, url, payload, digest)
        return url, payload, self._send_attempt(
            base / 'attempts' / f'{number + 1:04d}', url, payload, digest,
            retry=True, previous=previous,
            allowed_unknown=allowed, tolerated_unknown=tolerated, before_claim=recheck,
            authorization={'retryReason': 'explicit_owner_authorization',
                           'authorization': authorization,
                           'authorizationRawBase64': base64.b64encode(raw).decode('ascii'),
                           'authorizationSha256': hashlib.sha256(raw).hexdigest()})


def run_authorized_retry(lesson, work, authorization_path, *, companions=(), post=None,
                         health_get=default_health_get, slots_dir=SLOTS_DIR):
    """Send only one frozen TTS payload; never load the current lesson lines.

    companions: other owner authorizations of this work whose open TTS 500 may stay open
    while this one is sent; they are validated but not sent.
    """
    for path in (authorization_path, *companions):
        authorization = _load(path)
        if (not isinstance(authorization, dict) or authorization.get('lesson') != lesson
                or not isinstance(authorization.get('work'), str)
                or Path(authorization['work']).resolve() != Path(work).resolve()):
            raise DispatchError('authorization_mismatch', str(path))
    with work_lock(work, lesson) as work:
        recorded = RecordedPost(work, post=post or default_post, health_get=health_get,
                                slots_dir=slots_dir)
        url, payload, response = recorded.retry_authorized(authorization_path, companions=companions)
        def replay_only(request_url, request_payload):
            if request_url != url or request_payload != payload:
                raise DispatchError('authorized_payload_changed', str(authorization_path))
            return response
        line = {'id': payload['audioId'], 'text': payload['text'], 'voice': payload['ttsVoice']}
        clips = voice.voice_lines([line], work / 'media', post=replay_only,
                                   cache_path=work / 'voice-cache.json', jobs=1, sleep=lambda _: None,
                                   endpoint=url.rsplit('/api/', 1)[0])
        return {'voice': clips}


def run_dispatch(lesson, work, *, steps=('pictures', 'voice'), jobs=2,
                 source_root=SOURCE_ROOT, endpoint=DEFAULT_ENDPOINT, post=None,
                 fetch=None, health_get=default_health_get, slots_dir=SLOTS_DIR,
                 retry_rate_limited=False):
    if (not isinstance(lesson, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', lesson)
            or not isinstance(jobs, int) or isinstance(jobs, bool) or jobs < 1):
        raise DispatchError('arguments_invalid', 'lesson must be a slug and jobs must be positive')
    if not steps or set(steps) - {'pictures', 'voice'} or len(steps) != len(set(steps)):
        raise DispatchError('steps_invalid', str(steps))
    source_root = Path(source_root).resolve()
    source = (source_root / lesson).resolve()
    if source.parent != source_root or not source.is_dir():
        raise DispatchError('lesson_missing', str(source))
    with work_lock(work, lesson) as work:
        recorded_post = RecordedPost(work, post=post or default_post, health_get=health_get,
                                     slots_dir=slots_dir, retry_rate_limited=retry_rate_limited,
                                     picture_assets=source / 'assets')
        results = {}
        # Load all selected inputs before a paid call; the existing helpers validate them.
        requests = _load(source / 'pictures.json') if 'pictures' in steps else None
        lines = _load(work / 'lines.json') if 'voice' in steps else None
        if 'pictures' in steps:
            results['pictures'] = picture.generate_pictures(
                requests, source / 'assets', post=recorded_post, fetch=fetch or picture.default_fetch,
                cache_path=work / 'picture-cache.json', endpoint=endpoint, jobs=jobs,
                sleep=lambda _: None)
        if 'voice' in steps:
            results['voice'] = voice.voice_lines(
                lines, work / 'media', post=recorded_post, cache_path=work / 'voice-cache.json',
                endpoint=endpoint, jobs=jobs, sleep=lambda _: None)
        return results


def run_unsubmitted_tts(lesson, work, pending, response_sha, lines_sha, *, additional=(), lines_file=None,
                        post=None, health_get=default_health_get, slots_dir=SLOTS_DIR):
    """Continue untouched lines without retrying or settling any recorded TTS 500."""
    known = {pending: response_sha}
    for item in additional:
        payload_sha, separator, old_response_sha = item.partition(':')
        if not separator or payload_sha in known:
            raise DispatchError('continuation_hash_invalid', lesson)
        known[payload_sha] = old_response_sha
    if any(not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value)
           for value in [lines_sha, *known, *known.values()]):
        raise DispatchError('continuation_hash_invalid', lesson)
    url = DEFAULT_ENDPOINT + '/api/generate/tts'
    with work_lock(work, lesson) as work:
        recorded = RecordedPost(work, post=post or default_post, health_get=health_get, slots_dir=slots_dir)
        allowed, prior_payloads = set(), []
        for prior_sha, prior_response_sha in known.items():
            prior = recorded.requests / prior_sha
            claim = _load(prior / 'claim.json')
            response = prior / 'response.json'
            status, _ = recorded._read_attempt(prior, url, claim['payload'], prior_sha)
            if (status != 500 or (prior / 'attempts').exists()
                    or hashlib.sha256(response.read_bytes()).hexdigest() != prior_response_sha):
                raise DispatchError('continuation_response_mismatch', str(response))
            allowed.add(str(prior / 'claim.json'))
            prior_payloads.append(claim['payload'])
        if allowed != recorded._unresolved:
            raise DispatchError('continuation_unknown_scope', str(recorded.requests))

        lines_path = Path(lines_file) if lines_file is not None else work / 'lines.json'
        raw_lines = lines_path.read_bytes()
        if hashlib.sha256(raw_lines).hexdigest() != lines_sha:
            raise DispatchError('continuation_lines_changed', str(lines_path))
        lines = json.loads(raw_lines)
        if not isinstance(lines, list) or any(not isinstance(line, dict) or not isinstance(line.get('id'), str)
                                              for line in lines):
            raise DispatchError('continuation_lines_invalid', str(lines_path))
        if len({line['id'] for line in lines}) != len(lines):
            raise DispatchError('continuation_lines_invalid', str(lines_path))
        existing_ids = set()
        for path in recorded.requests.glob('*/claim.json'):
            entry = _load(path)
            if entry['url'].endswith('/api/generate/tts'):
                existing_ids.add(entry['payload']['audioId'])
        indexed = {line['id']: line for line in lines}
        for prior_payload in prior_payloads:
            prior_line = indexed.get(prior_payload['audioId'])
            if prior_line is not None and (prior_line.get('text') != prior_payload['text']
                                           or prior_line.get('voice') != prior_payload['ttsVoice']):
                raise DispatchError('continuation_pending_line_changed', str(lines_path))
        pending_texts = {payload['text'] for payload in prior_payloads}
        first = {line['id']: line for line in lines if line['id'] not in existing_ids
                 and line.get('text') not in pending_texts}
        evidence = {'pendingPayloadSha256': pending, 'pendingResponseSha256': response_sha, 'linesSha256': lines_sha}
        if additional:
            evidence['additionalUnresolved'] = [{'payloadSha256': p, 'responseSha256': r}
                                                for p, r in known.items() if p != pending]

        def send_first(request_url, payload):
            line = first.get(payload['audioId'])
            digest = hashlib.sha256(_json_bytes(payload)).hexdigest()
            directory = recorded.requests / digest
            if (request_url != url or line is None or line['text'] != payload['text']
                    or line['voice'] != payload['ttsVoice'] or directory.exists()):
                raise DispatchError('continuation_first_post_only', digest)
            return recorded._send_attempt(directory, url, payload, digest, allowed_unknown=allowed,
                                          continuation=evidence)

        clips = voice.voice_lines(list(first.values()), work / 'media', post=send_first,
                                  cache_path=work / 'voice-cache.json', endpoint=DEFAULT_ENDPOINT,
                                  jobs=1, sleep=lambda _: None)
        result = {'voice': clips, 'pending': {'payloadSha256': pending, 'outcome': 'unknown_upstream_outcome'}}
        if additional:
            result['additionalPending'] = [digest for digest in known if digest != pending]
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lesson', required=True, help='slug under courseware/lessons')
    parser.add_argument('--work', required=True, help='explicit existing/new lesson work directory')
    parser.add_argument('--steps', default='pictures,voice', help='pictures, voice, or pictures,voice')
    parser.add_argument('--jobs', type=int, default=2)
    retries = parser.add_mutually_exclusive_group()
    retries.add_argument('--retry-rate-limited', action='store_true',
                         help='one explicit recovery per verified TTS RATE_LIMITED HTTP429 payload')
    retries.add_argument('--retry-authorized-request', metavar='AUTHORIZATION', action='append',
                         help='send only the frozen TTS payload bound by this one-use owner authorization; '
                              'repeat it for several authorized payloads of the same work, sent in order')
    retries.add_argument('--continue-unsubmitted-tts-after', metavar='PAYLOAD_SHA256',
                         help='send untouched TTS lines only, retaining this known unresolved 500')
    parser.add_argument('--response-sha256', help='byte hash of the unresolved response for continuation')
    parser.add_argument('--lines-file', type=Path, help='reviewed continuation lines; defaults to lines.json in --work')
    parser.add_argument('--lines-sha256', help='byte hash of the reviewed continuation lines file')
    parser.add_argument('--additional-unresolved-tts', action='append', default=[],
                        metavar='PAYLOAD_SHA256:RESPONSE_SHA256', help='another recorded unresolved TTS 500')
    args = parser.parse_args(argv)
    if not args.continue_unsubmitted_tts_after and (
            args.response_sha256 or args.lines_file or args.lines_sha256 or args.additional_unresolved_tts):
        parser.error('Continuation options require --continue-unsubmitted-tts-after')
    try:
        if args.retry_authorized_request:
            paths = args.retry_authorized_request
            if len(set(paths)) != len(paths):
                parser.error('Name each authorization once')
            if len(paths) == 1:
                result = run_authorized_retry(args.lesson, args.work, paths[0])
            else:
                files, voiced, reused = {}, 0, 0
                for index, path in enumerate(paths):
                    # Later authorizations stay open until their own turn; nothing else may.
                    clips = run_authorized_retry(args.lesson, args.work, path,
                                                 companions=tuple(paths[index + 1:]))['voice']
                    files.update(clips['files'])
                    voiced += clips['voiced']
                    reused += clips['reused']
                result = {'voice': {'files': files, 'voiced': voiced, 'reused': reused}}
        elif args.continue_unsubmitted_tts_after:
            result = run_unsubmitted_tts(args.lesson, args.work, args.continue_unsubmitted_tts_after,
                                         args.response_sha256, args.lines_sha256,
                                         additional=args.additional_unresolved_tts, lines_file=args.lines_file)
        else:
            result = run_dispatch(args.lesson, args.work, steps=tuple(args.steps.split(',')), jobs=args.jobs,
                                  retry_rate_limited=args.retry_rate_limited)
    except (DispatchError, picture.PictureError, voice.VoiceError, OSError, ValueError) as exc:
        print(f'{type(exc).__name__}: ' + ': '.join(str(part) for part in exc.args), file=sys.stderr)
        return 1
    for step, info in result.items():
        print(step, json.dumps(info, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
