#!/usr/bin/env python3
"""Supplement verified current course archives with their exact fixed materials.

Inventory is read-only. --apply uploads immutable per-course ZIP supplements,
verifies remote bytes, then activates only previously missing file heads.
Original files, course publication, learning records and dynamic state stay put.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import zipfile

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from core.config import AppConfig
from core.course_storage_config import CourseStorageConfig
from core.database import Database
from repositories.course_storage_repository import CourseStorageRepository, normalize_source_path, storage_id_for
from scripts.course_storage_releases import _formal_authorities, _other_published_courses, read_only_connection
from scripts.complete_course_storage_registry import json_bytes, read_stable, write_private, private_workspace, no_links
from services.course_archive_exporter import CourseArchiveExporter, _check_public, _safe_relative, _require_private_space
from services.course_archive_queue import NodeArchiveClient
from services.course_file_store import CourseFileStore, _RangeFile, _RemoteObject

SCHEMA = 'mira.course-fixed-materials.supplement.v1'
SOURCE_KIND = 'course_material_supplement'
MATERIAL_ROOT = 'openmaic-runtime/.runtime/OpenMAIC/data/materials/'
MAX_BYTES = 64 * 1024 * 1024


def require(value, code):
    if not value:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parsed(value):
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def current_courses(database):
    """Read minimal frozen binding fields, never load or regenerate course bodies."""
    with read_only_connection(database) as conn:
        books = conn.execute("""SELECT b.content_key,b.course_id,b.course_version,
            JSON_UNQUOTE(JSON_EXTRACT(b.review_json,'$.release.sha256')) AS release_sha,
            p.classroom_id AS authoring_classroom,
            JSON_UNQUOTE(JSON_EXTRACT(p.input_json,'$.authoring.sessionId')) AS session_id,
            JSON_UNQUOTE(JSON_EXTRACT(p.input_json,'$.authoring.stageId')) AS stage_id
            FROM learning_textbook_course_builds b
            JOIN learning_courses c ON c.id=b.course_id AND c.version=b.course_version
            JOIN learning_textbook_revisions r ON r.edition_id=b.edition_id AND r.revision_id=b.revision_id
            LEFT JOIN learning_textbook_course_previews p
              ON p.preview_key=JSON_UNQUOTE(JSON_EXTRACT(b.input_json,'$.previewKey'))
            WHERE b.status='published' AND c.status='published' AND c.quality_status='released'
              AND c.retired_at IS NULL AND r.retired_at IS NULL""").fetchall()
        result = {}
        for b in books:
            result[(b['course_id'], b['course_version'])] = {
                'courseId': b['course_id'], 'courseVersion': b['course_version'],
                'contentKey': b['content_key'], 'classroomId': 'tbpub_' + b['content_key'][:24],
                'sourceDigest': b['release_sha'], 'sessionId': b['session_id'],
                'stageId': b['stage_id'] or b['authoring_classroom'], 'sourceKind': 'textbook_release'}
        for c in _other_published_courses(conn):
            authorities = _formal_authorities(conn, c)
            require(len(authorities) == 1, 'materials_formal_binding_ambiguous')
            a = authorities[0]
            result[(c['courseId'], c['courseVersion'])] = {
                'courseId': c['courseId'], 'courseVersion': c['courseVersion'],
                'contentKey': None, 'classroomId': a['upstream_classroom_id'],
                'sourceDigest': a['publication_receipt_hash'], 'sessionId': None,
                'stageId': a['upstream_classroom_id'], 'sourceKind': 'formal_release'}
        previews = conn.execute("""SELECT p.preview_key,p.classroom_id,p.classroom_sha256,
            JSON_UNQUOTE(JSON_EXTRACT(p.input_json,'$.authoring.sessionId')) AS session_id,
            JSON_UNQUOTE(JSON_EXTRACT(p.input_json,'$.authoring.stageId')) AS stage_id
            FROM learning_textbook_course_previews p
            JOIN learning_textbook_revisions r ON r.edition_id=p.edition_id AND r.revision_id=p.revision_id
            WHERE r.retired_at IS NULL AND p.status IN ('preview_ready','review_required')
              AND p.classroom_id IS NOT NULL AND p.classroom_sha256 IS NOT NULL""").fetchall()
        for p in previews:
            cid, version = 'textbook-preview:' + p['preview_key'], 'saved-' + p['classroom_sha256'][:16]
            result[(cid, version)] = {'courseId': cid, 'courseVersion': version,
                'contentKey': None, 'classroomId': p['classroom_id'],
                'sourceDigest': p['classroom_sha256'], 'sessionId': p['session_id'],
                'stageId': p['stage_id'] or p['classroom_id'], 'sourceKind': 'textbook_preview'}
    return result


def selected_bindings(database, state_root):
    current = current_courses(database)
    selected, published, seen = [], set(), set()
    for path in sorted((state_root / 'archive-queue/items').glob('*.json')):
        job = parsed(read_stable(path)[0])
        if job.get('priority', 99) > 1 or job.get('status') != 'complete':
            continue
        identity = job['identity']
        key = identity.get('courseId'), identity.get('courseVersion')
        binding = current.get(key)
        if binding is None:
            continue
        require(identity['sourceDigest'] == binding['sourceDigest']
                and identity['sourceKind'] == binding['sourceKind'], 'materials_current_source_changed')
        index_raw, _ = read_stable(Path(job['export']['indexPath']))
        require(sha(index_raw) == job['export']['indexSha256'], 'materials_parent_index_changed')
        index = parsed(index_raw)
        receipt_raw, _ = read_stable(Path(job['receiptPath']))
        require(sha(receipt_raw) == job['receiptSha256'], 'materials_parent_receipt_changed')
        receipt = parsed(receipt_raw)
        require(index['complete'] is True and receipt.get('complete') is True
                and receipt['indexSha256'] == sha(index_raw)
                and all(index.get(k) == binding[k] for k in ('courseId','courseVersion','classroomId','sourceDigest')),
                'materials_parent_archive_unverified')
        directory = index['objectDirectory']
        _safe_relative(directory)
        require(len(directory.split('/')) == 5, 'materials_parent_directory_invalid')
        require(key not in seen, 'materials_current_archive_ambiguous')
        seen.add(key)
        if binding['sourceKind'] != 'textbook_preview':
            published.add(key)
        selected.append({**binding, 'storageDirectory': directory,
            'parentArchiveId': index['archiveId'], 'parentIndexSha256': sha(index_raw)})
    expected = {key for key, b in current.items() if b['sourceKind'] != 'textbook_preview'}
    require(published == expected, 'materials_published_parent_archive_missing')
    return sorted(selected, key=lambda b: (b['sourceKind'] == 'textbook_preview', b['storageDirectory'], b['courseId']))


def request_for(binding):
    stage = binding.get('stageId')
    if stage in (None, '', 'null'):
        return None
    request = {'stageId': stage, 'bindingKind': 'frozen_authoring'}
    if binding.get('sessionId') not in (None, '', 'null'):
        request['sessionId'] = binding['sessionId']
    return request


def inventory(exporter, binding, store):
    request = request_for(binding)
    if request is None:
        return {'schemaVersion': SCHEMA, 'binding': binding, 'files': [],
            'dependencySha256': sha(json_bytes([])), 'localSnapshots': {}}, {}
    source = exporter._material_inventory(request)
    require(source.get('schemaVersion') == 'mira.course-material-inventory.v1'
            and isinstance(source.get('materials'), list), 'materials_inventory_invalid')
    from services.course_archive_exporter import validate_material_bytes
    files, snapshots, raws = [], {}, {}
    for item in sorted(source['materials'], key=lambda m: m['sourcePath']):
        relative = normalize_source_path(item['sourcePath'])
        require(relative.startswith(MATERIAL_ROOT), 'materials_source_outside_library')
        no_links(ROOT / relative, ROOT)
        entry = store.resolve(ROOT / relative)
        if entry:
            raw = store.read_bytes(ROOT / relative, expected_sha256=entry['sha256'], max_bytes=MAX_BYTES)
            before = None
        else:
            raw, before = read_stable(ROOT / relative)
        require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_BYTES, 'materials_source_size_invalid')
        mime = validate_material_bytes(raw, item['mimeType'])
        if item.get('byteSize') is not None:
            require(len(raw) == item['byteSize'], 'materials_source_length_mismatch')
        if item.get('sha256'):
            require(sha(raw) == item['sha256'], 'materials_source_digest_mismatch')
        record = {'sourcePath': relative, 'archivePath': '原稿/' + relative,
            'sha256': sha(raw), 'byteSize': len(raw), 'mimeType': mime,
            'displayName': item.get('displayName') or Path(relative).name,
            'disposition': 'registered' if entry else 'zip'}
        if entry:
            require((entry['sha256'], entry['byteSize'], entry['mimeType']) ==
                    (record['sha256'], record['byteSize'], record['mimeType']), 'materials_registered_source_conflict')
            record['locator'] = entry['locator']
        files.append(record)
        snapshots[relative] = list(before) if before is not None else None
        if entry is None:
            raws[relative] = raw
    require(len({r['sourcePath'] for r in files}) == len(files), 'materials_inventory_duplicate')
    result = {'schemaVersion': SCHEMA, 'binding': binding,
        'dependencySha256': source['dependencySha256'], 'files': files, 'localSnapshots': snapshots}
    _check_public(result)
    return result, raws


def prepare(plan, raws, state_root):
    manifest = {k: plan[k] for k in ('schemaVersion','binding','dependencySha256','files')}
    manifest.update(sourceKind=SOURCE_KIND, complete=True)
    manifest_raw = json_bytes(manifest)
    digest = sha(manifest_raw)
    archive_id = 'materials-' + digest[:24]
    stage = private_workspace(ROOT, state_root / 'archives' / archive_id)
    stage.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(not stage.stat().st_mode & 0o077, 'materials_workspace_not_private')
    manifest_path, zip_path = stage / 'manifest.json', stage / 'materials.zip'
    _require_private_space(stage, sum(len(raw) for raw in raws.values()) + len(manifest_raw), phase='materials')
    write_private(stage / 'source-plan.json', json_bytes(plan))
    write_private(manifest_path, manifest_raw)
    if not zip_path.exists():
        partial = zip_path.with_suffix('.zip.part')
        with zipfile.ZipFile(partial, 'x', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            os.chmod(partial, 0o600)
            archive.writestr('manifest.json', manifest_raw)
            for item in plan['files']:
                if item['disposition'] == 'zip':
                    archive.writestr(item['archivePath'], raws[item['sourcePath']])
        os.replace(partial, zip_path)
    require(not zip_path.is_symlink(), 'materials_zip_symlink')
    zip_raw, _ = read_stable(zip_path)
    verify_zip(zipfile.ZipFile(zip_path), manifest, manifest_raw)
    b = plan['binding']
    prefix = b['storageDirectory'] + '/制作材料-' + digest[:12]
    entries = [dict(localPath=str(path), relativePath=prefix + suffix, sha256=sha(raw),
                    byteSize=len(raw), mimeType=mime)
               for path, raw, suffix, mime in ((zip_path, zip_raw, '.zip', 'application/zip'),
                   (manifest_path, manifest_raw, '.json', 'application/json'))]
    index = {'schemaVersion': 'mira.course-archive.export.v1', 'archiveId': archive_id,
        'complete': True, 'missingSources': [], 'sourceKind': SOURCE_KIND,
        'sourceDigest': digest, 'courseId': b['courseId'], 'courseVersion': b['courseVersion'],
        'classroomId': b['classroomId'], 'contentKey': b.get('contentKey'),
        'objectDirectory': b['storageDirectory'], 'manifestPath': str(manifest_path),
        'zip': {'path': str(zip_path), 'sha256': sha(zip_raw), 'byteSize': len(zip_raw)},
        'generatedPublicFiles': entries}
    path = stage / 'index.json'
    write_private(path, json_bytes(index))
    return path, index, manifest, manifest_raw


def verify_zip(archive, manifest, raw):
    with archive:
        records = [r for r in manifest['files'] if r['disposition'] == 'zip']
        names = ['manifest.json'] + [r['archivePath'] for r in records]
        require(len(archive.infolist()) == len(names) and set(archive.namelist()) == set(names),
                'materials_zip_members_invalid')
        require(archive.read('manifest.json') == raw, 'materials_zip_manifest_changed')
        for item in records:
            info = archive.getinfo(item['archivePath'])
            require(info.file_size == item['byteSize'] and not info.flag_bits & 1
                    and not info.is_dir() and stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG),
                    'materials_zip_member_invalid')
            require(sha(archive.read(info)) == item['sha256'], 'materials_zip_member_changed')


def verify_sources(plan):
    for relative, expected in plan['localSnapshots'].items():
        if expected is not None:
            raw, _ = read_stable(ROOT / relative, expected)
            item = next(r for r in plan['files'] if r['sourcePath'] == relative)
            require(sha(raw) == item['sha256'], 'materials_source_changed')


def apply(plan, raws, *, database, config, registry, exporter, store, client, state_root):
    binding = plan['binding']
    def recheck():
        require(binding in selected_bindings(database, state_root), 'materials_current_binding_changed')
        request = request_for(binding)
        require(request is not None and exporter._material_inventory(request)['dependencySha256'] == plan['dependencySha256'],
                'materials_current_dependencies_changed')
        verify_sources(plan)
    recheck()
    index_path, index, manifest, manifest_raw = prepare(plan, raws, state_root)
    receipt = client.upload(index_path)
    require(receipt.get('complete') is True and receipt['indexSha256'] == sha(read_stable(index_path)[0])
            and receipt['storage'] == {'endpoint': config.endpoint.rstrip('/'), 'bucket': config.bucket, 'region': config.region},
            'materials_upload_not_verified')
    objects = {o['objectKey']: o for o in receipt['objects']}
    zip_entry = next(e for e in index['generatedPublicFiles'] if e['mimeType'] == 'application/zip')
    descriptor = objects[zip_entry['relativePath']]
    require(descriptor['sha256'] == index['zip']['sha256'] and descriptor['byteSize'] == index['zip']['byteSize'],
            'materials_remote_zip_unverified')
    locator = {'kind': 'zip_member', 'objectKey': descriptor['objectKey'], 'etag': descriptor['etag'],
        'archiveSha256': descriptor['sha256'], 'archiveByteSize': descriptor['byteSize']}
    if descriptor.get('versionId'):
        locator['versionId'] = descriptor['versionId']
    verify_zip(zipfile.ZipFile(_RangeFile(_RemoteObject(config, locator, descriptor['byteSize']))), manifest, manifest_raw)
    files = []
    for item in plan['files']:
        existing = store.resolve(ROOT / item['sourcePath'])
        if existing:
            require((existing['sha256'], existing['byteSize'], existing['mimeType']) ==
                    (item['sha256'], item['byteSize'], item['mimeType']), 'materials_current_head_changed')
        files.append({**{k: item[k] for k in ('sourcePath','sha256','byteSize','mimeType')},
            'locator': item.get('locator') or {**locator, 'memberPath': item['archivePath']}})
    recheck()
    storage_id = storage_id_for(config.endpoint, config.bucket, config.region)
    key = sha(('mira.course-materials:' + storage_id + ':' + sha(manifest_raw)).encode())
    metadata = {'scopeKey': key, 'sourceKind': SOURCE_KIND, 'sourceDigest': sha(manifest_raw),
        'courseId': binding['courseId'], 'courseVersion': binding['courseVersion'],
        'classroomId': binding['classroomId'], 'storageDirectory': binding['storageDirectory'],
        'parentArchiveId': binding['parentArchiveId'], 'materialDependencySha256': plan['dependencySha256']}
    if binding.get('contentKey'):
        metadata['contentKey'] = binding['contentKey']
    registry.register_scope(metadata, files, storage_id, activate=False)
    activation = registry.activate_missing_heads(key, storage_id)
    for item in files:
        head = store.resolve(ROOT / item['sourcePath'])
        require(head is not None and head['sha256'] == item['sha256'], 'materials_current_head_changed')
        require(store.read_bytes(ROOT / item['sourcePath'], expected_sha256=item['sha256'],
                expected_bytes=item['byteSize'], max_bytes=MAX_BYTES) is not None, 'materials_registered_read_failed')
    result = {'schemaVersion': SCHEMA, 'scopeKey': key, 'complete': True,
        'courseId': binding['courseId'], 'files': len(files), 'newHeads': activation['activated'],
        'verifiedAt': datetime.now(timezone.utc).isoformat()}
    receipt_path = index_path.parent / 'registered.json'
    if receipt_path.exists():
        prior = parsed(read_stable(receipt_path)[0])
        require(all(prior.get(k) == result[k] for k in ('schemaVersion','scopeKey','complete','courseId','files'))
                and type(prior.get('newHeads')) is int and 0 <= prior['newHeads'] <= len(files),
                'materials_registration_receipt_changed')
    else:
        write_private(receipt_path, json_bytes(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--course-id', help='Pilot or resume one exact current course')
    args = parser.parse_args()
    try:
        app = AppConfig.from_env()
        config = CourseStorageConfig.from_env()
        require(config.mode == 'registry', 'materials_registry_mode_required')
        database = Database(app.DATABASE_URL)
        registry = CourseStorageRepository(database)
        store = CourseFileStore(config=config, repository=registry)
        exporter = CourseArchiveExporter()
        state = ROOT / 'backend/data/course-storage'
        bindings = selected_bindings(database, state)
        if args.course_id:
            bindings = [b for b in bindings if b['courseId'] == args.course_id]
            require(len(bindings) == 1, 'materials_exact_current_course_required')
        client = NodeArchiveClient(project_root=ROOT, node=os.environ.get('COURSE_ARCHIVE_NODE', 'node'))
        counts = Counter()
        sources = set()
        for binding in bindings:
            plan, raws = inventory(exporter, binding, store)
            if not plan['files']:
                continue
            counts['courses'] += 1
            counts['references'] += len(plan['files'])
            sources.update(item['sourcePath'] for item in plan['files'])
            if args.apply:
                scopes = registry.find_scopes(storage_id=storage_id_for(config.endpoint, config.bucket, config.region),
                    course_id=binding['courseId'], course_version=binding['courseVersion'])
                if (all(item['disposition'] == 'registered' for item in plan['files'])
                        and any(scope['metadata'].get('sourceKind') == SOURCE_KIND
                            and scope['metadata'].get('materialDependencySha256') == plan['dependencySha256']
                            and scope['metadata'].get('parentArchiveId') == binding['parentArchiveId'] for scope in scopes)):
                    counts['alreadyVerified'] += 1
                    continue
                result = apply(plan, raws, database=database, config=config, registry=registry,
                    exporter=exporter, store=store, client=client, state_root=state)
                counts['newHeads'] += result['newHeads']
                print(json.dumps({'courseId': binding['courseId'], 'files': result['files'],
                    'newHeads': result['newHeads'], 'complete': True}, ensure_ascii=False), flush=True)
        print(json.dumps({'ok': True, 'applied': args.apply, 'selectedArchives': len(bindings),
            'uniqueMaterialFiles': len(sources), **counts}, ensure_ascii=False))
        return 0
    except Exception as error:
        # Do not expose SQL, private paths, raw material data or provider errors.
        code = str(error) if isinstance(error, ValueError) and str(error).startswith(('materials_', 'course_material_', 'supplement_', 'archive_')) else type(error).__name__
        print(json.dumps({'ok': False, 'error': code}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
