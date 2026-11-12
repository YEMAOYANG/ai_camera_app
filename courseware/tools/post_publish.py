"""Complete one published lesson's archive, playback, recovery and ledger checks.

Run via tools/task_tmp.py with backend/.venv/bin/python -m courseware.tools.post_publish.
The disposable workspace receives the independent download and restore. The
verified local recovery archive and completion receipt stay in the backup folder.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlencode
import zipfile

from courseware.tools.student_acceptance_state import ensure_state
from tools import courseware_backup


ROOT = Path(__file__).resolve().parents[2]
CLASSROOMS = 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms'
IDENTITY = ('editionId', 'revisionId', 'nodeId')
SHA = re.compile(r'[0-9a-f]{64}\Z')
DELIVERY_SCHEMA = 'mira.courseware.post-publish-delivery.v2'
COMPLETION_SCHEMA = 'mira.courseware.post-publish.v2'
DEFAULT_BATCH = 'currentGoalBatch'
COS_TRANSFER_TIMEOUT_SECONDS = 3600


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, document):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


@contextmanager
def file_lock(path, *, exclusive=False):
    with os.fdopen(os.open(path, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600), 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | (fcntl.LOCK_NB if exclusive else 0))
        yield


def update_ledger(path, update):
    with file_lock(path.with_suffix('.lock')):
        ledger = read_json(path)
        update(ledger)
        write_json(path, ledger)


def validate_assignment(ledger, owner, identity, source_slug, *, batch_key=DEFAULT_BATCH):
    batch = ledger.get(batch_key)
    require(isinstance(batch, dict), 'Selected production batch is missing')
    assignment = batch.get('active', {}).get(owner)
    require(isinstance(assignment, dict), 'Owner is not active in the selected production batch')
    require(assignment['owner'] == '/root/' + owner, 'Ledger owner mismatch')
    require(all(assignment[field] == identity[field] for field in IDENTITY)
            and assignment.get('sourceSlug', assignment.get('slug')) == source_slug, 'Ledger lesson mismatch')
    return batch, assignment


def matches_owner_confirmation(batch, confirmation):
    authorizations = [batch, *batch.get('ownerConfirmationHistory', [])]
    return confirmation.get('confirmedBy') == 'owner' and any(
        confirmation.get('userQuote') == row['ownerQuote'] and confirmation.get('confirmedAt') == row['confirmedAt']
        for row in authorizations)


def record_completion(ledger, owner, identity, source_slug, receipt, *, batch_key=DEFAULT_BATCH):
    _, assignment = validate_assignment(ledger, owner, identity, source_slug, batch_key=batch_key)
    require(assignment.get('contentKey', receipt['contentKey']) == receipt['contentKey'],
            'Ledger release changed')
    timings = {**assignment.get('timingsSeconds', {}), **receipt['timingsSeconds']}
    assignment.update({field: receipt[field] for field in ('contentKey', 'classroomId', 'releaseSha256', 'verifiedAt')},
                      status='published_registered_student_verified_independently_restored',
                      timingsSeconds=timings, slowestStep=max(timings, key=timings.get),
                      postPublishReceipt=receipt['receiptPath'])
    assignment.setdefault('localCleanup', 'awaiting_independent_second_backup')


def wait_for_scope(registry, storage, release, *, timeout, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + timeout
    while True:
        scopes = registry.find_scopes(storage_id=storage, content_key=release['contentKey'],
                                     classroom_id=release['classroomId'])
        for scope in scopes:
            if scope['metadata'].get('sourceDigest') == release['sha256']:
                return scope
        remaining = deadline - clock()
        require(remaining > 0, 'Timed out waiting for the exact archive to register')
        sleep(min(5, remaining))


def readback(scope, release, inventory, store, *, classroom_digest):
    classroom = release['classroomId']
    bindings = {entry['sourcePath']: entry['sha256'] for entry in scope['bindings']}
    classroom_path = f'{CLASSROOMS}/{classroom}.json'
    raw = store.read_bytes(ROOT / classroom_path, expected_sha256=bindings[classroom_path])
    require(raw is not None and classroom_digest(json.loads(raw)) == release['classroomSha256'],
            'Archived classroom bytes do not match the release')
    prefix = f'/api/classroom-media/{classroom}/'
    for entry in inventory:
        path = f'{CLASSROOMS}/{classroom}/' + entry['path'].removeprefix(prefix)
        require(bindings.get(path) == entry['sha256'], 'Media absent from exact archive: ' + entry['path'])
        raw = store.read_bytes(ROOT / path, expected_sha256=entry['sha256'], expected_bytes=entry['byteSize'])
        require(raw is not None and len(raw) == entry['byteSize'] and sha256(raw).hexdigest() == entry['sha256'],
                'Remote media verification failed: ' + entry['path'])
    return {'scopeKey': scope['scopeKey'], 'mediaVerifiedCount': len(inventory),
            'mediaVerifiedBytes': sum(item['byteSize'] for item in inventory), 'registryOnly': True}


def validate_delivery(proof, expected, scope, inventory, *, directory_identity=None):
    require(all(proof.get(field) == value for field, value in expected.items()),
            'Delivery receipt belongs to a different publication')
    media = proof['archiveReadback']
    require(media['scopeKey'] == scope['scopeKey'] and media['registryOnly'] is True
            and media['mediaVerifiedCount'] == len(inventory)
            and media['mediaVerifiedBytes'] == sum(item['byteSize'] for item in inventory),
            'Delivery receipt no longer matches the registered archive')
    student = proof['studentPlayback']
    if directory_identity is not None:
        observed = student.get('directoryIdentity', {})
        require(isinstance(observed, dict) and observed.get('selected') is True
                and all(observed.get(field) == directory_identity[field] for field in IDENTITY),
                'Student playback did not verify the exact selected textbook directory lesson')
    require(student['ok'] is True and student['mode'] == 'student-launch'
            and student['openedFromDirectory'] is True and student['recordedAudioPlayed'] is True
            and student['classroomId'] == expected['classroomId']
            and any((entry['path'], entry['sha256'], entry['byteSize']) ==
                    (student['audioPath'], student['audioSha256'], student['audioBytes'])
                    and entry['mimeType'].startswith('audio/') for entry in inventory),
            'Student playback did not prove a recorded clip of this release')


def delivery_checkpoint(path, expected, scope, inventory, collect, *, directory_identity):
    """Called under the lesson's backup lock. Preserve successful delivery across backup retries."""
    require(not path.is_symlink(), 'Linked delivery receipt')
    if path.exists():
        proof = read_json(path)
        require(proof['schemaVersion'] == DELIVERY_SCHEMA, 'Unrecognized delivery receipt')
        validate_delivery(proof, expected, scope, inventory, directory_identity=directory_identity)
        return proof
    require(collect is not None, 'Explicit delivery receipt does not exist')
    proof = {'schemaVersion': DELIVERY_SCHEMA, **expected, **collect()}
    validate_delivery(proof, expected, scope, inventory, directory_identity=directory_identity)
    write_json(path, proof)
    return proof


def command_json(*command, timeout=900):
    result = subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.PIPE, text=True, timeout=timeout)
    return json.loads(result.stdout)


def private_dir(path, boundary):
    absolute = Path(os.path.abspath(path))
    require(absolute.is_relative_to(boundary) and absolute != boundary
            and absolute.resolve() == absolute, 'Unexpected or linked path: ' + str(path))
    return absolute


def save_primary_backup(backup, roots):
    archive = backup / courseware_backup.ARCHIVE_NAME
    receipt_path = backup / 'remote-verification.json'
    require(not receipt_path.is_symlink(), 'Linked primary backup receipt')
    if not archive.exists():
        require(not receipt_path.exists(), 'Local archive missing for the primary backup receipt')
        courseware_backup.create_backup(courseware_backup.build_plan(ROOT, roots), backup)
    index = courseware_backup.verify_backup(archive, remote_export=True)
    require(index['sourceRoots'] == roots and not index['symlinks'], 'Recovery package source scope changed')
    if not receipt_path.exists():
        return command_json('node', 'courseware/tools/store_backup.mjs', 'upload', '--backup', str(backup))

    # The independent fetch still verifies every remote object. Retain the original upload proof.
    receipt = read_json(receipt_path)
    local_receipt = backup / 'backup-receipt.json'
    raw = local_receipt.read_bytes()
    archive_info = json.loads(raw)
    expected = {(archive.name, archive_info['sha256'], archive_info['byteSize']),
                (local_receipt.name, sha256(raw).hexdigest(), len(raw))}
    expected.update((item['backupPath'], item['sha256'], item['byteSize']) for item in index['sidecars'])
    files = receipt['files']
    require(receipt['schemaVersion'] == 'mira.courseware-backup.remote.v1' and receipt['complete'] is True
            and receipt['archiveSha256'] == archive_info['sha256'] and len(files) == len(expected)
            and {(item['path'], item['sha256'], item['byteSize']) for item in files} == expected,
            'Primary backup receipt does not match the local archive and its files')
    return {**receipt, 'files': len(files)}


def verify_restore(download, workspace, receipt, package, check_release):
    archive = download / courseware_backup.ARCHIVE_NAME
    index = courseware_backup.verify_backup(archive)
    downloaded_receipt = read_json(download / 'backup-receipt.json')
    require(downloaded_receipt['sha256'] == receipt['archiveSha256'], 'Downloaded recovery archive changed')
    # Execute only the byte-identical portable tool bundled by our backup command.
    restore = workspace / 'restore.py'
    with zipfile.ZipFile(archive) as zip_file:
        program = zip_file.read('restore.py')
    require(program == Path(courseware_backup.__file__).read_bytes(), 'Unexpected portable restore program')
    with restore.open('xb') as stream:
        stream.write(program)
    target = workspace / 'restored'
    restored = command_json(sys.executable, str(restore), 'restore', '--archive', str(archive), '--destination', str(target))
    require(restored['restoredFiles'] == len(index['files']), 'Incomplete portable restore')
    relative_package = package.relative_to(ROOT)
    checked = check_release(target / relative_package)
    require(checked['ok'] and checked['prepared']['release']['sha256'] == receipt['releaseSha256'],
            'Restored release does not pass the original release checks')
    return {'archiveSha256': receipt['archiveSha256'], 'restoredFiles': restored['restoredFiles'],
            'portableRestore': True, 'restoredReleaseSha256': checked['prepared']['release']['sha256']}


def verify_cos_recovery(backup, workspace, primary, package, check_release, require_current):
    """Recover from the second store without rewriting the primary evidence."""
    receipt_path = backup / 'post-publish-cos-receipt.json'
    require(not receipt_path.is_symlink(), 'Linked COS recovery receipt')
    identity = {key: primary[key] for key in ('contentKey', 'classroomId', 'releaseSha256')}
    expected = {'schemaVersion': 'mira.courseware.post-publish-cos.v1', **identity,
                'receiptPath': receipt_path.relative_to(ROOT).as_posix()}
    source_path = backup / 'remote-verification.json'
    require(not source_path.is_symlink(), 'Linked primary recovery receipt')
    source = read_json(source_path)
    recovery = primary['recovery']
    require(source['complete'] is True and source['archiveSha256'] == recovery['archiveSha256'],
            'Primary backup receipt changed')

    def validate_transfer(transfer):
        uploaded, downloaded = transfer['uploaded'], transfer['downloaded']
        keys = ('path', 'sha256', 'byteSize', 'objectKey')
        primary_files = {tuple(item[key] for key in keys) for item in source['files']}
        cos_files = {tuple(item[key] for key in keys) for item in uploaded['files']}
        require(uploaded['complete'] is True and downloaded['complete'] is True
                and uploaded['archiveSha256'] == downloaded['archiveSha256'] == source['archiveSha256']
                and uploaded['storage'] == downloaded['storage']
                and uploaded['storage']['endpoint'] != source['storage']['endpoint']
                and uploaded['files'] == downloaded['files']
                and primary_files == cos_files and len(uploaded['files']) == len(source['files'])
                and all(item.get('versionId') not in (None, '', 'null') for item in uploaded['files']),
                'Independent COS download did not match the primary archive and COS upload')

    if receipt_path.exists():
        receipt = read_json(receipt_path)
        require(all(receipt.get(k) == v for k, v in expected.items()) and receipt['recovery'] == recovery,
                'COS recovery receipt belongs to a different release')
        validate_transfer(receipt['transfer'])
        require_current()
        return receipt

    require(shutil.disk_usage(workspace).free >= 3 * 1024**3, 'COS restore requires 3 GiB of free workspace')
    cos_workspace = workspace / 'cos'
    cos_workspace.mkdir(mode=0o700)
    print('cosTransferAndIndependentFetch', file=sys.stderr, flush=True)
    started = time.monotonic()
    transfer = command_json('node', 'courseware/tools/store_backup.mjs', 'mirror-cos',
                            '--backup', str(backup), '--workspace', str(cos_workspace),
                            timeout=COS_TRANSFER_TIMEOUT_SECONDS)
    validate_transfer(transfer)
    transfer_seconds = round(time.monotonic() - started, 3)
    print('cosPortableRestore', file=sys.stderr, flush=True)
    started = time.monotonic()
    restored = verify_restore(cos_workspace / 'download', cos_workspace,
                              {**identity, **transfer['downloaded']}, package, check_release)
    require(restored == recovery, 'COS recovery differs from the primary restored release')
    require_current()
    receipt = {**expected, 'verifiedAt': datetime.now(timezone.utc).isoformat(), 'transfer': transfer,
               'recovery': restored, 'timingsSeconds': {'cosTransferAndIndependentFetch': transfer_seconds,
                                                       'cosPortableRestore': round(time.monotonic() - started, 3)}}
    write_json(receipt_path, receipt)
    return receipt


def finalize(args, workspace):
    # Reuse the backend's release validator and registry-only reader. The CLI
    # writes no application rows and never edits a published release package.
    sys.path.insert(0, str(ROOT / 'backend'))
    from core.config import AppConfig
    from core.course_storage_config import CourseStorageConfig
    from core.database import Database
    from content.textbook_catalog import digest
    from repositories.course_storage_repository import CourseStorageRepository, storage_id_for
    from repositories.textbook_repository import TextbookRepository
    from scripts.course_storage_releases import delivery_media
    from services.course_file_store import CourseFileStore
    from services.courseware_publish_service import CoursewarePublishService

    source = private_dir(args.source, ROOT / 'courseware/lessons')
    package = private_dir(args.package, ROOT / 'output/courseware-lessons')
    backup = private_dir(args.backup, ROOT / 'output/courseware-backups')
    ledger = private_dir(args.ledger, ROOT / 'output/courseware-production')
    publication = read_json(private_dir(args.publication, ROOT / 'output/courseware-lessons'))
    identity = read_json(package / 'identity.json')
    batch, _ = validate_assignment(read_json(ledger), args.owner, identity, source.name, batch_key=args.batch)
    confirmation = identity['confirmation']
    require(matches_owner_confirmation(batch, confirmation),
            'Packaged owner authorization does not match the ledger')
    require(publication.get('applied') is True and publication.get('status') == 'published', 'Publish receipt required')
    require('ownerWaiver' not in identity and not (package / 'owner-waiver.json').exists(), 'Independent verification required')
    verification = read_json(package / 'verification.json')
    require(verification['verifier']['model'] == 'gpt-6.1-terra'
            and 'gpt-6.1-terra' not in {m.lower() for m in identity['authorModels']}, 'Verifier is not independent')

    db = Database(AppConfig.from_env().DATABASE_URL)
    config = CourseStorageConfig.from_env()
    require(config.mode == 'registry', 'Registry storage is required for remote acceptance')
    storage = storage_id_for(config.endpoint, config.bucket, config.region)
    registry = CourseStorageRepository(db)
    store = CourseFileStore(config=config, repository=registry)
    service = CoursewarePublishService(TextbookRepository(db), classroom_directory=ROOT / CLASSROOMS)

    def check_release(directory):
        return service.check(directory, confirmation=confirmation)

    def require_current():
        state = service.status(content_key=publication['contentKey'])
        require(state['status'] == 'published' and state['classroomId'] == publication['classroomId'],
                'Course is no longer published')

    checked = check_release(package)
    require(checked['ok'] and all(checked['gates'][f'G{i}']['passed'] for i in range(9)), 'G0–G8 did not pass')
    release = checked['prepared']['release']
    manifest = checked['prepared']['manifest']
    unit_id = next(unit['unitId'] for unit in manifest['units']
                   if any(lesson['nodeId'] == identity['nodeId'] for lesson in unit['lessons']))
    directory_query = urlencode({'editionId': identity['editionId'], 'revisionId': identity['revisionId'], 'unitId': unit_id})
    fields = ('contentKey', 'classroomId', 'releaseSha256')
    expected = dict(zip(fields, (release['contentKey'], release['classroomId'], release['sha256'])))
    require(all(publication[k] == v for k, v in expected.items()), 'Package does not match the publish receipt')
    require_current()

    timings = {}

    def step(name, action):
        started = time.monotonic()
        print(name, file=sys.stderr, flush=True)
        result = action()
        timings[name] = round(time.monotonic() - started, 3)
        return result

    def complete(receipt):
        def update(data):
            record_completion(data, args.owner, identity, source.name, receipt, batch_key=args.batch)
            if 'cosRecovery' in receipt:
                _, assignment = validate_assignment(data, args.owner, identity, source.name, batch_key=args.batch)
                secondary = receipt['cosRecovery']
                assignment['secondBackupReceipt'] = secondary['receiptPath']
                timings = assignment['timingsSeconds']
                timings.update(secondary['timingsSeconds'])
                assignment['slowestStep'] = max(timings, key=timings.get)
                if assignment['localCleanup'] == 'awaiting_independent_second_backup':
                    assignment['localCleanup'] = 'awaiting_dedicated_cleanup'

        update_ledger(ledger, update)
        if args.verify_cos:
            secondary = verify_cos_recovery(backup, workspace, receipt, package, check_release, require_current)
            receipt = {**receipt, 'cosRecovery': secondary}
            update_ledger(ledger, update)
        return receipt

    backup.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(backup.with_suffix('.lock'), exclusive=True):
        scope = step('archiveRegistration', lambda: wait_for_scope(registry, storage, release, timeout=args.wait_seconds))
        inventory = delivery_media(release)
        receipt_path = backup / 'post-publish-receipt.json'
        require(not receipt_path.is_symlink(), 'Linked post-publish receipt')
        if receipt_path.exists():
            receipt = read_json(receipt_path)
            schema = receipt['schemaVersion']
            validate_delivery(receipt, expected, scope, inventory,
                              directory_identity=identity if schema == COMPLETION_SCHEMA else None)
            require(schema in ('mira.courseware.post-publish.v1', COMPLETION_SCHEMA) and receipt['ok'] is True
                    and receipt['recovery']['portableRestore'] is True
                    and receipt['recovery']['restoredReleaseSha256'] == release['sha256']
                    and receipt['receiptPath'] == receipt_path.relative_to(ROOT).as_posix(),
                    'Post-publish receipt does not prove an independent recovery')
            require_current()
            return complete(receipt)

        def playback():
            ensure_state()
            return command_json('node', 'courseware/tools/student_playback.mjs', release['contentKey'],
                                release['classroomId'], directory_query, identity['nodeId'])

        def collect_delivery():
            media = step('remoteMediaReadback', lambda: readback(scope, release, inventory, store,
                                                               classroom_digest=digest))
            student = step('studentPlayback', playback)
            require_current()
            return {'archiveReadback': media, 'studentPlayback': student, 'timingsSeconds': timings,
                    'verifiedAt': datetime.now(timezone.utc).isoformat()}

        if args.delivery_proof:
            proof_path = private_dir(args.delivery_proof, ROOT / 'output/courseware-backups')
            collect = None
        else:
            proof_path = backup.with_name(backup.name + '-delivery-v2.json')
            collect = collect_delivery
        delivery = delivery_checkpoint(proof_path, expected, scope, inventory, collect, directory_identity=identity)
        timings.update(delivery['timingsSeconds'])
        evidence = [private_dir(path, ROOT / 'output/courseware-lessons') for path in args.evidence]
        inputs = {source, package, *evidence}
        publish_receipt = private_dir(args.publication, ROOT / 'output/courseware-lessons')
        if not any(publish_receipt.is_relative_to(path) for path in inputs):
            inputs.add(publish_receipt)
        roots = sorted(path.relative_to(ROOT).as_posix() for path in inputs)
        uploaded = step('backupUpload', lambda: save_primary_backup(backup, roots))
        require(uploaded['complete'] and SHA.fullmatch(uploaded['archiveSha256']), 'Remote backup did not verify')
        download = workspace / 'download'

        def restore():
            downloaded = command_json('node', 'courseware/tools/store_backup.mjs', 'fetch',
                '--receipt', str(backup / 'remote-verification.json'), '--destination', str(download))
            require(downloaded['complete'] and all(downloaded[field] == uploaded[field]
                    for field in ('archiveSha256', 'storage', 'files')),
                    'Independent download did not match the uploaded archive')
            return verify_restore(download, workspace, {**expected, **downloaded}, package, check_release)

        recovery = step('downloadAndRestore', restore)
        require_current()
        receipt = {'schemaVersion': COMPLETION_SCHEMA, 'ok': True, **expected,
                   'verifiedAt': datetime.now(timezone.utc).isoformat(), 'archiveReadback': delivery['archiveReadback'],
                   'studentPlayback': delivery['studentPlayback'], 'recovery': recovery, 'timingsSeconds': timings,
                   'receiptPath': receipt_path.relative_to(ROOT).as_posix()}
        write_json(receipt_path, receipt)
        return complete(receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'package', 'backup', 'publication'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--ledger', type=Path, default=ROOT / 'output/courseware-production/production-run.json')
    parser.add_argument('--batch', default=DEFAULT_BATCH, help='top-level production ledger key for this assignment')
    parser.add_argument('--evidence', type=Path, action='append', default=[])
    parser.add_argument('--delivery-proof', type=Path,
                        help='reuse an existing exact delivery receipt when the recovery destination changes')
    parser.add_argument('--verify-cos', action='store_true',
                        help='also download and independently restore this same backup from the configured COS target')
    parser.add_argument('--owner', required=True)
    parser.add_argument('--wait-seconds', type=int, default=600)
    args = parser.parse_args()
    try:
        workspace = Path(os.environ['MIRA_TASK_TMPDIR']).resolve(strict=True)
        require(workspace.is_dir() and workspace.stat().st_mode & 0o077 == 0, 'Private task workspace required')
        print(json.dumps(finalize(args, workspace), ensure_ascii=False))
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f'Post-publication verification failed: {error}\n')


if __name__ == '__main__':
    main()
