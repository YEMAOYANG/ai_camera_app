#!/usr/bin/env python3
"""Inventory and supplement only current published adaptive-activity dependencies.

No generator runs here. prepare writes private artifacts only; the explicit
transfer-register command uploads and verifies before registering immutable
versions and atomically activating unchanged heads.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from content import textbook_journey as journey
from content.textbook_catalog import digest
from content.textbook_journey_registry import definitions
from core.config import AppConfig
from core.course_storage_config import CourseStorageConfig
from core.database import Database
from repositories.course_storage_repository import CourseStorageRepository, normalize_source_path, storage_id_for, storage_identity
from scripts.complete_course_storage_registry import (
    SupplementError, require, json_bytes, parse_json, sha, read_stable, no_links,
    inspect_source, write_private, private_workspace, verify_zip, original_directory,
    registered_media_aliases,
)
from scripts.course_storage_releases import _current_keys, _validated_release, parsed, read_only_connection
from scripts.prepare_textbook_journey_audio import texts as journey_texts
from scripts.prepare_learning_navigation import texts as navigation_texts
from services.course_archive_exporter import MAX_FILES, _check_public, _safe_relative
from services.course_archive_queue import NodeArchiveClient
from services.course_file_store import CourseFileStore, _RangeFile, _RemoteObject

SCHEMA = 'mira.course-runtime-dependency.supplement.v1'
SOURCE_KIND = 'runtime_dependency_supplement'
REASON = 'current-published-activity-and-enumerated-validator-dependencies'
ACTIVITIES = Path('backend/content/textbooks/activities')
NAVIGATION_POLICY = Path('backend/content/learning_navigation.v1.json')
RESERVE_BYTES = 10214473604
SHA = re.compile(r'[a-f0-9]{64}\Z')


def allowed_texts(spec):
    """Use the original pack compiler's enumeration, never an invented template."""
    require(spec.renderer == 'tiandiren' and spec.audio_pack == 'audio-v2',
            'activity_pack_compiler_not_registered')
    values = journey_texts(plan=spec.plan, flow=spec.flow)
    require(values and all(isinstance(t, str) and t for t in values), 'activity_pack_texts_invalid')
    return values


def _raw_database(value):
    return value.encode() if isinstance(value, str) else json_bytes(value)


def load_current(database, registry, store):
    """Freeze the current publication set; fully validate every supported release."""
    current, active = [], []
    storage_id = storage_id_for(store.config.endpoint, store.config.bucket, store.config.region)
    with read_only_connection(database) as conn:
        for key in _current_keys(conn, None):
            build = conn.execute('SELECT * FROM learning_textbook_course_builds WHERE content_key=?', (key,)).fetchone()
            require(build is not None, 'activity_current_build_missing')
            release = parsed(build['review_json']).get('release')
            require(isinstance(release, dict) and SHA.fullmatch(str(release.get('sha256', '')))
                    and digest({k: v for k, v in release.items() if k != 'sha256'}) == release['sha256']
                    and release.get('contentKey') == key, 'activity_release_identity_invalid')
            identity = {'contentKey': key, 'courseId': build['course_id'], 'courseVersion': build['course_version'],
                'classroomId': release['classroomId'], 'originalSourceDigest': release['sha256'],
                'frozenInputSha256': sha(_raw_database(build['input_json'])),
                'frozenReviewSha256': sha(_raw_database(build['review_json']))}
            current.append(identity)
            if not journey.supported(release):
                continue
            _, _, verified, _ = _validated_release(conn, key)
            require(verified == release, 'activity_current_release_changed')
            spec = journey.definition(release=verified)
            directory, _ = original_directory(registry, storage_id, identity)
            active.append((identity, verified, directory, spec))
    require(current and active, 'activity_no_current_supported_release')
    return current, active


def _read_source(project_root, relative, registry, storage_id, store):
    relative = normalize_source_path(relative)
    path = project_root / relative
    no_links(path, project_root)
    existing = registry.resolve(relative, storage_id=storage_id)
    if path.exists():
        raw, snapshot = read_stable(path)
    else:
        require(existing is not None, 'activity_source_missing')
        raw = store.read_bytes(path, expected_sha256=existing['sha256'], expected_bytes=existing['byteSize'])
        require(raw is not None, 'activity_registered_source_missing')
        snapshot = None
    inspect_source(raw, path)
    mime = 'audio/wav' if path.suffix == '.wav' else 'application/json'
    require(path.suffix in {'.wav', '.json'}, 'activity_source_format_invalid')
    if existing is not None:
        require((existing['sha256'], existing['byteSize'], existing['mimeType']) == (sha(raw), len(raw), mime),
                'activity_registered_source_conflict')
        verified = store.read_bytes(path, expected_sha256=sha(raw), expected_bytes=len(raw))
        require(verified == raw, 'activity_registered_source_remote_mismatch')
    return {'sourcePath': relative, 'sha256': sha(raw), 'byteSize': len(raw), 'mimeType': mime,
            'archivePath': '原稿/' + relative, 'disposition': 'already_registered' if existing else 'zip',
            **({'locator': existing['locator']} if existing else {})}, raw, snapshot


def _rule_paths(registry_data, all_specs):
    paths = {ACTIVITIES / 'registry.v1.json'}
    for row in registry_data['definitions']:
        for name in ('plan', 'flow'):
            value = row[name]['file']
            _safe_relative(value)
            require(Path(value).suffix == '.json', 'activity_rule_path_invalid')
            paths.add(ACTIVITIES / value)
    if any(spec.renderer == 'tiandiren' for spec in all_specs):
        paths.add(ACTIVITIES / 'tiandiren.visuals.v1.json')
    return sorted(p.as_posix() for p in paths)


def inventory_for_course(project_root, identity, release, storage_directory, current, registry, store, *, spec=None, all_specs=None):
    project_root = Path(project_root).resolve()
    storage_id = storage_id_for(store.config.endpoint, store.config.bucket, store.config.region)
    spec = spec or journey.definition(release=release)
    all_specs = tuple(all_specs or definitions())
    require(spec.plan['releaseSha256'] == release['sha256'] == identity['originalSourceDigest'],
            'activity_definition_release_mismatch')
    require(identity in current and len({r['contentKey'] for r in current}) == len(current),
            'activity_current_selection_invalid')
    _safe_relative(storage_directory)
    require(len(storage_directory.split('/')) == 5, 'activity_storage_directory_invalid')
    records, snapshots, blocked, raw_sources = {}, {}, [], {}

    def take(relative):
        relative = str(relative)
        if relative not in records:
            record, raw, snapshot = _read_source(project_root, relative, registry, storage_id, store)
            records[relative], snapshots[relative], raw_sources[relative] = record, snapshot, raw
        return records[relative], raw_sources[relative]

    registry_record, registry_raw = take((ACTIVITIES / 'registry.v1.json').as_posix())
    registry_data = parse_json(registry_raw)
    rules = _rule_paths(registry_data, all_specs)
    for relative in rules:
        take(relative)
    # The definition reader above preserves every original plan/flow SHA gate.
    for row in registry_data['definitions']:
        for name in ('plan', 'flow'):
            record = records[(ACTIVITIES / row[name]['file']).as_posix()]
            require(record['sha256'] == row[name]['sha256'], 'activity_rule_sha_mismatch')
    policy_path = project_root / NAVIGATION_POLICY
    no_links(policy_path, project_root)
    policy_raw, policy_stat = read_stable(policy_path)
    inspect_source(policy_raw, policy_path)
    nav = navigation_texts(parse_json(policy_raw))
    packs = []
    for pack, texts in ((spec.audio_pack, allowed_texts(spec)), ('navigation-audio-v1', nav)):
        require(re.fullmatch(r'[a-z0-9-]+', pack), 'activity_pack_invalid')
        manifest_path = ACTIVITIES / pack / 'manifest.json'
        manifest_record, manifest_raw = take(manifest_path.as_posix())
        manifest = parse_json(manifest_raw)
        expected_assets = []
        for text in sorted(texts):
            asset = journey.audio_id(text) + '.wav'
            expected_assets.append(asset)
            entry = manifest.get(asset)
            require(isinstance(entry, dict) and entry.get('text') == text and entry.get('providerId') == 'qwen-tts'
                    and entry.get('fallbackUsed') is False and SHA.fullmatch(str(entry.get('sha256', '')))
                    and type(entry.get('bytes')) is int and 0 < entry['bytes'] <= journey.MAX_AUDIO_BYTES,
                    'activity_allowed_audio_manifest_missing_or_invalid')
            filename = entry.get('file', asset)
            _safe_relative(filename)
            require(Path(filename).name == asset and filename.endswith('.wav'), 'activity_audio_path_invalid')
            relative = (ACTIVITIES / pack / filename).as_posix()
            try:
                record, _ = take(relative)
                require((record['sha256'], record['byteSize']) == (entry['sha256'], entry['bytes']),
                        'activity_audio_receipt_mismatch')
            except (OSError, ValueError) as error:
                blocked.append({'sourcePath': relative, 'reason': str(error) if isinstance(error, SupplementError) else 'activity_source_unavailable'})
        packs.append({'audioPack': pack, 'manifestSha256': manifest_record['sha256'],
                      'allowedTextSetSha256': digest(sorted(texts)), 'allowedAssets': sorted(expected_assets)})
    require(len(records) <= MAX_FILES, 'activity_source_count_exceeded')
    binding = {**identity, 'selectionReason': REASON, 'storageDirectory': storage_directory,
        'currentPublishedCount': len(current), 'currentPublishedSetSha256': digest(current),
        'activityId': spec.plan['id'], 'activityDefinitionSha256': digest({'plan': spec.plan, 'flow': spec.flow,
            'renderer': spec.renderer, 'audioPack': spec.audio_pack}), 'packs': packs,
        'ruleFiles': [{k: records[p][k] for k in ('sourcePath', 'sha256', 'byteSize')} for p in rules],
        'navigationPolicySha256': sha(policy_raw), 'sourceRoots': [ACTIVITIES.as_posix()]}
    _check_public(binding)
    ordered = sorted(records.values(), key=lambda r: r['sourcePath'])
    aliases = registered_media_aliases(registry, storage_id, binding, ordered)
    for record in ordered:
        alias = aliases.get(record['sha256'])
        if record['disposition'] != 'zip' or record['mimeType'] != 'audio/wav' or alias is None:
            continue
        require((alias['byteSize'], alias['mimeType']) == (record['byteSize'], record['mimeType']), 'activity_alias_identity_mismatch')
        raw = store.read_bytes(project_root / alias['sourcePath'], expected_sha256=record['sha256'], expected_bytes=record['byteSize'])
        require(raw is not None and sha(raw) == record['sha256'] and len(raw) == record['byteSize'], 'activity_alias_remote_hash_mismatch')
        record.update(disposition='reuse_registered', locator=alias['locator'], verifiedAliasSourcePath=alias['sourcePath'])
    return {'binding': binding, 'files': ordered, 'sourceStats': snapshots, 'blocked': blocked,
        'platformDependency': {'sourcePath': NAVIGATION_POLICY.as_posix(), 'sha256': sha(policy_raw), 'stat': policy_stat}}


def assert_sources(plan, project_root, registry, store):
    require(not plan['blocked'], 'activity_sources_blocked')
    root = Path(project_root).resolve()
    records = plan['files']
    require(records and len(records) <= MAX_FILES and len({r['sourcePath'] for r in records}) == len(records)
            and set(plan['sourceStats']) == {r['sourcePath'] for r in records}, 'activity_source_set_invalid')
    by_path, raw_sources = {r['sourcePath']: r for r in records}, {}
    for record in records:
        relative = normalize_source_path(record['sourcePath'])
        require(relative.startswith(ACTIVITIES.as_posix() + '/') and record['archivePath'] == '原稿/' + relative
                and record['disposition'] in {'zip', 'already_registered', 'reuse_registered'}, 'activity_source_record_invalid')
        path = root / relative
        no_links(path, root)
        expected = plan['sourceStats'][relative]
        if expected is not None:
            raw, _ = read_stable(path, expected)
        else:
            require(not path.exists(), 'activity_local_source_appeared')
            raw = store.read_bytes(path, expected_sha256=record['sha256'], expected_bytes=record['byteSize'])
            require(raw is not None, 'activity_registered_source_missing')
        require((sha(raw), len(raw)) == (record['sha256'], record['byteSize']), 'activity_source_hash_changed')
        require(record['mimeType'] == ('audio/wav' if path.suffix == '.wav' else 'application/json')
                and path.suffix in {'.wav', '.json'}, 'activity_source_record_invalid')
        inspect_source(raw, path)
        raw_sources[relative] = raw
    binding = plan['binding']
    require(binding.get('selectionReason') == REASON and binding.get('sourceRoots') == [ACTIVITIES.as_posix()],
            'activity_selection_invalid')
    selected = {r['sourcePath'] for r in binding['ruleFiles']}
    require(len(selected) == len(binding['ruleFiles']), 'activity_source_set_invalid')
    for rule in binding['ruleFiles']:
        record = by_path.get(rule['sourcePath'])
        require(record is not None and all(record[k] == rule[k] for k in ('sha256', 'byteSize')),
                'activity_rule_sha_mismatch')
    for pack in binding['packs']:
        manifest_path = (ACTIVITIES / pack['audioPack'] / 'manifest.json').as_posix()
        selected.add(manifest_path)
        require(manifest_path in raw_sources and sha(raw_sources[manifest_path]) == pack['manifestSha256'], 'activity_pack_manifest_changed')
        manifest = parse_json(raw_sources[manifest_path])
        require(len(set(pack['allowedAssets'])) == len(pack['allowedAssets']), 'activity_pack_selection_invalid')
        for asset in pack['allowedAssets']:
            entry = manifest[asset]
            _safe_relative(entry['file'])
            relative = (ACTIVITIES / pack['audioPack'] / entry['file']).as_posix()
            selected.add(relative)
            require(relative in by_path and (by_path[relative]['sha256'], by_path[relative]['byteSize']) ==
                    (entry['sha256'], entry['bytes']), 'activity_audio_receipt_mismatch')
    require(selected == set(by_path), 'activity_selected_source_set_changed')
    policy = plan['platformDependency']
    require(policy['sourcePath'] == NAVIGATION_POLICY.as_posix(), 'activity_platform_dependency_invalid')
    no_links(root / NAVIGATION_POLICY, root)
    raw, _ = read_stable(root / NAVIGATION_POLICY, policy['stat'])
    require(sha(raw) == policy['sha256'] == plan['binding']['navigationPolicySha256'], 'activity_navigation_policy_changed')


def manifest_for(plan):
    files = [r for r in plan['files'] if r['disposition'] != 'already_registered']
    require(files, 'activity_no_missing_originals')
    return {'schemaVersion': SCHEMA, 'sourceKind': SOURCE_KIND, 'complete': True, 'binding': plan['binding'],
        'files': files, 'alreadyRegistered': [{k: r[k] for k in ('sourcePath', 'sha256', 'byteSize')}
            for r in plan['files'] if r['disposition'] == 'already_registered']}


def prepare_supplement(plan, project_root, destination, *, registry, store, reserve_free_bytes=RESERVE_BYTES):
    root = Path(project_root).resolve()
    destination = private_workspace(root, destination)
    assert_sources(plan, root, registry, store)
    manifest = manifest_for(plan)
    _check_public(manifest)
    raw_manifest = json_bytes(manifest)
    checksum = sha(raw_manifest)
    zipped = [r for r in manifest['files'] if r['disposition'] == 'zip']
    require(type(reserve_free_bytes) is int and reserve_free_bytes >= RESERVE_BYTES, 'activity_disk_reserve_invalid')
    upper = sum(r['byteSize'] for r in zipped) + len(raw_manifest) * 3 + len(json_bytes(plan)) + len(zipped) * 1024 + 2 * 1024 ** 2
    existing = destination
    while not existing.exists():
        existing = existing.parent
    space = os.statvfs(existing)
    require(space.f_bavail * space.f_frsize >= upper + reserve_free_bytes, 'activity_disk_reserve_insufficient')
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(not destination.stat().st_mode & 0o077, 'activity_workspace_not_private')
    manifest_path, zip_path = destination / 'manifest.json', destination / 'activity-dependencies.zip'
    write_private(manifest_path, raw_manifest)
    require(not zip_path.is_symlink(), 'activity_private_artifact_symlink')
    if not zip_path.exists():
        partial = zip_path.with_suffix('.zip.part')
        with zipfile.ZipFile(partial, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for name, raw in [('manifest.json', raw_manifest)]:
                info = zipfile.ZipInfo(name)
                info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, (stat.S_IFREG | 0o600) << 16
                archive.writestr(info, raw)
            for record in zipped:
                raw, _ = read_stable(root / record['sourcePath'], plan['sourceStats'][record['sourcePath']])
                require((sha(raw), len(raw)) == (record['sha256'], record['byteSize']), 'activity_source_hash_changed')
                info = zipfile.ZipInfo(record['archivePath'])
                info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, (stat.S_IFREG | 0o600) << 16
                archive.writestr(info, raw)
        os.chmod(partial, 0o600)
        with partial.open('rb') as handle:
            os.fsync(handle.fileno())
        os.replace(partial, zip_path)
    raw_zip, _ = read_stable(zip_path)
    verify_zip(zip_path.open('rb'), manifest, raw_manifest)
    assert_sources(plan, root, registry, store)
    entries = []
    for path, suffix, mime in ((manifest_path, '.json', 'application/json'), (zip_path, '.zip', 'application/zip')):
        raw, _ = read_stable(path)
        entries.append({'localPath': str(path), 'relativePath': plan['binding']['storageDirectory'] + '/互动资源补充-' + checksum[:24] + suffix,
                        'sha256': sha(raw), 'byteSize': len(raw), 'mimeType': mime})
    binding = plan['binding']
    index = {'schemaVersion': 'mira.course-archive.export.v1', 'sourceKind': SOURCE_KIND,
        'archiveId': 'activity-supplement-' + checksum[:24], 'complete': True, 'missingSources': [],
        'courseId': binding['courseId'], 'courseVersion': binding['courseVersion'], 'contentKey': binding['contentKey'],
        'classroomId': binding['classroomId'], 'sourceDigest': checksum, 'objectDirectory': binding['storageDirectory'],
        'manifestPath': str(manifest_path), 'indexPath': str(destination / 'index.json'), 'generatedPublicFiles': entries,
        'zip': {'path': str(zip_path), 'sha256': sha(raw_zip), 'byteSize': len(raw_zip)}}
    write_private(destination / 'source-plan.json', json_bytes(plan))
    write_private(destination / 'index.json', json_bytes(index))
    descriptor = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return index


def verify_and_register(index_path, *, binding_loader, registry, config, node_client,
                        store=None, remote_zip_factory=None, remote_object_read=None):
    root = Path(node_client.root).resolve()
    path = Path(index_path).absolute()
    path = private_workspace(root, path.parent) / path.name
    require(path.name == 'index.json' and not path.parent.stat().st_mode & 0o077, 'activity_private_workspace_required')
    no_links(path, path.parent)
    raw_index, _ = read_stable(path)
    index = parse_json(raw_index)
    plan = parse_json(read_stable(path.parent / 'source-plan.json')[0])
    binding = plan['binding']
    require(binding_loader(binding) == binding, 'activity_current_binding_changed')
    store = store or CourseFileStore(config=config, project_root=root, repository=registry)
    assert_sources(plan, root, registry, store)
    manifest_raw, _ = read_stable(path.parent / 'manifest.json')
    manifest = parse_json(manifest_raw)
    require(manifest == manifest_for(plan) and index.get('sourceKind') == SOURCE_KIND
            and index.get('schemaVersion') == 'mira.course-archive.export.v1' and index.get('complete') is True
            and index.get('sourceDigest') == sha(manifest_raw)
            and index.get('archiveId') == 'activity-supplement-' + sha(manifest_raw)[:24]
            and index.get('objectDirectory') == binding['storageDirectory']
            and index.get('indexPath') == str(path) and index.get('manifestPath') == str(path.parent / 'manifest.json')
            and index.get('missingSources') == []
            and all(index.get(k) == binding[k] for k in ('courseId', 'courseVersion', 'contentKey', 'classroomId')),
            'activity_index_manifest_binding_invalid')
    _check_public(manifest)
    entries = index['generatedPublicFiles']
    require(len(entries) == 2 and {e['mimeType'] for e in entries} == {'application/json', 'application/zip'}, 'activity_two_objects_required')
    for entry in entries:
        suffix = '.zip' if entry['mimeType'] == 'application/zip' else '.json'
        local = path.parent / ('activity-dependencies.zip' if suffix == '.zip' else 'manifest.json')
        no_links(local, path.parent)
        raw, _ = read_stable(local)
        require(entry.get('localPath') == str(local) and entry.get('relativePath') == binding['storageDirectory'] + '/互动资源补充-' + sha(manifest_raw)[:24] + suffix
                and (entry.get('sha256'), entry.get('byteSize')) == (sha(raw), len(raw)), 'activity_public_artifact_changed')
    zipped = next(e for e in entries if e['mimeType'] == 'application/zip')
    require(index.get('zip') == {'path': zipped['localPath'], 'sha256': zipped['sha256'], 'byteSize': zipped['byteSize']}, 'activity_zip_identity_invalid')
    verify_zip(Path(zipped['localPath']).open('rb'), manifest, manifest_raw)
    storage_id = storage_id_for(config.endpoint, config.bucket, config.region)
    expected_heads = {}
    for record in manifest['files']:
        current = registry.resolve(record['sourcePath'], storage_id=storage_id)
        require(current is None or (current['sha256'], current['byteSize'], current['mimeType']) ==
                (record['sha256'], record['byteSize'], record['mimeType']), 'activity_source_head_changed')
        if current is None:
            expected_heads[record['sourcePath']] = None
        else:
            scope = registry.head_scope(record['sourcePath'], storage_id)
            raw = store.read_bytes(root / record['sourcePath'], expected_sha256=record['sha256'], expected_bytes=record['byteSize'])
            require(scope is not None and raw is not None and (sha(raw), len(raw)) ==
                    (record['sha256'], record['byteSize']), 'activity_existing_head_remote_mismatch')
            expected_heads[record['sourcePath']] = {'sha256': current['sha256'], 'scopeKey': scope['scopeKey']}
    receipt = node_client.upload(str(path))
    require(receipt.get('schemaVersion') == 'mira.course-archive.verification.v1' and receipt.get('complete') is True
            and receipt.get('archiveId') == index['archiveId'] and receipt.get('indexSha256') == sha(raw_index)
            and receipt.get('storage') == storage_identity(config.endpoint, config.bucket, config.region)
            and all(receipt.get(k) == index[k] for k in ('courseId', 'courseVersion', 'sourceDigest')), 'activity_upload_receipt_invalid')
    objects = receipt.get('objects', [])
    require(len(objects) == 2 and {o['objectKey'] for o in objects} == {e['relativePath'] for e in entries}, 'activity_remote_object_set_invalid')
    by_key = {o['objectKey']: o for o in objects}
    for entry in entries:
        remote = by_key[entry['relativePath']]
        require((remote.get('sha256'), remote.get('byteSize')) == (entry['sha256'], entry['byteSize'])
                and isinstance(remote.get('etag'), str) and remote['etag'], 'activity_remote_identity_invalid')
    def locator(remote):
        return {'kind': 'object', 'objectKey': remote['objectKey'], 'etag': remote['etag'],
                **({'versionId': remote['versionId']} if remote.get('versionId') else {})}
    manifest_entry = next(e for e in entries if e['mimeType'] == 'application/json')
    json_remote, zip_remote = by_key[manifest_entry['relativePath']], by_key[zipped['relativePath']]
    reader = remote_object_read or (lambda r: _RemoteObject(config, locator(r), r['byteSize']).get(whole=True))
    require(reader(json_remote) == manifest_raw, 'activity_remote_manifest_mismatch')
    factory = remote_zip_factory or (lambda r: _RangeFile(_RemoteObject(config, locator(r), r['byteSize'])))
    verify_zip(factory(zip_remote), manifest, manifest_raw)
    files = []
    for record in manifest['files']:
        if record['disposition'] == 'zip':
            selected = {**locator(zip_remote), 'kind': 'zip_member', 'archiveSha256': zip_remote['sha256'],
                        'archiveByteSize': zip_remote['byteSize'], 'memberPath': record['archivePath']}
        else:
            require(record['disposition'] == 'reuse_registered', 'activity_disposition_invalid')
            alias = registry.resolve(record['verifiedAliasSourcePath'], storage_id=storage_id, expected_sha=record['sha256'])
            require(alias is not None and alias['locator'] == record['locator'], 'activity_alias_locator_changed')
            raw = store.read_bytes(root / alias['sourcePath'], expected_sha256=record['sha256'], expected_bytes=record['byteSize'])
            require(raw is not None and (sha(raw), len(raw)) == (record['sha256'], record['byteSize']), 'activity_alias_remote_mismatch')
            selected = record['locator']
        files.append({**{k: record[k] for k in ('sourcePath', 'sha256', 'byteSize', 'mimeType')}, 'locator': selected})
    require(binding_loader(binding) == binding, 'activity_current_binding_changed')
    assert_sources(plan, root, registry, store)
    metadata = {'registryVersion': 4, 'sourceKind': SOURCE_KIND, 'sourceDigest': sha(manifest_raw),
        'originalSourceDigest': binding['originalSourceDigest'], 'courseId': binding['courseId'], 'courseVersion': binding['courseVersion'],
        'contentKey': binding['contentKey'], 'classroomId': binding['classroomId'], 'storageDirectory': binding['storageDirectory'],
        'selectionReason': REASON, 'sourceRoots': binding['sourceRoots'], 'frozenBindingSha256': digest(binding),
        'currentPublishedSetSha256': binding['currentPublishedSetSha256'], 'supplementManifestSha256': sha(manifest_raw),
        'archiveSha256': zip_remote['sha256']}
    metadata['scopeKey'] = digest(metadata)
    scope = registry.register_scope(metadata, files, storage_id, activate=False)
    activation = registry.activate_heads_if_unchanged(metadata['scopeKey'], storage_id, expected_heads)
    return {'scope': scope, 'activation': activation, 'registeredFiles': len(files), 'sourceKind': SOURCE_KIND,
            'sourceDigest': metadata['sourceDigest']}


def summary(plan):
    return {'binding': plan['binding'], 'files': len(plan['files']), 'bytes': sum(r['byteSize'] for r in plan['files']),
        'zipFiles': sum(r['disposition'] == 'zip' for r in plan['files']),
        'zipBytes': sum(r['byteSize'] for r in plan['files'] if r['disposition'] == 'zip'),
        'reuseRegistered': sum(r['disposition'] == 'reuse_registered' for r in plan['files']),
        'alreadyRegistered': sum(r['disposition'] == 'already_registered' for r in plan['files']), 'blocked': plan['blocked']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('inventory')
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--output-root', type=Path, required=True)
    prepare.add_argument('--reserve-free-bytes', type=int, default=RESERVE_BYTES)
    transfer = commands.add_parser('transfer-register')
    transfer.add_argument('--index', type=Path, required=True)
    transfer.add_argument('--node', default=os.environ.get('COURSE_ARCHIVE_NODE', 'node'))
    args = parser.parse_args(argv)
    try:
        config = CourseStorageConfig.from_env()
        require(config.mode == 'registry', 'activity_registry_mode_required')
        database = Database(AppConfig.from_env().DATABASE_URL)
        registry = CourseStorageRepository(database)
        store = CourseFileStore(config=config, project_root=ROOT, repository=registry)
        def current_plans():
            current, active = load_current(database, registry, store)
            return [inventory_for_course(ROOT, identity, release, directory, current, registry, store, spec=spec)
                    for identity, release, directory, spec in active]
        if args.command == 'transfer-register':
            def reload_binding(binding):
                matches = [p['binding'] for p in current_plans() if p['binding']['contentKey'] == binding['contentKey']]
                require(len(matches) == 1, 'activity_current_binding_ambiguous')
                return matches[0]
            result = verify_and_register(args.index, binding_loader=reload_binding, registry=registry, config=config,
                node_client=NodeArchiveClient(project_root=ROOT, node=args.node), store=store)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        plans = current_plans()
        for plan in plans:
            result = summary(plan)
            if args.command == 'prepare':
                target = args.output_root / digest(plan['binding'])[:24]
                result['indexPath'] = prepare_supplement(plan, ROOT, target, registry=registry, store=store,
                    reserve_free_bytes=args.reserve_free_bytes)['indexPath']
            print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0 if all(not p['blocked'] for p in plans) else 1
    except Exception as error:
        code = str(error) if isinstance(error, SupplementError) else 'activity_operation_failed'
        print(json.dumps({'ok': False, 'errorType': type(error).__name__,
            'errorCode': code if re.fullmatch(r'[a-z0-9_]+', code) else 'activity_operation_failed'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
