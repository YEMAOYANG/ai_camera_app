"""Lossless split of the bulky audio evidence inside a published review record.

A few published reviews (the ones that reuse ASR provenance, audio-audit schemas
v3 and v4) embed every recording several times as base64 inside
``release.audioAudit.literalAudit`` and repeat the same large plan objects in
every origin. Such a record is 100-200 MB: each full read transfers and
decompresses all of it, and each backup stores the same bytes again.

``split_review`` moves two kinds of content out of ``literalAudit`` and leaves a
reference in their place. Nothing else in the record changes.

* A string of at least 1024 characters that is exactly canonical base64 becomes
  ``"mira-blob:sha256:<sha256 of the decoded bytes>"``.
* A JSON object of at least 800 bytes that occurs more than once in the audit
  becomes ``{"$mira-ref": "<sha256 of its canonical JSON>"}``.

The moved bytes live once each in ``learning_textbook_review_evidence``, keyed by
their own SHA-256 (migration 105; the database itself rejects a row whose key is
not the hash of its bytes). Evidence is plain bytes: the reference decides
whether they are read as a recording or as JSON, so identical bytes are always
one row. ``restore_review`` rebuilds the original value exactly, so every sealed
digest in the record (literal audit, release, content key, course content) is
unchanged and no new course version is needed. Restoring verifies every item
against its key; a missing or altered item fails closed, and the lesson is then
rejected as before, never accepted on less evidence.

Only ``validate_release`` and the textbook directory cache need the restored
value. Everything that hashes the stored record text keeps hashing the stored
(split) text, so those hashes stay consistent with each other.
"""
import base64
import binascii
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
import logging
import re

from content.textbook_catalog import canonical, digest
from core.errors import ApiError

LOGGER = logging.getLogger(__name__)

SPLIT_SCHEMA = 'mira.textbook.review-evidence-split.v1'
SCOPE = 'release.audioAudit.literalAudit'
MARKER = 'evidenceSplit'
MARKER_TEXT = '"' + MARKER + '"'
BLOB_PREFIX = 'mira-blob:sha256:'
REF_KEY = '$mira-ref'
MIN_BLOB_CHARS = 1024
MIN_SHARED_BYTES = 800
MAX_ITEMS = 20_000
MAX_RESTORED_BYTES = 1024 * 1024 * 1024
_SHA256 = re.compile(r'[a-f0-9]{64}')
_READ_CHUNK = 100


class EvidenceError(ValueError):
    """The split evidence cannot be produced or restored exactly."""


# ---------------------------------------------------------------- locating

def _literal(review):
    release = review.get('release') if isinstance(review, dict) else None
    audit = release.get('audioAudit') if isinstance(release, dict) else None
    literal = audit.get('literalAudit') if isinstance(audit, dict) else None
    return literal if isinstance(literal, dict) else None


def is_split(review):
    literal = _literal(review)
    return literal is not None and MARKER in literal


def _with_literal(review, literal):
    audit = {**review['release']['audioAudit'], 'literalAudit': literal}
    return {**review, 'release': {**review['release'], 'audioAudit': audit}}


# ---------------------------------------------------------------- text form

def _pg_order(value):
    if isinstance(value, dict):
        keys = sorted(value, key=lambda key: (len(key.encode('utf-8')), key.encode('utf-8')))
        return {key: _pg_order(value[key]) for key in keys}
    if isinstance(value, list):
        return [_pg_order(item) for item in value]
    return value


def pg_jsonb_text(value):
    """The text PostgreSQL prints for this value stored as ``jsonb``.

    Object keys are ordered by byte length and then bytewise, separators are
    ``", "`` and ``": "``. Numbers print the way Python prints them, which is
    exact for integers, booleans and ordinary decimals; callers that need a
    guarantee compare this text with a stored record before relying on it.
    """
    return json.dumps(_pg_order(value), ensure_ascii=False, separators=(', ', ': '))


def text_sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------- splitting

def _canonical_bytes(text):
    """Decoded bytes of a long string that is exactly standard base64, else None."""
    if len(text) < MIN_BLOB_CHARS or len(text) % 4:
        return None
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None
    return raw if base64.b64encode(raw).decode('ascii') == text else None


def _externalize(node, evidence):
    if isinstance(node, dict):
        if REF_KEY in node:
            raise EvidenceError('the audit already contains the reserved key ' + REF_KEY)
        return {key: _externalize(value, evidence) for key, value in node.items()}
    if isinstance(node, list):
        return [_externalize(value, evidence) for value in node]
    if isinstance(node, str):
        if node.startswith(BLOB_PREFIX):
            raise EvidenceError('the audit already contains the reserved text ' + BLOB_PREFIX)
        raw = _canonical_bytes(node)
        if raw is not None:
            sha = hashlib.sha256(raw).hexdigest()
            evidence[sha] = raw
            return BLOB_PREFIX + sha
    return node


def _node_body(node):
    body = canonical(node).encode('utf-8')
    return hashlib.sha256(body).hexdigest(), body


def _count_repeats(node, counts):
    if isinstance(node, (dict, list)):
        sha, body = _node_body(node)
        if len(body) >= MIN_SHARED_BYTES:
            counts[sha] += 1
        for child in (node.values() if isinstance(node, dict) else node):
            _count_repeats(child, counts)


def _share_repeats(node, counts, evidence):
    if isinstance(node, (dict, list)):
        sha, body = _node_body(node)
        if len(body) >= MIN_SHARED_BYTES and counts[sha] >= 2:
            evidence[sha] = body
            return {REF_KEY: sha}
        if isinstance(node, dict):
            return {key: _share_repeats(value, counts, evidence) for key, value in node.items()}
        return [_share_repeats(value, counts, evidence) for value in node]
    return node


def _references(node, objects, blobs):
    """Collect the evidence keys a value points at; a malformed reference is an error."""
    if isinstance(node, dict):
        if REF_KEY in node:
            sha = node[REF_KEY]
            if set(node) != {REF_KEY} or not isinstance(sha, str) or not _SHA256.fullmatch(sha):
                raise EvidenceError('malformed shared-object reference')
            objects.add(sha)
            return
        for child in node.values():
            _references(child, objects, blobs)
    elif isinstance(node, list):
        for child in node:
            _references(child, objects, blobs)
    elif isinstance(node, str) and node.startswith(BLOB_PREFIX):
        sha = node[len(BLOB_PREFIX):]
        if not _SHA256.fullmatch(sha):
            raise EvidenceError('malformed recording reference')
        blobs.add(sha)


def split_review(review):
    """Return ``(split review, evidence)``; ``evidence`` maps sha256 -> bytes.

    The result is proven before it is returned: restoring it from ``evidence``
    gives back exactly the input.
    """
    literal = _literal(review)
    if literal is None:
        raise EvidenceError('the review has no ' + SCOPE)
    if MARKER in literal:
        raise EvidenceError('the review is already split')
    evidence = {}
    stripped = _externalize(literal, evidence)
    counts = Counter()
    _count_repeats(stripped, counts)
    shared = _share_repeats(stripped, counts, evidence)
    objects, blobs = set(), set()
    _references(shared, objects, blobs)
    for sha in objects:
        _references(json.loads(evidence[sha]), set(), blobs)
    marker = {'schemaVersion': SPLIT_SCHEMA, 'scope': SCOPE, 'originalSha256': digest(literal),
              'blobs': len(blobs), 'objects': len(objects)}
    result = _with_literal(review, {**shared, MARKER: marker})
    restored = restore_review(result, MemoryStore(evidence), verify_digest=True)
    if restored != review or digest(restored) != digest(review):
        raise EvidenceError('the split does not restore to the original value')
    return result, evidence


# ---------------------------------------------------------------- restoring

def _check_marker(marker):
    if (not isinstance(marker, dict) or set(marker) != {'schemaVersion', 'scope', 'originalSha256', 'blobs', 'objects'}
            or marker['schemaVersion'] != SPLIT_SCHEMA or marker['scope'] != SCOPE
            or not isinstance(marker['originalSha256'], str) or not _SHA256.fullmatch(marker['originalSha256'])
            or type(marker['blobs']) is not int or type(marker['objects']) is not int):
        raise EvidenceError('unknown or malformed evidence-split marker')


def _load(store, hashes, as_json, budget):
    if not hashes:
        return {}
    rows = store.read(sorted(hashes))
    loaded = {}
    for sha in hashes:
        body = rows.get(sha)
        if body is None:
            raise EvidenceError('missing evidence ' + sha)
        if hashlib.sha256(body).hexdigest() != sha:
            raise EvidenceError('evidence ' + sha + ' is not the bytes its key names')
        budget[0] += len(body)
        if budget[0] > MAX_RESTORED_BYTES:
            raise EvidenceError('restored evidence exceeds the size limit')
        if as_json:
            try:
                loaded[sha] = json.loads(body.decode('utf-8'))
            except (UnicodeError, ValueError):
                raise EvidenceError('shared evidence ' + sha + ' is not JSON') from None
        else:
            loaded[sha] = body
    return loaded


def _rebuild(node, objects, blobs):
    if isinstance(node, dict):
        if REF_KEY in node:
            return _rebuild(objects[node[REF_KEY]], objects, blobs)
        return {key: _rebuild(value, objects, blobs) for key, value in node.items()}
    if isinstance(node, list):
        return [_rebuild(value, objects, blobs) for value in node]
    if isinstance(node, str) and node.startswith(BLOB_PREFIX):
        return base64.b64encode(blobs[node[len(BLOB_PREFIX):]]).decode('ascii')
    return node


def restore_review(review, store=None, *, verify_digest=False):
    """The original review; the input itself when it is not split.

    ``verify_digest`` also compares the restored audit with the digest recorded
    when it was split. Validation does not need that, because it re-checks the
    audit's own sealed digest and every item is already verified by its key.
    """
    literal = _literal(review)
    if literal is None or MARKER not in literal:
        return review
    marker = literal[MARKER]
    _check_marker(marker)
    body = {key: value for key, value in literal.items() if key != MARKER}
    object_hashes, blob_hashes = set(), set()
    _references(body, object_hashes, blob_hashes)
    if len(object_hashes) + len(blob_hashes) > MAX_ITEMS:
        raise EvidenceError('too many evidence items')
    store = store if store is not None else current_store()
    budget = [0]
    objects = _load(store, object_hashes, True, budget)
    for shared in objects.values():
        nested = set()
        _references(shared, nested, blob_hashes)
        if nested:
            raise EvidenceError('shared evidence may not point at other shared evidence')
    blobs = _load(store, blob_hashes, False, budget)
    if marker['blobs'] != len(blob_hashes) or marker['objects'] != len(object_hashes):
        raise EvidenceError('the evidence counts differ from the marker')
    restored = _rebuild(body, objects, blobs)
    if verify_digest and digest(restored) != marker['originalSha256']:
        raise EvidenceError('the restored audit differs from the split original')
    return _with_literal(review, restored)


def restore_split_review(review):
    """``validate_release`` entry point: invisible for ordinary records, fail closed otherwise."""
    if not is_split(review):
        return review
    try:
        return restore_review(review)
    except EvidenceError as error:
        LOGGER.warning('textbook review evidence cannot be restored: %s', error)
        raise ApiError('textbook_release_unavailable', '这节课的发布资料不完整，请稍后再来', 409) from None


def restore_review_text(text, store=None):
    """The stored record text with its evidence put back, as PostgreSQL would print it.

    For an ordinary record this is the input itself. For a split record it is
    byte-identical to the text that was stored before the split.
    """
    if not isinstance(text, str) or MARKER_TEXT not in text:
        return text
    review = json.loads(text)
    if not is_split(review):
        return text
    return pg_jsonb_text(restore_review(review, store))


# ---------------------------------------------------------------- storage

class MemoryStore:
    """Evidence held in a dict; for tests and offline rehearsals."""

    def __init__(self, evidence=None):
        self.evidence = dict(evidence or {})

    def read(self, hashes):
        return {sha: self.evidence[sha] for sha in hashes if sha in self.evidence}


class ConnectionStore:
    """Evidence read through one open connection (inside a caller's transaction)."""

    def __init__(self, conn):
        self.conn = conn

    def read(self, hashes):
        from core.database import DatabaseError
        hashes = list(hashes)
        found = {}
        try:
            for start in range(0, len(hashes), _READ_CHUNK):
                chunk = hashes[start:start + _READ_CHUNK]
                marks = ','.join('?' for _ in chunk)
                rows = self.conn.execute(
                    'SELECT sha256,body FROM learning_textbook_review_evidence '
                    f'WHERE sha256 IN ({marks})', tuple(chunk)).fetchall()
                for row in rows:
                    found[row['sha256']] = bytes(row['body'])
        except DatabaseError as error:
            raise EvidenceError('the evidence table cannot be read: ' + type(error).__name__) from None
        return found


class DatabaseStore:
    """Evidence read on a short-lived connection of its own.

    Evidence is immutable and content-addressed, so it needs no part in the
    caller's transaction: whatever is read is checked against its own key.
    """

    def __init__(self, database):
        self.database = database

    def read(self, hashes):
        from core.database import DatabaseError
        try:
            with self.database.transaction() as conn:
                return ConnectionStore(conn).read(hashes)
        except DatabaseError as error:
            raise EvidenceError('the evidence table cannot be reached: ' + type(error).__name__) from None


def store_evidence(conn, evidence, *, now):
    """Insert each item once inside the caller's transaction and prove it reads back identically."""
    for sha, body in evidence.items():
        conn.execute(
            'INSERT INTO learning_textbook_review_evidence (sha256,body,byte_length,created_at) '
            'VALUES (?,?,?,?) ON CONFLICT (sha256) DO NOTHING', (sha, body, len(body), now))
    stored = ConnectionStore(conn).read(list(evidence))
    for sha, body in evidence.items():
        if stored.get(sha) != body:
            raise EvidenceError('evidence ' + sha + ' was not stored identically')


_store = None


@contextmanager
def using_store(store):
    """Use this store for the duration of a block (a maintenance tool's own transaction)."""
    global _store
    previous, _store = _store, store
    try:
        yield
    finally:
        _store = previous


def configure(store):
    """Use this evidence store (a Database-like object is wrapped); ``None`` resets to the default."""
    global _store
    _store = DatabaseStore(store) if hasattr(store, 'transaction') else store


def current_store():
    global _store
    if _store is None:
        try:
            from core.config import AppConfig
            from core.database import Database
            _store = DatabaseStore(Database(AppConfig.from_env().DATABASE_URL))
        except Exception as error:  # noqa: BLE001 - any configuration problem must fail closed
            raise EvidenceError('no evidence store is configured: ' + type(error).__name__) from None
    return _store
