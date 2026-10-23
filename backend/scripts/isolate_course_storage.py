#!/usr/bin/env python3
"""Plan, quarantine and restore exact registered local course files; never delete.

Only current registry heads and the explicitly retired active-manifest index are
eligible. A complete immutable journal is durable before the first same-device
rename. Small cursors are advisory: recovery inspects both paths and their bytes.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.course_storage_config import CourseStorageConfig
from repositories.course_storage_repository import MAX_FILE_BYTES, normalize_source_path, storage_id_for

SCHEMA = 'mira.course-storage.local-isolation.v1'
INDEX_PATH = 'backend/data/course-storage/active-manifest.json'
STATE_PATH = 'backend/data/course-storage/local-isolation'
SHA = re.compile(r'[a-f0-9]{64}\Z')
MAX_JOURNAL = 128 * 1024 * 1024
MAX_ENTRIES = 200_000
BATCH = 128


class IsolationError(ValueError):
    def __init__(self, code, source_path=None):
        super().__init__(code)
        self.source_path = source_path


def _require(condition, code, source=None):
    if not condition:
        raise IsolationError(code, source)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _absolute(value):
    text = os.fspath(value)
    _require(os.path.isabs(text) and not any(p in {'.', '..'} for p in text.split(os.sep)),
             'isolation_absolute_unlinked_path_required')
    return Path(text)


def _open_dir(value, *, create=False, private_root=None):
    """Walk with directory descriptors: neither existing nor raced links qualify."""
    path = _absolute(value)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(path.anchor, flags)
    current = Path(path.anchor)
    try:
        for part in path.parts[1:]:
            current /= part
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
                os.fsync(descriptor)
                child = os.open(part, flags, dir_fd=descriptor)
            except OSError as error:
                if error.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise IsolationError('isolation_directory_link_or_non_directory', str(current)) from None
                raise
            os.close(descriptor)
            descriptor = child
            if private_root is not None and current.is_relative_to(private_root):
                info = os.fstat(descriptor)
                _require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                         'isolation_state_not_private', str(current))
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _directory_device(path):
    """Check every existing ancestor without creating the destination."""
    path = _absolute(path)
    while True:
        try:
            descriptor = _open_dir(path)
            try:
                return os.fstat(descriptor).st_dev
            finally:
                os.close(descriptor)
        except FileNotFoundError:
            path = path.parent


def _stat(info):
    return {'dev': info.st_dev, 'ino': info.st_ino, 'size': info.st_size,
            'mtimeNs': info.st_mtime_ns, 'ctimeNs': info.st_ctime_ns,
            'mode': stat.S_IMODE(info.st_mode)}


def _inspect(path, *, private_root=None):
    path = _absolute(path)
    try:
        parent = _open_dir(path.parent, private_root=private_root)
    except FileNotFoundError:
        return None
    descriptor = None
    try:
        try:
            initial = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            _require(not stat.S_ISLNK(initial.st_mode), 'isolation_file_symlink', str(path))
            _require(stat.S_ISREG(initial.st_mode), 'isolation_source_not_regular', str(path))
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except FileNotFoundError:
            return None
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise IsolationError('isolation_file_symlink', str(path)) from None
            raise
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode) and _stat(initial) == _stat(before),
                 'isolation_source_changed', str(path))
        checksum = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            checksum.update(chunk)
        after = os.fstat(descriptor)
        current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        _require(_stat(before) == _stat(after) == _stat(current), 'isolation_source_changed', str(path))
        return {'sha256': checksum.hexdigest(), 'byteSize': before.st_size, 'stat': _stat(before)}
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def _same_bytes(observed, entry, *, original=False):
    _require(observed is not None and observed['sha256'] == entry['sha256']
             and observed['byteSize'] == entry['byteSize'], 'isolation_integrity_mismatch', entry['sourcePath'])
    if original:
        _require(observed['stat'] == entry['stat'], 'isolation_source_stat_changed', entry['sourcePath'])


def _rename_exclusive(source, destination):
    """A true same-device, no-replace rename, including across crash recovery."""
    source, destination = _absolute(source), _absolute(destination)
    a, b = _open_dir(source.parent), _open_dir(destination.parent)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        try:
            if sys.platform == 'darwin':
                function = libc.renameatx_np
                flag = 0x00000004  # RENAME_EXCL
            elif sys.platform.startswith('linux'):
                function = libc.renameat2
                flag = 1  # RENAME_NOREPLACE
            else:
                raise AttributeError
        except AttributeError:
            raise IsolationError('isolation_exclusive_rename_unsupported')
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        if function(a, os.fsencode(source.name), b, os.fsencode(destination.name), flag):
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        os.fsync(a)
        if a != b:
            os.fsync(b)
    finally:
        os.close(a)
        os.close(b)


def _write_json(path, value, *, exclusive=False):
    parent = _open_dir(path.parent)
    temporary = path.parent / ('.isolation-' + uuid.uuid4().hex)
    try:
        descriptor = os.open(temporary.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(_json(value) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            _rename_exclusive(temporary, path)
        else:
            try:
                info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                         and stat.S_IMODE(info.st_mode) == 0o600, 'isolation_cursor_not_private')
            except FileNotFoundError:
                pass
            os.replace(temporary.name, path.name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
    finally:
        try:
            os.unlink(temporary.name, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


@contextmanager
def _lock(state):
    parent = _open_dir(state, private_root=state)
    descriptor = None
    try:
        descriptor = os.open('operation.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                             0o600, dir_fd=parent)
        info = os.fstat(descriptor)
        _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                 and stat.S_IMODE(info.st_mode) == 0o600, 'isolation_lock_not_private')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise IsolationError('isolation_operation_locked') from None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def _heads(heads):
    _require(isinstance(heads, list) and len(heads) <= MAX_ENTRIES, 'isolation_registry_snapshot_invalid')
    result, seen = [], set()
    for value in heads:
        _require(isinstance(value, dict) and isinstance(value.get('sourcePath'), str),
                 'isolation_registry_snapshot_invalid')
        path = normalize_source_path(value['sourcePath'])
        checksum, size = value.get('sha256'), value.get('byteSize')
        _require(path not in seen and isinstance(checksum, str) and SHA.fullmatch(checksum)
                 and type(size) is int and 0 <= size <= MAX_FILE_BYTES, 'isolation_registry_snapshot_invalid', path)
        seen.add(path)
        result.append({'sourcePath': path, 'sha256': checksum, 'byteSize': size})
    return sorted(result, key=lambda e: e['sourcePath'])


def _state(root, value=None):
    root = _absolute(root)
    descriptor = _open_dir(root)
    os.close(descriptor)
    base = root / STATE_PATH
    state = _absolute(value) if value is not None else base / str(uuid.uuid4())
    _require(state.parent == base and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', state.name),
             'isolation_state_must_be_private_course_storage_child')
    return root, state


def _cursor(state, journal, phase, **counts):
    _write_json(state / 'cursor.json', {'schemaVersion': SCHEMA, 'planSha256': journal['planSha256'],
        'phase': phase, 'updatedAt': _now(), **counts})


def _summary(journal, phase, **counts):
    return {'journal': str(Path(journal['stateDir']) / 'journal.json'), 'phase': phase,
            'planSha256': journal['planSha256'], **journal['counts'], **counts}


def _load_journal(path):
    path = _absolute(path)
    _require(path.name == 'journal.json', 'isolation_journal_filename_invalid')
    parent = _open_dir(path.parent, private_root=path.parent)
    try:
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                     and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= MAX_JOURNAL,
                     'isolation_journal_not_private_or_oversized')
            journal = json.loads(stream.read(MAX_JOURNAL + 1))
    finally:
        os.close(parent)
    checksum = journal.get('planSha256')
    _require(journal.get('schemaVersion') == SCHEMA and isinstance(checksum, str)
             and SHA.fullmatch(checksum) and _sha(_json({k: v for k, v in journal.items() if k != 'planSha256'})) == checksum,
             'isolation_journal_integrity_invalid')
    root, state = _state(journal['projectRoot'], journal['stateDir'])
    _require(path.parent == state and journal.get('ownerUid') == os.getuid(), 'isolation_journal_identity_invalid')
    _require(isinstance(journal.get('entries'), list) and len(journal['entries']) <= MAX_ENTRIES + 1,
             'isolation_journal_entries_invalid')
    registered, seen = [], set()
    for entry in journal['entries']:
        source = entry['sourcePath']
        if entry.get('kind') == 'registered':
            registered.append(entry)
            normalize_source_path(source)
        else:
            _require(entry.get('kind') == 'legacy_index' and source == INDEX_PATH,
                     'isolation_journal_entries_invalid')
        _require(source not in seen and entry.get('localState') in {'present', 'missing'}
                 and isinstance(entry.get('sha256'), str) and SHA.fullmatch(entry['sha256'])
                 and type(entry.get('byteSize')) is int and entry['byteSize'] >= 0,
                 'isolation_journal_entries_invalid')
        seen.add(source)
        if entry['localState'] == 'present':
            _require(isinstance(entry.get('stat'), dict) and set(entry['stat']) == {'dev', 'ino', 'size', 'mtimeNs', 'ctimeNs', 'mode'}
                     and all(type(v) is int and v >= 0 for v in entry['stat'].values())
                     and entry['stat']['size'] == entry['byteSize'], 'isolation_journal_stat_invalid')
        else:
            _require(entry['kind'] == 'registered' and 'stat' not in entry, 'isolation_journal_entries_invalid')
    _require(_sha(_json(_heads(registered))) == journal.get('headsSha256'), 'isolation_journal_heads_invalid')
    return root, state, journal


def plan_isolation(project_root, *, config, heads, state_dir=None):
    _require(config.mode == 'registry', 'isolation_registry_mode_required')
    root, state = _state(project_root, state_dir)
    registered = _heads(heads)
    _require(registered, 'isolation_empty_registry')
    device = _directory_device(state)
    entries, physical_files = [], set()
    for value in registered:
        observed = _inspect(root / value['sourcePath'])
        entry = {**value, 'kind': 'registered', 'localState': 'missing' if observed is None else 'present'}
        if observed is not None:
            _same_bytes(observed, entry)
            _require(observed['stat']['dev'] == device, 'isolation_cross_device', value['sourcePath'])
            physical = (observed['stat']['dev'], observed['stat']['ino'])
            _require(physical not in physical_files, 'isolation_source_alias_collision', value['sourcePath'])
            physical_files.add(physical)
            entry['stat'] = observed['stat']
        entries.append(entry)
    index = _inspect(root / INDEX_PATH)
    if index is not None:
        _require(index['stat']['dev'] == device, 'isolation_cross_device', INDEX_PATH)
        _require((index['stat']['dev'], index['stat']['ino']) not in physical_files,
                 'isolation_source_alias_collision', INDEX_PATH)
        entries.append({'sourcePath': INDEX_PATH, 'kind': 'legacy_index', 'localState': 'present', **index})
    present = [e for e in entries if e['localState'] == 'present']
    journal = {'schemaVersion': SCHEMA, 'projectRoot': str(root), 'stateDir': str(state), 'ownerUid': os.getuid(),
        'createdAt': _now(), 'storageId': storage_id_for(config.endpoint, config.bucket, config.region),
        'headsSha256': _sha(_json(registered)), 'entries': entries,
        'counts': {'registeredFiles': len(registered), 'missingRegisteredFiles': len(entries) - len(present),
                   'filesToMove': len(present), 'bytesToMove': sum(e['byteSize'] for e in present),
                   'legacyIndexFiles': sum(e['kind'] == 'legacy_index' for e in entries)}}
    journal['planSha256'] = _sha(_json(journal))
    _require(len(_json(journal)) <= MAX_JOURNAL, 'isolation_plan_oversized')
    descriptor = _open_dir(state, create=True, private_root=state)
    try:
        _require(not os.listdir(descriptor), 'isolation_state_not_empty')
    finally:
        os.close(descriptor)
    with _lock(state):
        _write_json(state / 'journal.json', journal, exclusive=True)
        _cursor(state, journal, 'planned')
    return _summary(journal, 'planned')


def _preflight_pairs(root, state, journal, *, restoring):
    actions, complete, retained = [], 0, 0
    physical_files = {}
    device = _directory_device(state)
    for entry in journal['entries']:
        source, destination = root / entry['sourcePath'], state / 'files' / entry['sourcePath']
        _require(_directory_device((source if restoring else destination).parent) == device,
                 'isolation_cross_device', entry['sourcePath'])
        a, b = _inspect(source), _inspect(destination, private_root=state)
        if entry['localState'] == 'missing':
            _require(a is None and b is None, 'isolation_missing_source_state_changed', entry['sourcePath'])
            continue
        _require(a is not None or b is not None, 'isolation_both_paths_missing', entry['sourcePath'])
        for value in (a, b):
            if value is not None:
                _same_bytes(value, entry)
                _require(value['stat']['dev'] == device, 'isolation_cross_device', entry['sourcePath'])
                physical = (value['stat']['dev'], value['stat']['ino'])
                _require(physical_files.get(physical, entry['sourcePath']) == entry['sourcePath'],
                         'isolation_source_alias_collision', entry['sourcePath'])
                physical_files[physical] = entry['sourcePath']
        if restoring:
            if a is not None:
                complete += 1
                retained += b is not None
            else:
                _require(b['stat']['mode'] == entry['stat']['mode'], 'isolation_quarantine_mode_changed', entry['sourcePath'])
                actions.append((entry, destination, source, b))
        else:
            _require(not (a is not None and b is not None), 'isolation_both_paths_present', entry['sourcePath'])
            if b is not None:
                complete += 1
            else:
                _same_bytes(a, entry, original=True)
                actions.append((entry, source, destination, a))
    return actions, complete, retained


def _move_plan(root, state, journal, *, restoring=False):
    actions, complete, retained = _preflight_pairs(root, state, journal, restoring=restoring)
    phase = 'restoring' if restoring else 'isolating'
    _cursor(state, journal, phase, completed=complete, remaining=len(actions), retainedCopies=retained)
    for number, (entry, source, destination, expected) in enumerate(actions, 1):
        _same_bytes(_inspect(source), {**entry, 'stat': expected['stat']}, original=True)
        parent = _open_dir(destination.parent, create=True, private_root=None if restoring else state)
        os.close(parent)
        _require(_inspect(destination) is None, 'isolation_destination_appeared', entry['sourcePath'])
        _rename_exclusive(source, destination)
        _require(_inspect(source) is None, 'isolation_source_remains_after_move', entry['sourcePath'])
        observed = _inspect(destination)
        _same_bytes(observed, entry)
        _require(observed['stat']['ino'] == expected['stat']['ino'] and observed['stat']['dev'] == expected['stat']['dev']
                 and observed['stat']['mode'] == expected['stat']['mode'] and observed['stat']['mtimeNs'] == expected['stat']['mtimeNs'],
                 'isolation_move_stat_changed', entry['sourcePath'])
        if number % BATCH == 0:
            _cursor(state, journal, phase, completed=complete + number, remaining=len(actions) - number,
                    retainedCopies=retained)
    phase = 'restored' if restoring else 'isolated'
    _cursor(state, journal, phase, completed=complete + len(actions), remaining=0, retainedCopies=retained)
    return _summary(journal, phase, completed=complete + len(actions), movedThisRun=len(actions), retainedCopies=retained)


def isolate(project_root, *, config, heads, state_dir=None):
    _require(config.mode == 'registry', 'isolation_registry_mode_required')
    root, state = _state(project_root, state_dir)
    if _inspect(state / 'journal.json') is None:
        plan_isolation(root, config=config, heads=heads, state_dir=state)
    root, state, journal = _load_journal(state / 'journal.json')
    _require(journal['headsSha256'] == _sha(_json(_heads(heads)))
             and journal['storageId'] == storage_id_for(config.endpoint, config.bucket, config.region),
             'isolation_registry_heads_changed')
    with _lock(state):
        return _move_plan(root, state, journal)


def restore_isolation(journal_path):
    root, state, journal = _load_journal(journal_path)
    with _lock(state):
        return _move_plan(root, state, journal, restoring=True)


def current_heads(database, config):
    _require(config.mode == 'registry', 'isolation_registry_mode_required')
    from scripts.course_storage_releases import read_only_connection
    identity = storage_id_for(config.endpoint, config.bucket, config.region)
    with read_only_connection(database) as conn:
        rows = conn.execute('SELECT f.source_path AS sourcePath,f.content_sha256 AS sha256,'
            'f.byte_size AS byteSize,f.source_path_sha256 AS pathSha256 FROM course_storage_heads h '
            'LEFT JOIN course_storage_files f ON f.storage_id=h.storage_id AND f.source_path_sha256=h.source_path_sha256 '
            'AND f.content_sha256=h.content_sha256 WHERE h.storage_id=? ORDER BY f.source_path LIMIT ' + str(MAX_ENTRIES + 1),
            (identity,)).fetchall()
        _require(all(isinstance(r['sourcePath'], str) and r['pathSha256'] == _sha(r['sourcePath'].encode()) for r in rows),
                 'isolation_registry_path_identity_invalid')
        return _heads([dict(r) for r in rows])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    for name in ('plan', 'isolate'):
        command = commands.add_parser(name)
        command.add_argument('--project-root', required=True)
        command.add_argument('--state-dir')
    command = commands.add_parser('restore')
    command.add_argument('--journal', required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == 'restore':
            result = restore_isolation(args.journal)
        else:
            from core.config import AppConfig
            from core.database import Database
            app = AppConfig.from_env()
            config = CourseStorageConfig.from_env()
            heads = current_heads(Database(app.DATABASE_URL), config)
            operation = plan_isolation if args.operation == 'plan' else isolate
            result = operation(args.project_root, config=config, heads=heads, state_dir=args.state_dir)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (IsolationError, OSError, ValueError, KeyError, TypeError) as error:
        result = {'ok': False, 'error': str(error) if isinstance(error, IsolationError) else 'isolation_operation_failed'}
        if isinstance(error, IsolationError) and error.source_path:
            result['sourcePath'] = error.source_path
        print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
