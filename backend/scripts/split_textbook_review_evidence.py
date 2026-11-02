"""Split the bulky audio evidence out of oversized published review records, reversibly.

Some published reviews (audio-audit v3 and v4) embed every recording several times and
reach 100-200 MB. This tool keeps each recording once in learning_textbook_review_evidence
(migration 105) and leaves references in the record; restoring gives back the original
text byte for byte, so no sealed digest or course identity changes. See
content/textbook_review_evidence.py.

Subcommands (each takes --content-key, repeatable):

  plan     Read-only. Show what the split would do and prove it on the stored record: the
           split record restores to the stored text byte for byte and is under 3 MB.
  backup   Read-only on the database. Write each stored review text gzip-compressed to a NEW
           --backup-dir with a manifest of its hashes and of every other column of the row.
           Verifies the files and re-reads the database. Never overwrites.
  apply    Dry run unless --execute. For each record: prove the split outside any lock, store
           the evidence (inert until a record points at it), then in one transaction check the
           stored text and the other columns against the manifest, replace only review_json,
           check that no other column (updated_at included) moved, restore from the database
           and compare with the original hash, and run the full validate_release. Any failure
           rolls that record back untouched.
  verify   Read-only. Check size, exact restore, the other columns, the directory row,
           validate_release, the runtime release path and the archive queue.
  restore  Dry run unless --execute. Put the original review text back from the backup.
           Evidence rows stay: they are inert and immutable.

updated_at must never move. course_archive_exporter hashes it into archiveSourceRevision, and
the archive worker would export and upload a new multi-hundred-MB package for every course
whose value changed. apply and restore therefore write review_json only and prove the rest
of the row is identical before they commit.

Order of work: deploy the code that understands split records and restart first, apply
second; restore the data first and roll the code back second. Code that predates this tool
rejects a split record.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from content import textbook_review_evidence as ev  # noqa: E402

MANIFEST_NAME = 'manifest.json'
MANIFEST_SCHEMA = 'mira.textbook.review-backup.v1'
COLUMNS = ('content_key', 'edition_id', 'revision_id', 'node_id', 'part_index', 'teaching_revision',
           'input_json', 'status', 'course_id', 'course_version', 'course_content_sha256',
           'created_at', 'updated_at')
SIZE_LIMIT = 3_000_000
SMALL_RECORD = 8_000_000
QUEUE_ITEMS = BACKEND / 'data/course-storage/archive-queue/items'
HEX_DIGITS = frozenset('0123456789abcdef')


class ToolError(RuntimeError):
    pass


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def _require(condition, message):
    if not condition:
        raise ToolError(message)


# ---------------------------------------------------------------- database reads

def read_columns(conn, key, *, lock=False):
    """Every column of the build except the review text, optionally under a row lock."""
    _require(len(key) == 64 and set(key) <= HEX_DIGITS, 'a content key is 64 lowercase hex digits')
    row = conn.execute('SELECT ' + ','.join(COLUMNS) + ',review_json IS NOT NULL AS has_review '
                       'FROM learning_textbook_course_builds WHERE content_key=?' + (' FOR UPDATE' if lock else ''),
                       (key,)).fetchone()
    _require(row is not None, 'no build ' + key)
    _require(row['status'] == 'published' and row['has_review'],
             'only a published build with a review record can be split: ' + key)
    return {name: row[name] for name in COLUMNS}


def read_review_text(conn, key):
    return conn.execute('SELECT review_json FROM learning_textbook_course_builds WHERE content_key=?',
                        (key,)).fetchone()['review_json']


def stored_text_facts(conn, key):
    """Size and hash of the stored text, rendered once by the database itself."""
    row = conn.execute(
        'SELECT octet_length(t) AS text_bytes, encode(sha256(t),\'hex\') AS text_sha256 FROM '
        '(SELECT convert_to(CAST(review_json AS TEXT),\'UTF8\') AS t FROM learning_textbook_course_builds '
        'WHERE content_key=?) s', (key,)).fetchone()
    stored = conn.execute('SELECT pg_column_size(review_json) AS stored_bytes FROM learning_textbook_course_builds '
                          'WHERE content_key=?', (key,)).fetchone()
    return {'textBytes': row['text_bytes'], 'textSha256': row['text_sha256'], 'storedBytes': stored['stored_bytes']}


def current_database(conn):
    return conn.execute('SELECT current_database() AS name').fetchone()['name']


def directory_row(conn, key):
    """The derived directory row (migration 104), or None when that table is not there yet."""
    if conn.execute("SELECT to_regclass('learning_textbook_build_directory') AS name").fetchone()['name'] is None:
        return None
    row = conn.execute('SELECT review_evidence_json,release_summary_json FROM learning_textbook_build_directory '
                       'WHERE content_key=?', (key,)).fetchone()
    return None if row is None else {k: row[k] for k in ('review_evidence_json', 'release_summary_json')}


def projection_of(conn, text):
    """The directory projection PostgreSQL computes for this record text, or None without migration 104."""
    if conn.execute("SELECT to_regprocedure('textbook_build_directory_projection(jsonb)') AS name").fetchone()['name'] is None:
        return None
    row = conn.execute('SELECT evidence_json,summary_json FROM textbook_build_directory_projection(CAST(? AS jsonb))',
                       (text,)).fetchone()
    return {'review_evidence_json': row['evidence_json'], 'release_summary_json': row['summary_json']}


def queue_state(keys, directory=QUEUE_ITEMS):
    """Archive-queue jobs that belong to these builds (read-only file scan)."""
    directory = Path(directory)
    if not directory.is_dir():
        return None
    found = {key: [] for key in keys}
    for path in directory.glob('*.json'):
        try:
            job = json.loads(path.read_text(encoding='utf-8'))
            course = (job.get('event') or {}).get('course') or {}
        except (OSError, ValueError, AttributeError):
            continue
        if course.get('contentKey') in found:
            found[course['contentKey']].append({'status': job.get('status'),
                                                'revision': (course.get('archiveSourceRevision') or '')[:12]})
    return found


# ---------------------------------------------------------------- plan

def plan_record(columns, text):
    """Prove the split on a stored record text. Returns (report, split text, evidence)."""
    review = json.loads(text)
    _require(not ev.is_split(review), 'already split: ' + columns['content_key'])
    _require(ev.pg_jsonb_text(review) == text,
             'the stored text is not what this tool would print; refusing to split ' + columns['content_key'])
    split, items = ev.split_review(review)
    del review
    split_text = ev.pg_jsonb_text(split)
    restored = ev.restore_review_text(split_text, ev.MemoryStore(items))
    report = {'contentKey': columns['content_key'], 'nodeId': columns['node_id'],
              'storedBytes': len(text.encode('utf-8')), 'splitBytes': len(split_text.encode('utf-8')),
              'evidenceItems': len(items), 'evidenceBytes': sum(len(body) for body in items.values()),
              'restoresByteForByte': restored == text}
    report['belowLimit'] = report['splitBytes'] < SIZE_LIMIT
    _require(report['restoresByteForByte'], 'the split does not restore byte for byte: ' + columns['content_key'])
    _require(report['belowLimit'], 'the split record is not under the size limit: ' + columns['content_key'])
    return report, split_text, items


# ---------------------------------------------------------------- backup

def _write_private(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def load_manifest(directory):
    manifest = json.loads((Path(directory) / MANIFEST_NAME).read_text(encoding='utf-8'))
    _require(manifest.get('schemaVersion') == MANIFEST_SCHEMA and isinstance(manifest.get('entries'), list),
             'not a review backup manifest')
    return manifest


def manifest_entry(manifest, key):
    matches = [entry for entry in manifest['entries'] if entry['contentKey'] == key]
    _require(len(matches) == 1, 'the backup manifest has no single entry for ' + key)
    return matches[0]


def read_backup_text(directory, manifest, key):
    entry = manifest_entry(manifest, key)
    compressed = (Path(directory) / entry['file']).read_bytes()
    _require(sha256_hex(compressed) == entry['fileSha256'], 'backup file changed: ' + entry['file'])
    raw = gzip.decompress(compressed)
    _require(sha256_hex(raw) == entry['originalReviewSha256'] and len(raw) == entry['originalReviewBytes'],
             'backup content differs from its manifest: ' + entry['file'])
    return raw.decode('utf-8')


def backup_records(database, keys, directory):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    entries = []
    with database.transaction() as conn:
        database_name = current_database(conn)
    for key in keys:
        with database.transaction() as conn:
            columns = read_columns(conn, key)
            facts = stored_text_facts(conn, key)
            text = read_review_text(conn, key)
            snapshot = directory_row(conn, key)
        _require(ev.MARKER_TEXT not in text or not ev.is_split(json.loads(text)),
                 'already split; its original is not stored here: ' + key)
        raw = text.encode('utf-8')
        del text
        _require(sha256_hex(raw) == facts['textSha256'], 'the text read differs from the text hashed by the database: ' + key)
        compressed = gzip.compress(raw, compresslevel=6, mtime=0)
        file_name = key + '.review.json.gz'
        _write_private(directory / file_name, compressed)
        entries.append({'contentKey': key, 'file': file_name, 'fileSha256': sha256_hex(compressed),
                        'fileBytes': len(compressed), 'originalReviewSha256': sha256_hex(raw),
                        'originalReviewBytes': len(raw), 'row': columns, 'directory': snapshot})
        del raw, compressed
    manifest = {'schemaVersion': MANIFEST_SCHEMA, 'database': database_name,
                'createdAt': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'entries': entries}
    _write_private(directory / MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
    # Prove the copy: every file decompresses to the recorded hash and the database still holds those bytes.
    for entry in entries:
        read_backup_text(directory, manifest, entry['contentKey'])
        with database.transaction() as conn:
            _require(stored_text_facts(conn, entry['contentKey'])['textSha256'] == entry['originalReviewSha256'],
                     'the database no longer holds the backed-up text: ' + entry['contentKey'])
    return manifest


# ---------------------------------------------------------------- apply / restore

def _validate_in(conn, columns, review_text):
    """The application's own full validation of this record, reading evidence through ``conn``."""
    from content.textbook_catalog import digest
    from content.textbook_release import validate_release
    from repositories.textbook_repository import TextbookRepository
    repo = TextbookRepository(None)
    revision = repo.get_revision(conn, columns['edition_id'], columns['revision_id'])
    course = conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=?',
                          (columns['course_id'], columns['course_version'])).fetchone()
    _require(revision is not None and course is not None, 'the revision or course of ' + columns['content_key'] + ' is missing')
    manifest = repo.manifest(revision)
    _require(digest(manifest) == revision['manifest_sha256'], 'the textbook manifest digest differs')
    with ev.using_store(ev.ConnectionStore(conn)):
        release = validate_release({**columns, 'review_json': review_text}, manifest, course)
    _require(isinstance(release, dict), 'validate_release did not accept ' + columns['content_key'])
    return release


def _check_origin(conn, entry, columns, facts):
    _require(current_database(conn) == entry['database'], 'the backup was taken from another database')
    _require(columns == entry['row'], 'the row changed since the backup: ' + entry['contentKey'])
    _require(facts['textSha256'] == entry['originalReviewSha256'],
             'the stored review is not the backed-up original: ' + entry['contentKey'])


def apply_record(database, entry, *, execute, now_ms):
    key = entry['contentKey']
    # 1. Prove the split on the stored record without holding any lock.
    with database.transaction() as conn:
        columns = read_columns(conn, key)
        _check_origin(conn, entry, columns, stored_text_facts(conn, key))
        text = read_review_text(conn, key)
    report, split_text, items = plan_record(columns, text)
    del text
    report['dryRun'] = not execute
    if not execute:
        return report
    # 2. Evidence first. Until a record points at it the evidence is inert.
    with database.transaction() as conn:
        ev.store_evidence(conn, items, now=now_ms)
    # 3. Replace review_json and nothing else, and prove it before committing.
    with database.transaction() as conn:
        columns = read_columns(conn, key, lock=True)
        _check_origin(conn, entry, columns, stored_text_facts(conn, key))
        conn.execute('UPDATE learning_textbook_course_builds SET review_json=? WHERE content_key=?', (split_text, key))
        after = read_columns(conn, key)
        _require(after == entry['row'], 'a column other than review_json moved; rolled back: ' + key)
        facts = stored_text_facts(conn, key)
        _require(facts['textBytes'] < SIZE_LIMIT, 'the stored split record is not under the size limit; rolled back: ' + key)
        stored = read_review_text(conn, key)
        restored = ev.restore_review_text(stored, ev.ConnectionStore(conn))
        _require(sha256_hex(restored.encode('utf-8')) == entry['originalReviewSha256'],
                 'the split does not restore to the original; rolled back: ' + key)
        del restored
        if entry.get('directory') is not None:
            _require(projection_of(conn, stored) == entry['directory'],
                     'the directory projection changed; rolled back: ' + key)
        _validate_in(conn, after, stored)
        report.update(stored=facts, committed=True)
    return report


def restore_record(database, directory, manifest, key, *, execute):
    entry = {**manifest_entry(manifest, key), 'database': manifest['database']}
    original = read_backup_text(directory, manifest, key)
    with database.transaction() as conn:
        columns = read_columns(conn, key, lock=True)
        _require(current_database(conn) == entry['database'], 'the backup was taken from another database')
        _require(columns == entry['row'], 'a column other than review_json differs from the backup: ' + key)
        facts = stored_text_facts(conn, key)
        if facts['textSha256'] == entry['originalReviewSha256']:
            return {'contentKey': key, 'alreadyOriginal': True}
        _require(facts['textBytes'] < SMALL_RECORD and ev.is_split(json.loads(read_review_text(conn, key))),
                 'the stored review is neither the original nor a split record: ' + key)
        report = {'contentKey': key, 'dryRun': not execute, 'originalBytes': entry['originalReviewBytes']}
        if not execute:
            return report
        conn.execute('UPDATE learning_textbook_course_builds SET review_json=? WHERE content_key=?', (original, key))
        del original
        _require(read_columns(conn, key) == entry['row'], 'a column other than review_json moved; rolled back: ' + key)
        facts = stored_text_facts(conn, key)
        _require(facts['textSha256'] == entry['originalReviewSha256'],
                 'the restored text differs from the original; rolled back: ' + key)
        report.update(stored=facts, committed=True)
    return report


# ---------------------------------------------------------------- verify

def verify_records(database, keys, *, manifest_dir=None, queue_dir=QUEUE_ITEMS):
    from repositories.textbook_repository import TextbookRepository
    from services import textbook_runtime_release_cache as runtime
    manifest = load_manifest(manifest_dir) if manifest_dir else None
    ev.configure(database)
    repo = TextbookRepository(database)
    results = []
    for key in keys:
        entry = manifest_entry(manifest, key) if manifest else None
        with database.transaction() as conn:
            columns = read_columns(conn, key)
            facts = stored_text_facts(conn, key)
            result = {'contentKey': key, 'nodeId': columns['node_id'], **facts,
                      'belowLimit': facts['textBytes'] < SIZE_LIMIT}
            split = False
            if facts['textBytes'] < SMALL_RECORD:
                text = read_review_text(conn, key)
                split = ev.MARKER_TEXT in text and ev.is_split(json.loads(text))
                if split and entry:
                    restored = ev.restore_review_text(text, ev.ConnectionStore(conn))
                    result['restoresToOriginal'] = sha256_hex(restored.encode('utf-8')) == entry['originalReviewSha256']
                    del restored
                del text
            result['split'] = split
            if entry:
                result['otherColumnsUnchanged'] = columns == entry['row']
                if not split:
                    result['isTheBackedUpOriginal'] = facts['textSha256'] == entry['originalReviewSha256']
                if entry.get('directory') is not None:
                    result['directoryRowUnchanged'] = directory_row(conn, key) == entry['directory']
            grade = repo.manifest(repo.get_revision(conn, columns['edition_id'], columns['revision_id']))['gradeCode']
        started = time.perf_counter()
        with repo.transaction() as conn:
            _build, release, _course, _manifest = runtime.published_runtime_release(repo, conn, key, {'grade_code': grade})
        cold = time.perf_counter() - started
        started = time.perf_counter()
        with repo.transaction() as conn:
            runtime.published_runtime_release(repo, conn, key, {'grade_code': grade})
        result.update(runtimeReleaseOk=isinstance(release, dict), runtimeColdSeconds=round(cold, 2),
                      runtimeCachedSeconds=round(time.perf_counter() - started, 3))
        results.append(result)
    return {'releases': results, 'archiveQueue': queue_state(keys, queue_dir)}


# ---------------------------------------------------------------- command line

def _database(url):
    from core.config import AppConfig
    from core.database import Database
    return Database(url or AppConfig.from_env().DATABASE_URL)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('plan', 'backup', 'apply', 'verify', 'restore'))
    parser.add_argument('--content-key', action='append', required=True)
    parser.add_argument('--backup-dir', type=Path)
    parser.add_argument('--database-url')
    parser.add_argument('--execute', action='store_true', help='apply and restore only change data with this flag')
    args = parser.parse_args(argv)
    if args.command in {'backup', 'apply', 'restore'} and not args.backup_dir:
        parser.error(args.command + ' needs --backup-dir')
    database = _database(args.database_url)
    keys = list(dict.fromkeys(args.content_key))
    try:
        if args.command == 'plan':
            result = []
            for key in keys:
                with database.transaction() as conn:
                    columns = read_columns(conn, key)
                    text = read_review_text(conn, key)
                result.append(plan_record(columns, text)[0])
                del text
        elif args.command == 'backup':
            result = backup_records(database, keys, args.backup_dir)
        elif args.command == 'apply':
            from core.security import now_ms
            manifest = load_manifest(args.backup_dir)
            result = [apply_record(database, {**manifest_entry(manifest, key), 'database': manifest['database']},
                                   execute=args.execute, now_ms=now_ms()) for key in keys]
        elif args.command == 'restore':
            manifest = load_manifest(args.backup_dir)
            result = [restore_record(database, args.backup_dir, manifest, key, execute=args.execute) for key in keys]
        else:
            result = verify_records(database, keys, manifest_dir=args.backup_dir)
    except ToolError as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
