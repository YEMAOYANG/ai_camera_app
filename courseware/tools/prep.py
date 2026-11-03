import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MATERIALS_URL = 'https://s-file-2.ykt.cbern.com.cn/zxx/ndrs/national_lesson/teachingmaterials/version/data_version.json'
MATERIAL_URL = 'https://s-file-2.ykt.cbern.com.cn/zxx/ndrs/national_lesson/teachingmaterials/{}/resources/parts.json'
DETAILS_URL = 'https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/resources/details/{}.json'
KINDS = {'coursewares': 'courseware', 'lesson_plandesign': 'teachingDesign',
         'learning_task': 'learningTaskSheet', 'after_class_exercise': 'afterClassExercise',
         'micro_lesson_video': 'video'}


class PrepError(Exception):
    pass


def default_fetch(url):
    time.sleep(0.3)
    try:
        with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()
    except (URLError, OSError) as exc:
        raise PrepError('fetch_failed', f'{url}: {exc}') from exc


def _request(fetch, url):
    try:
        return fetch(url)
    except PrepError:
        raise
    except Exception as exc:
        raise PrepError('fetch_failed', f'{url}: {exc}') from exc


def _json(fetch, url):
    status, body = _request(fetch, url)
    if status != 200:
        raise PrepError('fetch_failed', f'{url}: HTTP {status}')
    try:
        return json.loads(body), body
    except (ValueError, UnicodeDecodeError) as exc:
        raise PrepError('fetch_failed', f'{url}: invalid JSON') from exc


def _hash(body):
    return hashlib.sha256(body).hexdigest()


def _title(value):
    value = unicodedata.normalize('NFKC', value).strip()
    value = re.sub(r'^\d+\s*[.、]?\s*', '', value, count=1)
    return re.sub(r'\s+', '', value)


def _write_manifest(out_dir, manifest):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')


def prep_lesson(identity, out_dir, fetch, *, overwrite=False, now=None):
    out_dir = Path(out_dir)
    version, _ = _json(fetch, MATERIALS_URL)
    materials = []
    for url in version['urls']:
        part, _ = _json(fetch, url)
        materials.extend(part)
    material = next((m for m in materials if m['id'] == identity['officialMaterialId']), None)
    if material is None:
        raise PrepError('material_mismatch', 'unknown material id')
    tags = [tag['tag_name'] for tag in material['tag_list']]
    subjects = {'math': '数学', 'chinese': '语文', 'english': '英语', 'science': '科学'}
    grades = {f'primary_{i}': f'{name}年级' for i, name in enumerate('一二三四五六', 1)}
    for label, value in [('subject', subjects.get(identity['subject'])),
                         ('grade', grades.get(identity['gradeCode'])),
                         ('volume', {'upper': '上册', 'lower': '下册'}.get(identity['volume']))]:
        if value is None or value not in tags:
            raise PrepError('material_mismatch', f'missing {label}: {value}')

    listing_url = MATERIAL_URL.format(material['id'])
    parts, listing_body = _json(fetch, listing_url)
    entries = []
    for url in parts:
        part, _ = _json(fetch, url)
        entries.extend(part)
    timestamp = (now or datetime.now(timezone(timedelta(hours=8)))).isoformat()
    manifest = {'schemaVersion': 'mira.courseware.official-sources.v1', 'fetchedAt': timestamp}
    if not entries:
        manifest.update(status='no_official_resources', evidence={
            'listingUrl': listing_url, 'listingSha256': _hash(listing_body)})
        _write_manifest(out_dir, manifest)
        return manifest

    candidates = [entry for entry in entries if entry['resource_type_code'] in ('national_lesson', 'elite_lesson')]
    if identity.get('officialChapterId'):
        candidates = [entry for entry in candidates if identity['officialChapterId'] in entry.get('chapter_ids', [])]
    else:
        candidates = [entry for entry in candidates if _title(entry['title']) == _title(identity['lessonTitle'])]
    if not candidates:
        raise PrepError('lesson_not_found', identity['lessonTitle'])
    if len(candidates) > 1:
        raise PrepError('lesson_ambiguous', [entry['id'] for entry in candidates])
    lesson = candidates[0]
    details_url = DETAILS_URL.format(lesson['id'])
    details, details_body = _json(fetch, details_url)
    hours = details['resource_structure']['relations']
    if 'classHours' in identity:
        requested = set(identity['classHours'])
        missing = requested - {hour['id'] for hour in hours}
        if missing:
            raise PrepError('class_hour_not_found', ', '.join(sorted(missing)))
        hours = [hour for hour in hours if hour['id'] in requested]
    manifest.update(status='ok', material={'id': material['id'], 'title': material['title'], 'tags': tags},
                    lesson={'activityId': lesson['id'], 'title': lesson['title'],
                            'chapterIds': lesson['chapter_ids'], 'detailsUrl': details_url,
                            'detailsSha256': _hash(details_body)}, classHours=[])
    all_resources = details['relations']['national_course_resource']
    for hour in hours:
        resources = {}
        for ref in hour.get('res_ref', []):
            match = re.fullmatch(r'\$\.relations\.national_course_resource\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]', ref)
            if ref == '$.relations.national_course_resource[*]':
                indexes = range(len(all_resources))
            elif match:
                indexes = map(int, match.group(1).split(','))
            else:
                continue
            for index in indexes:
                if index < len(all_resources):
                    resource = all_resources[index]
                    if resource.get('resource_type_code') in KINDS:
                        resources[resource['resource_type_code']] = resource
        result = {'id': hour['id'], 'title': hour['title'], 'resources': {}}
        for code, kind in KINDS.items():
            resource = resources.get(code)
            if resource is None:
                result['resources'][kind] = {'status': 'absent_in_listing'}
                continue
            if code == 'micro_lesson_video':
                result['resources'][kind] = {'status': 'waived', 'resourceId': resource['id']}
                continue
            base = next((url for item in resource.get('ti_items', [])
                         if item.get('ti_file_flag') == 'image' and item.get('ti_format') == 'folder'
                         for url in item.get('ti_storages', [])
                         if url.startswith('https://r1-ndr-private.ykt.cbern.com.cn/')), None)
            if not base:
                raise PrepError('fetch_failed', f"image location missing: {resource['id']}")
            base = base.replace('https://r1-ndr-private.ykt.cbern.com.cn/', 'https://r1-ndr.ykt.cbern.com.cn/', 1).rstrip('/')
            pages = []
            for number in range(1, 201):
                url = f'{base}/{number}.jpg'
                status, body = _request(fetch, url)
                if status != 200:
                    if number == 1:
                        raise PrepError('page_missing', url)
                    if status not in (403, 404):
                        # Past the last page the server answers 403 or 404; any other status is a failure, not the end.
                        raise PrepError('fetch_failed', f'{url}: HTTP {status}')
                    break
                if not body.startswith(b'\xff\xd8'):
                    raise PrepError('page_not_jpeg', url)
                relative = Path(hour['id']) / f'{kind}-{number:02d}.jpg'
                path = out_dir / relative
                digest = _hash(body)
                if path.exists() and _hash(path.read_bytes()) != digest and not overwrite:
                    raise PrepError('page_changed', str(relative))
                if not path.exists() or _hash(path.read_bytes()) != digest:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(body)
                pages.append({'page': number, 'url': url, 'path': relative.as_posix(),
                              'bytes': len(body), 'sha256': digest})
            result['resources'][kind] = {'status': 'fetched', 'resourceId': resource['id'], 'pages': pages}
        manifest['classHours'].append(result)
    _write_manifest(out_dir, manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description='Fetch official lesson document page images')
    parser.add_argument('--identity', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args(argv)
    try:
        identity = json.loads(Path(args.identity).read_text(encoding='utf-8'))
        manifest = prep_lesson(identity, args.out, default_fetch, overwrite=args.overwrite)
    except PrepError as exc:
        print(f'{exc.args[0]}: {exc.args[1] if len(exc.args) > 1 else ""}', file=sys.stderr)
        return 1
    if manifest['status'] == 'no_official_resources':
        return 2
    for hour in manifest['classHours']:
        for kind, resource in hour['resources'].items():
            print(f"{hour['id']} {kind}: {len(resource.get('pages', []))} pages")
    return 0


if __name__ == '__main__':
    sys.exit(main())
